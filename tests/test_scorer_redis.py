"""
tests.test_scorer_redis
========================
Unit tests for RedisAgreementScorer (FIX-2 ZSET backend).

All tests use unittest.mock.MagicMock for the Redis client -- no live Redis
server required.  These are WIRING/contract tests: they lock down the exact
Redis commands, keys, ms score conversion, and the Lua EVAL signature.  The
behavioural quorum/TTL/scaling logic (which lives in the Lua script) is
mirrored by, and exercised against, the in-process AgreementScorer in
tests/test_agreement_scorer.py; the two backends are drop-in equivalents.

Test inventory
--------------
RS1  ingest -> zadd on both agree and observer keys (change_detected=True)
RS2  ingest change_detected=False -> observer zadd only, no agree zadd
RS3  ingest empty contributing_orgs -> no zadd, no expire
RS4  promote: eval() returns 0 -> None
RS5  promote: eval() returns 3 -> 3
RS6  promote: custom floor forwarded to eval as ARGV
RS7  clear -> delete on the agree key only
RS8  ADVERSARIAL Sybil-replay: same org zadd'd twice; eval still 0 -> None
RS9  key format for agree/observer keys
RS10 ns -> ms score conversion on ingest
RS11 promote uses Lua eval with correct script, numkeys=2, keys, and args
RS12 observe -> zadd on observer key

ENG-1 (T6): the ZSET key names carry suite_version, and the two backends
must return identical verdicts for the T4/T5 scenarios.

RS13 key format includes the suite segment
RS14 ingest/observe/clear target the suite-scoped keys
RS15 promote passes the suite-scoped keys to the SAME Lua script
RS16 T4/T5 verdict parity with the in-process scorer
RS17 ms score domain unchanged by suite scoping (risk R1)
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from engine.correlation import DEFAULT_TTL_NS, ChangePointResult
from engine.scorer_redis import (
    _PROMOTE_LUA_SCRIPT,
    RedisAgreementScorer,
    _agree_key,
    _obs_key,
)

MODEL = "openai/gpt-4o@2025-08"
METRIC = "json_success_rate"
CLIENT_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CLIENT_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
SUITE = "v1.1.0"
SUITE2 = "v2.0.0"
# ENG-1: the ZSET key carries the suite_version segment.  The legacy ""
# bucket therefore renders as an EMPTY segment between model and metric.
AGREE_KEY = f"sg:quorum:{MODEL}::{METRIC}"
OBS_KEY = f"sg:observers:{MODEL}::{METRIC}"
AGREE_KEY_V1 = f"sg:quorum:{MODEL}:{SUITE}:{METRIC}"
OBS_KEY_V1 = f"sg:observers:{MODEL}:{SUITE}:{METRIC}"
AGREE_KEY_V2 = f"sg:quorum:{MODEL}:{SUITE2}:{METRIC}"
TTL_MS = DEFAULT_TTL_NS // 1_000_000


@pytest.fixture()
def mock_redis() -> MagicMock:
    """A MagicMock mimicking a redis.Redis client; eval defaults to 0."""
    client = MagicMock()
    client.eval.return_value = 0
    return client


@pytest.fixture()
def scorer(mock_redis: MagicMock) -> RedisAgreementScorer:
    return RedisAgreementScorer(mock_redis)


def _make_result(
    change_detected: bool = True,
    contributing_orgs: list[str] | None = None,
    metric_name: str = METRIC,
    timestamp_ns: int = 0,
    suite_version: str = "",
) -> ChangePointResult:
    return ChangePointResult(
        model_tuple=MODEL,
        change_detected=change_detected,
        score=7.5,
        threshold=5.0,
        contributing_orgs=(
            contributing_orgs if contributing_orgs is not None else [CLIENT_A]
        ),
        metric_name=metric_name,
        timestamp_ns=timestamp_ns,
        suite_version=suite_version,
    )


def test_redis_scorer_key_format() -> None:
    """RS9: key format is sg:quorum|observers:{mt}:{suite}:{metric}.

    A two-argument call (every pre-ENG-1 call site) still resolves and
    lands in the legacy empty-suite segment.
    """
    assert _agree_key(MODEL, METRIC) == AGREE_KEY
    assert _obs_key(MODEL, METRIC) == OBS_KEY


def test_redis_scorer_ingest_calls_zadd(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS1: change_detected ingest zadds into BOTH agree and observer sets.

    #SG-TRACE: REQ-ENGINE-013 | test: test_redis_scorer_ingest_calls_zadd
    """
    scorer.ingest(_make_result(timestamp_ns=5_000_000))  # 5 ms
    mock_redis.zadd.assert_any_call(OBS_KEY, {CLIENT_A: 5})
    mock_redis.zadd.assert_any_call(AGREE_KEY, {CLIENT_A: 5})


def test_redis_scorer_ingest_not_detected_observer_only(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS2: change_detected=False records an observer but NOT an agree vote."""
    scorer.ingest(_make_result(change_detected=False, timestamp_ns=9_000_000))
    mock_redis.zadd.assert_called_once_with(OBS_KEY, {CLIENT_A: 9})


def test_redis_scorer_ingest_empty_noop(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS3: empty contributing_orgs -> no zadd, no expire."""
    scorer.ingest(_make_result(contributing_orgs=[]))
    mock_redis.zadd.assert_not_called()
    mock_redis.expire.assert_not_called()


def test_redis_scorer_observe_calls_zadd(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS12: observe() zadds the org into the observer set with ms score."""
    scorer.observe(MODEL, METRIC, CLIENT_B, timestamp_ns=12_000_000)
    mock_redis.zadd.assert_called_once_with(OBS_KEY, {CLIENT_B: 12})


def test_redis_scorer_promote_quorum_not_met(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS4: eval() returns 0 -> promote_to_public_alert() returns None."""
    mock_redis.eval.return_value = 0
    assert scorer.promote_to_public_alert(MODEL, METRIC) is None


def test_redis_scorer_promote_quorum_met(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS5: eval() returns 3 -> promote_to_public_alert() returns 3."""
    mock_redis.eval.return_value = 3
    assert scorer.promote_to_public_alert(MODEL, METRIC) == 3


def test_redis_scorer_promote_custom_floor(mock_redis: MagicMock) -> None:
    """RS6: floor override is forwarded to eval as ARGV[2]."""
    scorer5 = RedisAgreementScorer(mock_redis, quorum=5)
    mock_redis.eval.return_value = 0
    assert scorer5.promote_to_public_alert(MODEL, METRIC, now_ns=0) is None
    # eval args: script, numkeys, akey, okey, cutoff, now, floor, fnum, fden
    args = mock_redis.eval.call_args.args
    assert args[0] == _PROMOTE_LUA_SCRIPT
    assert args[1] == 2
    assert args[2] == AGREE_KEY
    assert args[3] == OBS_KEY
    assert args[6] == 5  # floor


def test_redis_scorer_clear_calls_delete(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS7: clear() deletes the agree key only (observers retained)."""
    scorer.clear(MODEL, METRIC)
    mock_redis.delete.assert_called_once_with(AGREE_KEY)


def test_redis_scorer_sybil_replay(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS8 ADVERSARIAL: same org ingested twice; ZSET dedup keeps quorum unmet.

    ZADD of a duplicate member updates its score without adding a new
    member, so the Lua ZCARD stays 1 and eval() returns 0.

    #SG-TRACE: REQ-ENGINE-009 | test: test_redis_scorer_sybil_replay
    """
    mock_redis.eval.return_value = 0
    scorer.ingest(
        _make_result(contributing_orgs=[CLIENT_A], timestamp_ns=3_000_000)
    )
    scorer.ingest(
        _make_result(contributing_orgs=[CLIENT_A], timestamp_ns=4_000_000)
    )
    # Both ingests target the same member; ZSET semantics dedup (ZCARD=1).
    assert call(AGREE_KEY, {CLIENT_A: 3}) in mock_redis.zadd.call_args_list
    assert call(AGREE_KEY, {CLIENT_A: 4}) in mock_redis.zadd.call_args_list
    assert scorer.promote_to_public_alert(MODEL, METRIC) is None


def test_redis_scorer_ns_to_ms(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS10: ns event-time is floored to ms in the ZSET score."""
    scorer.ingest(_make_result(timestamp_ns=1_699_999_999))  # -> 1699 ms
    mock_redis.zadd.assert_any_call(AGREE_KEY, {CLIENT_A: 1699})


def test_redis_scorer_promote_uses_lua_eval(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS11: promote() calls eval() with the exact script, numkeys, keys, args.

    now_ns=0 makes the cutoff deterministic: 0 - TTL_MS.

    #SG-TRACE: REQ-ENGINE-011 | test: test_redis_scorer_promote_uses_lua_eval
    """
    mock_redis.eval.return_value = 3
    scorer.promote_to_public_alert(MODEL, METRIC, now_ns=0)
    mock_redis.eval.assert_called_once_with(
        _PROMOTE_LUA_SCRIPT,
        2,
        AGREE_KEY,
        OBS_KEY,
        0 - TTL_MS,  # cutoff
        0,  # now_ms
        3,  # floor (default QUORUM_FLOOR)
        1,  # frac_num
        3,  # frac_den (FIX-2b: ceil(M/3) Seismo bound; was 2)
    )
    mock_redis.scard.assert_not_called()
    mock_redis.delete.assert_not_called()


def test_redis_scorer_ingest_multiple_orgs(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """Two distinct orgs -> agree zadd called for each."""
    scorer.ingest(
        _make_result(
            contributing_orgs=[CLIENT_A, CLIENT_B], timestamp_ns=7_000_000
        )
    )
    assert call(AGREE_KEY, {CLIENT_A: 7}) in mock_redis.zadd.call_args_list
    assert call(AGREE_KEY, {CLIENT_B: 7}) in mock_redis.zadd.call_args_list


# ---------------------------------------------------------------------------
# ENG-1 / T6 -- suite-scoped ZSET keys, identical Lua, identical verdicts
# ---------------------------------------------------------------------------


def test_redis_scorer_suite_key_format() -> None:
    """RS13: suite_version is a key segment on both ZSETs.

    #SG-TRACE: REQ-ENGSCOPE-006 | test: test_redis_scorer_suite_key_format
    """
    assert _agree_key(MODEL, METRIC, SUITE) == AGREE_KEY_V1
    assert _obs_key(MODEL, METRIC, SUITE) == OBS_KEY_V1
    # Distinct suites -> distinct keys; no bucket can alias another.
    assert _agree_key(MODEL, METRIC, SUITE) != _agree_key(
        MODEL, METRIC, SUITE2
    )
    assert _agree_key(MODEL, METRIC, SUITE) != _agree_key(MODEL, METRIC)


def test_redis_scorer_suite_scoped_ingest(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS14: ingest zadds into the suite-scoped agree AND observer keys.

    #SG-TRACE: REQ-ENGSCOPE-006 | test: test_redis_scorer_suite_scoped_ingest
    """
    scorer.ingest(_make_result(timestamp_ns=5_000_000, suite_version=SUITE))
    mock_redis.zadd.assert_any_call(OBS_KEY_V1, {CLIENT_A: 5})
    mock_redis.zadd.assert_any_call(AGREE_KEY_V1, {CLIENT_A: 5})
    # Nothing was written to the legacy bucket.
    assert call(AGREE_KEY, {CLIENT_A: 5}) not in mock_redis.zadd.call_args_list


def test_redis_scorer_suite_scoped_observe(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS14: observe() targets the suite-scoped observer key."""
    scorer.observe(
        MODEL, METRIC, CLIENT_B, timestamp_ns=12_000_000, suite_version=SUITE
    )
    mock_redis.zadd.assert_called_once_with(OBS_KEY_V1, {CLIENT_B: 12})


def test_redis_scorer_suite_scoped_clear(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS14: clear() deletes only the requested suite's agree key."""
    scorer.clear(MODEL, METRIC, SUITE2)
    mock_redis.delete.assert_called_once_with(AGREE_KEY_V2)


def test_redis_scorer_suite_scoped_promote_eval_args(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS15: promote() passes suite-scoped KEYS to the UNCHANGED Lua script.

    The script body, numkeys=2 atomicity, and the ms-domain cutoff/now args
    are byte-identical to FIX-2 -- only the two key names moved (risk R1).

    #SG-TRACE: REQ-ENGSCOPE-006
    #   | test: test_redis_scorer_suite_scoped_promote_eval_args
    """
    mock_redis.eval.return_value = 3
    scorer.promote_to_public_alert(
        MODEL, METRIC, now_ns=0, suite_version=SUITE
    )
    mock_redis.eval.assert_called_once_with(
        _PROMOTE_LUA_SCRIPT,
        2,
        AGREE_KEY_V1,
        OBS_KEY_V1,
        0 - TTL_MS,  # cutoff, still milliseconds
        0,  # now_ms
        3,  # floor (unchanged)
        1,  # frac_num (unchanged)
        3,  # frac_den (unchanged)
    )


def test_redis_scorer_suite_scoped_ns_to_ms(
    scorer: RedisAgreementScorer, mock_redis: MagicMock
) -> None:
    """RS17: scores stay in MILLISECONDS under suite scoping (risk R1).

    ZSET scores and Lua numbers are IEEE-754 doubles (2**53); a nanosecond
    wall-clock (~1.7e18) would lose precision.  A realistic ns event-time
    must still arrive as a ms integer well inside the safe range.

    #SG-TRACE: REQ-ENGSCOPE-006
    #   | test: test_redis_scorer_suite_scoped_ns_to_ms
    """
    ts_ns = 1_785_000_000_123_456_789  # ~2026 wall-clock, in ns
    scorer.ingest(_make_result(timestamp_ns=ts_ns, suite_version=SUITE))
    expected_ms = ts_ns // 1_000_000
    mock_redis.zadd.assert_any_call(AGREE_KEY_V1, {CLIENT_A: expected_ms})
    assert expected_ms < 2**53


def test_redis_scorer_t4_t5_verdict_parity(mock_redis: MagicMock) -> None:
    """RS16: T4/T5 verdicts match the in-process scorer, per suite bucket.

    The quorum arithmetic lives in Lua, so the mock replays what a real
    Redis would return for each bucket's member count; what this test locks
    down is that the backend asks the question about the RIGHT key -- the
    v1 bucket (2 orgs) and the v2 bucket (1 org) are addressed separately,
    exactly as ``AgreementScorer`` buckets them.

    #SG-TRACE: REQ-ENGSCOPE-006 | test: test_redis_scorer_t4_t5_verdict_parity
    """
    scorer = RedisAgreementScorer(mock_redis)
    ts = 5_000_000
    scorer.ingest(
        _make_result(
            contributing_orgs=[CLIENT_A], timestamp_ns=ts, suite_version=SUITE
        )
    )
    scorer.ingest(
        _make_result(
            contributing_orgs=[CLIENT_B], timestamp_ns=ts, suite_version=SUITE
        )
    )
    scorer.ingest(
        _make_result(
            contributing_orgs=[CLIENT_A], timestamp_ns=ts, suite_version=SUITE2
        )
    )

    # T4: split population -- Redis reports sub-quorum for both buckets.
    mock_redis.eval.return_value = 0
    assert (
        scorer.promote_to_public_alert(MODEL, METRIC, suite_version=SUITE)
        is None
    )
    assert (
        scorer.promote_to_public_alert(MODEL, METRIC, suite_version=SUITE2)
        is None
    )
    evaluated_keys = [c.args[2] for c in mock_redis.eval.call_args_list]
    assert evaluated_keys == [AGREE_KEY_V1, AGREE_KEY_V2]

    # T5: all three orgs in one bucket -- that bucket promotes with 3.
    mock_redis.eval.reset_mock()
    mock_redis.eval.return_value = 3
    assert (
        scorer.promote_to_public_alert(MODEL, METRIC, suite_version=SUITE2)
        == 3
    )
    assert mock_redis.eval.call_args.args[2] == AGREE_KEY_V2
