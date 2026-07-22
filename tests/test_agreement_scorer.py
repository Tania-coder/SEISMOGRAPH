"""
tests.test_agreement_scorer
===========================
Behavioural + adversarial tests for the in-process AgreementScorer (FIX-2).

This file carries the quorum/TTL/scaling LOGIC coverage for the correlation
layer (the Redis backend in tests/test_scorer_redis.py is a wiring mirror of
the same semantics).  It exercises all three FIX-2 gaps and both Constitution
adversarial cases:

  G1  metric-scoped agreement          -- test_metric_scoped_*
  G2  per-candidate TTL expiry         -- test_ttl_*
  G3  population-scaled quorum q(M)     -- test_required_quorum_scaling,
                                          test_quorum_scales_with_population
  ADV-a Sybil / fabricated orgs        -- test_sybil_*
  ADV-b semantic-only cross-org shift  -- test_semantic_only_shift_promotes

#SG-TRACE: REQ-ENGINE-012
#SG-TRACE: REQ-ENGINE-013
"""

from __future__ import annotations

from engine.correlation import (
    QUORUM_FLOOR,
    AgreementScorer,
    ChangePointResult,
    required_quorum,
)

MODEL = "anthropic/claude-sonnet-4@global"
M1 = "json_success_rate"
M2 = "avg_output_length"

DAY_NS = 86_400 * 1_000_000_000


def _cp(
    org: str,
    metric: str = M1,
    ts_ns: int = 0,
    change_detected: bool = True,
) -> ChangePointResult:
    return ChangePointResult(
        model_tuple=MODEL,
        change_detected=change_detected,
        score=7.5,
        threshold=5.0,
        contributing_orgs=[org],
        metric_name=metric,
        timestamp_ns=ts_ns,
    )


# ---------------------------------------------------------------------------
# G3 -- required_quorum(M) policy
# ---------------------------------------------------------------------------


def test_required_quorum_scaling() -> None:
    """q(M) = max(3, ceil(M/3)) -- FIX-2b Seismo bound; floor holds to M=9.

    #SG-TRACE: REQ-ENGINE-012 | test: test_required_quorum_scaling
    """
    assert required_quorum(0) == 3
    assert required_quorum(1) == 3
    assert required_quorum(3) == 3  # ceil(3/3)=1 -> floor 3
    assert required_quorum(6) == 3  # ceil(6/3)=2 -> floor 3
    assert required_quorum(7) == 3  # ceil(7/3)=3
    assert required_quorum(9) == 3  # ceil(9/3)=3 -- flat to here
    assert required_quorum(10) == 4  # ceil(10/3)=4 > floor -- knee
    assert required_quorum(12) == 4
    assert required_quorum(13) == 5  # ceil(13/3)=5
    assert required_quorum(15) == 5
    assert required_quorum(20) == 7  # ceil(20/3)=7 (was 10 under ceil(M/2))
    assert required_quorum(-5) == 3  # negatives clamp to 0
    # Floor override
    assert required_quorum(2, floor=2) == 2
    assert required_quorum(1, floor=2) == 2
    # frac_den override recovers the legacy ceil(M/2) shape
    assert required_quorum(7, frac_den=2) == 4


def test_floor_default_is_three() -> None:
    """The default scorer floor is QUORUM_FLOOR (3), not the legacy 2."""
    assert AgreementScorer().quorum == QUORUM_FLOOR == 3


# ---------------------------------------------------------------------------
# Single-org invariant
# ---------------------------------------------------------------------------


def test_single_org_never_promotes() -> None:
    """One org, replayed many times, never reaches quorum.

    #SG-TRACE: REQ-ENGINE-008 | test: test_agreement_scorer_single_org_blocked
    """
    s = AgreementScorer()
    for i in range(50):
        s.ingest(_cp("org-a", ts_ns=i * DAY_NS))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=50 * DAY_NS) is None


# ---------------------------------------------------------------------------
# G1 -- metric-scoped agreement
# ---------------------------------------------------------------------------


def test_metric_scoped_same_metric_promotes() -> None:
    """Three orgs agreeing on the SAME metric promote; other metric does not.

    #SG-TRACE: REQ-ENGINE-012 | test: test_agreement_scorer_metric_scoped
    """
    s = AgreementScorer()
    now = 10 * DAY_NS
    for org in ("a", "b", "c"):
        # each org observes both metrics but only drifts on M1
        s.observe(MODEL, M2, org, timestamp_ns=now)
        s.ingest(_cp(org, metric=M1, ts_ns=now))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) == 3
    assert s.promote_to_public_alert(MODEL, M2, now_ns=now) is None


def test_metric_scoped_split_metrics_block() -> None:
    """Orgs drifting on DIFFERENT metrics do not form a quorum on either."""
    s = AgreementScorer()
    now = 5 * DAY_NS
    s.ingest(_cp("a", metric=M1, ts_ns=now))
    s.ingest(_cp("b", metric=M2, ts_ns=now))
    s.ingest(_cp("c", metric=M1, ts_ns=now))  # M1: {a, c} = 2
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) is None
    assert s.promote_to_public_alert(MODEL, M2, now_ns=now) is None


# ---------------------------------------------------------------------------
# G2 -- candidate TTL expiry
# ---------------------------------------------------------------------------


def test_ttl_expired_candidates_do_not_count() -> None:
    """A stale candidate (older than TTL) does not count toward quorum.

    Three orgs would meet the floor, but one fired long ago and has expired.

    #SG-TRACE: REQ-ENGINE-013 | test: test_agreement_scorer_ttl_expiry
    """
    ttl = 14 * DAY_NS
    s = AgreementScorer(ttl_ns=ttl)
    s.ingest(_cp("a", ts_ns=1 * DAY_NS))
    s.ingest(_cp("b", ts_ns=30 * DAY_NS))
    s.ingest(_cp("c", ts_ns=30 * DAY_NS))
    # now = day 30: cutoff = day 16; org-a (day 1) has expired -> only {b, c}
    assert s.promote_to_public_alert(MODEL, M1, now_ns=30 * DAY_NS) is None


def test_ttl_within_window_promotes() -> None:
    """Three candidates inside the TTL window promote."""
    ttl = 14 * DAY_NS
    s = AgreementScorer(ttl_ns=ttl)
    for org in ("a", "b", "c"):
        s.ingest(_cp(org, ts_ns=20 * DAY_NS))
    # cutoff = day 6; all three at day 20 are live
    assert s.promote_to_public_alert(MODEL, M1, now_ns=20 * DAY_NS) == 3


def test_ttl_prevents_slow_coincidence() -> None:
    """Orgs firing weeks apart never coincide within one TTL window."""
    ttl = 7 * DAY_NS
    s = AgreementScorer(ttl_ns=ttl)
    s.ingest(_cp("a", ts_ns=1 * DAY_NS))
    s.ingest(_cp("b", ts_ns=20 * DAY_NS))
    s.ingest(_cp("c", ts_ns=40 * DAY_NS))
    for now in (1 * DAY_NS, 20 * DAY_NS, 40 * DAY_NS):
        assert s.promote_to_public_alert(MODEL, M1, now_ns=now) is None


# ---------------------------------------------------------------------------
# G3 -- population-scaled quorum end-to-end
# ---------------------------------------------------------------------------


def test_quorum_scales_with_population() -> None:
    """3 agreeing orgs promote at M=3 but NOT at M=10 (q rises to 4).

    FIX-2b: under the ceil(M/3) schedule the knee is at M=10 (q(9)=3,
    q(10)=4), not M=7 -- the near-term horizon stays at the floor.

    #SG-TRACE: REQ-ENGINE-012
    #   | test: test_agreement_scorer_quorum_scales_with_population
    """
    now = DAY_NS
    # Small network: 3 observers, all 3 agree -> q(3)=3 -> promote.
    small = AgreementScorer()
    for org in ("a", "b", "c"):
        small.ingest(_cp(org, ts_ns=now))
    assert small.promote_to_public_alert(MODEL, M1, now_ns=now) == 3

    # Near-term still flat: 9 observers, only 3 agree -> q(9)=3 -> promote.
    mid = AgreementScorer()
    for i in range(9):
        mid.observe(MODEL, M1, f"obs-{i}", timestamp_ns=now)
    for org in ("obs-0", "obs-1", "obs-2"):
        mid.ingest(_cp(org, ts_ns=now))
    assert mid.promote_to_public_alert(MODEL, M1, now_ns=now) == 3

    # Large network: 10 observers, only 3 agree -> q(10)=4 -> no promote.
    large = AgreementScorer()
    for i in range(10):
        large.observe(MODEL, M1, f"obs-{i}", timestamp_ns=now)
    for org in ("obs-0", "obs-1", "obs-2"):
        large.ingest(_cp(org, ts_ns=now))
    assert large.promote_to_public_alert(MODEL, M1, now_ns=now) is None
    # A fourth agreeing org meets q(10)=4.
    large.ingest(_cp("obs-3", ts_ns=now))
    assert large.promote_to_public_alert(MODEL, M1, now_ns=now) == 4


def test_promotion_clears_candidates_keeps_observers() -> None:
    """After promotion the agree set clears; observers persist (no re-fire)."""
    now = DAY_NS
    s = AgreementScorer()
    for org in ("a", "b", "c"):
        s.ingest(_cp(org, ts_ns=now))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) == 3
    # Immediately after, the candidates are gone; a lone new org can't re-fire.
    s.ingest(_cp("d", ts_ns=now))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) is None


# ---------------------------------------------------------------------------
# ADV-b -- semantic-only provider shift MUST promote (no over-tightening)
# ---------------------------------------------------------------------------


def test_semantic_only_shift_promotes() -> None:
    """A pure semantic shift seen by >= floor honest orgs within TTL promotes.

    Guards against over-tightening the quorum into false negatives: the
    detector fires on json_success_rate with no latency/uptime signal, three
    independent honest orgs agree within the window, and the alert surfaces.

    #SG-TRACE: REQ-ENGINE-012 | test: test_semantic_only_shift_promotes
    """
    ttl = 14 * DAY_NS
    s = AgreementScorer(ttl_ns=ttl)
    base = 5 * DAY_NS
    # three honest orgs fire within a few days of each other
    s.ingest(_cp("honest-1", ts_ns=base))
    s.ingest(_cp("honest-2", ts_ns=base + 2 * DAY_NS))
    s.ingest(_cp("honest-3", ts_ns=base + 4 * DAY_NS))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=base + 4 * DAY_NS) == 3


# ---------------------------------------------------------------------------
# ADV-a -- Sybil / fabricated-org resistance
# ---------------------------------------------------------------------------


def test_sybil_single_identity_cannot_manufacture_quorum() -> None:
    """One Sybil org replaying daily never reaches the floor alone.

    The scorer deduplicates by org_id; a single controlled identity is one
    vote no matter how many candidates it emits.  (Forging DISTINCT org_ids
    is prevented upstream by Ed25519 one-org-one-key binding, not here.)

    #SG-TRACE: REQ-ENGINE-009 | test: test_sybil_single_identity
    """
    s = AgreementScorer()
    for day in range(90):
        s.ingest(_cp("org-sybil", ts_ns=day * DAY_NS))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=90 * DAY_NS) is None


def test_sybil_observer_inflation_does_not_promote() -> None:
    """A Sybil inflating the observer population only RAISES q (defensive).

    Fabricated observer heartbeats increase M, which increases q(M), making
    promotion strictly harder -- never a promotion attack.  With one real
    agreeing org and many fake observers, no alert surfaces.
    """
    now = DAY_NS
    s = AgreementScorer()
    for i in range(20):
        s.observe(MODEL, M1, f"sybil-obs-{i}", timestamp_ns=now)
    s.ingest(_cp("honest-1", ts_ns=now))
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) is None


def test_sybil_plus_two_honest_below_floor() -> None:
    """Sybil (1 identity) + 2 honest false alarms = 3 votes? No -- 3 distinct.

    If the Sybil controls exactly one org_id, it contributes one vote; with
    two honest false alarms that is 3 distinct orgs and DOES meet floor 3.
    This test documents the residual: at exactly the floor, one Sybil plus
    (floor-1) honest coincidences can promote -- the known unweighted-quorum
    residual (EXP-2 C2), mitigated by Ed25519 binding + future reputation,
    NOT by this layer.  We assert the honest-only counterfactual to show the
    Sybil is the marginal vote.
    """
    now = DAY_NS
    # honest-only: 2 orgs, below floor -> no promote
    honest = AgreementScorer()
    honest.ingest(_cp("h1", ts_ns=now))
    honest.ingest(_cp("h2", ts_ns=now))
    assert honest.promote_to_public_alert(MODEL, M1, now_ns=now) is None
    # + 1 Sybil identity -> 3 distinct -> promotes (documented residual)
    honest.ingest(_cp("org-sybil", ts_ns=now))
    assert honest.promote_to_public_alert(MODEL, M1, now_ns=now) == 3
