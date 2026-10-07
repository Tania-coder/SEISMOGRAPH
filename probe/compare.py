"""
seismograph.probe.compare
=========================
``python -m probe.compare`` -- old model vs new model on your own prompts.

One command runs a JSONL suite of the user's prompts against two models,
``k`` times each, and writes ``report.html`` and ``evidence.json`` into a
local ``compare-<timestamp>/`` directory.  Contract:
docs/arch/COMPARE-1-contract.md (accepted 2026-10-01).

The rule that keeps it honest (contract section 4)
--------------------------------------------------
A model does not always repeat itself (FLOOR-1 measured ~60%
self-agreement for one model).  So "A and B answered differently" is only
a change when it is larger than how differently A answers A, and B
answers B.  For every metric this module computes, per item, the mean
pairwise distance within A's repeats, within B's repeats, and across A
and B, and gives one of three verdicts:

* ``CHANGED``      -- the across-model distance is above BOTH within-model
                      distances AND a within-item permutation test
                      rejects "the A/B labels are exchangeable" at
                      ``ALPHA``;
* ``WITHIN NOISE`` -- otherwise;
* ``NOT MEASURED`` -- too few valid responses (fewer than
                      ``MIN_ITEMS_PER_METRIC`` items with at least two
                      valid repeats on each side), or the side had more
                      than 10% infrastructure failures.

The report never says "stable" (CLAMP-1 rule): a WITHIN NOISE verdict
means "not distinguishable at this sample size", nothing more.

Privacy and network (contract section 8)
----------------------------------------
* The only network calls are to the two configured endpoints, through
  ``probe.providers`` (stdlib urllib).  No gateway, no telemetry.
* Answer text lives in memory and, unless ``--no-text``, in the local
  ``report.html``.  ``evidence.json`` holds hashes, lengths, flags and
  aggregates only.  Nothing is logged.
* API keys are read from the environment and handed to the provider;
  they are never printed or written.

#SG-TRACE: REQ-COMPARE-001
#   | assumption: per-item energy-style distance (cross minus mean
#     within) plus a within-item label permutation test is a faithful
#     formalisation of "outside both within-model ranges" (section 4)
#   | test: test_c3_noise_floor_not_reported_as_changed
#SG-TRACE: REQ-COMPARE-002
#   | assumption: answer text never reaches evidence.json
#   | test: test_c10_evidence_has_no_prompt_answer_or_key
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

from probe.canary import _hash_output, _is_json_valid
from probe.providers import (
    CompletionResult,
    OpenAICompatibleProvider,
    ProviderError,
)

# ---------------------------------------------------------------------------
# Constants (all reported in evidence.json under "method")
# ---------------------------------------------------------------------------

TOOL_NAME = "seismograph compare"
EVIDENCE_SCHEMA = "seismograph.compare.evidence/1"
HOMEPAGE = "https://driftdefense.dev"

MAX_ITEMS = 200
MIN_REPEATS = 2
# Upper bound keeps the exact within-item permutation space small
# (C(10, 5) = 252 splits per item) so the test stays exact and fast in
# pure Python.  [design decision S060, Director approval pending]
MAX_REPEATS = 5
MIN_ITEMS_PER_METRIC = 5
INFRA_FAILURE_LIMIT = 0.10
ALPHA = 0.01
N_PERMUTATIONS = 999
MAX_RETRIES = 2
RETRY_BASE_S = 1.0
TOP_N = 10
DEFAULT_MAX_TOKENS = 512

CHANGED = "CHANGED"
WITHIN_NOISE = "WITHIN NOISE"
NOT_MEASURED = "NOT MEASURED"

TEMP_ZERO = "0"
TEMP_DEFAULT = "provider default"

# Failure classes (contract section 5).  ``bad_request`` (a 400 that is
# not the temperature rejection, or a 404) and ``not_attempted`` (calls
# skipped after a fatal auth/quota failure) are additions, stated in the
# COMPARE-1 Keystone.
RETRYABLE = frozenset({"rate_limit", "provider_error"})
FATAL = frozenset({"auth", "quota"})
QUOTA_CODE_HINTS = ("quota", "billing", "credit", "insufficient")

REFUSAL_VERSION = "refusal@1"
REFUSAL_PATTERNS: tuple[str, ...] = (
    "i can't help",
    "i cannot help",
    "i can't assist",
    "i cannot assist",
    "i can't provide",
    "i cannot provide",
    "i can't comply",
    "i cannot comply",
    "i won't be able",
    "i'm not able to",
    "i am not able to",
    "i'm unable to",
    "i am unable to",
    "i'm sorry, but i",
    "i am sorry, but i",
    "i must decline",
    "as an ai",
)
REFUSAL_WINDOW = 300

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
}

Caller = Callable[["SuiteItem", bool], CompletionResult]


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


class SuiteError(ValueError):
    """The suite file is unusable.  The message is safe to print."""


@dataclass(frozen=True)
class SuiteItem:
    """One prompt from the user's suite."""

    id: str
    user: str
    system: str | None
    expect_json: bool


def load_suite(path: str | Path) -> tuple[list[SuiteItem], str]:
    """Parse a JSONL suite; return (items, SHA-256 of the file bytes).

    More than ``MAX_ITEMS`` items is refused, never truncated.

    #SG-TRACE: REQ-COMPARE-003
    #   | assumption: the constitution's 200-prompt cap applies to user
    #     suites too; refusing is safer than silently dropping prompts
    #   | test: test_c11_suite_over_cap_refused
    """
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SuiteError("suite is not UTF-8") from None
    lines = [
        (n, line)
        for n, line in enumerate(text.splitlines(), 1)
        if line.strip()
    ]
    if len(lines) > MAX_ITEMS:
        raise SuiteError(
            f"suite has {len(lines)} items; the limit is {MAX_ITEMS}. "
            "Refused, not truncated: split the suite."
        )
    if not lines:
        raise SuiteError("suite is empty")
    items: list[SuiteItem] = []
    seen: set[str] = set()
    for n, line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            raise SuiteError(f"line {n}: not valid JSON") from None
        if not isinstance(obj, dict):
            raise SuiteError(f"line {n}: expected a JSON object")
        item_id = obj.get("id")
        user = obj.get("user")
        system = obj.get("system")
        expect_json = obj.get("expect_json", False)
        if not isinstance(item_id, str) or not item_id:
            raise SuiteError(f"line {n}: 'id' must be a non-empty string")
        if item_id in seen:
            raise SuiteError(f"line {n}: duplicate id {item_id!r}")
        if not isinstance(user, str) or not user:
            raise SuiteError(f"line {n}: 'user' must be a non-empty string")
        if system is not None and not isinstance(system, str):
            raise SuiteError(f"line {n}: 'system' must be a string")
        if not isinstance(expect_json, bool):
            raise SuiteError(f"line {n}: 'expect_json' must be true/false")
        seen.add(item_id)
        items.append(SuiteItem(item_id, user, system or None, expect_json))
    return items, digest


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """One call's outcome.  ``text`` stays in memory only."""

    failure: str | None
    text: str = ""
    hash: str | None = None
    length: int | None = None
    finish_reason: str | None = None
    empty: bool | None = None
    json_valid: bool | None = None
    refusal: bool | None = None
    latency_ms: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    returned_model: str | None = None

    @property
    def valid(self) -> bool:
        return self.failure is None


def is_refusal(text: str) -> bool:
    """Heuristic refusal detector, pattern list ``refusal@1``.

    #SG-TRACE: REQ-COMPARE-004
    #   | assumption: refusals announce themselves in the first few
    #     hundred characters; this is a heuristic and is labelled so
    #   | test: test_c5_refusal_rate_rises_flagged_heuristic
    """
    head = text[:REFUSAL_WINDOW].lower().replace("’", "'")
    return any(p in head for p in REFUSAL_PATTERNS)


def observe(item: SuiteItem, res: CompletionResult) -> Observation:
    """Derive the measured features of one successful call."""
    text = res.text
    return Observation(
        failure=None,
        text=text,
        hash=_hash_output(text),
        length=len(text),
        finish_reason=res.finish_reason,
        empty=not text.strip(),
        json_valid=_is_json_valid(text) if item.expect_json else None,
        refusal=is_refusal(text),
        latency_ms=res.latency_ms,
        output_tokens=res.output_tokens,
        reasoning_tokens=res.reasoning_tokens,
        returned_model=res.returned_model,
    )


def classify(exc: ProviderError) -> str:
    """Map a ProviderError to a failure class, structurally.

    #SG-TRACE: REQ-COMPARE-005
    #   | assumption: status code, sanitised error code and failure_kind
    #     are enough to classify; the message is never parsed (CAN-2a C3)
    #   | test: test_classify_table
    """
    status = exc.status_code
    code = (getattr(exc, "error_code", None) or "").lower()
    kind = getattr(exc, "failure_kind", None)
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "quota"
    if status == 429:
        if any(h in code for h in QUOTA_CODE_HINTS):
            return "quota"
        return "rate_limit"
    if status is not None and status >= 500:
        return "provider_error"
    if status is not None:
        return "bad_request"
    if kind == "timeout":
        return "timeout"
    if kind in ("bad_body", "bad_schema"):
        return "provider_error"
    return "network"


class Side:
    """One model under comparison: calls, retries, temperature fallback.

    #SG-TRACE: REQ-COMPARE-006
    #   | assumption: a 400 on the first temperature=0 call is retried
    #     ONCE without temperature; on success the whole side switches to
    #     provider default and the report header says so (section 6)
    #   | test: test_c8_temperature_rejected_retried_once_and_stated
    """

    def __init__(
        self,
        label: str,
        requested: str,
        caller: Caller,
        *,
        delay_ms: int = 0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.label = label
        self.requested = requested
        self._caller = caller
        self._delay_s = max(delay_ms, 0) / 1000.0
        self._sleep = sleep
        self.send_temperature = True
        self.temperature = TEMP_ZERO
        self._fallback_tried = False
        self.fatal: str | None = None
        self.calls_made = 0

    def _call(self, item: SuiteItem, send_temperature: bool):
        self.calls_made += 1
        try:
            return self._caller(item, send_temperature)
        finally:
            if self._delay_s:
                self._sleep(self._delay_s)

    def ask(self, item: SuiteItem) -> Observation:
        """Ask one item once; never raises for provider failures."""
        if self.fatal is not None:
            return Observation(failure="not_attempted")
        retries = 0
        while True:
            try:
                res = self._call(item, self.send_temperature)
            except ProviderError as exc:
                if (
                    exc.status_code == 400
                    and self.send_temperature
                    and not self._fallback_tried
                ):
                    return self._temperature_fallback(item)
                cls = classify(exc)
                if cls in RETRYABLE and retries < MAX_RETRIES:
                    retries += 1
                    self._sleep(RETRY_BASE_S * 2 ** (retries - 1))
                    continue
                if cls in FATAL:
                    self.fatal = cls
                return Observation(failure=cls)
            return observe(item, res)

    def _temperature_fallback(self, item: SuiteItem) -> Observation:
        self._fallback_tried = True
        try:
            res = self._call(item, False)
        except ProviderError as exc:
            cls = classify(exc)
            if cls in FATAL:
                self.fatal = cls
            return Observation(failure=cls)
        self.send_temperature = False
        self.temperature = TEMP_DEFAULT
        return observe(item, res)


def run_calls(
    items: Sequence[SuiteItem],
    sides: Sequence[Side],
    repeats: int,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, dict[str, list[Observation]]]:
    """Ask every item ``repeats`` times on every side, interleaved.

    Order is repeat -> item -> side, so both models see the same
    time-of-day conditions as closely as possible.  ``progress`` is
    called with (planned calls done, planned total) after every item.
    """
    total = len(items) * repeats * len(sides)
    done = 0
    obs: dict[str, dict[str, list[Observation]]] = {
        s.label: {it.id: [] for it in items} for s in sides
    }
    for _ in range(repeats):
        for item in items:
            for side in sides:
                obs[side.label][item.id].append(side.ask(item))
                done += 1
            if progress is not None:
                progress(done, total)
    return obs


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def _dist_eq(a: object, b: object) -> float:
    return 0.0 if a == b else 1.0


def _dist_abs(a: float, b: float) -> float:
    return abs(float(a) - float(b))


def _f(attr: str) -> Callable[[Observation], object]:
    return lambda o: getattr(o, attr)


@dataclass(frozen=True)
class MetricSpec:
    name: str
    label: str
    value: Callable[[Observation], object]
    dist: Callable[[object, object], float]
    unit: str
    heuristic: bool = False
    json_only: bool = False


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "agreement", "answer identity", _f("hash"), _dist_eq, "disagree"
    ),
    MetricSpec("length", "length (chars)", _f("length"), _dist_abs, "chars"),
    MetricSpec(
        "json_valid",
        "JSON validity",
        _f("json_valid"),
        _dist_abs,
        "rate",
        json_only=True,
    ),
    MetricSpec(
        "truncated",
        "truncated (finish_reason=length)",
        lambda o: o.finish_reason == "length",
        _dist_abs,
        "rate",
    ),
    MetricSpec("empty", "empty answer", _f("empty"), _dist_abs, "rate"),
    MetricSpec(
        "refusal",
        "refusal (heuristic)",
        _f("refusal"),
        _dist_abs,
        "rate",
        heuristic=True,
    ),
    MetricSpec("latency", "latency (ms)", _f("latency_ms"), _dist_abs, "ms"),
    MetricSpec(
        "output_tokens",
        "output tokens",
        _f("output_tokens"),
        _dist_abs,
        "tokens",
    ),
    MetricSpec(
        "reasoning_tokens",
        "reasoning tokens",
        _f("reasoning_tokens"),
        _dist_abs,
        "tokens",
    ),
)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _within(vals: Sequence[object], dist) -> float:
    pairs = list(combinations(vals, 2))
    return _mean([dist(a, b) for a, b in pairs])


def _cross(a: Sequence[object], b: Sequence[object], dist) -> float:
    return _mean([dist(x, y) for x in a for y in b])


def item_stat(a: Sequence[object], b: Sequence[object], dist):
    """Return (within_a, within_b, cross, t) for one item.

    ``t = cross - (within_a + within_b) / 2``: zero in expectation when
    A and B are the same process, positive when they differ.
    """
    wa = _within(a, dist)
    wb = _within(b, dist)
    cr = _cross(a, b, dist)
    return wa, wb, cr, cr - (wa + wb) / 2.0


def _split_stats(a, b, dist) -> list[float]:
    """t for every way of splitting the pooled repeats into |a| and |b|."""
    pooled = list(a) + list(b)
    n, na = len(pooled), len(a)
    d = [[dist(pooled[i], pooled[j]) for j in range(n)] for i in range(n)]
    if all(v == 0.0 for row in d for v in row):
        return [0.0]
    out = []
    for left in combinations(range(n), na):
        ls = set(left)
        right = [i for i in range(n) if i not in ls]
        wa = _mean([d[i][j] for i, j in combinations(left, 2)])
        wb = _mean([d[i][j] for i, j in combinations(right, 2)])
        cr = _mean([d[i][j] for i in left for j in right])
        out.append(cr - (wa + wb) / 2.0)
    return out


def permutation_p(
    per_item: Sequence[tuple[Sequence[object], Sequence[object]]],
    dist,
    rng: random.Random,
    n_perm: int = N_PERMUTATIONS,
) -> float:
    """Monte Carlo p-value of mean t under within-item label exchange.

    #SG-TRACE: REQ-COMPARE-007
    #   | assumption: under "no change" the A/B labels of one item's
    #     pooled repeats are exchangeable; a seeded RNG makes the p-value
    #     reproducible (evidence.json records the seed)
    #   | test: test_property_permutation_symmetry_and_null_calibration
    """
    observed = _mean([item_stat(a, b, dist)[3] for a, b in per_item])
    tables = [_split_stats(a, b, dist) for a, b in per_item]
    if all(len(t) == 1 for t in tables):
        return 1.0
    n_items = len(tables)
    hits = 0
    for _ in range(n_perm):
        total = 0.0
        for t in tables:
            total += t[0] if len(t) == 1 else t[rng.randrange(len(t))]
        if total / n_items >= observed - 1e-12:
            hits += 1
    return (1 + hits) / (1 + n_perm)


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 6)


def _percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (deterministic, no interpolation)."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(-(-q * len(s) // 1)) - 1))
    return float(s[k])


def evaluate_metric(
    spec: MetricSpec,
    items: Sequence[SuiteItem],
    obs_a: dict[str, list[Observation]],
    obs_b: dict[str, list[Observation]],
    measured: bool,
    rng: random.Random,
) -> dict:
    """Within A / within B / A vs B and the verdict for one metric."""
    pairs = []
    for item in items:
        if spec.json_only and not item.expect_json:
            continue
        a = [spec.value(o) for o in obs_a[item.id] if o.valid]
        b = [spec.value(o) for o in obs_b[item.id] if o.valid]
        a = [v for v in a if v is not None]
        b = [v for v in b if v is not None]
        if len(a) >= 2 and len(b) >= 2:
            pairs.append((a, b))
    row: dict = {
        "metric": spec.name,
        "label": spec.label,
        "unit": spec.unit,
        "heuristic": spec.heuristic,
        "eligible_items": len(pairs),
        "within_a": None,
        "within_b": None,
        "a_vs_b": None,
        "p_value": None,
    }
    if not measured:
        row["verdict"] = NOT_MEASURED
        row["reason"] = "side over infrastructure-failure limit"
        return row
    if len(pairs) < MIN_ITEMS_PER_METRIC:
        row["verdict"] = NOT_MEASURED
        row["reason"] = (
            f"{len(pairs)} items with >=2 valid repeats per side "
            f"(need {MIN_ITEMS_PER_METRIC})"
        )
        return row
    stats = [item_stat(a, b, spec.dist) for a, b in pairs]
    wa = _mean([s[0] for s in stats])
    wb = _mean([s[1] for s in stats])
    cr = _mean([s[2] for s in stats])
    p = permutation_p(pairs, spec.dist, rng)
    changed = p <= ALPHA and cr > max(wa, wb) + 1e-12
    row.update(
        within_a=_r(wa),
        within_b=_r(wb),
        a_vs_b=_r(cr),
        p_value=_r(p),
        verdict=CHANGED if changed else WITHIN_NOISE,
    )
    return row


def side_levels(
    items: Sequence[SuiteItem], obs: dict[str, list[Observation]]
) -> dict:
    """Per-side summary levels in natural units."""
    valid = [o for it in items for o in obs[it.id] if o.valid]
    json_obs = [
        o for it in items if it.expect_json for o in obs[it.id] if o.valid
    ]

    def rate(xs):
        return _r(_mean([1.0 if x else 0.0 for x in xs])) if xs else None

    lengths = [float(o.length) for o in valid]
    lat = [float(o.latency_ms) for o in valid if o.latency_ms is not None]
    out_t = [
        float(o.output_tokens) for o in valid if o.output_tokens is not None
    ]
    rea_t = [
        float(o.reasoning_tokens)
        for o in valid
        if o.reasoning_tokens is not None
    ]
    self_agree = []
    for it in items:
        hs = [o.hash for o in obs[it.id] if o.valid]
        if len(hs) >= 2:
            self_agree.append(1.0 - _within(hs, _dist_eq))
    return {
        "valid_responses": len(valid),
        "self_agreement": _r(_mean(self_agree)) if self_agree else None,
        "length_median": _percentile(lengths, 0.5),
        "length_p90": _percentile(lengths, 0.9),
        "json_valid_rate": rate([o.json_valid for o in json_obs]),
        "truncated_rate": rate([o.finish_reason == "length" for o in valid]),
        "empty_rate": rate([o.empty for o in valid]),
        "refusal_rate": rate([o.refusal for o in valid]),
        "latency_p50": _percentile(lat, 0.5),
        "latency_p95": _percentile(lat, 0.95),
        "output_tokens_mean": _r(_mean(out_t)) if out_t else None,
        "reasoning_tokens_mean": _r(_mean(rea_t)) if rea_t else None,
    }


def _modal(observations: Sequence[Observation]) -> Observation | None:
    valid = [o for o in observations if o.valid]
    if not valid:
        return None
    counts = Counter(o.hash for o in valid)
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return next(o for o in valid if o.hash == best)


def top_changes(
    items: Sequence[SuiteItem],
    obs_a: dict[str, list[Observation]],
    obs_b: dict[str, list[Observation]],
) -> list[dict]:
    """Items with the largest A-vs-B answer difference beyond noise."""
    scored = []
    for it in items:
        a = [o.hash for o in obs_a[it.id] if o.valid]
        b = [o.hash for o in obs_b[it.id] if o.valid]
        if not a or not b:
            continue
        score = item_stat(a, b, _dist_eq)[3]
        if score <= 1e-12:
            continue
        ma, mb = _modal(obs_a[it.id]), _modal(obs_b[it.id])
        dlen = abs((ma.length or 0) - (mb.length or 0))
        scored.append((-score, -dlen, it.id, score, ma, mb))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [
        {"id": s[2], "score": _r(s[3]), "modal_a": s[4], "modal_b": s[5]}
        for s in scored[:TOP_N]
    ]


# ---------------------------------------------------------------------------
# Evidence and report
# ---------------------------------------------------------------------------


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("seismograph-probe")
    except Exception:  # noqa: BLE001 -- metadata absent in a source tree
        return "source"


def _tool_commit() -> str | None:
    """git commit of the probe source tree, or None when not a checkout."""
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else None


def _source_sha256() -> dict[str, str]:
    """SHA-256 of the source files that produced the evidence.

    git HEAD alone is not enough: the first live run (S060) recorded a
    HEAD that did not yet contain compare.py, because the working tree
    was uncommitted.  The file hashes identify the code that ran.

    #SG-TRACE: REQ-COMPARE-009
    #   | assumption: these three modules fully determine every number
    #     in evidence.json (transport, features, statistics)
    #   | test: test_evidence_records_source_hashes
    """
    here = Path(__file__).resolve().parent
    out = {}
    for name in ("compare.py", "providers.py", "canary.py"):
        try:
            out[name] = hashlib.sha256((here / name).read_bytes()).hexdigest()
        except OSError:
            out[name] = "unreadable"
    return out


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed(suite_sha: str, model_a: str, model_b: str, repeats: int) -> int:
    blob = f"{suite_sha}|{model_a}|{model_b}|{repeats}".encode()
    return int(hashlib.sha256(blob).hexdigest()[:16], 16)


def _obs_record(o: Observation) -> dict:
    if not o.valid:
        return {"failure": o.failure}
    return {
        "hash": o.hash,
        "length": o.length,
        "finish_reason": o.finish_reason,
        "empty": o.empty,
        "json_valid": o.json_valid,
        "refusal": o.refusal,
        "latency_ms": o.latency_ms,
        "output_tokens": o.output_tokens,
        "reasoning_tokens": o.reasoning_tokens,
    }


@dataclass(frozen=True)
class CompareResult:
    evidence: dict
    report_html: str
    out_dir: Path
    evidence_sha256: str
    exit_code: int


def compare(
    items: Sequence[SuiteItem],
    suite_sha: str,
    side_a: Side,
    side_b: Side,
    *,
    repeats: int,
    out_dir: str | Path,
    no_text: bool = False,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    now: Callable[[], datetime] = _utcnow,
    tool_commit: str | None = None,
    tool_version: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> CompareResult:
    """Run the comparison, write report.html and evidence.json.

    Exit code: 0 when both sides were measured, 2 when either side is
    NOT MEASURED (over the infrastructure-failure limit).
    """
    if not MIN_REPEATS <= repeats <= MAX_REPEATS:
        raise ValueError(f"repeats must be {MIN_REPEATS}..{MAX_REPEATS}")
    started = now()
    obs = run_calls(items, (side_a, side_b), repeats, progress)
    finished = now()
    seed = _seed(suite_sha, side_a.requested, side_b.requested, repeats)

    sides: dict[str, dict] = {}
    measured: dict[str, bool] = {}
    for side in (side_a, side_b):
        all_obs = [o for it in items for o in obs[side.label][it.id]]
        failures = Counter(o.failure for o in all_obs if not o.valid)
        rate = len(all_obs) and sum(failures.values()) / len(all_obs)
        measured[side.label] = rate <= INFRA_FAILURE_LIMIT
        returned = sorted(
            {o.returned_model for o in all_obs if o.returned_model}
        )
        sides[side.label] = {
            "requested": side.requested,
            "returned": returned,
            "temperature": side.temperature,
            "planned_calls": len(all_obs),
            "calls_made": side.calls_made,
            "failures": dict(sorted(failures.items())),
            "failure_rate": _r(rate),
            "measured": measured[side.label],
            "levels": side_levels(items, obs[side.label]),
        }
    both = measured[side_a.label] and measured[side_b.label]
    metrics = []
    for i, spec in enumerate(METRICS):
        rng = random.Random(seed + i)
        metrics.append(
            evaluate_metric(
                spec,
                items,
                obs[side_a.label],
                obs[side_b.label],
                both,
                rng,
            )
        )
    modal_match = []
    for it in items:
        ma, mb = (
            _modal(obs[side_a.label][it.id]),
            _modal(obs[side_b.label][it.id]),
        )
        if ma is not None and mb is not None:
            modal_match.append(1.0 if ma.hash == mb.hash else 0.0)
    top = top_changes(items, obs[side_a.label], obs[side_b.label])
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "tool": {
            "name": TOOL_NAME,
            "version": tool_version or _tool_version(),
            "git_commit": tool_commit,
            "git_commit_note": (
                "HEAD at run time; the working tree may differ. "
                "source_sha256 identifies the code that ran."
            ),
            "source_sha256": _source_sha256(),
        },
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "suite": {"sha256": suite_sha, "items": len(items)},
        "repeats": repeats,
        "method": {
            "alpha": ALPHA,
            "permutations": N_PERMUTATIONS,
            "seed": seed,
            "min_items_per_metric": MIN_ITEMS_PER_METRIC,
            "infra_failure_limit": INFRA_FAILURE_LIMIT,
            "max_retries": MAX_RETRIES,
            "max_tokens": max_tokens,
            "refusal_patterns": REFUSAL_VERSION,
            "verdict_rule": (
                "CHANGED iff a_vs_b > max(within_a, within_b) and "
                "within-item permutation p <= alpha"
            ),
        },
        "sides": sides,
        "metrics": metrics,
        "modal_match_share": _r(_mean(modal_match)) if modal_match else None,
        "top_changes": [{"id": t["id"], "score": t["score"]} for t in top],
        "items": [
            {
                "id": it.id,
                "expect_json": it.expect_json,
                side_a.label: [
                    _obs_record(o) for o in obs[side_a.label][it.id]
                ],
                side_b.label: [
                    _obs_record(o) for o in obs[side_b.label][it.id]
                ],
            }
            for it in items
        ],
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ev_bytes = (
        json.dumps(evidence, sort_keys=True, indent=2, ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    (out / "evidence.json").write_bytes(ev_bytes)
    report = render_report(evidence, top, no_text=no_text)
    (out / "report.html").write_text(report, encoding="utf-8")
    return CompareResult(
        evidence=evidence,
        report_html=report,
        out_dir=out,
        evidence_sha256=hashlib.sha256(ev_bytes).hexdigest(),
        exit_code=0 if both else 2,
    )


_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e2dfd6;
--chg:#b3261e;--chgbg:#fbe9e7;--noise:#3d5a40;--noisebg:#eaf1e8;
--nm:#6b6a65;--nmbg:#eeede8;--code:#f2f0ea}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;
--muted:#a3a29b;--line:#34332f;--chg:#ffb4a9;--chgbg:#3b1d19;
--noise:#b7d3b1;--noisebg:#1f2b1f;--nm:#a3a29b;--nmbg:#262522;
--code:#211f1c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:36px 0 10px;
border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--muted);margin:0 0 18px}
.note{border-left:3px solid var(--chg);padding:6px 12px;margin:12px 0;
background:var(--chgbg)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);
vertical-align:top}
th{color:var(--muted);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.v{display:inline-block;padding:1px 8px;border-radius:10px;
font-size:12px;font-weight:600;white-space:nowrap}
.v-CHANGED{color:var(--chg);background:var(--chgbg)}
.v-NOISE{color:var(--noise);background:var(--noisebg)}
.v-NM{color:var(--nm);background:var(--nmbg)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:6px 0 18px}
pre{white-space:pre-wrap;word-break:break-word;margin:0;padding:10px;
background:var(--code);border-radius:6px;font-size:13px;max-height:320px;
overflow:auto}
.wrap{overflow-x:auto}
footer{color:var(--muted);font-size:13px;margin-top:40px}
@media (max-width:640px){.pair{grid-template-columns:1fr}}
"""


def _e(x: object) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def _fmt(x: object, unit: str = "") -> str:
    if x is None:
        return "&ndash;"
    if isinstance(x, float):
        if unit == "rate" or unit == "disagree":
            return f"{x * 100:.1f}%"
        return f"{x:.1f}"
    return _e(x)


def _verdict_badge(v: str) -> str:
    cls = {CHANGED: "v-CHANGED", WITHIN_NOISE: "v-NOISE"}.get(v, "v-NM")
    return f'<span class="v {cls}">{_e(v)}</span>'


def render_report(evidence: dict, top: list[dict], *, no_text: bool) -> str:
    """Self-contained HTML: no scripts, fonts, images or remote assets.

    #SG-TRACE: REQ-COMPARE-008
    #   | assumption: every dynamic string is HTML-escaped, so answer
    #     text containing URLs or markup is shown as text, never loaded
    #   | test: test_c9_report_is_offline
    """
    sa, sb = evidence["sides"]["A"], evidence["sides"]["B"]
    parts: list[str] = []
    add = parts.append
    add("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    add("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    add(f"<title>Compare: {_e(sa['requested'])} vs {_e(sb['requested'])}")
    add(f"</title><style>{_CSS}</style></head><body><main>")
    add(f"<h1>{_e(sa['requested'])} vs {_e(sb['requested'])}</h1>")
    add(
        f"<p class='sub'>{_e(evidence['started_at'][:19])}Z &middot; "
        f"{evidence['suite']['items']} items &times; "
        f"{evidence['repeats']} repeats per model &middot; suite sha256 "
        f"{_e(evidence['suite']['sha256'][:12])}&hellip;</p>"
    )
    add("<div class='wrap'><table><tr><th></th><th>Side A</th>")
    add("<th>Side B</th></tr>")
    rows = [
        ("Requested", sa["requested"], sb["requested"]),
        (
            "Returned by the API",
            ", ".join(sa["returned"]) or "none reported",
            ", ".join(sb["returned"]) or "none reported",
        ),
        ("Temperature", sa["temperature"], sb["temperature"]),
        (
            "Calls planned / made",
            f"{sa['planned_calls']} / {sa['calls_made']}",
            f"{sb['planned_calls']} / {sb['calls_made']}",
        ),
    ]
    for name, a, b in rows:
        add(f"<tr><th>{_e(name)}</th><td>{_e(a)}</td><td>{_e(b)}</td></tr>")
    add("</table></div>")
    for label, s in (("A", sa), ("B", sb)):
        if s["temperature"] == TEMP_DEFAULT:
            add(
                f"<p class='note'>Side {label} ran at provider default "
                "temperature: the provider rejected temperature=0, so the "
                "run retried once without it.</p>"
            )
        if not s["measured"]:
            add(
                f"<p class='note'>Side {label} had "
                f"{_fmt(s['failure_rate'], 'rate')} infrastructure "
                "failures (limit 10%). Every metric is NOT MEASURED; no "
                "behaviour change is claimed.</p>"
            )

    add("<h2>Verdicts</h2>")
    add(
        "<p class='sub'>Each metric is compared against repetition "
        "noise: how differently A answers A, and B answers B. "
        "&ldquo;Within&rdquo; and &ldquo;A vs B&rdquo; are mean "
        "pairwise differences between repeats.</p>"
    )
    add("<div class='wrap'><table><tr><th>Metric</th>")
    add("<th class='n'>Within A</th><th class='n'>Within B</th>")
    add("<th class='n'>A vs B</th><th class='n'>p</th><th>Verdict</th>")
    add("<th class='n'>Items</th></tr>")
    for m in evidence["metrics"]:
        label = m["label"] + (" *" if m["heuristic"] else "")
        p = "&ndash;" if m["p_value"] is None else f"{m['p_value']:.3f}"
        add(
            f"<tr><td>{_e(label)}</td>"
            f"<td class='n'>{_fmt(m['within_a'], m['unit'])}</td>"
            f"<td class='n'>{_fmt(m['within_b'], m['unit'])}</td>"
            f"<td class='n'>{_fmt(m['a_vs_b'], m['unit'])}</td>"
            f"<td class='n'>{p}</td>"
            f"<td>{_verdict_badge(m['verdict'])}"
            f"{' ' + _e(m.get('reason', '')) if m.get('reason') else ''}"
            f"</td><td class='n'>{m['eligible_items']}</td></tr>"
        )
    add("</table></div>")
    add(
        "<p class='sub'>* heuristic: refusal is detected by a fixed "
        f"phrase list ({_e(REFUSAL_VERSION)}), not by understanding the "
        "answer.</p>"
    )

    add("<h2>Levels per side</h2><div class='wrap'><table>")
    add("<tr><th></th><th class='n'>A</th><th class='n'>B</th></tr>")
    level_rows = [
        ("Self-agreement", "self_agreement", "rate"),
        ("Length median (chars)", "length_median", ""),
        ("Length p90 (chars)", "length_p90", ""),
        ("JSON valid", "json_valid_rate", "rate"),
        ("Truncated", "truncated_rate", "rate"),
        ("Empty", "empty_rate", "rate"),
        ("Refusal (heuristic)", "refusal_rate", "rate"),
        ("Latency p50 (ms)", "latency_p50", ""),
        ("Latency p95 (ms)", "latency_p95", ""),
        ("Output tokens (mean)", "output_tokens_mean", ""),
        ("Reasoning tokens (mean)", "reasoning_tokens_mean", ""),
    ]
    for name, key, unit in level_rows:
        add(
            f"<tr><td>{_e(name)}</td>"
            f"<td class='n'>{_fmt(sa['levels'][key], unit)}</td>"
            f"<td class='n'>{_fmt(sb['levels'][key], unit)}</td></tr>"
        )
    mm = evidence["modal_match_share"]
    add(
        "<tr><td>Items whose most frequent answer is identical</td>"
        f"<td class='n' colspan='2'>{_fmt(mm, 'rate')}</td></tr>"
    )
    add("</table></div>")

    add(f"<h2>Largest differences (up to {TOP_N})</h2>")
    if not top:
        add("<p class='sub'>No item differs beyond its own repeat noise.</p>")
    else:
        add(
            "<p class='sub'>Ranked by how much more A and B disagree than "
            "each disagrees with itself. Different is not necessarily "
            "worse.</p>"
        )
    for t in top:
        add(f"<h3>{_e(t['id'])} <span class='sub'>score {t['score']}</span>")
        add("</h3>")
        if no_text:
            continue
        add("<div class='pair'>")
        for lab, o in (("A", t["modal_a"]), ("B", t["modal_b"])):
            add(f"<div><b>{lab}</b><pre>{_e(o.text)}</pre></div>")
        add("</div>")

    add("<h2>Infrastructure failures</h2>")
    add("<p class='sub'>Not responses, never counted as behaviour.</p>")
    add("<div class='wrap'><table><tr><th>Class</th><th class='n'>A</th>")
    add("<th class='n'>B</th></tr>")
    classes = sorted(set(sa["failures"]) | set(sb["failures"]))
    if not classes:
        add("<tr><td colspan='3'>none</td></tr>")
    for c in classes:
        add(
            f"<tr><td>{_e(c)}</td>"
            f"<td class='n'>{sa['failures'].get(c, 0)}</td>"
            f"<td class='n'>{sb['failures'].get(c, 0)}</td></tr>"
        )
    add("</table></div>")

    add("<h2>Limits</h2><ul>")
    for line in (
        "Different is not worse. Only JSON validity, truncation and "
        "empty answers say anything about quality; nothing here checks "
        "whether an answer is correct.",
        "Repetition noise is estimated from "
        f"{evidence['repeats']} repeats per item; WITHIN NOISE means "
        "not distinguishable at this sample size, not identical.",
        "The model name returned by the API can be an alias (for "
        "example a -latest name); it does not prove which concrete "
        "version answered.",
        "Refusal detection is a phrase heuristic and misses polite or "
        "partial refusals.",
        "Latency reflects network and provider load at run time.",
        "Text in this file is local only; evidence.json contains hashes "
        "and numbers, no prompt or answer text.",
    ):
        add(f"<li>{_e(line)}</li>")
    add("</ul>")
    tool = evidence["tool"]
    add(
        f"<footer>{_e(TOOL_NAME)} {_e(tool['version'])}"
        f"{' @ ' + _e(tool['git_commit'][:12]) if tool['git_commit'] else ''}"
        f" &middot; <a href='{HOMEPAGE}'>driftdefense.dev</a></footer>"
    )
    add("</main></body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_model(spec: str) -> tuple[str, str]:
    if "/" not in spec:
        raise SuiteError(f"model must be provider/model, got {spec!r}")
    provider, model = spec.split("/", 1)
    if not provider or not model:
        raise SuiteError(f"model must be provider/model, got {spec!r}")
    return provider, model


def _endpoint(label: str, provider: str, env: dict) -> tuple[str, str | None]:
    base = env.get(f"SEISMOGRAPH_{label}_BASE_URL") or DEFAULT_BASE_URLS.get(
        provider
    )
    if not base:
        raise SuiteError(
            f"set SEISMOGRAPH_{label}_BASE_URL (no default for {provider!r})"
        )
    if urlparse(base).scheme not in ("http", "https"):
        raise SuiteError(f"SEISMOGRAPH_{label}_BASE_URL must be http(s)")
    return base, env.get(f"SEISMOGRAPH_{label}_API_KEY") or None


def provider_caller(provider: OpenAICompatibleProvider, model: str) -> Caller:
    """Adapt OpenAICompatibleProvider to the Side caller signature."""

    def call(item: SuiteItem, send_temperature: bool) -> CompletionResult:
        return provider.complete_ex(
            model,
            item.system,
            item.user,
            send_temperature=send_temperature,
            allow_null_content=True,
        )

    return call


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m probe.compare",
        description="Compare two models on your own prompts, against "
        "their own repetition noise. Writes report.html and "
        "evidence.json locally.",
    )
    p.add_argument("--suite", required=True, help="JSONL file of prompts")
    p.add_argument("--a", required=True, help="provider/model for side A")
    p.add_argument("--b", required=True, help="provider/model for side B")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--delay-ms-a", type=int, default=0)
    p.add_argument("--delay-ms-b", type=int, default=0)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--out", help="output directory")
    p.add_argument("--no-text", action="store_true")
    p.add_argument("--yes", action="store_true", help="proceed with calls")
    return p


def main(
    argv: Sequence[str] | None = None,
    *,
    env: dict | None = None,
    now: Callable[[], datetime] = _utcnow,
    sleep: Callable[[float], None] = time.sleep,
    out=print,
) -> int:
    """CLI entry.  Exit 0 ok, 1 usage error, 2 a side NOT MEASURED,
    3 confirmation required."""
    args = build_parser().parse_args(argv)
    env = dict(os.environ) if env is None else env
    try:
        items, suite_sha = load_suite(args.suite)
        if not MIN_REPEATS <= args.repeats <= MAX_REPEATS:
            raise SuiteError(f"--repeats must be {MIN_REPEATS}..{MAX_REPEATS}")
        prov_a, model_a = _split_model(args.a)
        prov_b, model_b = _split_model(args.b)
        base_a, key_a = _endpoint("A", prov_a, env)
        base_b, key_b = _endpoint("B", prov_b, env)
    except (SuiteError, OSError) as exc:
        out(f"error: {exc}")
        return 1
    calls = len(items) * args.repeats * 2
    out(
        f"{len(items)} items x {args.repeats} repeats x 2 models = "
        f"{calls} calls (plus at most {MAX_RETRIES} retries per failed "
        "call)."
    )
    out(f"A: {args.a} at {urlparse(base_a).netloc}")
    out(f"B: {args.b} at {urlparse(base_b).netloc}")
    if not args.yes:
        out("Nothing sent. Re-run with --yes to make these calls.")
        return 3
    try:
        pa = OpenAICompatibleProvider(
            base_a, key_a, max_tokens=args.max_tokens, timeout=args.timeout
        )
        pb = OpenAICompatibleProvider(
            base_b, key_b, max_tokens=args.max_tokens, timeout=args.timeout
        )
    except ProviderError as exc:
        out(f"error: {exc}")
        return 1
    side_a = Side(
        "A",
        args.a,
        provider_caller(pa, model_a),
        delay_ms=args.delay_ms_a,
        sleep=sleep,
    )
    side_b = Side(
        "B",
        args.b,
        provider_caller(pb, model_b),
        delay_ms=args.delay_ms_b,
        sleep=sleep,
    )
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    step = {"next": 0.1}

    def progress(done: int, total: int) -> None:
        # One line per 10% so a long run is never silent (S060 defect:
        # the first live run printed nothing for minutes).
        if done >= total * step["next"] - 1e-9 or done == total:
            out(f"  {done}/{total} calls")
            while step["next"] <= done / total + 1e-9:
                step["next"] += 0.1

    result = compare(
        items,
        suite_sha,
        side_a,
        side_b,
        repeats=args.repeats,
        out_dir=args.out or f"compare-{stamp}",
        no_text=args.no_text,
        max_tokens=args.max_tokens,
        now=now,
        tool_commit=_tool_commit(),
        progress=progress,
    )
    for m in result.evidence["metrics"]:
        out(f"  {m['label']:<34} {m['verdict']}")
    out(f"report:   {result.out_dir / 'report.html'}")
    out(f"evidence: {result.out_dir / 'evidence.json'}")
    out(f"evidence sha256: {result.evidence_sha256}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
