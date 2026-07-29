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

ENG-1 extends the bucket key to (model_tuple, suite_version, metric_name):

  T3    legacy no-suite construction   -- test_legacy_changepointresult_*
  T4    3 orgs split v1.1.0/v1.1.0/v2.0.0 -> neither bucket promotes
                                       -- test_three_orgs_split_suites_*
  T5    same 3 orgs, all on v2.0.0 -> promotes with org_count=3
                                       -- test_three_orgs_same_suite_promote
  T9    q(M) schedule unchanged under the new key
                                       -- test_quorum_schedule_unchanged_*
  ADV-1 one org fanning candidates across 6 fabricated suites
                                       -- test_adv1_sybil_suite_fanout_*

#SG-TRACE: REQ-ENGINE-012
#SG-TRACE: REQ-ENGINE-013
#SG-TRACE: REQ-ENGSCOPE-004
#SG-TRACE: REQ-ENGSCOPE-005
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
V1 = "v1.1.0"
V2 = "v2.0.0"

DAY_NS = 86_400 * 1_000_000_000


def _cp(
    org: str,
    metric: str = M1,
    ts_ns: int = 0,
    change_detected: bool = True,
    suite: str = "",
) -> ChangePointResult:
    return ChangePointResult(
        model_tuple=MODEL,
        change_detected=change_detected,
        score=7.5,
        threshold=5.0,
        contributing_orgs=[org],
        metric_name=metric,
        timestamp_ns=ts_ns,
        suite_version=suite,
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


# ---------------------------------------------------------------------------
# ENG-1 / T3 -- backward compatibility of the legacy bucket
# ---------------------------------------------------------------------------


def test_legacy_changepointresult_lands_in_empty_suite_bucket() -> None:
    """T3: a ChangePointResult built with legacy kwargs still works.

    No suite_version -> "" bucket, and FIX-2 behaviour (metric-scoped,
    TTL-bounded, floor-3 quorum) is preserved inside that bucket.

    #SG-TRACE: REQ-ENGSCOPE-004
    #   | test: test_legacy_changepointresult_lands_in_empty_suite_bucket
    """
    now = DAY_NS
    legacy = ChangePointResult(
        model_tuple=MODEL,
        change_detected=True,
        score=7.5,
        threshold=5.0,
        contributing_orgs=["a"],
        metric_name=M1,
        timestamp_ns=now,
    )
    assert legacy.suite_version == ""

    s = AgreementScorer()
    s.ingest(legacy)
    s.ingest(_cp("b", ts_ns=now))
    s.ingest(_cp("c", ts_ns=now))
    # All three landed in the same legacy bucket -> FIX-2 floor of 3 met.
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) == 3
    # ...and nothing leaked into a named-suite bucket.
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1)
        is None
    )


def test_legacy_promote_signature_still_positional() -> None:
    """promote_to_public_alert(mt, metric, now_ns) keeps its arity (C2)."""
    now = DAY_NS
    s = AgreementScorer()
    for org in ("a", "b", "c"):
        s.ingest(_cp(org, ts_ns=now))
    assert s.promote_to_public_alert(MODEL, M1, now) == 3


# ---------------------------------------------------------------------------
# ENG-1 / T4, T5 -- suite-scoped agreement
# ---------------------------------------------------------------------------


def test_three_orgs_split_suites_do_not_reach_quorum() -> None:
    """T4: suites v1.1.0 / v1.1.0 / v2.0.0 -> no bucket reaches q=3.

    This is contract §2 B2: without suite scoping these three orgs read as
    one agreeing population of 3 on (model, metric) although two of them
    are running an entirely different canary corpus.

    #SG-TRACE: REQ-ENGSCOPE-005
    #   | test: test_three_orgs_split_suites_do_not_reach_quorum
    """
    now = DAY_NS
    s = AgreementScorer()
    s.ingest(_cp("org-a", ts_ns=now, suite=V1))
    s.ingest(_cp("org-b", ts_ns=now, suite=V1))
    s.ingest(_cp("org-c", ts_ns=now, suite=V2))

    # 2 < q(2)=3 in the v1 bucket, 1 < q(1)=3 in the v2 bucket.
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1)
        is None
    )
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V2)
        is None
    )
    # And nothing accumulated in the legacy catch-all either.
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) is None


def test_three_orgs_same_suite_promote() -> None:
    """T5: the SAME three orgs all on v2.0.0 promote with org_count=3.

    Positive control for T4: the block there is the corpus split, not a
    tightened quorum.

    #SG-TRACE: REQ-ENGSCOPE-005 | test: test_three_orgs_same_suite_promote
    """
    now = DAY_NS
    s = AgreementScorer()
    for org in ("org-a", "org-b", "org-c"):
        s.ingest(_cp(org, ts_ns=now, suite=V2))
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V2) == 3
    )


def test_suite_scoped_split_suites_block() -> None:
    """Same metric, same model, different suites: never one agreement set."""
    now = 5 * DAY_NS
    s = AgreementScorer()
    for i in range(6):
        suite = V1 if i % 2 == 0 else V2
        s.ingest(_cp(f"org-{i}", ts_ns=now, suite=suite))
    # 3 orgs in each bucket -> each bucket promotes on its own merits...
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1) == 3
    )
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V2) == 3
    )
    # ...but never as a single pooled population of 6.
    assert s.promote_to_public_alert(MODEL, M1, now_ns=now) is None


def test_suite_scoped_observers_do_not_leak_across_suites() -> None:
    """Observers of one suite do not raise q(M) for another suite.

    A cutover must not make the incumbent bucket harder to promote.

    #SG-TRACE: REQ-ENGSCOPE-005
    #   | test: test_suite_scoped_observers_do_not_leak_across_suites
    """
    now = DAY_NS
    s = AgreementScorer()
    # 20 orgs watching the NEW corpus.
    for i in range(20):
        s.observe(MODEL, M1, f"new-{i}", now, V2)
    # 3 orgs agree on the OLD corpus, where only they are watching.
    for org in ("old-1", "old-2", "old-3"):
        s.ingest(_cp(org, ts_ns=now, suite=V1))
    # q is computed from the v1 bucket's own population (3), not 23.
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1) == 3
    )


def test_clear_is_suite_local() -> None:
    """clear() on one suite leaves another suite's candidates intact.

    #SG-TRACE: REQ-ENGSCOPE-005 | test: test_clear_is_suite_local
    """
    now = DAY_NS
    s = AgreementScorer()
    for org in ("a", "b", "c"):
        s.ingest(_cp(org, ts_ns=now, suite=V1))
        s.ingest(_cp(org, ts_ns=now, suite=V2))
    s.clear(MODEL, M1, V1)
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1)
        is None
    )
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V2) == 3
    )


def test_promotion_clears_only_its_own_suite_bucket() -> None:
    """A promotion under v1.1.0 must not wipe pending v2.0.0 candidates."""
    now = DAY_NS
    s = AgreementScorer()
    for org in ("a", "b", "c"):
        s.ingest(_cp(org, ts_ns=now, suite=V1))
    s.ingest(_cp("a", ts_ns=now, suite=V2))
    s.ingest(_cp("b", ts_ns=now, suite=V2))

    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1) == 3
    )
    # v2 still holds its two pending candidates; a third completes quorum.
    s.ingest(_cp("c", ts_ns=now, suite=V2))
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V2) == 3
    )


# ---------------------------------------------------------------------------
# ENG-1 / T9 -- q(M) schedule is untouched by the key change
# ---------------------------------------------------------------------------


def test_quorum_schedule_unchanged_under_suite_key() -> None:
    """T9: q(M)=max(3, ceil(M/3)) with the knee still at M=10, per bucket.

    ENG-1 changes the KEY, never the schedule (contract C5).  The knee is
    re-measured end-to-end inside a single suite bucket.

    #SG-TRACE: REQ-ENGSCOPE-005
    #   | test: test_quorum_schedule_unchanged_under_suite_key
    """
    assert required_quorum(9) == 3
    assert required_quorum(10) == 4
    assert AgreementScorer().quorum == QUORUM_FLOOR == 3

    now = DAY_NS
    # M=9 inside the v1 bucket: 3 agreeing orgs still meet the floor.
    flat = AgreementScorer()
    for i in range(9):
        flat.observe(MODEL, M1, f"obs-{i}", now, V1)
    for org in ("obs-0", "obs-1", "obs-2"):
        flat.ingest(_cp(org, ts_ns=now, suite=V1))
    assert (
        flat.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1)
        == 3
    )

    # M=10 inside the v1 bucket: q rises to 4, so 3 no longer promote.
    knee = AgreementScorer()
    for i in range(10):
        knee.observe(MODEL, M1, f"obs-{i}", now, V1)
    for org in ("obs-0", "obs-1", "obs-2"):
        knee.ingest(_cp(org, ts_ns=now, suite=V1))
    assert (
        knee.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1)
        is None
    )
    knee.ingest(_cp("obs-3", ts_ns=now, suite=V1))
    assert (
        knee.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1)
        == 4
    )


def test_ttl_unchanged_under_suite_key() -> None:
    """The 14d candidate TTL still expires stale candidates per bucket."""
    ttl = 14 * DAY_NS
    s = AgreementScorer(ttl_ns=ttl)
    s.ingest(_cp("a", ts_ns=1 * DAY_NS, suite=V1))
    s.ingest(_cp("b", ts_ns=30 * DAY_NS, suite=V1))
    s.ingest(_cp("c", ts_ns=30 * DAY_NS, suite=V1))
    assert (
        s.promote_to_public_alert(
            MODEL, M1, now_ns=30 * DAY_NS, suite_version=V1
        )
        is None
    )


# ---------------------------------------------------------------------------
# ADV-1 -- poisoned / Sybil probe fanning out across fabricated suites
# ---------------------------------------------------------------------------

_FAKE_SUITES: tuple[str, ...] = (
    "v1.1.0",
    "v1.1.1",
    "v9.9.9",
    "v0.0.1-rc1",
    "totally-real-corpus",
    "",
)


def test_adv1_sybil_suite_fanout_no_public_alert() -> None:
    """ADV-1: one org, 40 candidates, 6 fabricated suites -> NO public alert.

    The attack: now that suite_version is part of the bucket key, a hostile
    probe controls a key-space dimension.  It floods candidates across many
    fabricated suite labels on one (model_tuple, metric) hoping that a
    wider key space is a cheaper route to apparent agreement.

    It is not.  The gate is DISTINCT ORGS PER BUCKET, and a single identity
    contributes exactly one vote to each bucket it touches, so every bucket
    sits at 1 < floor 3.  Splitting a population can only ever LOWER a
    bucket's agreeing count.

    #SG-TRACE: REQ-ENGSCOPE-005
    #   | test: test_adv1_sybil_suite_fanout_no_public_alert
    """
    s = AgreementScorer()
    now = 40 * DAY_NS

    # n=40 candidates fanned across 6 fabricated suite labels, all from ONE
    # org, all on the same (model_tuple, metric_name).
    for i in range(40):
        s.ingest(
            _cp(
                "org-sybil",
                ts_ns=(i + 1) * DAY_NS,
                suite=_FAKE_SUITES[i % len(_FAKE_SUITES)],
            )
        )

    # Every fabricated bucket -- and the legacy one -- refuses to promote.
    for suite in _FAKE_SUITES:
        assert (
            s.promote_to_public_alert(
                MODEL, M1, now_ns=now, suite_version=suite
            )
            is None
        ), f"suite {suite!r} must not promote on one org"

    # Distinct-org counting is still the gate: each bucket holds exactly one
    # org, no matter how many candidates were replayed into it.
    for suite in _FAKE_SUITES:
        bucket = s._agree[(MODEL, suite, M1)]
        assert set(bucket) == {"org-sybil"}, (
            f"bucket {suite!r} must hold exactly one distinct org"
        )
    assert len(s._agree) == len(_FAKE_SUITES)


def test_adv1_sybil_fanout_does_not_dilute_honest_quorum() -> None:
    """The same flood cannot block an honest quorum either (no DoS).

    Complement to ADV-1: the Sybil's extra buckets are inert.  Three honest
    orgs agreeing inside one real suite still promote, and the Sybil is
    exactly one extra vote there -- never a majority-maker on its own.

    #SG-TRACE: REQ-ENGSCOPE-005
    #   | test: test_adv1_sybil_fanout_does_not_dilute_honest_quorum
    """
    s = AgreementScorer()
    now = 40 * DAY_NS
    for i in range(40):
        s.ingest(
            _cp(
                "org-sybil",
                ts_ns=(i + 1) * DAY_NS,
                suite=_FAKE_SUITES[i % len(_FAKE_SUITES)],
            )
        )
    # Two honest orgs in the real suite: with the Sybil that is 3 distinct
    # orgs -- the documented unweighted-quorum residual (EXP-2 C2), which
    # ENG-1 neither worsens nor fixes.
    for org in ("honest-1", "honest-2"):
        s.ingest(_cp(org, ts_ns=now, suite=V1))
    assert (
        s.promote_to_public_alert(MODEL, M1, now_ns=now, suite_version=V1) == 3
    )

    # In a suite the Sybil never touched, two honest orgs stay below floor.
    fresh = AgreementScorer()
    for org in ("honest-1", "honest-2"):
        fresh.ingest(_cp(org, ts_ns=now, suite="v3.0.0"))
    assert (
        fresh.promote_to_public_alert(
            MODEL, M1, now_ns=now, suite_version="v3.0.0"
        )
        is None
    )
