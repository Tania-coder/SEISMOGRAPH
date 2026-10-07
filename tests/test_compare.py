"""
COMPARE-1 acceptance tests (docs/arch/COMPARE-1-contract.md section 9).

Fully offline: fake callers and a fake HTTP transport.  No network.
Tests c1..c12 map one-to-one to the contract's acceptance list; the rest
cover section 8 (network, keys), the --yes gate, failure classification
and a property test on the permutation statistic.

Constitution case (a), a Sybil probe, does not apply: compare is a
single-organisation local tool and publishes nothing.  Case (b), a
silent semantic shift with no latency/length signal, is c4.

#SG-TRACE: REQ-COMPARE-001 | test: test_c3_noise_floor_not_reported_as_changed
#SG-TRACE: REQ-COMPARE-002 | test: test_c10_evidence_has_no_prompt_answer_or_key
#SG-TRACE: REQ-COMPARE-003 | test: test_c11_suite_over_cap_refused
#SG-TRACE: REQ-COMPARE-004 | test: test_c5_refusal_rate_rises_flagged_heuristic
#SG-TRACE: REQ-COMPARE-005 | test: test_classify_table
#SG-TRACE: REQ-COMPARE-006 | test: test_c8_temperature_rejected_retried_once_and_stated
#SG-TRACE: REQ-COMPARE-007 | test: test_property_permutation_symmetry_and_null_calibration
#SG-TRACE: REQ-COMPARE-008 | test: test_c9_report_is_offline
"""  # noqa: E501

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
from probe import compare as cmp
from probe import providers
from probe.providers import CompletionResult, ProviderError

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _clock(start=T0):
    state = {"t": start}

    def now():
        state["t"] += timedelta(seconds=1)
        return state["t"]

    return now


def _items(n=50, n_json=0):
    return [
        cmp.SuiteItem(
            id=f"q{i:03d}",
            user=f"Private prompt number {i} about the quarterly figures",
            system=None,
            expect_json=i < n_json,
        )
        for i in range(n)
    ]


def _answer(item):
    if item.expect_json:
        return '{"result": "value-' + item.id + '", "ok": true}'
    return f"Confidential answer for {item.id}: option seven is preferred."


def _fake(fn=None, *, latency=50):
    """Caller whose output is fn(item, repeat_index) -> str | dict | exc."""
    fn = fn or (lambda item, r: _answer(item))
    seen: dict[str, int] = {}
    calls: list[tuple[str, bool]] = []

    def call(item, send_temperature):
        r = seen.get(item.id, 0)
        calls.append((item.id, send_temperature))
        out = (
            fn(item, r)
            if fn.__code__.co_argcount == 2
            else fn(item, r, send_temperature)
        )
        seen[item.id] = r + 1
        if isinstance(out, Exception):
            raise out
        spec = {"text": out} if isinstance(out, str) else dict(out)
        return CompletionResult(
            text=spec["text"],
            tool_calls_json=None,
            output_tokens=spec.get("tokens", 20),
            reasoning_tokens=None,
            latency_ms=spec.get("latency", latency),
            finish_reason=spec.get("finish", "stop"),
            returned_model=spec.get("model", "model-x"),
        )

    call.calls = calls
    return call


def _run(tmp_path, fa, fb, items=None, repeats=3, sleep=None, **kw):
    items = items or _items()
    sa = cmp.Side("A", "p/a", fa, sleep=sleep or (lambda s: None))
    sb = cmp.Side("B", "p/b", fb, sleep=sleep or (lambda s: None))
    return cmp.compare(
        items,
        "f" * 64,
        sa,
        sb,
        repeats=repeats,
        out_dir=tmp_path / kw.pop("sub", "out"),
        now=kw.pop("now", _clock()),
        tool_commit="c0ffee",
        tool_version="test",
        **kw,
    )


def _verdicts(result):
    return {m["metric"]: m["verdict"] for m in result.evidence["metrics"]}


# --- c1 ------------------------------------------------------------------


def test_c1_identical_deterministic_within_noise(tmp_path) -> None:
    res = _run(tmp_path, _fake(), _fake())
    v = _verdicts(res)
    for name in ("agreement", "length", "truncated", "empty", "refusal"):
        assert v[name] == cmp.WITHIN_NOISE, name
    assert v["latency"] == cmp.WITHIN_NOISE
    assert res.evidence["modal_match_share"] == 1.0
    agree = next(
        m for m in res.evidence["metrics"] if m["metric"] == "agreement"
    )
    assert agree["a_vs_b"] == 0.0
    assert res.evidence["top_changes"] == []
    assert res.exit_code == 0
    assert "stable" not in res.report_html.lower()


# --- c2 ------------------------------------------------------------------


def test_c2_ten_changed_items_listed_exactly(tmp_path) -> None:
    changed = {f"q{i:03d}" for i in (1, 4, 9, 13, 17, 22, 28, 33, 40, 47)}

    def b(item, r):
        base = _answer(item)
        return base + " Revised." if item.id in changed else base

    res = _run(tmp_path, _fake(), _fake(b))
    assert {t["id"] for t in res.evidence["top_changes"]} == changed
    assert _verdicts(res)["agreement"] == cmp.CHANGED


# --- c3 ------------------------------------------------------------------


def _noisy(seed):
    rng = random.Random(seed)

    def fn(item, r):
        if rng.random() < 0.4:
            return f"{_answer(item)} Variant {rng.choice('xy')}."
        return _answer(item)

    return fn


@pytest.mark.parametrize("seed", range(6))
def test_c3_noise_floor_not_reported_as_changed(tmp_path, seed) -> None:
    """Adversarial: A varies ~40% between repeats; B is the same process."""
    res = _run(tmp_path, _fake(_noisy(seed)), _fake(_noisy(1000 + seed)))
    v = _verdicts(res)
    assert v["agreement"] != cmp.CHANGED
    assert v["length"] != cmp.CHANGED
    agree = next(
        m for m in res.evidence["metrics"] if m["metric"] == "agreement"
    )
    assert agree["within_a"] > 0.1  # the noise is really there


# --- c4 ------------------------------------------------------------------


def test_c4_silent_semantic_shift_json_only(tmp_path) -> None:
    """Constitution case (b): same latency and length, broken JSON."""
    items = _items(50, n_json=20)
    broken = {f"q{i:03d}" for i in range(0, 20, 2)}

    def b(item, r):
        text = _answer(item)
        if item.id in broken:
            text = text[:-1] + "]"  # same length, invalid JSON
        return text

    res = _run(tmp_path, _fake(), _fake(b), items=items)
    v = _verdicts(res)
    assert v["json_valid"] == cmp.CHANGED
    assert v["latency"] == cmp.WITHIN_NOISE
    assert v["length"] == cmp.WITHIN_NOISE
    lv = res.evidence["sides"]
    assert lv["A"]["levels"]["json_valid_rate"] == 1.0
    assert lv["B"]["levels"]["json_valid_rate"] == 0.5


# --- c5 ------------------------------------------------------------------


def test_c5_refusal_rate_rises_flagged_heuristic(tmp_path) -> None:
    refused = {f"q{i:03d}" for i in range(0, 50, 5)}  # 20%

    def b(item, r):
        if item.id in refused:
            return "I'm sorry, but I can't help with that request."
        return _answer(item)

    res = _run(tmp_path, _fake(), _fake(b))
    row = next(m for m in res.evidence["metrics"] if m["metric"] == "refusal")
    assert row["verdict"] == cmp.CHANGED
    assert row["heuristic"] is True
    lv = res.evidence["sides"]
    assert lv["B"]["levels"]["refusal_rate"] == 0.2
    assert lv["A"]["levels"]["refusal_rate"] == 0.0
    assert "heuristic" in res.report_html


# --- c6 ------------------------------------------------------------------


def test_c6_truncation_rate_rises(tmp_path) -> None:
    cut = {f"q{i:03d}" for i in range(15)}  # 30%

    def b(item, r):
        fin = "length" if item.id in cut else "stop"
        return {"text": _answer(item), "finish": fin}

    res = _run(tmp_path, _fake(), _fake(b))
    assert _verdicts(res)["truncated"] == cmp.CHANGED
    assert res.evidence["sides"]["B"]["levels"]["truncated_rate"] == 0.3


# --- c7 ------------------------------------------------------------------


def test_c7_auth_failure_not_measured_nonzero_exit(tmp_path) -> None:
    fb = _fake(lambda item, r: ProviderError("provider HTTP 401", 401))
    res = _run(tmp_path, _fake(), fb)
    sb = res.evidence["sides"]["B"]
    assert sb["failures"]["auth"] == 1
    assert sb["failures"]["not_attempted"] == 149
    assert sb["calls_made"] == 1  # stopped after the fatal failure
    assert all(
        m["verdict"] == cmp.NOT_MEASURED for m in res.evidence["metrics"]
    )
    assert res.exit_code != 0
    assert 'class="v v-CHANGED"' not in res.report_html
    assert "auth" in res.report_html


# --- c8 ------------------------------------------------------------------


def test_c8_temperature_rejected_retried_once_and_stated(tmp_path) -> None:
    def b(item, r, send_temperature):
        if send_temperature:
            return ProviderError("provider HTTP 400", 400)
        return _answer(item)

    fb = _fake(b)
    res = _run(tmp_path, _fake(), fb)
    assert sum(1 for _, t in fb.calls if t) == 1
    assert res.evidence["sides"]["B"]["temperature"] == cmp.TEMP_DEFAULT
    assert res.evidence["sides"]["A"]["temperature"] == cmp.TEMP_ZERO
    assert res.evidence["sides"]["B"]["failures"] == {}
    assert "Side B ran at provider default temperature" in res.report_html
    assert _verdicts(res)["agreement"] == cmp.WITHIN_NOISE


def test_c8b_fallback_failure_is_not_retried_again(tmp_path) -> None:
    fb = _fake(lambda item, r: ProviderError("provider HTTP 400", 400))
    res = _run(tmp_path, _fake(), fb)
    assert sum(1 for _, t in fb.calls if not t) == 1
    assert res.evidence["sides"]["B"]["temperature"] == cmp.TEMP_ZERO
    assert res.evidence["sides"]["B"]["failures"]["bad_request"] == 150


# --- c9 ------------------------------------------------------------------


def test_c9_report_is_offline(tmp_path) -> None:
    def b(item, r):
        return (
            '<img src="https://evil.example/x.png"> see http://tracker.example'
            f' <script src="//cdn.example/a.js"></script> {item.id}'
        )

    res = _run(tmp_path, _fake(), _fake(b))
    page = res.report_html
    refs = re.findall(
        r"""(?:src|href)\s*=\s*["']?((?:https?:)?//[^"'\s>]+)""", page
    )
    assert refs == [cmp.HOMEPAGE]
    lowered = page.lower()
    for bad in ("<script", "<link", "@import", "url(", "<img"):
        assert bad not in lowered, bad
    assert "&lt;img src=" in page  # shown as text, not loaded


# --- c10 + section 8 (network, keys) -------------------------------------


KEY_A = "sk-alphaKEY0123456789abcdef"
KEY_B = "sk-bravoKEY9876543210fedcba"


def _suite_file(tmp_path, n=12, n_json=4):
    lines = []
    for it in _items(n, n_json):
        rec = {"id": it.id, "user": it.user, "expect_json": it.expect_json}
        lines.append(json.dumps(rec))
    path = tmp_path / "suite.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _http_fake(answers):
    seen: list[str] = []

    def transport(url, headers, body, timeout):
        seen.append(url)
        payload = json.loads(body)
        user = payload["messages"][-1]["content"]
        text = answers(urlparse(url).netloc, user)
        answers.produced.append(text)
        return {
            "model": payload["model"],
            "choices": [
                {"message": {"content": text}, "finish_reason": "stop"}
            ],
            "usage": {"completion_tokens": 12},
        }

    transport.seen = seen
    return transport


def _answers():
    def fn(host, user):
        return f"Secret reply from {host} to: {user} -- ends here."

    fn.produced = []
    return fn


def _env():
    return {
        "SEISMOGRAPH_A_BASE_URL": "https://a.example/v1",
        "SEISMOGRAPH_A_API_KEY": KEY_A,
        "SEISMOGRAPH_B_BASE_URL": "https://b.example/v1",
        "SEISMOGRAPH_B_API_KEY": KEY_B,
    }


def _main(tmp_path, monkeypatch, transport, extra=()):
    printed: list[str] = []
    monkeypatch.setattr(providers, "_urllib_transport", transport)
    code = cmp.main(
        [
            "--suite",
            str(_suite_file(tmp_path)),
            "--a",
            "x/model-a",
            "--b",
            "y/model-b",
            "--out",
            str(tmp_path / "run"),
            *extra,
        ],
        env=_env(),
        now=_clock(),
        sleep=lambda s: None,
        out=printed.append,
    )
    return code, printed


def _windows(secret, n=8):
    return {secret[i : i + n] for i in range(len(secret) - n + 1)}


def test_c10_evidence_has_no_prompt_answer_or_key(
    tmp_path, monkeypatch
) -> None:
    answers = _answers()
    code, printed = _main(
        tmp_path, monkeypatch, _http_fake(answers), extra=["--yes"]
    )
    assert code == 0
    ev = (tmp_path / "run" / "evidence.json").read_bytes()
    report = (tmp_path / "run" / "report.html").read_bytes()
    stdout = "\n".join(printed).encode()
    for it in _items(12, 4):
        assert it.user.encode() not in ev
    assert answers.produced
    for text in set(answers.produced):
        assert text.encode() not in ev
    for key in (KEY_A, KEY_B):
        for w in _windows(key):
            for blob in (ev, report, stdout):
                assert w.encode() not in blob
    sha = next(line for line in printed if line.startswith("evidence sha256"))
    import hashlib

    assert hashlib.sha256(ev).hexdigest() in sha


def test_section8_only_configured_hosts_contacted(
    tmp_path, monkeypatch
) -> None:
    import socket

    def no_socket(*a, **k):
        raise AssertionError("a real socket was opened")

    monkeypatch.setattr(socket.socket, "connect", no_socket)
    tr = _http_fake(_answers())
    code, printed = _main(tmp_path, monkeypatch, tr, extra=["--yes"])
    assert code == 0
    progress = [line for line in printed if line.endswith(" calls")]
    assert progress[-1].strip() == "72/72 calls"
    assert 5 <= len(progress) <= 11  # never silent, never flooding
    assert {urlparse(u).netloc for u in tr.seen} == {"a.example", "b.example"}
    assert len(tr.seen) == 12 * 3 * 2


def test_yes_required_before_any_call(tmp_path, monkeypatch) -> None:
    tr = _http_fake(_answers())
    code, printed = _main(tmp_path, monkeypatch, tr)
    assert code == 3
    assert tr.seen == []
    assert any("72 calls" in line for line in printed)


def test_no_text_omits_answers_from_report(tmp_path) -> None:
    def b(item, r):
        return _answer(item) + " Revised."

    res = _run(tmp_path, _fake(), _fake(b), no_text=True)
    assert res.evidence["top_changes"]
    assert "Confidential answer" not in res.report_html


# --- c11 -----------------------------------------------------------------


def test_c11_suite_over_cap_refused(tmp_path, monkeypatch) -> None:
    path = tmp_path / "big.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"id": f"i{i}", "user": f"u{i}"}) for i in range(201)
        ),
        encoding="utf-8",
    )
    with pytest.raises(cmp.SuiteError, match="201 items; the limit is 200"):
        cmp.load_suite(path)
    tr = _http_fake(_answers())
    monkeypatch.setattr(providers, "_urllib_transport", tr)
    printed: list[str] = []
    code = cmp.main(
        ["--suite", str(path), "--a", "x/a", "--b", "y/b", "--yes"],
        env=_env(),
        out=printed.append,
    )
    assert code == 1
    assert tr.seen == []
    assert "Refused, not truncated" in printed[0]


def test_suite_200_items_accepted(tmp_path) -> None:
    path = tmp_path / "ok.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"id": f"i{i}", "user": f"u{i}"}) for i in range(200)
        ),
        encoding="utf-8",
    )
    items, sha = cmp.load_suite(path)
    assert len(items) == 200 and len(sha) == 64


# --- c12 -----------------------------------------------------------------


def _strip_times(raw: bytes) -> dict:
    ev = json.loads(raw)
    ev.pop("started_at")
    ev.pop("finished_at")
    return ev


def test_c12_evidence_reproducible_apart_from_timestamps(tmp_path) -> None:
    def b(item, r):
        return _answer(item) + (" Revised." if item.id < "q010" else "")

    r1 = _run(tmp_path, _fake(_noisy(3)), _fake(b), sub="one")
    r2 = _run(
        tmp_path,
        _fake(_noisy(3)),
        _fake(b),
        sub="two",
        now=_clock(T0 + timedelta(days=3)),
    )
    e1 = (r1.out_dir / "evidence.json").read_bytes()
    e2 = (r2.out_dir / "evidence.json").read_bytes()
    assert e1 != e2  # timestamps differ
    assert json.dumps(_strip_times(e1), sort_keys=True) == json.dumps(
        _strip_times(e2), sort_keys=True
    )
    r3 = _run(tmp_path, _fake(_noisy(3)), _fake(b), sub="three")
    assert (r3.out_dir / "evidence.json").read_bytes() == e1


# --- retries and classification ------------------------------------------


def test_rate_limit_retried_then_succeeds(tmp_path) -> None:
    waits: list[float] = []
    state = {"n": 0}

    def b(item, r):
        state["n"] += 1
        if state["n"] <= 2:
            return ProviderError("provider HTTP 429", 429)
        return _answer(item)

    res = _run(tmp_path, _fake(), _fake(b), sleep=waits.append)
    assert waits == [1.0, 2.0]
    assert res.evidence["sides"]["B"]["failures"] == {}


def test_quota_is_fatal_not_retried(tmp_path) -> None:
    exc = ProviderError(
        "provider HTTP 429", 429, error_code="insufficient_quota"
    )
    fb = _fake(lambda item, r: exc)
    res = _run(tmp_path, _fake(), fb)
    assert len(fb.calls) == 1
    assert res.evidence["sides"]["B"]["failures"]["quota"] == 1


def test_classify_table() -> None:
    def e(status=None, code=None, kind=None):
        return ProviderError("x", status, error_code=code, failure_kind=kind)

    assert cmp.classify(e(401)) == "auth"
    assert cmp.classify(e(403)) == "auth"
    assert cmp.classify(e(402)) == "quota"
    assert cmp.classify(e(429, "insufficient_quota")) == "quota"
    assert cmp.classify(e(429)) == "rate_limit"
    assert cmp.classify(e(503)) == "provider_error"
    assert cmp.classify(e(404)) == "bad_request"
    assert cmp.classify(e(kind="timeout")) == "timeout"
    assert cmp.classify(e(kind="network")) == "network"
    assert cmp.classify(e(kind="bad_schema")) == "provider_error"


def test_few_eligible_items_not_measured(tmp_path) -> None:
    res = _run(tmp_path, _fake(), _fake(), items=_items(50, n_json=3))
    row = next(
        m for m in res.evidence["metrics"] if m["metric"] == "json_valid"
    )
    assert row["verdict"] == cmp.NOT_MEASURED
    tok = next(
        m for m in res.evidence["metrics"] if m["metric"] == "reasoning_tokens"
    )
    assert tok["verdict"] == cmp.NOT_MEASURED


def test_repeats_bounds_enforced(tmp_path) -> None:
    with pytest.raises(ValueError):
        _run(tmp_path, _fake(), _fake(), repeats=1)
    with pytest.raises(ValueError):
        _run(tmp_path, _fake(), _fake(), repeats=cmp.MAX_REPEATS + 1)


# --- property test on the permutation statistic --------------------------


def test_property_permutation_symmetry_and_null_calibration() -> None:
    """Over seeded random datasets:

    1. item_stat is symmetric in A and B;
    2. the mean of t over all label splits of a pooled item is exactly 0
       (the statistic is centred under exchangeability);
    3. identical data per item gives p == 1;
    4. under a true null (A and B from one process) the rate of
       p <= 0.05 stays near 0.05 (bounded at 0.12 over 120 datasets).
    """
    rng = random.Random(20261007)
    dist = cmp._dist_abs
    false_hits = 0
    datasets = 120
    for _ in range(datasets):
        per_item = []
        for _i in range(12):
            mu = rng.uniform(0, 100)
            a = [round(rng.gauss(mu, 5)) for _ in range(3)]
            b = [round(rng.gauss(mu, 5)) for _ in range(3)]
            wa, wb, cr, t = cmp.item_stat(a, b, dist)
            assert cmp.item_stat(b, a, dist) == (wb, wa, cr, t)
            splits = cmp._split_stats(a, b, dist)
            assert abs(sum(splits) / len(splits)) < 1e-9
            per_item.append((a, b))
        p = cmp.permutation_p(per_item, dist, random.Random(1), n_perm=199)
        false_hits += p <= 0.05
        same = [(a, list(a)) for a, _ in per_item]
        if all(len(set(a)) == 1 for a, _ in same):
            assert cmp.permutation_p(same, dist, random.Random(1)) == 1.0
    assert false_hits / datasets <= 0.12
    constant = [([5, 5, 5], [5, 5, 5])] * 6
    assert cmp.permutation_p(constant, dist, random.Random(1)) == 1.0


def test_evidence_records_source_hashes(tmp_path) -> None:
    import hashlib
    from pathlib import Path

    res = _run(tmp_path, _fake(), _fake())
    src = res.evidence["tool"]["source_sha256"]
    here = Path(cmp.__file__).resolve().parent
    assert (
        src["compare.py"]
        == hashlib.sha256((here / "compare.py").read_bytes()).hexdigest()
    )
    assert set(src) == {"compare.py", "providers.py", "canary.py"}
