"""
tests.test_canary_suite_v2
==========================
CAN-2: canary corpus expansion 4 -> 50 prompts (suite v2.0.0).

All tests run fully OFFLINE (frozen mocks / injected fake providers).
No network, no provider keys.

Covers the CAN-2 Stage-1 contract test table (section 6):
  U1  CANARY_SUITE_V2[:4] == CANARY_SUITE_V1_1   (append-only proof)
  U2  suite hash v1.1.0 != v2.0.0; stable across calls AND processes
  U3  mock run -> 50 results, ids in suite order
  U4  tool_call_valid non-None exactly 8 times, all True
  U5  json_valid True exactly 9 times
  U6  corpus ASCII sweep (prompts AND frozen mocks)
  U7  id uniqueness + category membership
  U8  cost model < 0.10 USD/day; len(suite) <= 200
  U9  _metric_sensitivity("avg_output_length", 50) == 8192/50 == n4/12.5
  U10 flush of 50 results -> exactly six metric keys, result_count 50

  ADV-1 single-org Sybil at n=50 cannot promote, and the verdict is
        identical to the same attack at n=4
  ADV-2 semantic-only shift (no latency/result_count signal) is visible
        in avg_reasoning_tokens above the DP noise scale at n=50
  R1    discard-on-partial: a partial suite run is never flushed at
        reduced n

#SG-TRACE: REQ-CAN2-001..013 | tests below
"""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from engine.correlation import (
    AgreementScorer,
    ChangePointResult,
    required_quorum,
)
from engine.detector import CUSUMDetector
from probe.canary import (
    CANARY_CATEGORIES_V2,
    CANARY_SUITE_V1_1,
    CANARY_SUITE_V2,
    CANARY_SUITE_V2_NEW,
    FROZEN_TOOL_SCHEMA_V1,
    SUITE_VERSION_V1_1,
    SUITE_VERSION_V2,
    TOOL_CANARY_MAX_TOKENS,
    CanaryResult,
    PartialSuiteError,
    _mock_text_for,
    _mock_tool_calls_for,
    execute_canary,
    execute_canary_strict,
    suite_content_hash,
)
from probe.privacy import (
    EPSILON,
    MAX_OUTPUT_LENGTH,
    MAX_TOKEN_COUNT,
    Aggregator,
    _metric_sensitivity,
)
from probe.providers import CompletionResult, ProviderError

MODEL = "openai/gpt-4o@2025-08"
REPO_ROOT = Path(__file__).resolve().parents[1]

# Contract section 4 composition table.
EXPECTED_CATEGORY_COUNTS: dict[str, int] = {
    "logic_reasoning": 9,
    "structured_output": 9,
    "refusal_tone": 8,
    "tool_calling": 8,
    "reasoning_length": 8,
    "multilingual": 8,
}


def _mock_run() -> list[CanaryResult]:
    """One full offline v2.0.0 suite execution."""
    return execute_canary(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=True,
        suite_version=SUITE_VERSION_V2,
    )


def _ids_of(category: str) -> list[str]:
    """Prompt ids belonging to one category, in suite order."""
    return [
        p["prompt_id"] for p in CANARY_SUITE_V2 if p["category"] == category
    ]


# ---------------------------------------------------------------------------
# U1 -- append-only
# ---------------------------------------------------------------------------


def test_v2_suite_is_append_only() -> None:
    """U1/A1: the first four entries ARE the frozen v1.1.0 corpus.

    Identity (``is``) is asserted, not just equality: the v2 list reuses
    the very same dict objects, so no copy of a frozen prompt can drift
    from its original.

    #SG-TRACE: REQ-CAN2-009 | test: (this)
    """
    assert SUITE_VERSION_V2 == "v2.0.0"
    assert len(CANARY_SUITE_V2) == 50
    assert len(CANARY_SUITE_V2_NEW) == 46
    assert CANARY_SUITE_V2[:4] == CANARY_SUITE_V1_1
    for new, frozen in zip(
        CANARY_SUITE_V2[:4], CANARY_SUITE_V1_1, strict=True
    ):
        assert new is frozen
    # Every legacy id survives unchanged.
    legacy = {p["prompt_id"] for p in CANARY_SUITE_V1_1}
    assert legacy <= {p["prompt_id"] for p in CANARY_SUITE_V2}
    assert legacy == {
        "v1.0.0-logic",
        "v1.0.0-format",
        "v1.0.0-refusal",
        "v1.1.0-toolcall",
    }
    # No new prompt reuses a frozen id.
    assert not legacy & {p["prompt_id"] for p in CANARY_SUITE_V2_NEW}


def test_v2_category_counts_match_contract() -> None:
    """Section 4 composition table, exactly.

    #SG-TRACE: REQ-CAN2-001 | test: (this)
    """
    counts = Counter(p["category"] for p in CANARY_SUITE_V2)
    assert dict(counts) == EXPECTED_CATEGORY_COUNTS
    assert sum(EXPECTED_CATEGORY_COUNTS.values()) == 50


def test_v2_entry_shape_matches_v1() -> None:
    """Every new entry has exactly the key set of a frozen v1 entry.

    An extra key would change the canonical JSON of the whole corpus
    (and therefore the content hash) for reasons unrelated to prompts.

    #SG-TRACE: REQ-CAN2-002 | test: (this)
    """
    expected_keys = set(CANARY_SUITE_V1_1[0])
    assert expected_keys == {"prompt_id", "category", "system", "user"}
    for prompt in CANARY_SUITE_V2_NEW:
        assert set(prompt) == expected_keys
        assert all(isinstance(v, str) for v in prompt.values())
        assert prompt["user"].strip() and prompt["system"].strip()


# ---------------------------------------------------------------------------
# U2 -- content hash
# ---------------------------------------------------------------------------


def test_v2_suite_content_hash_differs_and_is_stable() -> None:
    """U2/A2: v2 hash != v1.1 hash, stable across calls and processes.

    Cross-process stability is the real assertion: PYTHONHASHSEED is
    randomised per interpreter, so a hash that depended on dict or set
    iteration order would differ between the two runs.

    #SG-TRACE: REQ-TOOLCAN-002, REQ-CAN2-009 | test: (this)
    """
    tools = [FROZEN_TOOL_SCHEMA_V1]
    h_v11 = suite_content_hash(CANARY_SUITE_V1_1, tools=tools)
    h_v2 = suite_content_hash(CANARY_SUITE_V2, tools=tools)
    assert h_v2 != h_v11
    assert h_v2 == suite_content_hash(CANARY_SUITE_V2, tools=tools)
    assert len(h_v2) == 64
    assert all(c in "0123456789abcdef" for c in h_v2)

    script = (
        "from probe.canary import CANARY_SUITE_V2, "
        "FROZEN_TOOL_SCHEMA_V1, suite_content_hash; "
        "print(suite_content_hash(CANARY_SUITE_V2, "
        "tools=[FROZEN_TOOL_SCHEMA_V1]))"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == h_v2


# ---------------------------------------------------------------------------
# U3/U4/U5 -- offline execution
# ---------------------------------------------------------------------------


def test_v2_mock_run_returns_fifty_results_in_order() -> None:
    """U3/A3: 50 results, one per prompt, in suite order.

    #SG-TRACE: REQ-CAN2-005 | test: (this)
    """
    results = _mock_run()
    assert len(results) == 50
    assert [r.prompt_id for r in results] == [
        p["prompt_id"] for p in CANARY_SUITE_V2
    ]
    assert all(r.suite_version == SUITE_VERSION_V2 for r in results)
    assert all(r.latency_ms == -1 for r in results)
    assert all(len(r.response_hash) == 64 for r in results)


def test_v2_tool_call_valid_non_none_exactly_for_tools() -> None:
    """U4/A3: tool_call_valid is non-None for the 8 tool prompts only.

    #SG-TRACE: REQ-CAN2-011 | test: (this)
    """
    results = _mock_run()
    scored = [r for r in results if r.tool_call_valid is not None]
    assert len(scored) == 8
    assert all(r.tool_call_valid is True for r in scored)
    assert [r.prompt_id for r in scored] == _ids_of("tool_calling")
    others = [r for r in results if r.tool_call_valid is None]
    assert len(others) == 42


def test_v2_json_valid_true_exactly_for_structured_prompts() -> None:
    """U5/A4: json_valid is True for the 9 structured_output prompts.

    #SG-TRACE: REQ-CAN2-006 | test: (this)
    """
    results = _mock_run()
    valid = [r for r in results if r.json_valid]
    assert len(valid) == 9
    assert [r.prompt_id for r in valid] == _ids_of("structured_output")
    # And every structured mock really is parseable JSON of the right
    # top-level type (an object, per every schema in the corpus).
    for pid in _ids_of("structured_output"):
        assert isinstance(json.loads(_mock_text_for(pid)), dict)


def test_every_v2_prompt_has_a_frozen_mock() -> None:
    """A5: no prompt falls back to the empty-string mock.

    R4 in the contract calls the 46 hand-written mocks "mechanical but
    error-prone volume"; this sweep is the guard.

    #SG-TRACE: REQ-CAN2-010, REQ-CAN2-012 | test: (this)
    """
    for prompt in CANARY_SUITE_V2:
        pid = prompt["prompt_id"]
        if prompt["category"] == "tool_calling":
            mock = _mock_tool_calls_for(pid)
        else:
            mock = _mock_text_for(pid)
        assert mock, f"{pid} has no frozen mock response"
    # Mock lookup never mutates or shadows the frozen v1 dicts.
    assert _mock_text_for("v1.0.0-logic").startswith("7 crossings.")
    assert "call_mock_0" in _mock_tool_calls_for("v1.1.0-toolcall")
    assert _mock_text_for("no-such-prompt") == ""
    assert _mock_tool_calls_for("no-such-prompt") == ""


# ---------------------------------------------------------------------------
# U6 -- ASCII sweep
# ---------------------------------------------------------------------------


def test_v2_corpus_is_ascii() -> None:
    """U6/A6/C3: every prompt AND every frozen mock is ASCII.

    Multilingual drift is probed by ASCII English instructions that
    REQUEST another language, never by non-ASCII prompt text -- so the
    sweep covers the multilingual mocks too.

    #SG-TRACE: REQ-CAN2-004 | test: (this)
    """
    for prompt in CANARY_SUITE_V2:
        for key, text in prompt.items():
            assert text.isascii(), f"non-ASCII in {prompt['prompt_id']}.{key}"
    for prompt in CANARY_SUITE_V2:
        pid = prompt["prompt_id"]
        assert _mock_text_for(pid).isascii(), pid
        assert _mock_tool_calls_for(pid).isascii(), pid

    # The multilingual category asks for a named language in English.
    langs = (
        "German",
        "Spanish",
        "Dutch",
        "Swedish",
        "Norwegian",
        "Indonesian",
        "Swahili",
        "Filipino",
    )
    users = [
        p["user"] for p in CANARY_SUITE_V2 if p["category"] == "multilingual"
    ]
    assert len(users) == 8
    assert {lang for lang in langs if any(lang in u for u in users)} == set(
        langs
    ), "each multilingual prompt names a distinct target language"


# ---------------------------------------------------------------------------
# U7 -- ids and categories
# ---------------------------------------------------------------------------


def test_v2_prompt_ids_unique_and_categories_known() -> None:
    """U7/A9: ids unique corpus-wide; categories from the six names.

    #SG-TRACE: REQ-CAN2-001 | test: (this)
    """
    ids = [p["prompt_id"] for p in CANARY_SUITE_V2]
    assert len(ids) == len(set(ids)) == 50
    assert set(CANARY_CATEGORIES_V2) == set(EXPECTED_CATEGORY_COUNTS)
    for prompt in CANARY_SUITE_V2:
        assert prompt["category"] in CANARY_CATEGORIES_V2


def test_v2_prompt_id_naming_convention() -> None:
    """New ids follow v2.0.0-<slug>-<nn>, numbered from 01 per slug.

    #SG-TRACE: REQ-CAN2-002 | test: (this)
    """
    slugs = {
        "logic_reasoning": "logic",
        "structured_output": "format",
        "refusal_tone": "refusal",
        "tool_calling": "toolcall",
        "reasoning_length": "reason",
        "multilingual": "multiling",
    }
    seen: dict[str, list[int]] = {}
    for prompt in CANARY_SUITE_V2_NEW:
        version, slug, nn = prompt["prompt_id"].rsplit("-", 2)
        assert version == "v2.0.0"
        assert slug == slugs[prompt["category"]]
        assert len(nn) == 2 and nn.isdigit()
        seen.setdefault(slug, []).append(int(nn))
    for slug, numbers in seen.items():
        assert numbers == list(range(1, len(numbers) + 1)), slug


def test_v2_tool_prompts_reuse_frozen_schema() -> None:
    """No new tool schema: all 8 tool canaries share the frozen one.

    A second schema would change the tool corpus folded into
    suite_content_hash and confound schema drift with argument
    extraction drift.  The mocks must be schema-valid against
    FROZEN_TOOL_SCHEMA_V1 with both enum values exercised.

    #SG-TRACE: REQ-CAN2-008 | test: (this)
    """
    units = []
    for pid in _ids_of("tool_calling"):
        calls = json.loads(_mock_tool_calls_for(pid))
        assert len(calls) == 1
        fn = calls[0]["function"]
        assert fn["name"] == FROZEN_TOOL_SCHEMA_V1["function"]["name"]
        args = json.loads(fn["arguments"])
        assert set(args) == {"location", "unit"}
        units.append(args["unit"])
    enum = FROZEN_TOOL_SCHEMA_V1["function"]["parameters"]["properties"][
        "unit"
    ]["enum"]
    assert set(units) == set(enum) == {"celsius", "fahrenheit"}


def test_v2_refusal_prompts_are_professionally_framed() -> None:
    """C5 / REQ-CANARY-012 ToS review flag for the new corpus.

    refusal_tone probes hedging and tone stability on legitimate
    professional questions.  Each prompt must name the professional
    context it is written for (the register of the frozen
    v1.0.0-refusal chemistry prompt) and must be phrased as an
    explanation request, never as an operational request.

    #SG-TRACE: REQ-CAN2-007 | test: (this)
    """
    professions = (
        "pharmacist",
        "administrator",
        "safety officer",
        "hygienist",
        "trainer",
        "inspector",
    )
    for prompt in CANARY_SUITE_V2_NEW:
        if prompt["category"] != "refusal_tone":
            continue
        user = prompt["user"]
        assert any(p in user for p in professions), user
        assert user.startswith(("Explain", "State", "Describe")), user
    # Nothing anywhere in the corpus reads as an operational request.
    banned = (
        "how do i make",
        "how to make",
        "step-by-step instructions for",
        "help me build a",
        "without getting caught",
    )
    for prompt in CANARY_SUITE_V2:
        lowered = prompt["user"].lower()
        assert not any(b in lowered for b in banned), prompt["prompt_id"]


# ---------------------------------------------------------------------------
# U8 -- cost model
# ---------------------------------------------------------------------------

# Public list price of the cheapest provider leg currently probed by
# .github/workflows/probe_weather.yml (google/gemini-3.5-flash-lite,
# list price as of 2026-07): USD 0.10 per 1M input tokens and USD 0.40
# per 1M output tokens.  Constants live in the test, not in the probe:
# the probe must not carry a pricing table it cannot keep current.
USD_PER_INPUT_TOKEN: float = 0.10 / 1_000_000
USD_PER_OUTPUT_TOKEN: float = 0.40 / 1_000_000
CHARS_PER_TOKEN: float = 4.0
FLUSHES_PER_DAY: int = 5  # contract section 8 warm-up ceiling
COST_CAP_USD_PER_DAY: float = 0.10
SUITE_SIZE_CAP: int = 200  # REQ-CANARY-002


def _estimated_input_tokens(prompt: dict[str, str]) -> float:
    """Chars/4 estimate of one prompt's input tokens, tool schema included."""
    chars = len(prompt["system"]) + len(prompt["user"])
    if prompt["category"] == "tool_calling":
        chars += len(json.dumps(FROZEN_TOOL_SCHEMA_V1))
    return chars / CHARS_PER_TOKEN


def test_v2_cost_model_under_daily_cap() -> None:
    """U8/A7/C4: modelled spend < 0.10 USD/day; suite <= 200 prompts.

    Computed, not asserted from prose: every prompt's input tokens are
    estimated from its own text, output tokens are capped at the
    provider max_tokens the probe sends, and the whole suite runs
    FLUSHES_PER_DAY times.

    #SG-TRACE: REQ-CAN2-001 | test: (this)
    """
    assert len(CANARY_SUITE_V2) <= SUITE_SIZE_CAP

    input_tokens = sum(_estimated_input_tokens(p) for p in CANARY_SUITE_V2)
    output_tokens = len(CANARY_SUITE_V2) * TOOL_CANARY_MAX_TOKENS
    cost_per_run = (
        input_tokens * USD_PER_INPUT_TOKEN
        + output_tokens * USD_PER_OUTPUT_TOKEN
    )
    cost_per_day = cost_per_run * FLUSHES_PER_DAY

    assert cost_per_day < COST_CAP_USD_PER_DAY
    # Headroom check: even a 10x token-estimate error stays under cap,
    # so the result is not an artefact of the chars/4 heuristic.
    assert cost_per_day * 10 < COST_CAP_USD_PER_DAY
    # A 200-prompt suite (the hard cap) would also stay under budget.
    scaled = cost_per_day * (SUITE_SIZE_CAP / len(CANARY_SUITE_V2))
    assert scaled < COST_CAP_USD_PER_DAY


# ---------------------------------------------------------------------------
# U9/U10 -- DP sensitivity and flush key set at n=50
# ---------------------------------------------------------------------------


def test_metric_sensitivity_at_n50_is_12_5x_quieter() -> None:
    """U9/A8: delta_f = 8192/50, exactly 1/12.5 of the n=4 value.

    #SG-TRACE: REQ-PRIV-010, REQ-CAN2-001 | test: (this)
    """
    s50 = _metric_sensitivity("avg_output_length", 50)
    s4 = _metric_sensitivity("avg_output_length", 4)
    assert s50 == MAX_OUTPUT_LENGTH / 50 == 163.84
    assert s4 == MAX_OUTPUT_LENGTH / 4 == 2048.0
    assert s50 == pytest.approx(s4 / 12.5)
    assert 50 / 4 == 12.5
    # The same 12.5x holds for every clamped-mean metric.
    for metric in (
        "json_success_rate",
        "tool_call_validity_rate",
        "avg_output_tokens",
        "avg_reasoning_tokens",
    ):
        assert _metric_sensitivity(metric, 50) == pytest.approx(
            _metric_sensitivity(metric, 4) / 12.5
        )
    # Laplace sigma = sqrt(2) * b, b = delta_f / EPSILON (contract s2).
    sigma_4 = math.sqrt(2) * s4 / EPSILON
    sigma_50 = math.sqrt(2) * s50 / EPSILON
    assert round(sigma_4) == 1448
    assert round(sigma_50) == 116


def _tokenised(results: list[CanaryResult]) -> list[CanaryResult]:
    """Attach plausible usage counters to a mock run (mocks carry none)."""
    return [
        replace(r, output_tokens=48, reasoning_tokens=120) for r in results
    ]


def test_flush_of_fifty_results_emits_six_metric_keys() -> None:
    """U10/A8: exactly the six allowed keys; result_count == 50.

    #SG-TRACE: REQ-GW-030, REQ-CAN2-001 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(1))
    for result in _tokenised(_mock_run()):
        agg.add_result(result)
    batch = agg.flush(MODEL)

    assert set(batch.metrics) == {
        "avg_output_length",
        "json_success_rate",
        "tool_call_validity_rate",
        "avg_output_tokens",
        "avg_reasoning_tokens",
        "result_count",
    }
    assert batch.metrics["result_count"] == 50.0
    assert batch.result_count == 50
    assert batch.suite_version == SUITE_VERSION_V2
    # One hash per prompt id -- 50 distinct canary hashes on the wire.
    assert len(batch.canary_hashes) == 50


# ---------------------------------------------------------------------------
# ADV-1 -- single-org Sybil injecting false drift under v2.0.0
# ---------------------------------------------------------------------------


def _forged_results(n: int, suite_version: str) -> list[CanaryResult]:
    """n fabricated results with every metric at its clamp extreme."""
    return [
        CanaryResult(
            timestamp=f"2026-07-29T12:{i // 60:02d}:{i % 60:02d}+00:00",
            model_tuple=MODEL,
            suite_version=suite_version,
            prompt_id=f"forged-{i:03d}",
            # Fabricated: a hash of a string the probe never produced.
            response_hash=f"{i:064x}",
            output_length=MAX_OUTPUT_LENGTH * 4,  # clamps to 8192
            json_valid=True,
            latency_ms=-1,
            tool_call_valid=True,
            output_tokens=MAX_TOKEN_COUNT * 4,  # clamps to 8192
            reasoning_tokens=MAX_TOKEN_COUNT * 4,
        )
        for i in range(n)
    ]


def _mount_single_org_attack(n: int, suite_version: str) -> tuple:
    """Run the full single-org attack at batch size n; return the verdict.

    The attacker owns one org identity, fabricates every canary hash,
    and drives every metric to the top of its clamped range, then
    replays the batch daily for 90 days.  Returns
    (promoted, quorum_required, local_alert_fired) -- the "verdict".
    """
    agg = Aggregator(_rng=random.Random(99))
    detector = CUSUMDetector()
    scorer = AgreementScorer()
    day_ns = 86_400 * 1_000_000_000
    local_alert_fired = False

    # Honest baseline for this org's own CUSUM stream.
    for _ in range(12):
        for result in _forged_results(n, suite_version):
            agg.add_result(replace(result, output_length=300))
        batch = agg.flush(MODEL)
        detector.update(
            MODEL, "avg_output_length", batch.metrics["avg_output_length"]
        )

    for day in range(12, 90):
        for result in _forged_results(n, suite_version):
            agg.add_result(result)
        batch = agg.flush(MODEL)
        assert batch.result_count == n
        alert = detector.update(
            MODEL, "avg_output_length", batch.metrics["avg_output_length"]
        )
        if alert is not None:
            local_alert_fired = True
        scorer.ingest(
            ChangePointResult(
                model_tuple=MODEL,
                change_detected=True,
                score=9.9,
                threshold=5.0,
                contributing_orgs=["org-sybil"],
                metric_name="avg_output_length",
                timestamp_ns=day * day_ns,
            )
        )

    now_ns = 90 * day_ns
    promoted = scorer.promote_to_public_alert(
        MODEL, "avg_output_length", now_ns=now_ns
    )
    return promoted, required_quorum(1), local_alert_fired


def test_adv1_single_org_sybil_cannot_promote_at_n50() -> None:
    """ADV-1: expansion does not create a cheaper Sybil path.

    One org, 50 fabricated canary hashes per batch, every metric pinned
    to its clamp extreme, replayed for 78 consecutive days.  The local
    CUSUM does fire (that is its job -- the org sees its own stream
    move), but promote_to_public_alert returns None: quorum is
    q(M) = max(3, ceil(M/3)) = 3 distinct orgs and M = 1.

    The verdict at n=50 must be IDENTICAL to the same attack at n=4:
    corpus size is not an axis the attacker can buy quorum along.

    #SG-TRACE: REQ-ENGINE-008, REQ-ENGINE-012, REQ-CAN2-009 | test: (this)
    """
    verdict_50 = _mount_single_org_attack(50, SUITE_VERSION_V2)
    verdict_4 = _mount_single_org_attack(4, SUITE_VERSION_V1_1)

    promoted_50, quorum_50, local_50 = verdict_50
    assert promoted_50 is None, "one org must never promote a public alert"
    assert quorum_50 == 3
    assert local_50 is True, "local CUSUM is expected to fire (see ADV-1)"
    assert verdict_50 == verdict_4

    # And the attacker gains nothing by spreading the same forged batch
    # over many client_ids: agreement is keyed on org identity.
    scorer = AgreementScorer()
    for i in range(200):
        scorer.ingest(
            ChangePointResult(
                model_tuple=MODEL,
                change_detected=True,
                score=9.9,
                threshold=5.0,
                contributing_orgs=["org-sybil"],
                metric_name="avg_output_length",
                timestamp_ns=i * 1_000_000_000,
            )
        )
    assert (
        scorer.promote_to_public_alert(
            MODEL, "avg_output_length", now_ns=200 * 1_000_000_000
        )
        is None
    )


# ---------------------------------------------------------------------------
# ADV-2 -- provider-side semantic shift with no latency/uptime signal
# ---------------------------------------------------------------------------

# Stable-window feature model for the 50-prompt corpus.
STABLE_REASONING_TOKENS: int = 900  # reasoning_length prompts
BASE_REASONING_TOKENS: int = 40  # every other prompt
SHIFTED_REASONING_TOKENS: int = 0  # budget withdrawn by the provider
SHIFTED_MULTILINGUAL_LENGTH: int = 8  # answers collapse to a stub
# Warm-up length of a new suite-scoped stream (contract section 8 R3).
BASELINE_SAMPLES: int = 30


def _adv2_results(shifted: bool, day: int) -> list[CanaryResult]:
    """One 50-result window; ``shifted`` moves ONLY semantic features.

    latency_ms and the record count are a pure function of the prompt
    index, identical in both windows -- a latency/uptime monitor sees
    nothing at all.
    """
    mock = {r.prompt_id: r for r in _mock_run()}
    out: list[CanaryResult] = []
    for i, prompt in enumerate(CANARY_SUITE_V2):
        pid = prompt["prompt_id"]
        category = prompt["category"]
        length = mock[pid].output_length
        reasoning = BASE_REASONING_TOKENS
        if category == "reasoning_length":
            reasoning = STABLE_REASONING_TOKENS
        if shifted and category == "reasoning_length":
            reasoning = SHIFTED_REASONING_TOKENS
        if shifted and category == "multilingual":
            length = SHIFTED_MULTILINGUAL_LENGTH
        out.append(
            replace(
                mock[pid],
                timestamp=f"2026-08-{day + 1:02d}T09:{i // 60:02d}"
                f":{i % 60:02d}+00:00",
                output_length=length,
                latency_ms=400 + (i % 7) * 13,
                output_tokens=48,
                reasoning_tokens=reasoning,
            )
        )
    return out


def _raw_mean(results: list[CanaryResult], attr: str) -> float:
    return sum(getattr(r, attr) for r in results) / len(results)


def test_adv2_semantic_only_shift_visible_in_reasoning_tokens() -> None:
    """ADV-2: reasoning-budget withdrawal, no latency or uptime signal.

    Window A and window B have byte-identical latency_ms per prompt and
    an identical result_count of 50.  Only semantics move: the 8
    multilingual answers collapse to a stub and the 8 reasoning_length
    prompts lose their reasoning budget.

    The raw shift in avg_reasoning_tokens is
    8 * 900 / 50 = 144 tokens, against a DP noise scale of
    sqrt(2) * b = sqrt(2) * (8192/50)/2 = 115.85 tokens -- so the
    shift clears the per-flush noise floor, and CUSUM raises a
    candidate on the DP-noised stream.

    #SG-TRACE: REQ-CAN2-003, REQ-TOKMET-011 | test: (this)
    """
    stable = _adv2_results(shifted=False, day=0)
    shifted = _adv2_results(shifted=True, day=0)

    # 1. The features a latency/uptime monitor watches do NOT move.
    assert len(stable) == len(shifted) == 50
    assert [r.latency_ms for r in stable] == [r.latency_ms for r in shifted]
    assert [r.prompt_id for r in stable] == [r.prompt_id for r in shifted]
    assert [r.json_valid for r in stable] == [r.json_valid for r in shifted]
    assert [r.tool_call_valid for r in stable] == [
        r.tool_call_valid for r in shifted
    ]
    # Only the 16 semantic records differ at all.
    moved = [
        a.prompt_id
        for a, b in zip(stable, shifted, strict=True)
        if (a.output_length, a.reasoning_tokens)
        != (b.output_length, b.reasoning_tokens)
    ]
    assert len(moved) == 16

    # 2. The shift exceeds the DP noise scale at n=50.
    b_scale = _metric_sensitivity("avg_reasoning_tokens", 50) / EPSILON
    dp_sigma = math.sqrt(2) * b_scale
    delta = _raw_mean(stable, "reasoning_tokens") - _raw_mean(
        shifted, "reasoning_tokens"
    )
    assert delta == pytest.approx(8 * STABLE_REASONING_TOKENS / 50)
    assert delta == pytest.approx(144.0)
    assert dp_sigma == pytest.approx(115.852, abs=0.01)
    assert delta > dp_sigma
    # At n=4 the same per-prompt change is invisible: sigma is 12.5x
    # larger while the mean shift cannot be (only 4 records exist).
    sigma_4 = (
        math.sqrt(2) * _metric_sensitivity("avg_reasoning_tokens", 4) / EPSILON
    )
    assert delta < sigma_4

    # 3. CUSUM raises a candidate on the DP-noised metric stream.
    agg = Aggregator(_rng=random.Random(42))
    detector = CUSUMDetector(baseline_samples=BASELINE_SAMPLES)
    for day in range(BASELINE_SAMPLES):  # warm-up window
        for r in _adv2_results(shifted=False, day=day):
            agg.add_result(r)
        batch = agg.flush(MODEL)
        assert batch.metrics["result_count"] == 50.0
        assert (
            detector.update(
                MODEL,
                "avg_reasoning_tokens",
                batch.metrics["avg_reasoning_tokens"],
            )
            is None
        )

    alert = None
    for day in range(BASELINE_SAMPLES, BASELINE_SAMPLES + 20):
        for r in _adv2_results(shifted=True, day=day % 28):
            agg.add_result(r)
        batch = agg.flush(MODEL)
        alert = alert or detector.update(
            MODEL,
            "avg_reasoning_tokens",
            batch.metrics["avg_reasoning_tokens"],
        )
    assert alert is not None, "CUSUM must raise a candidate on the shift"
    assert alert.metric_name == "avg_reasoning_tokens"
    assert alert.direction == "negative"
    assert alert.cusum_score > alert.threshold


def test_adv2_control_stable_stream_raises_no_candidate() -> None:
    """ADV-2 control: the same pipeline on an unshifted stream is quiet.

    Without this, the ADV-2 alert could be an artefact of DP noise
    rather than of the semantic shift: the SAME seeded noise stream,
    the same 30-sample warm-up and 40 further windows, with only the
    semantic shift removed, produces no candidate at all.

    Scope note: this is a seeded single-stream control, not a
    false-positive rate.  Laplace noise at epsilon=2 is heavy-tailed
    and a shorter warm-up trips this detector on some seeds -- which
    is exactly why the contract specifies a 30-sample baseline
    (section 8, R3).

    #SG-TRACE: REQ-CAN2-003 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(42))
    detector = CUSUMDetector(baseline_samples=BASELINE_SAMPLES)
    alerts = []
    for day in range(BASELINE_SAMPLES + 40):
        for r in _adv2_results(shifted=False, day=day % 28):
            agg.add_result(r)
        batch = agg.flush(MODEL)
        alert = detector.update(
            MODEL,
            "avg_reasoning_tokens",
            batch.metrics["avg_reasoning_tokens"],
        )
        if alert is not None:
            alerts.append(alert)
    assert alerts == []


def test_adv2_output_length_shift_is_below_the_single_flush_dp_floor() -> None:
    """ADV-2 caveat, asserted rather than asserted-away.

    The contract asks for the SAME sqrt(2)*b assertion on
    avg_output_length.  It is not attainable in one flush, and the
    arithmetic is not close: the probe sends max_tokens=64, so a canary
    answer cannot exceed a few hundred characters, while
    MAX_OUTPUT_LENGTH -- the constant that sets the DP sensitivity --
    is 8192.  Even if all 8 multilingual answers collapsed from the
    longest output the wire permits to zero characters, the mean shift
    would be 8 * 256 / 50 = 41 characters against a noise scale of
    115.85.

    The gap is a mis-calibrated sensitivity constant in probe/privacy.py
    (8192 vs a true bound of ~256 chars at max_tokens=64), NOT a
    property of the corpus expansion.  Tightening MAX_OUTPUT_LENGTH is
    a privacy-layer change and is out of scope for CAN-2; this test
    pins the arithmetic so the claim cannot be quietly lost.

    #SG-TRACE: REQ-CAN2-003 | test: (this)
    """
    stable = _adv2_results(shifted=False, day=0)
    shifted = _adv2_results(shifted=True, day=0)
    delta = _raw_mean(stable, "output_length") - _raw_mean(
        shifted, "output_length"
    )
    dp_sigma = (
        math.sqrt(2) * _metric_sensitivity("avg_output_length", 50) / EPSILON
    )
    assert delta > 0  # the multilingual answers really did shorten
    assert delta < dp_sigma  # ... but below the single-flush DP floor

    # Upper bound of ANY multilingual-only length shift on the wire.
    max_chars_at_64_tokens = 64 * CHARS_PER_TOKEN
    best_case = 8 * max_chars_at_64_tokens / 50
    assert best_case < dp_sigma
    # If MAX_OUTPUT_LENGTH matched the wire bound, the same shift would
    # clear the floor by a wide margin -- the fix is a constant, not a
    # bigger corpus.
    tightened_sigma = math.sqrt(2) * (max_chars_at_64_tokens / 50) / EPSILON
    assert best_case > 10 * tightened_sigma


# ---------------------------------------------------------------------------
# R1 -- discard-on-partial
# ---------------------------------------------------------------------------


class _FlakyProvider:
    """complete_ex that raises ProviderError for chosen user prompts.

    Models the R1 failure mode: a free-tier endpoint returning 503 for
    a few prompts of a 50-prompt leg while answering the rest normally.
    """

    def __init__(self, fail_on: set[str]) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    def complete_ex(
        self,
        model: str,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        self.calls.append(user)
        if user in self.fail_on:
            raise ProviderError("provider HTTP 503")
        if tools:
            return CompletionResult(
                text="",
                tool_calls_json=_mock_tool_calls_for("v1.1.0-toolcall"),
                output_tokens=12,
                reasoning_tokens=4,
                latency_ms=41,
            )
        return CompletionResult(
            text="ok",
            tool_calls_json=None,
            output_tokens=12,
            reasoning_tokens=4,
            latency_ms=41,
        )


def test_partial_suite_run_is_discarded_not_flushed() -> None:
    """R1: a partial suite raises and stages NOTHING for aggregation.

    Flushing 48 of 50 results would silently change both the metric
    (a mean over a provider-selected subset of the corpus) and the DP
    noise scale (MAX/n), which the CUSUM baseline cannot distinguish
    from real drift.  Decision (contract section 7 R1):
    discard-on-partial.

    #SG-TRACE: REQ-CAN2-013 | test: (this)
    """
    doomed = [CANARY_SUITE_V2[7]["user"], CANARY_SUITE_V2[40]["user"]]
    provider = _FlakyProvider(fail_on=set(doomed))
    aggregator = Aggregator(_rng=random.Random(3))

    with pytest.raises(PartialSuiteError) as exc_info:
        results = execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2,
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
        )
        for result in results:
            aggregator.add_result(result)

    exc = exc_info.value
    assert exc.completed == 48
    assert exc.expected == 50
    assert exc.failed_prompt_ids == [
        CANARY_SUITE_V2[7]["prompt_id"],
        CANARY_SUITE_V2[40]["prompt_id"],
    ]
    # The leg was not abandoned at the first failure: every prompt was
    # attempted, which is what makes the failure list meaningful.
    assert len(provider.calls) == 50

    # Nothing was staged -> nothing can be flushed at reduced n.
    assert aggregator.pending_count(MODEL) == 0
    with pytest.raises(ValueError, match="No pending results"):
        aggregator.flush(MODEL)

    # Why it matters, numerically: flushing at n=48 would widen the
    # noise scale of the stream by ~4% against the same baseline.
    assert _metric_sensitivity("avg_output_length", 48) > _metric_sensitivity(
        "avg_output_length", 50
    )


def test_strict_runner_returns_full_suite_when_complete() -> None:
    """R1 happy path: a complete run behaves exactly like execute_canary.

    #SG-TRACE: REQ-CAN2-013 | test: (this)
    """
    strict = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=True,
        suite_version=SUITE_VERSION_V2,
    )
    plain = _mock_run()
    assert len(strict) == 50
    assert [r.prompt_id for r in strict] == [r.prompt_id for r in plain]
    assert [r.response_hash for r in strict] == [
        r.response_hash for r in plain
    ]
    assert [r.tool_call_valid for r in strict] == [
        r.tool_call_valid for r in plain
    ]
    assert [r.json_valid for r in strict] == [r.json_valid for r in plain]


def test_strict_runner_config_errors_are_not_partial_runs() -> None:
    """A misconfigured leg fails loudly instead of looking like a 503.

    #SG-TRACE: REQ-CAN2-013 | test: (this)
    """

    class LegacyProvider:
        def complete(self, model, system, user):
            return "ok", 1

    with pytest.raises(ValueError, match="requires a provider"):
        execute_canary_strict(
            MODEL, suite=CANARY_SUITE_V2, mock=False, provider=None
        )
    with pytest.raises(ValueError, match="complete_ex"):
        execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2,
            mock=False,
            provider=LegacyProvider(),
            suite_version=SUITE_VERSION_V2,
        )
