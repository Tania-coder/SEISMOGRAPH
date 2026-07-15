#!/usr/bin/env python3
"""
scripts/experiment_stable_fp.py
================================
EXP-1C: Stable-window false-positive verification (adversarial).

Question: at the default operating point (CUSUM h=5.0, k=0.5,
baseline_samples=30 -- the exact configuration used by
scripts/anthropic_backtest.py), do (a) a stable provider window and
(b) Laplace DP noise alone fire drift alerts?

Method
------
Synthesize 90-day windows containing ONLY phase-0 "stable baseline"
statistics by reusing simulate_day() from scripts/anthropic_backtest
with dates strictly before BUG_DATE (get_phase() == 0 for the whole
window; asserted at runtime).  Metrics: json_success_rate and
avg_output_length.  No generator constants are duplicated here.

Conditions (200 runs each, deterministic seeding):
  1. DP OFF  -- 200 independent data seeds, no noise.
  2. DP ON   -- data seed fixed to the backtest SEED (42);
                200 independent Laplace noise seeds
                (epsilon=2.0, one flush per day).
  3. DP ON   -- 200 runs varying data seed and noise seed together.

DP noise replicates probe.privacy.Aggregator.flush() post-processing:
Laplace scale b = delta_f / EPSILON per metric, delta_f taken verbatim
from probe.privacy._METRIC_SENSITIVITY (avg_output_length: 8192.0,
json_success_rate: 1.0), same draw order as flush(), clamp to valid
range, round to 4 decimals.

FIX-1 (EXP-1R, REQ-PRIV-010): sensitivity is batch-aware, delta_f =
_metric_sensitivity(metric, N_BATCH) from probe/privacy.py, where
each daily flush publishes the mean of an n=N_BATCH-record canary
batch.  N_BATCH is read from env var SG_N_BATCH; the default (1)
degrades to the old worst-case bounds and reproduces the published
EXP-1C rates (0.400 / 0.600 / 0.620) exactly.

A window counts as a false positive if ANY stream fires at least one
alert.  A stream is not fed further after its first alert: in
production the caller resets after a confirmed alert, and counting
post-threshold re-fires would double-count a single excursion.

#SG-TRACE: EXP-1C
#   | assumption: phase-0 statistics of the backtest generator are a
#     faithful model of a stable provider window; simulate_day() is
#     reused (not re-implemented) so this holds by construction
#   | test: run twice, diff stdout (deterministic); expected FP rate 0
#     at h=5.0/k=0.5 -- honest rate reported if nonzero, no tuning
"""

from __future__ import annotations

import os
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.detector import CUSUMDetector  # noqa: E402
from probe.privacy import (  # noqa: E402
    EPSILON,
    _laplace_noise,
    _metric_sensitivity,
)
from scripts.anthropic_backtest import (  # noqa: E402
    BUG_DATE,
    CUSUM_H,
    CUSUM_K,
    MODEL,
    SEED,
    get_phase,
    simulate_day,
)

# ---------------------------------------------------------------------------
# Experiment constants
# ---------------------------------------------------------------------------

N_RUNS = 200
WINDOW_DAYS = 90
BASELINE_SAMPLES = 30  # matches anthropic_backtest.run()
METRICS = ("json_success_rate", "avg_output_length")
NS_PER_DAY = 86_400_000_000_000

# FIX-1 (REQ-PRIV-010): batch-aware DP sensitivity.  delta_f =
# _metric_sensitivity(metric, N_BATCH); default 1 reproduces the
# published EXP-1C rates exactly (old worst-case bounds).
# #SG-TRACE: EXP-1R
#   | assumption: one flush/day of an n=N_BATCH canary batch
#   | test: sanity gate (SG_N_BATCH unset must reproduce
#     0.4000 / 0.6000 / 0.6200; N_BATCH never touches the data)
N_BATCH = int(os.environ.get("SG_N_BATCH", "1"))

# Stable-only date range: 90 days ending the day before BUG_DATE.
# get_phase() returns 0 for every date < BUG_DATE, so the entire
# window draws from the generator's phase-0 statistics.
STABLE_END = BUG_DATE - timedelta(days=1)
STABLE_START = BUG_DATE - timedelta(days=WINDOW_DAYS)

# Deterministic master seeding: disjoint seed bases per condition so
# no RNG stream is reused across conditions.
C1_DATA_BASE = 10_000
C2_NOISE_BASE = 20_000
C3_DATA_BASE = 30_000
C3_NOISE_BASE = 40_000


def synth_stable_window(data_seed: int) -> list[dict[str, float]]:
    """Return 90 days of phase-0 metrics via the backtest generator.

    #SG-TRACE: EXP-1C
    #   | assumption: every date in [STABLE_START, STABLE_END] maps to
    #     phase 0; asserted per-day so a timeline change in the
    #     generator cannot silently contaminate this experiment
    #   | test: assert get_phase(d) == 0 for all window days
    """
    rng = random.Random(data_seed)
    days: list[dict[str, float]] = []
    d = STABLE_START
    while d <= STABLE_END:
        assert get_phase(d) == 0, f"non-stable date in window: {d}"
        days.append(simulate_day(d, rng))
        d += timedelta(days=1)
    return days


def apply_dp(
    metrics: dict[str, float], noise_rng: random.Random
) -> dict[str, float]:
    """Replicate Aggregator.flush() DP post-processing for one day.

    Draw order (avg_output_length first, then json_success_rate),
    clamping, and 4-decimal rounding match probe/privacy.py flush().

    #SG-TRACE: EXP-1R
    #   | assumption: one flush/day of an n=N_BATCH canary batch;
    #     delta_f taken verbatim from
    #     probe.privacy._metric_sensitivity, no local re-derivation
    #   | test: sanity gate; b = 8192/(n*2.0) and 1.0/(n*2.0)
    #     by construction
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


def run_window(
    days: list[dict[str, float]], noise_seed: int | None = None
) -> dict[str, tuple[int, str]]:
    """Feed one 90-day window to a fresh detector.

    Returns {metric_name: (first_alert_day_index, direction)} for
    streams that alerted.  Empty dict == clean window.
    """
    detector = CUSUMDetector(
        h=CUSUM_H, k=CUSUM_K, baseline_samples=BASELINE_SAMPLES
    )
    noise_rng = random.Random(noise_seed) if noise_seed is not None else None
    alerted: dict[str, tuple[int, str]] = {}
    for i, raw in enumerate(days):
        m = apply_dp(raw, noise_rng) if noise_rng is not None else raw
        for name in METRICS:
            if name in alerted:
                continue
            alert = detector.update(
                MODEL, name, m[name], timestamp_ns=i * NS_PER_DAY
            )
            if alert is not None:
                alerted[name] = (i, alert.direction)
    return alerted


def summarize(label: str, results: list[dict[str, tuple[int, str]]]) -> None:
    """Print a stable, deterministic summary block for one condition."""
    n = len(results)
    n_fp = sum(1 for r in results if r)
    total_alerts = sum(len(r) for r in results)
    print(f"  {label}")
    print(f"    windows run:      {n}")
    print(f"    FP windows:       {n_fp}")
    print(f"    FP window rate:   {n_fp / n:.4f}")
    print(f"    total alerts:     {total_alerts}")
    for metric in METRICS:
        hits = [r[metric] for r in results if metric in r]
        if not hits:
            print(f"    {metric}: 0 alerts")
            continue
        first_days = sorted(d for d, _ in hits)
        directions = sorted({direction for _, direction in hits})
        print(
            f"    {metric}: {len(hits)} alerts, "
            f"first-alert day range {first_days[0]}-{first_days[-1]}, "
            f"directions {directions}"
        )
    print()


def run() -> None:
    d_len = _metric_sensitivity("avg_output_length", N_BATCH)
    d_rate = _metric_sensitivity("json_success_rate", N_BATCH)
    sep = "=" * 62
    print(sep)
    print("EXP-1C: Stable-window false-positive verification")
    print(sep)
    print()
    print(
        f"  Window:   {STABLE_START} .. {STABLE_END} "
        f"({WINDOW_DAYS} days, all phase 0)"
    )
    print(
        f"  Detector: CUSUM h={CUSUM_H}, k={CUSUM_K}, "
        f"baseline_samples={BASELINE_SAMPLES}"
    )
    print(
        f"  DP:       Laplace, epsilon={EPSILON}, one flush/day; "
        f"delta_f avg_output_length={d_len}, "
        f"json_success_rate={d_rate}"
    )
    print(f"  Batch:    n_batch={N_BATCH} (FIX-1, REQ-PRIV-010)")
    print(f"  Runs per condition: {N_RUNS}")
    print()

    c1 = [
        run_window(synth_stable_window(C1_DATA_BASE + i))
        for i in range(N_RUNS)
    ]
    summarize(f"Condition 1: DP OFF, {N_RUNS} independent data seeds", c1)

    fixed_days = synth_stable_window(SEED)
    c2 = [
        run_window(fixed_days, noise_seed=C2_NOISE_BASE + i)
        for i in range(N_RUNS)
    ]
    summarize(
        f"Condition 2: DP ON, data seed fixed ({SEED}), {N_RUNS} noise seeds",
        c2,
    )

    c3 = [
        run_window(
            synth_stable_window(C3_DATA_BASE + i),
            noise_seed=C3_NOISE_BASE + i,
        )
        for i in range(N_RUNS)
    ]
    summarize(f"Condition 3: DP ON, {N_RUNS} seeds varying data+noise", c3)

    print(sep)
    print("  Reproducible: python3 scripts/experiment_stable_fp.py")
    print(sep)


if __name__ == "__main__":
    run()
