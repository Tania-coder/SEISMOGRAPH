#!/usr/bin/env python3
"""
scripts/experiment_dp_backtest.py
==================================
EXP-1A: DP-noise-ON variant of the Anthropic Claude Sonnet 4 backtest.

The noise-OFF backtest (scripts/anthropic_backtest.py) shows that a
seeded backtest flags the Aug-Sep 2025 silent degradation 38 days
before the official postmortem (first alert 2025-08-10).  That
simulation feeds raw daily metrics to the CUSUM detector.  Live
probes, however, apply Laplace differential-privacy noise to every
flushed metric (probe/privacy.py, epsilon=2.0 per flush).  This
experiment quantifies how that DP noise changes detection.

Method
------
- Data: identical seeded generator (SEED=42) imported from
  scripts.anthropic_backtest; the raw daily series is identical to
  the noise-OFF run.
- Noise: one flush per simulated day.  Laplace noise per metric with
  scale b = delta_f / epsilon, reusing the exact sensitivity values
  from probe/privacy.py (_METRIC_SENSITIVITY, EPSILON) and the same
  post-noise clamping and 4-decimal rounding as Aggregator.flush().
- N=200 independent noise seeds (noise RNG fully separate from the
  data RNG), derived from a fixed master seed -- reproducible.
- Control: the noise-OFF series is run through this same harness and
  must reproduce the canonical 2025-08-10 first alert exactly.

Outputs
-------
- Deterministic summary on stdout (re-runs are byte-identical).
- docs/experiments/dp_backtest_hist.png (first-alert histogram;
  suffixed _n<N_BATCH> when SG_N_BATCH != 1).

FIX-1 (EXP-1R, REQ-PRIV-010)
----------------------------
Sensitivity is now batch-aware: each daily flush publishes the mean
of an n=N_BATCH-record canary batch, so delta_f =
_metric_sensitivity(metric, N_BATCH) from probe/privacy.py.
N_BATCH is read from env var SG_N_BATCH; the default (1) degrades
to the old worst-case bounds and reproduces the published EXP-1
numbers exactly.

#SG-TRACE: EXP-1A
#   | assumption: one SignalBatch flush per simulated day; live
#     deployments may flush up to 5x/day (budget 10.0 at epsilon
#     2.0 each), which changes per-observation noise and cadence
#   | test: control run reproduces noise-OFF alert 2025-08-10;
#     stdout is byte-identical across re-runs
"""

from __future__ import annotations

import math
import os
import random
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(
    os.environ.get(
        "SEISMOGRAPH_ROOT",
        Path(__file__).resolve().parent.parent,
    )
)
sys.path.insert(0, str(REPO_ROOT))

from engine.detector import CUSUMDetector  # noqa: E402
from probe.privacy import (  # noqa: E402
    EPSILON,
    _laplace_noise,
    _metric_sensitivity,
)
from scripts.anthropic_backtest import (  # noqa: E402
    BASELINE_START,
    BUG_DATE,
    CUSUM_H,
    CUSUM_K,
    MODEL,
    POSTMORTEM_DATE,
    SEED,
    simulate_day,
)

# ---------------------------------------------------------------------------
# Experiment constants
# ---------------------------------------------------------------------------

# Mirrors anthropic_backtest.run(): CUSUMDetector(..., baseline_samples=30).
BASELINE_SAMPLES = 30
N_NOISE_SEEDS = 200
NOISE_MASTER_SEED = 1337
NOISE_OFF_ALERT_DATE = date(2025, 8, 10)
METRIC_NAMES = ("json_success_rate", "avg_output_length")

# FIX-1 (REQ-PRIV-010): batch-aware DP sensitivity.  delta_f =
# _metric_sensitivity(metric, N_BATCH); default 1 reproduces the
# published EXP-1 numbers exactly (old worst-case bounds).
# #SG-TRACE: EXP-1R
#   | assumption: one flush/day of an n=N_BATCH canary batch
#   | test: sanity gate (noise-OFF control must still reproduce the
#     canonical 2025-08-10 alert; N_BATCH never touches the data)
N_BATCH = int(os.environ.get("SG_N_BATCH", "1"))

_FIG_SUFFIX = "" if N_BATCH == 1 else f"_n{N_BATCH}"
FIGURE_PATH = (
    REPO_ROOT / "docs" / "experiments" / f"dp_backtest_hist{_FIG_SUFFIX}.png"
)


def generate_series() -> list[tuple[date, dict[str, float]]]:
    """Regenerate the exact noise-OFF daily series (data SEED=42).

    #SG-TRACE: EXP-1A
    #   | assumption: single random.Random(SEED) consumed in date
    #     order reproduces anthropic_backtest.run() byte-for-byte
    #   | test: control assertion in main()
    """
    rng = random.Random(SEED)
    series: list[tuple[date, dict[str, float]]] = []
    day = BASELINE_START
    while day <= POSTMORTEM_DATE:
        series.append((day, simulate_day(day, rng)))
        day += timedelta(days=1)
    return series


def generate_null_series() -> list[tuple[date, dict[str, float]]]:
    """Counterfactual no-bug series: phase 0 on every day.

    Same date axis and data seed, but every day is drawn from the
    stable baseline distribution (simulate_day dispatches on date;
    BASELINE_START is always phase 0).  Any alert on this series is
    a false alarm by construction -- used to separate noise-driven
    alerts from bug-driven detection.

    #SG-TRACE: EXP-1A
    #   | assumption: null series with identical noise seeds is a
    #     valid false-alarm control for the DP-noised detector
    #   | test: null alert rate reported alongside detection rate
    """
    rng = random.Random(SEED)
    series: list[tuple[date, dict[str, float]]] = []
    day = BASELINE_START
    while day <= POSTMORTEM_DATE:
        series.append((day, simulate_day(BASELINE_START, rng)))
        day += timedelta(days=1)
    return series


def apply_dp_noise(
    metrics: dict[str, float], rng: random.Random
) -> dict[str, float]:
    """Apply one flush worth of Laplace DP noise to a day's metrics.

    Mirrors Aggregator.flush() in probe/privacy.py: identical scale
    b = delta_f / EPSILON with delta_f =
    _metric_sensitivity(metric, N_BATCH) (FIX-1, REQ-PRIV-010; base
    sensitivities avg_output_length=8192.0, json_success_rate=1.0;
    EPSILON=2.0), identical draw order (avg_output_length first,
    then json_success_rate), identical clamps (length >= 0; rate in
    [0, 1]) and 4-decimal rounding.

    #SG-TRACE: EXP-1R
    #   | assumption: one flush/day of an n=N_BATCH canary batch;
    #     sensitivity taken verbatim from probe.privacy
    #     _metric_sensitivity, no local re-derivation
    #   | test: sanity gate; scales printed in summary equal
    #     4096.0/N_BATCH and 0.5/N_BATCH
    """
    noised_len = max(
        0.0,
        metrics["avg_output_length"]
        + _laplace_noise(
            _metric_sensitivity("avg_output_length", N_BATCH) / EPSILON,
            rng,
        ),
    )
    noised_rate = max(
        0.0,
        min(
            1.0,
            metrics["json_success_rate"]
            + _laplace_noise(
                _metric_sensitivity("json_success_rate", N_BATCH) / EPSILON,
                rng,
            ),
        ),
    )
    return {
        "json_success_rate": round(noised_rate, 4),
        "avg_output_length": round(noised_len, 4),
    }


def run_detector(
    series: list[tuple[date, dict[str, float]]],
) -> dict[str, date | None]:
    """Feed one daily series to a fresh CUSUM detector.

    Returns the first-alert date per metric (None if that metric
    never alerted).  Update order matches anthropic_backtest.run():
    json_success_rate first, then avg_output_length, one timestamp
    per day.
    """
    detector = CUSUMDetector(
        h=CUSUM_H, k=CUSUM_K, baseline_samples=BASELINE_SAMPLES
    )
    first: dict[str, date | None] = {m: None for m in METRIC_NAMES}
    for day_num, (day, metrics) in enumerate(series):
        ts_ns = day_num * 86_400_000_000_000
        for metric_name in METRIC_NAMES:
            alert = detector.update(
                MODEL, metric_name, metrics[metric_name], timestamp_ns=ts_ns
            )
            if alert is not None and first[metric_name] is None:
                first[metric_name] = day
    return first


def overall_first(first: dict[str, date | None]) -> date | None:
    """Earliest first-alert date across metrics, or None."""
    dates = [d for d in first.values() if d is not None]
    return min(dates) if dates else None


def nearest_rank(sorted_vals: list[date], q: float) -> date:
    """Nearest-rank percentile (q in (0, 100]) of a sorted list."""
    idx = max(0, math.ceil(q / 100.0 * len(sorted_vals)) - 1)
    return sorted_vals[idx]


def make_figure(detected_dates: list[date]) -> None:
    """Histogram of first-alert dates with reference lines.

    #SG-TRACE: EXP-1A
    #   | assumption: headless Agg backend; PNG bytes need not be
    #     byte-identical across runs (only stdout must be)
    #   | test: file exists and is a valid PNG after run
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts = Counter(detected_dates)
    days = sorted(counts)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(
        days,
        [counts[d] for d in days],
        width=0.9,
        color="#4878a8",
        label=(
            f"first alert per noise seed "
            f"(n={len(detected_dates)}/{N_NOISE_SEEDS})"
        ),
    )
    ax.axvline(
        BUG_DATE, color="0.4", linestyle=":", label=f"bug onset {BUG_DATE}"
    )
    ax.axvline(
        NOISE_OFF_ALERT_DATE,
        color="green",
        linestyle="--",
        label=f"noise-OFF alert {NOISE_OFF_ALERT_DATE}",
    )
    ax.axvline(
        POSTMORTEM_DATE,
        color="red",
        linestyle="--",
        label=f"postmortem {POSTMORTEM_DATE}",
    )
    ax.set_title(
        "EXP-1A: first CUSUM alert under Laplace DP noise "
        f"(epsilon={EPSILON}, n_batch={N_BATCH}, "
        f"{N_NOISE_SEEDS} noise seeds)"
    )
    ax.set_xlabel("first-alert date")
    ax.set_ylabel("noise seeds")
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate()
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=150)
    plt.close(fig)


def main() -> None:
    series = generate_series()

    # ---- Sanity gate: noise-OFF control must reproduce canon ----------
    control_first = overall_first(run_detector(series))
    if control_first != NOISE_OFF_ALERT_DATE:
        raise AssertionError(
            f"Control mismatch: harness noise-OFF first alert is "
            f"{control_first}, expected {NOISE_OFF_ALERT_DATE}. "
            "Do not trust the DP results below."
        )

    # ---- DP-noise-ON runs ---------------------------------------------
    master = random.Random(NOISE_MASTER_SEED)
    noise_seeds = [master.randrange(2**32) for _ in range(N_NOISE_SEEDS)]

    per_seed_first: list[date | None] = []
    per_metric_detected = dict.fromkeys(METRIC_NAMES, 0)
    for noise_seed in noise_seeds:
        noise_rng = random.Random(noise_seed)
        noised = [
            (day, apply_dp_noise(metrics, noise_rng))
            for day, metrics in series
        ]
        first = run_detector(noised)
        per_seed_first.append(overall_first(first))
        for m in METRIC_NAMES:
            d = first[m]
            if d is not None and d < POSTMORTEM_DATE:
                per_metric_detected[m] += 1

    # ---- No-bug null control (false-alarm rate) -------------------------
    null_series = generate_null_series()
    null_alerts = 0
    for noise_seed in noise_seeds:
        noise_rng = random.Random(noise_seed)
        noised_null = [
            (day, apply_dp_noise(metrics, noise_rng))
            for day, metrics in null_series
        ]
        null_first = overall_first(run_detector(noised_null))
        if null_first is not None and null_first < POSTMORTEM_DATE:
            null_alerts += 1
    null_rate = 100.0 * null_alerts / N_NOISE_SEEDS

    detected = sorted(
        d for d in per_seed_first if d is not None and d < POSTMORTEM_DATE
    )
    on_postmortem = sum(1 for d in per_seed_first if d == POSTMORTEM_DATE)
    no_alert = sum(1 for d in per_seed_first if d is None)
    pre_onset = sum(1 for d in detected if d < BUG_DATE)
    detection_rate = 100.0 * len(detected) / N_NOISE_SEEDS

    s_rate = _metric_sensitivity("json_success_rate", N_BATCH)
    s_len = _metric_sensitivity("avg_output_length", N_BATCH)
    b_rate = s_rate / EPSILON
    b_len = s_len / EPSILON

    sep = "=" * 66
    print(sep)
    print("SEISMOGRAPH EXP-1A -- DP-noise-ON backtest")
    print("Anthropic Claude Sonnet 4, Aug-Sep 2025 (synthetic)")
    print(sep)
    print()
    print(f"  Model:            {MODEL}")
    print(f"  Data seed:        {SEED} (identical to noise-OFF backtest)")
    print(
        f"  CUSUM:            h={CUSUM_H}, k={CUSUM_K}, "
        f"baseline={BASELINE_SAMPLES}"
    )
    print(
        f"  Control:          noise-OFF first alert {control_first} "
        "== canon (OK)"
    )
    print()
    print(f"  DP noise:         Laplace, epsilon={EPSILON} per daily flush")
    print(
        f"  Batch (FIX-1):    n_batch={N_BATCH} "
        "(REQ-PRIV-010 batch-aware sensitivity)"
    )
    print(f"    b(json_success_rate) = {s_rate}/{EPSILON} = {b_rate}")
    print(f"    b(avg_output_length) = {s_len}/{EPSILON} = {b_len}")
    print(
        f"  Noise seeds:      N={N_NOISE_SEEDS} "
        f"(master seed {NOISE_MASTER_SEED})"
    )
    print()
    print(f"  Detection (first alert strictly before {POSTMORTEM_DATE}):")
    print(
        f"    detected seeds:            {len(detected)}/{N_NOISE_SEEDS} "
        f"({detection_rate:.1f}%)"
    )
    print(
        "    via json_success_rate:     "
        f"{per_metric_detected['json_success_rate']}"
    )
    print(
        "    via avg_output_length:     "
        f"{per_metric_detected['avg_output_length']}"
    )
    print(f"    pre-onset (< {BUG_DATE}, false alarm): {pre_onset}")
    print(
        f"    first alert on {POSTMORTEM_DATE} (not counted): {on_postmortem}"
    )
    print(f"    no alert at all:           {no_alert}")
    print()
    print("  No-bug null control (same noise seeds, phase-0 series):")
    print(
        f"    seeds alerting before {POSTMORTEM_DATE}: "
        f"{null_alerts}/{N_NOISE_SEEDS} ({null_rate:.1f}%)"
    )
    print("    (every null alert is a false alarm by construction)")
    print()
    if detected:
        med = nearest_rank(detected, 50)
        p90 = nearest_rank(detected, 90)
        delay = (med - NOISE_OFF_ALERT_DATE).days
        lead = (POSTMORTEM_DATE - med).days
        print("  First-alert date distribution (detected seeds only):")
        print(f"    min:    {detected[0]}")
        print(f"    median: {med}")
        print(f"    p90:    {p90}")
        print(f"    max:    {detected[-1]}")
        print(
            f"    median delay vs noise-OFF {NOISE_OFF_ALERT_DATE}: "
            f"{delay:+d} days"
        )
        print(f"    median lead vs postmortem {POSTMORTEM_DATE}:  {lead} days")
    else:
        print("  First-alert date distribution: n/a (no seed detected)")
    print()
    print(sep)

    make_figure(detected)
    print(f"  Figure: {FIGURE_PATH.relative_to(REPO_ROOT).as_posix()}")


if __name__ == "__main__":
    main()
