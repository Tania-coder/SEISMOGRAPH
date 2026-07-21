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
AGREE_KEY = f"sg:quorum:{MODEL}:{METRIC}"
OBS_KEY = f"sg:observers:{MODEL}:{METRIC}"
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
    )


def test_redis_scorer_key_format() -> None:
    """RS9: agree/observer key format is sg:quorum|observers:{mt}:{metric}."""
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
        2,  # frac_den
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
