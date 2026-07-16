#!/usr/bin/env python3
"""
scripts/experiment_quorum.py
=============================
EXP-2: Multi-observer quorum simulation.

EXP-1C showed a single observer at CUSUM h=5.0/k=0.5 has a 0.400
stable-window false-positive rate over 90 days (DP OFF).  The
architecture's answer is the correlation-first invariant: a
single-org signal is NEVER promoted to a public drift alert.  This
experiment demonstrates that invariant end-to-end: M independent
observers, each with its own CUSUMDetector, feed candidate alerts
into the LIVE engine.correlation.AgreementScorer.

Engine code exercised (not reimplemented)
-----------------------------------------
- engine.correlation.AgreementScorer -- the LIVE quorum gate:
  ingest() + promote_to_public_alert().  Promotion requires >= quorum
  DISTINCT org_ids with change_detected=True for one model_tuple.
  Semantics found by reading the code (they shape the results):
    * no time-window matching: pending candidates accumulate until
      clear(); two candidates 89 days apart still form quorum.  The
      "engine as-is" condition below therefore uses one persistent
      scorer polled daily -- worst case for coincidence FPs.  The
      "TTL=14d" condition enforces candidate expiry in the HARNESS
      (fresh scorer per day, re-ingesting only candidates from the
      last 14 days) because the engine has no expiry; the promotion
      decision itself is still the real scorer.  Proposed engine fix.
    * no weighting: observers are equal-weight; no reputation.
    * no metric/direction matching: ChangePointResult carries no
      metric name; orgs alerting on different metrics or in opposite
      directions still count as agreement.
- engine.correlation.ChangePointResult -- candidate alert envelope.
- engine.detector.CUSUMDetector -- per-(model_tuple, metric) Page-
  CUSUM, one instance per observer (h=5.0, k=0.5,
  baseline_samples=30, exactly as scripts/anthropic_backtest.py).
- probe.privacy._metric_sensitivity / _laplace_noise / EPSILON --
  DP noise identical to Aggregator.flush() post-processing (same
  draw order, clamping, 4-decimal rounding).
- scripts.anthropic_backtest.simulate_day -- canonical seeded
  incident generator (baseline 2025-07-01, bug 2025-08-05,
  escalation 2025-08-29, postmortem 2025-09-17).
- scripts.experiment_stable_fp.run_window / synth_stable_window --
  reused verbatim for the M=1 sanity gate, which must reproduce the
  published EXP-1C DP-OFF rate 0.400 exactly (condition 1 seeds).

Observer model
--------------
Each observer draws its OWN Gaussian noise around the SAME phase
means (same provider truth, independent sampling) via simulate_day()
with a per-observer data RNG, applies its OWN DP noise via a
per-observer noise RNG, and runs its OWN CUSUMDetector.  DP is ON
with n=N_BATCH=100 records per daily flush (env SG_N_BATCH
overrides): a realistic canary batch -- a probe running a
~100-prompt canary suite once per day -- rather than the worst-case
n=1 bound.  Noise scales: b = 8192/(100*2.0) = 40.96
(avg_output_length), b = 1/(100*2.0) = 0.005 (json_success_rate).

Experiments (200 trials each, deterministic seeding)
----------------------------------------------------
A  Incident timeline: public-alert detection rate before the
   postmortem, first-public-alert date distribution, median lead vs
   2025-09-17, quorum cost in days (median public-alert day minus
   median first single-observer candidate day).
B  Stable 90-day window: public-alert FP rate per M vs the
   single-observer floor.  Headline number.
C1 Single-org burst (M=3, quorum=2): a strong shift injected into
   ONE observer's series only.  Invariant: with zero honest
   candidate alerts, zero public alerts (asserted per trial).
C2 Sybil-lite (M=3, quorum=2): one malicious observer emits
   fabricated always-alerting signals daily.  Alone it never
   promotes (asserted); the residual collusion channel (Sybil + one
   honest false alarm at quorum 2) is measured and reported.

#SG-TRACE: EXP-2
#   | assumption: observers are statistically independent given the
#     provider truth; real observers share provider infrastructure,
#     so noise may correlate and quorum FP rates here are optimistic
#   | test: run twice, diff stdout (byte-identical); M=1 sanity gate
#     reproduces EXP-1C DP-OFF rate 0.400 exactly
"""

from __future__ import annotations

import os
import random
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(
    os.environ.get(
        "SEISMOGRAPH_ROOT",
        Path(__file__).resolve().parent.parent,
    )
)
sys.path.insert(0, str(REPO_ROOT))

from engine.correlation import (  # noqa: E402
    AgreementScorer,
    ChangePointResult,
)
from engine.detector import CUSUMDetector  # noqa: E402
from probe.privacy import (  # noqa: E402
    EPSILON,
    _laplace_noise,
    _metric_sensitivity,
)
from scripts.anthropic_backtest import (  # noqa: E402
    BASELINE_START,
    CUSUM_H,
    CUSUM_K,
    MODEL,
    POSTMORTEM_DATE,
    simulate_day,
)
from scripts.experiment_stable_fp import (  # noqa: E402
    C1_DATA_BASE as EXP1C_DATA_BASE,
)
from scripts.experiment_stable_fp import (  # noqa: E402
    STABLE_END,
    STABLE_START,
    run_window,
    synth_stable_window,
)

# ---------------------------------------------------------------------------
# Experiment constants
# ---------------------------------------------------------------------------

N_TRIALS = 200
MAX_M = 5
M_VALUES = (2, 3, 5)
QUORUMS = (2, 3)  # 2 = AgreementScorer.QUORUM_MIN; 3 = Phase 1 open Q
WINDOW_DAYS = 90
BASELINE_SAMPLES = 30  # matches anthropic_backtest.run() and EXP-1C
METRICS = ("json_success_rate", "avg_output_length")
NS_PER_DAY = 86_400_000_000_000
TTL_DAYS = 14  # harness-enforced candidate expiry (proposed fix)

# Realistic canary batch: one daily flush of a ~100-prompt suite.
# n=1 (EXP-1 worst case) is unrealistically noisy for a deployed
# probe; n=100 keeps DP ON while modelling actual suite size.
N_BATCH = int(os.environ.get("SG_N_BATCH", "100"))

# Deterministic master seeding: disjoint bases per experiment, and
# per-(trial, observer) offsets with stride > MAX_M so no RNG stream
# is ever reused across trials, observers, or experiments.  Bases
# 50k+ are disjoint from EXP-1C's 10k-40k bases.
SEED_STRIDE = 8
A_DATA_BASE = 50_000
A_NOISE_BASE = 60_000
B_DATA_BASE = 70_000
B_NOISE_BASE = 80_000
EC1_DATA_BASE = 90_000
EC1_NOISE_BASE = 95_000
EC2_DATA_BASE = 100_000
EC2_NOISE_BASE = 105_000

# C1 burst: a strong single-org shift (-10 sigma on the rate metric
# for 20 days) that is guaranteed to fire that observer's CUSUM.
BURST_START_DAY = 45
BURST_LEN_DAYS = 20
BURST_RATE_SHIFT = 0.06

SYBIL_ORG = "org-sybil"
SYBIL_SCORE = 999.0


def apply_dp(
    metrics: dict[str, float], noise_rng: random.Random
) -> dict[str, float]:
    """Replicate Aggregator.flush() DP post-processing for one day.

    Draw order (avg_output_length first, then json_success_rate),
    clamping, and 4-decimal rounding match probe/privacy.py flush().

    #SG-TRACE: EXP-2
    #   | assumption: one flush/day of an n=N_BATCH canary batch;
    #     delta_f taken verbatim from probe.privacy.
    #     _metric_sensitivity, no local re-derivation
    #   | test: b = 8192/(n*2.0) and 1.0/(n*2.0) by construction
    """
    noised_len = max(
        0.0,
        metrics["avg_output_length"]
        + _laplace_noise(
            _metric_sensitivity("avg_output_length", N_BATCH) / EPSILON,
            noise_rng,
        ),
    )
    noised_rate = max(
        0.0,
        min(
            1.0,
            metrics["json_success_rate"]
            + _laplace_noise(
                _metric_sensitivity("json_success_rate", N_BATCH) / EPSILON,
                noise_rng,
            ),
        ),
    )
    return {
        "json_success_rate": round(noised_rate, 4),
        "avg_output_length": round(noised_len, 4),
    }


def synth_incident_series(data_seed: int) -> list[dict[str, float]]:
    """One observer's daily metrics over the full incident timeline.

    Reuses simulate_day() so each observer draws independent Gaussian
    noise around the SAME phase means (shared provider truth).
    """
    rng = random.Random(data_seed)
    days: list[dict[str, float]] = []
    d = BASELINE_START
    while d <= POSTMORTEM_DATE:
        days.append(simulate_day(d, rng))
        d += timedelta(days=1)
    return days


def inject_burst(days: list[dict[str, float]]) -> list[dict[str, float]]:
    """Inject a correlated noise burst into ONE observer's series.

    Subtracts BURST_RATE_SHIFT (10x phase-0 sigma) from
    json_success_rate for BURST_LEN_DAYS starting at BURST_START_DAY.
    """
    out: list[dict[str, float]] = []
    burst_end = BURST_START_DAY + BURST_LEN_DAYS
    for i, m in enumerate(days):
        if BURST_START_DAY <= i < burst_end:
            m = dict(m)
            m["json_success_rate"] = max(
                0.0, m["json_success_rate"] - BURST_RATE_SHIFT
            )
        out.append(m)
    return out


def first_candidate_day(
    days: list[dict[str, float]], noise_seed: int
) -> tuple[int, float] | None:
    """Run one observer's detector; return its first candidate alert.

    DP is always ON (n=N_BATCH).  Returns (day_index, cusum_score) of
    the first DriftAlert on ANY metric stream, or None if the window
    is clean.  Only the first alert matters for quorum: subsequent
    alerts from the same org cannot change the distinct-org set.
    """
    detector = CUSUMDetector(
        h=CUSUM_H, k=CUSUM_K, baseline_samples=BASELINE_SAMPLES
    )
    noise_rng = random.Random(noise_seed)
    for i, raw in enumerate(days):
        m = apply_dp(raw, noise_rng)
        for name in METRICS:
            alert = detector.update(
                MODEL, name, m[name], timestamp_ns=i * NS_PER_DAY
            )
            if alert is not None:
                return i, alert.cusum_score
    return None


def promotion_day(
    candidates: list[tuple[int, float] | None],
    quorum: int,
    n_days: int,
    ttl_days: int | None = None,
    daily_orgs: tuple[str, ...] = (),
) -> int | None:
    """Replay candidate alerts through the LIVE AgreementScorer.

    candidates[i] is (first_alert_day, cusum_score) for org-i, or
    None if that observer never fired.  daily_orgs emit a fabricated
    always-alerting ChangePointResult every day (Sybil model).

    ttl_days=None: engine as-is -- one persistent scorer, candidates
    never expire (AgreementScorer has no time-window logic).
    ttl_days=T: harness-enforced expiry -- a fresh scorer per day is
    fed only candidates from the last T days; the promotion decision
    is still AgreementScorer.promote_to_public_alert().

    Returns the first day index with a non-None promotion, or None.

    #SG-TRACE: EXP-2
    #   | assumption: daily promote_to_public_alert() polling matches
    #     the production cadence of one scoring pass per flush window
    #   | test: promotion day == day the quorum-th distinct org fires
    """

    def _result(org: str, score: float) -> ChangePointResult:
        return ChangePointResult(
            model_tuple=MODEL,
            change_detected=True,
            score=score,
            threshold=CUSUM_H,
            contributing_orgs=[org],
        )

    by_day: dict[int, list[tuple[str, float]]] = {}
    for i, cand in enumerate(candidates):
        if cand is None:
            continue
        day, score = cand
        by_day.setdefault(day, []).append((f"org-{i}", score))

    if ttl_days is None:
        scorer = AgreementScorer(quorum=quorum)
        for day in range(n_days):
            for org, score in by_day.get(day, []):
                scorer.ingest(_result(org, score))
            for org in daily_orgs:
                scorer.ingest(_result(org, SYBIL_SCORE))
            if scorer.promote_to_public_alert(MODEL) is not None:
                return day
        return None

    for day in range(n_days):
        scorer = AgreementScorer(quorum=quorum)
        for d0 in range(max(0, day - ttl_days + 1), day + 1):
            for org, score in by_day.get(d0, []):
                scorer.ingest(_result(org, score))
        for org in daily_orgs:
            scorer.ingest(_result(org, SYBIL_SCORE))
        if scorer.promote_to_public_alert(MODEL) is not None:
            return day
    return None


def _order_stat(sorted_vals: list[int], num: int, den: int) -> int:
    """Deterministic lower order statistic: index num*(n-1)//den."""
    return sorted_vals[num * (len(sorted_vals) - 1) // den]


def run_sanity_gate() -> None:
    """M=1 gate: reproduce the EXP-1C DP-OFF stable FP rate exactly.

    Same construction as EXP-1C condition 1 (DP OFF, data seeds
    10000+i), via run_window()/synth_stable_window() imported from
    scripts.experiment_stable_fp -- identical by construction.  The
    EXP-2 experiments run DP ON at n=100; the M=1 DP-ON rate under
    that condition is reported separately in Experiment B.
    """
    results = [
        run_window(synth_stable_window(EXP1C_DATA_BASE + i))
        for i in range(N_TRIALS)
    ]
    rate = sum(1 for r in results if r) / N_TRIALS
    print(
        "  Sanity gate: M=1 stable FP rate "
        f"(DP OFF, EXP-1C condition 1 seeds) = {rate:.4f}"
    )
    assert abs(rate - 0.400) < 1e-9, (
        f"sanity gate FAILED: {rate:.4f} != 0.4000 (EXP-1C DP OFF)"
    )
    print("  Gate PASSED (matches published EXP-1C rate 0.4000)")


def _collect_candidates(
    data_base: int, noise_base: int, synth, n_obs: int
) -> list[list[tuple[int, float] | None]]:
    """Per-trial, per-observer first candidate alerts (DP ON)."""
    trials: list[list[tuple[int, float] | None]] = []
    for t in range(N_TRIALS):
        cand: list[tuple[int, float] | None] = []
        for o in range(n_obs):
            days = synth(data_base + t * SEED_STRIDE + o)
            cand.append(
                first_candidate_day(days, noise_base + t * SEED_STRIDE + o)
            )
        trials.append(cand)
    return trials


def run_experiment_a() -> dict[tuple[int, int], dict[str, float]]:
    """Experiment A: incident timeline detection through quorum."""
    n_days = (POSTMORTEM_DATE - BASELINE_START).days + 1
    pm_day = n_days - 1
    trials = _collect_candidates(
        A_DATA_BASE, A_NOISE_BASE, synth_incident_series, MAX_M
    )
    print(
        "  Experiment A: incident timeline "
        f"({BASELINE_START}..{POSTMORTEM_DATE}, {N_TRIALS} trials)"
    )
    out: dict[tuple[int, int], dict[str, float]] = {}
    for m in M_VALUES:
        for q in QUORUMS:
            if q > m:
                continue
            pubs: list[int | None] = []
            firsts: list[int | None] = []
            for cand in trials:
                sub = cand[:m]
                pubs.append(promotion_day(sub, q, n_days))
                fire = sorted(c[0] for c in sub if c is not None)
                firsts.append(fire[0] if fire else None)
            det = sorted(p for p in pubs if p is not None and p < pm_day)
            rate = len(det) / N_TRIALS
            print(f"    M={m} quorum={q}:")
            print(f"      detection rate before postmortem: {rate:.4f}")
            if not det:
                out[(m, q)] = {"rate": rate}
                continue
            md = _order_stat(det, 1, 2)
            dates = [
                str(BASELINE_START + timedelta(days=d))
                for d in (det[0], md, _order_stat(det, 9, 10), det[-1])
            ]
            lead = (
                POSTMORTEM_DATE - (BASELINE_START + timedelta(days=md))
            ).days
            fd = sorted(f for f in firsts if f is not None)
            cost = md - _order_stat(fd, 1, 2)
            print(
                "      first public alert min/median/p90/max: "
                f"{dates[0]} / {dates[1]} / {dates[2]} / {dates[3]}"
            )
            print(f"      median lead vs postmortem: {lead} days")
            first_date = BASELINE_START + timedelta(days=_order_stat(fd, 1, 2))
            print(
                "      median first single-observer candidate: "
                f"{first_date}  -> quorum cost {cost} days"
            )
            out[(m, q)] = {"rate": rate, "lead": lead, "cost": cost}
    for m in M_VALUES:
        det = sorted(
            p
            for cand in trials
            if (p := promotion_day(cand[:m], 2, n_days, ttl_days=TTL_DAYS))
            is not None
            and p < pm_day
        )
        md_date = BASELINE_START + timedelta(days=_order_stat(det, 1, 2))
        print(
            f"    [TTL={TTL_DAYS}d check] M={m} quorum=2: rate "
            f"{len(det) / N_TRIALS:.4f}, median {md_date}"
        )
    return out


def run_experiment_b() -> tuple[
    float,
    float,
    dict[tuple[int, int], float],
    dict[tuple[int, int], float],
]:
    """Experiment B: stable-window public-alert FP rate per M."""
    trials = _collect_candidates(
        B_DATA_BASE, B_NOISE_BASE, synth_stable_window, MAX_M
    )
    m1 = sum(1 for c in trials if c[0] is not None) / N_TRIALS
    pooled = sum(1 for c in trials for x in c if x is not None) / (
        N_TRIALS * MAX_M
    )
    print(
        "  Experiment B: stable window "
        f"({STABLE_START}..{STABLE_END}, {N_TRIALS} trials)"
    )
    print(
        f"    M=1 candidate FP rate (DP ON, n={N_BATCH}): {m1:.4f} "
        f"(pooled over {N_TRIALS * MAX_M} observer-windows: "
        f"{pooled:.4f})"
    )
    print("    Public-alert FP rate (engine as-is | TTL=14d harness):")
    fp: dict[tuple[int, int], float] = {}
    fp_ttl: dict[tuple[int, int], float] = {}
    for m in M_VALUES:
        for q in QUORUMS:
            if q > m:
                continue
            hits = sum(
                1
                for cand in trials
                if promotion_day(cand[:m], q, WINDOW_DAYS) is not None
            )
            hits_ttl = sum(
                1
                for cand in trials
                if promotion_day(cand[:m], q, WINDOW_DAYS, ttl_days=TTL_DAYS)
                is not None
            )
            fp[(m, q)] = hits / N_TRIALS
            fp_ttl[(m, q)] = hits_ttl / N_TRIALS
            print(
                f"      M={m} quorum={q}: {fp[(m, q)]:.4f} | "
                f"{fp_ttl[(m, q)]:.4f}"
            )
    return m1, pooled, fp, fp_ttl


def run_experiment_c1() -> None:
    """Experiment C1: single-org correlated burst must stay private.

    #SG-TRACE: EXP-2
    #   | assumption: a -10 sigma rate shift for 20 days always fires
    #     the burst observer's CUSUM (asserted per trial)
    #   | test: zero public alerts in trials where both honest
    #     observers are quiet (asserted per trial)
    """
    pub_with = pub_without = pub_ttl = quiet = 0
    for t in range(N_TRIALS):
        honest: list[tuple[int, float] | None] = []
        for o in (0, 1):
            days = synth_stable_window(EC1_DATA_BASE + t * SEED_STRIDE + o)
            honest.append(
                first_candidate_day(days, EC1_NOISE_BASE + t * SEED_STRIDE + o)
            )
        bdays = inject_burst(
            synth_stable_window(EC1_DATA_BASE + t * SEED_STRIDE + 2)
        )
        burst = first_candidate_day(
            bdays, EC1_NOISE_BASE + t * SEED_STRIDE + 2
        )
        assert burst is not None, f"trial {t}: burst observer never fired"
        cand = [honest[0], honest[1], burst]
        pub = promotion_day(cand, 2, WINDOW_DAYS)
        if honest[0] is None and honest[1] is None:
            quiet += 1
            assert pub is None, (
                f"trial {t}: INVARIANT VIOLATION -- single-org burst "
                "promoted to public alert"
            )
        pub_with += pub is not None
        pub_without += promotion_day(honest, 2, WINDOW_DAYS) is not None
        pub_ttl += (
            promotion_day(cand, 2, WINDOW_DAYS, ttl_days=TTL_DAYS) is not None
        )
    print(
        f"  Experiment C1: single-org burst (M=3, quorum=2, {N_TRIALS} trials)"
    )
    print("    burst observer candidate rate: 1.0000 (asserted)")
    print(
        f"    trials with both honest observers quiet: {quiet} "
        "-> public alerts in those trials: 0 (asserted; "
        "invariant HELD)"
    )
    print(f"    public-alert rate with burst:    {pub_with / N_TRIALS:.4f}")
    print(
        "    public-alert rate without burst: "
        f"{pub_without / N_TRIALS:.4f} (counterfactual, same seeds)"
    )
    print(
        f"    delta (burst + >=1 honest false alarm at quorum 2): "
        f"{(pub_with - pub_without) / N_TRIALS:+.4f}"
    )
    print(
        f"    public-alert rate with burst, TTL={TTL_DAYS}d: "
        f"{pub_ttl / N_TRIALS:.4f}"
    )


def run_experiment_c2() -> None:
    """Experiment C2: Sybil-lite -- always-alerting malicious org.

    #SG-TRACE: EXP-2
    #   | assumption: Sybil controls one org_id and can fabricate
    #     ChangePointResults but cannot forge other org_ids
    #     (signature binding is upstream, gateway key registry)
    #   | test: Sybil alone never promotes (asserted); collusion
    #     rate with one honest false alarm reported honestly
    """
    alone = promotion_day([], 2, WINDOW_DAYS, daily_orgs=(SYBIL_ORG,))
    assert alone is None, "Sybil alone produced a public alert"
    coll2 = coll3 = quiet = 0
    for t in range(N_TRIALS):
        honest: list[tuple[int, float] | None] = []
        for o in (0, 1):
            days = synth_stable_window(EC2_DATA_BASE + t * SEED_STRIDE + o)
            honest.append(
                first_candidate_day(days, EC2_NOISE_BASE + t * SEED_STRIDE + o)
            )
        p2 = promotion_day(honest, 2, WINDOW_DAYS, daily_orgs=(SYBIL_ORG,))
        p3 = promotion_day(honest, 3, WINDOW_DAYS, daily_orgs=(SYBIL_ORG,))
        if honest[0] is None and honest[1] is None:
            quiet += 1
            assert p2 is None, (
                f"trial {t}: Sybil promoted without any honest candidate"
            )
        coll2 += p2 is not None
        coll3 += p3 is not None
    print(
        "  Experiment C2: Sybil-lite (M=3: 2 honest + 1 always-"
        f"alerting Sybil, {N_TRIALS} trials)"
    )
    print(
        "    Sybil alone (daily fabricated alerts, 90 days): "
        "NO public alert (asserted)"
    )
    print(
        f"    trials with both honest observers quiet: {quiet} "
        "-> public alerts: 0 (asserted)"
    )
    print(
        "    collude-promote rate, quorum=2 (Sybil + >=1 honest "
        f"false alarm): {coll2 / N_TRIALS:.4f}"
    )
    print(
        "    collude-promote rate, quorum=3 (Sybil + 2 honest "
        f"false alarms):  {coll3 / N_TRIALS:.4f}"
    )
    print(
        "    NOTE: this residual risk is inherent to unweighted "
        "quorum=2; reputation weighting and Ed25519 org binding "
        "(Phase 2) are the planned mitigations, not exercised here."
    )


def write_figure(
    a_stats: dict[tuple[int, int], dict[str, float]],
    m1_dp_on: float,
    fp: dict[tuple[int, int], float],
    fp_ttl: dict[tuple[int, int], float],
    out_path: Path,
) -> None:
    """FP rate and median lead vs M -> quorum_fp_vs_m.png (Agg)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.8))
    ms = list(M_VALUES)
    m3p = [m for m in ms if m >= 3]
    ax1.plot(
        ms,
        [fp[(m, 2)] for m in ms],
        "o-",
        color="#c0392b",
        label="quorum=2, engine as-is",
    )
    ax1.plot(
        m3p,
        [fp[(m, 3)] for m in m3p],
        "s-",
        color="#e67e22",
        label="quorum=3, engine as-is",
    )
    ax1.plot(
        ms,
        [fp_ttl[(m, 2)] for m in ms],
        "o--",
        color="#2980b9",
        label=f"quorum=2, TTL={TTL_DAYS}d",
    )
    ax1.plot(
        m3p,
        [fp_ttl[(m, 3)] for m in m3p],
        "s--",
        color="#27ae60",
        label=f"quorum=3, TTL={TTL_DAYS}d",
    )
    ax1.axhline(
        0.400,
        ls=":",
        color="gray",
        label="M=1 floor, DP OFF (EXP-1C)",
    )
    ax1.axhline(
        m1_dp_on,
        ls="-.",
        color="gray",
        label=f"M=1, DP ON n={N_BATCH}",
    )
    ax1.set_xlabel("observers M")
    ax1.set_ylabel("public-alert FP rate (90-day stable window)")
    ax1.set_title("Stable-window false positives")
    ax1.set_xticks(ms)
    ax1.set_ylim(0.0, 1.0)
    ax1.legend(fontsize=7)
    ax2.plot(
        ms,
        [a_stats[(m, 2)]["lead"] for m in ms],
        "o-",
        color="#c0392b",
        label="quorum=2",
    )
    ax2.plot(
        m3p,
        [a_stats[(m, 3)]["lead"] for m in m3p],
        "s-",
        color="#e67e22",
        label="quorum=3",
    )
    ax2.set_xlabel("observers M")
    ax2.set_ylabel("median lead vs postmortem (days)")
    ax2.set_title("Incident detection lead")
    ax2.set_xticks(ms)
    ax2.legend(fontsize=8)
    fig.suptitle(
        "EXP-2: quorum gating (LIVE AgreementScorer), "
        f"CUSUM h={CUSUM_H} k={CUSUM_K}, DP ON n={N_BATCH}",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def run() -> None:
    d_len = _metric_sensitivity("avg_output_length", N_BATCH)
    d_rate = _metric_sensitivity("json_success_rate", N_BATCH)
    sep = "=" * 62
    print(sep)
    print("EXP-2: Multi-observer quorum simulation")
    print(sep)
    print()
    print(
        f"  Observers: M in {list(M_VALUES)}; quorums {list(QUORUMS)} "
        "(2 = AgreementScorer.QUORUM_MIN)"
    )
    print(
        f"  Detector:  CUSUM h={CUSUM_H}, k={CUSUM_K}, "
        f"baseline_samples={BASELINE_SAMPLES} (per observer)"
    )
    print(
        f"  DP:        ON, Laplace epsilon={EPSILON}, "
        f"n_batch={N_BATCH} (realistic canary batch); "
        f"delta_f len={d_len}, rate={d_rate}"
    )
    print(
        "  Gate:      engine.correlation.AgreementScorer (LIVE); "
        "no candidate expiry in engine, "
        f"TTL={TTL_DAYS}d variant harness-enforced"
    )
    print(f"  Trials:    {N_TRIALS} per condition, master-seeded")
    print()
    run_sanity_gate()
    print()
    a_stats = run_experiment_a()
    print()
    m1, _pooled, fp, fp_ttl = run_experiment_b()
    print()
    run_experiment_c1()
    print()
    run_experiment_c2()
    print()
    fig_path = REPO_ROOT / "docs" / "experiments" / "quorum_fp_vs_m.png"
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    write_figure(a_stats, m1, fp, fp_ttl, fig_path)
    print(f"  Figure: docs/experiments/{fig_path.name}")
    print()
    print(sep)
    print("  Reproducible: python3 scripts/experiment_quorum.py")
    print(sep)


if __name__ == "__main__":
    run()
