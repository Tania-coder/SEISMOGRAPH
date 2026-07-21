"""
seismograph.engine.scorer_redis
================================
Redis-backed cross-observer agreement scorer for distributed quorum tracking.

Redis-backed twin of ``engine.correlation.AgreementScorer`` so that multiple
gateway instances can coordinate quorum state without all traffic hitting a
single node.  Implements the same FIX-2 semantics as the in-process scorer:

1. **Metric-scoped agreement.**  Each stream is keyed by
   ``(model_tuple, metric_name)``.  Two orgs drifting on different metrics of
   the same model do not agree.

2. **Per-candidate TTL.**  Agreement and observer state are Redis Sorted Sets
   scored by event-time.  A candidate counts only while its score is within
   ``ttl`` of the evaluation time; the promotion Lua script prunes stale
   members (``ZREMRANGEBYSCORE``) before counting.  This replaces the coarse
   Phase 2 set-level ``EXPIRE`` (which re-armed a single 24h window on the
   whole set and never expired individual members).

3. **Population-scaled quorum.**  The required quorum is
   ``max(floor, ceil(frac_num * M / frac_den))`` where M is the distinct live
   observer population for the stream.  A fixed absolute threshold is trivially
   met as the network grows (EXP-2: fixed quorum=2 -> 0.86 stable-window FP at
   M=5); q(M) holds the boundary.

Timestamp precision
-------------------
Sorted-set scores and Redis Lua numbers are IEEE-754 doubles (53-bit integer
mantissa, ~9.0e15).  Wall-clock nanoseconds (~1.7e18) exceed that and would
lose precision, so this backend stores event-time in **milliseconds**
(``ns // 1_000_000``, ~1.7e12).  The public interface still speaks
nanoseconds; conversion is internal.

Atomic promotion (P3-003 fix for KNOWN-LIMIT-003, preserved)
------------------------------------------------------------
``promote_to_public_alert()`` executes ``_PROMOTE_LUA_SCRIPT`` via ``EVAL``.
The Lua script atomically prunes stale members, checks the agreeing count
against the population-scaled quorum, and (on promotion) deletes the agreeing
set -- all in one single-threaded Redis operation, so two gateway nodes can
never both promote the same drift event.  Observer state is retained across a
promotion (those orgs are still watching).

Privacy invariants
------------------
* Redis keys ``sg:quorum:{mt}:{metric}`` and ``sg:observers:{mt}:{metric}``
  are derived from public identifiers only.  No raw prompts, outputs, or org
  secrets appear in any key or value.
* Members are pseudonymous Ed25519 public-key fingerprints bound at probe
  installation time.  The store never receives a private key or cleartext org
  identity.

Interface conformance
---------------------
``RedisAgreementScorer`` mirrors ``AgreementScorer``:
  ``observe(mt, metric, org, ts)``       -- record an observer (population M)
  ``ingest(result)``                     -- record one change-point candidate
  ``promote_to_public_alert(mt, metric)``-- return org count or None (atomic)
  ``clear(mt, metric)``                  -- evict agreeing candidates (stream)

Gateway code can switch implementations via the ``QUORUM_BACKEND`` env var
without any changes to the calling code in gateway/main.py.

#SG-TRACE: REQ-ENGINE-009
#   | assumption: injected redis_client exposes zadd, expire, eval, delete;
#     Ed25519 verification upstream prevents fabricated org_id injection
#   | test: test_redis_scorer_ingest_calls_zadd
#SG-TRACE: REQ-ENGINE-013
#   | assumption: per-member ZSET scores (event-time ms) + Lua
#     ZREMRANGEBYSCORE pruning realise per-candidate TTL; ms keeps scores
#     within IEEE-754 double precision
#   | test: test_redis_scorer_promote_prunes_and_scales
#SG-TRACE: REQ-ENGINE-011
#   | assumption: Lua EVAL atomicity eliminates the prune/check/DEL race in
#     multi-node deployments; Redis guarantees single-threaded Lua
#   | test: test_redis_scorer_promote_uses_lua_eval
"""

from __future__ import annotations

from typing import Any

from engine.correlation import (
    DEFAULT_TTL_NS,
    QUORUM_FLOOR,
    QUORUM_FRAC_DEN,
    QUORUM_FRAC_NUM,
    ChangePointResult,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AGREE_PREFIX: str = "sg:quorum"
_OBS_PREFIX: str = "sg:observers"
_NS_PER_MS: int = 1_000_000

# ---------------------------------------------------------------------------
# Lua script: atomic prune + population-scaled quorum check + delete
# ---------------------------------------------------------------------------
# KEYS[1] = agreeing sorted set   KEYS[2] = observer sorted set
# ARGV[1] = cutoff (ms; members with score < cutoff are expired)
# ARGV[2] = now (ms; members are counted only while score <= now)
# ARGV[3] = quorum floor
# ARGV[4] = frac_num             ARGV[5] = frac_den
#
# Prunes stale members from both sets, counts live members in [cutoff, now],
# computes M = max(observers, agreeing),
# derives q(M) = max(floor, ceil(frac_num*M/frac_den)); if the agreeing count
# meets q(M) it DELs the agreeing set and returns the count, else returns 0.
# Observer state is left intact.  All in one atomic Lua pass.
#
# #SG-TRACE: REQ-ENGINE-011
# #   | assumption: single-threaded Lua; no command observes the sets
# #     between prune, check, and DEL
# #   | test: test_redis_scorer_promote_uses_lua_eval
_PROMOTE_LUA_SCRIPT: str = """
local akey   = KEYS[1]
local okey   = KEYS[2]
local cutoff = tonumber(ARGV[1])
local now    = tonumber(ARGV[2])
local floor  = tonumber(ARGV[3])
local fnum   = tonumber(ARGV[4])
local fden   = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', akey, '-inf', '(' .. cutoff)
redis.call('ZREMRANGEBYSCORE', okey, '-inf', '(' .. cutoff)
local agree = redis.call('ZCOUNT', akey, cutoff, now)
if agree == 0 then
    return 0
end
local pop = redis.call('ZCOUNT', okey, cutoff, now)
if agree > pop then
    pop = agree
end
local scaled = math.floor((fnum * pop + fden - 1) / fden)
local q = floor
if scaled > q then
    q = scaled
end
if agree >= q then
    redis.call('DEL', akey)
    return agree
end
return 0
"""


def _agree_key(model_tuple: str, metric_name: str) -> str:
    """Redis key for the agreeing-candidate sorted set of a stream."""
    return f"{_AGREE_PREFIX}:{model_tuple}:{metric_name}"


def _obs_key(model_tuple: str, metric_name: str) -> str:
    """Redis key for the observer-population sorted set of a stream."""
    return f"{_OBS_PREFIX}:{model_tuple}:{metric_name}"


# ---------------------------------------------------------------------------
# RedisAgreementScorer
# ---------------------------------------------------------------------------


class RedisAgreementScorer:
    """Redis-backed cross-observer quorum gate (FIX-2 semantics).

    Drop-in replacement for ``engine.correlation.AgreementScorer`` storing
    quorum and observer state in Redis Sorted Sets keyed per
    ``(model_tuple, metric_name)``.  Gateway restarts no longer wipe pending
    quorum state, and multiple gateway nodes share one view.

    Attributes:
        floor: Minimum quorum q(M) regardless of population size.

    #SG-TRACE: REQ-ENGINE-013
    #   | assumption: injected redis_client is a connected redis.Redis (or
    #     compatible mock) exposing zadd, expire, eval, delete
    #   | test: test_redis_scorer_ingest_calls_zadd
    """

    QUORUM_MIN: int = QUORUM_FLOOR  # 3 (FIX-2 floor)

    def __init__(
        self,
        redis_client: Any,
        quorum: int | None = None,
        ttl_ns: int = DEFAULT_TTL_NS,
        frac_num: int = QUORUM_FRAC_NUM,
        frac_den: int = QUORUM_FRAC_DEN,
    ) -> None:
        """Initialise the Redis-backed scorer.

        Args:
            redis_client: A connected ``redis.Redis`` (or any object exposing
                ``zadd``, ``expire``, ``eval``, ``delete``).  Injected so tests
                can supply a ``MagicMock`` without a live server.
            quorum: Override for the quorum FLOOR.  Defaults to QUORUM_FLOOR
                (3) if None.
            ttl_ns: Candidate/observer expiry window in nanoseconds
                (default 14 days).  Stored internally as milliseconds.
            frac_num: Numerator of the proportional quorum term.
            frac_den: Denominator of the proportional quorum term.
        """
        self._redis = redis_client
        self.floor: int = quorum if quorum is not None else QUORUM_FLOOR
        self.ttl_ms: int = ttl_ns // _NS_PER_MS
        self.frac_num: int = frac_num
        self.frac_den: int = frac_den
        # GC backstop: fully idle streams self-evict after 2x the TTL.
        self._backstop_s: int = max(1, 2 * ttl_ns // 1_000_000_000)

    @property
    def quorum(self) -> int:
        """Backward-compatible alias: the scaled-quorum floor."""
        return self.floor

    @staticmethod
    def _now_ms() -> int:
        """Wall-clock event-time in milliseconds."""
        import time

        return time.time_ns() // _NS_PER_MS

    def _stamp_ms(self, timestamp_ns: int | None) -> int:
        """Convert an optional ns event-time to ms, defaulting to now."""
        if timestamp_ns:
            return timestamp_ns // _NS_PER_MS
        return self._now_ms()

    # ------------------------------------------------------------------
    # Public interface (mirrors AgreementScorer)
    # ------------------------------------------------------------------

    def observe(
        self,
        model_tuple: str,
        metric_name: str,
        org_id: str,
        timestamp_ns: int | None = None,
    ) -> None:
        """Record that ``org_id`` is watching this stream (population M).

        ``ZADD``s the org into the observer sorted set with an event-time
        (ms) score and re-arms the GC backstop TTL.

        #SG-TRACE: REQ-ENGINE-012
        #   | test: test_redis_scorer_observe_calls_zadd
        """
        ts = self._stamp_ms(timestamp_ns)
        okey = _obs_key(model_tuple, metric_name)
        self._redis.zadd(okey, {org_id: ts})
        self._redis.expire(okey, self._backstop_s)

    def ingest(self, result: ChangePointResult) -> None:
        """Record a change-point candidate from one or more orgs.

        For each org in ``result.contributing_orgs``:

        1. ``ZADD sg:observers:{mt}:{metric} {org: ts_ms}`` -- the org is an
           observer of the stream.
        2. If ``result.change_detected``:
           ``ZADD sg:quorum:{mt}:{metric} {org: ts_ms}`` -- and an agreeing
           candidate.

        Sorted-set semantics deduplicate on member: re-ingesting the same
        org updates its score, never inflating cardinality (Sybil-replay
        resistance).  Both keys get the GC backstop TTL re-armed.

        Args:
            result: A ``ChangePointResult`` with model_tuple, metric_name,
                contributing_orgs, and optional timestamp_ns.

        #SG-TRACE: REQ-ENGINE-009
        #   | assumption: empty contributing_orgs is a no-op
        #   | test: test_redis_scorer_ingest_empty_contributing_orgs_noop
        """
        if not result.contributing_orgs:
            return
        ts = self._stamp_ms(result.timestamp_ns)
        akey = _agree_key(result.model_tuple, result.metric_name)
        okey = _obs_key(result.model_tuple, result.metric_name)
        for org_id in result.contributing_orgs:
            self._redis.zadd(okey, {org_id: ts})
            if result.change_detected:
                self._redis.zadd(akey, {org_id: ts})
        self._redis.expire(okey, self._backstop_s)
        if result.change_detected:
            self._redis.expire(akey, self._backstop_s)

    def promote_to_public_alert(
        self,
        model_tuple: str,
        metric_name: str = "",
        now_ns: int | None = None,
    ) -> int | None:
        """Atomically prune, check population-scaled quorum, and promote.

        Executes ``_PROMOTE_LUA_SCRIPT`` via ``EVAL`` with the agreeing and
        observer keys and the ms cutoff/policy args.  The script prunes
        stale members, computes q(M), and (if met) deletes the agreeing set
        and returns the count.

        Args:
            model_tuple: Composite model identifier to evaluate.
            metric_name: Metric stream to evaluate.
            now_ns: Event-time reference for TTL; defaults to now.

        Returns:
            int count of distinct live agreeing orgs if >= q(M), else None.

        #SG-TRACE: REQ-ENGINE-011
        #   | test: test_redis_scorer_promote_uses_lua_eval
        """
        now_ms = self._now_ms() if now_ns is None else now_ns // _NS_PER_MS
        cutoff = now_ms - self.ttl_ms
        akey = _agree_key(model_tuple, metric_name)
        okey = _obs_key(model_tuple, metric_name)
        result: int = self._redis.eval(
            _PROMOTE_LUA_SCRIPT,
            2,
            akey,
            okey,
            cutoff,
            now_ms,
            self.floor,
            self.frac_num,
            self.frac_den,
        )
        return result if result else None

    def clear(self, model_tuple: str, metric_name: str = "") -> None:
        """Delete the agreeing-candidate set for a stream.

        Observer state is retained.  After a successful atomic promotion the
        agreeing key is already gone; ``clear()`` is then a safe idempotent
        no-op (Redis DEL on a missing key returns 0).

        #SG-TRACE: REQ-ENGINE-009
        #   | test: test_redis_scorer_clear_calls_delete
        """
        self._redis.delete(_agree_key(model_tuple, metric_name))
