#!/usr/bin/env python3
"""
scripts/experiment_sensitivity.py
==================================
EXP-1B: sensitivity sweep of the CUSUM detector over
(h, k, baseline_samples, sigma multiplier) on the seeded Anthropic
Claude Sonnet 4 backtest (scripts/anthropic_backtest.py).

For every grid point:
  (a) incident timeline (2025-07-01 .. 2025-09-17; bug 2025-08-05,
      escalation 2025-08-29) -> first-alert date on or after the
      bug date, lead time vs the 2025-09-17 postmortem, or
      "missed".  Alerts that fire *before* the bug date are
      pre-onset false alarms: they are counted separately and the
      stream is reset (operational triage analog) so they are
      never credited as detections.
  (b) stable-only window of equal length (79 days of phase-0
      baseline statistics, same generator, same data seed) ->
      false-positive count, split by CUSUM direction (S- =
      degradation-side, S+ = improvement-side).  The alerting
      stream is reset after each event.

Sanity gate: the default operating point (h=5.0, k=0.5,
baseline_samples=30, sigma=1.0) must reproduce the canonical result
-- a seeded backtest flags it 38 days before the postmortem (first
alert 2025-08-10).  The sweep aborts if it does not.

Outputs (docs/experiments/):
  sensitivity_grid.csv      full grid, one row per configuration
  sensitivity_results.md    slice table + findings + limitations
  sensitivity_heatmap.png   h x k lead-time heatmap
                            (sigma=1.0, baseline_samples=30)

Deterministic: data seed fixed at 42; re-runs produce byte-identical
CSV output.

Usage:
  python3 scripts/experiment_sensitivity.py

#SG-TRACE: EXP-1B
#   | assumption: scaling the generator's six Gaussian noise
#     constants is an adequate proxy for probe-noise sensitivity;
#     the misrouting shift magnitudes stay fixed
#   | test: sanity gate must reproduce first alert 2025-08-10 at
#     (h=5.0, k=0.5, baseline=30, sigma=1.0) before any row is
#     written
#SG-TRACE: EXP-1B
#   | assumption: an alert fired before BUG_DATE cannot be a
#     detection of the bug; it is counted as a pre-onset false
#     alarm and the stream is reset
#   | test: no CSV row reports lead > (POSTMORTEM - BUG_DATE) days
"""

from __future__ import annotations

import csv
import random
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.detector import CUSUMDetector  # noqa: E402
from scripts import anthropic_backtest as bt  # noqa: E402

# ---------------------------------------------------------------------------
# Sweep grid
# ---------------------------------------------------------------------------

H_GRID = (3.0, 4.0, 5.0, 6.0, 8.0)
K_GRID = (0.25, 0.5, 0.75, 1.0)
BASELINE_GRID = (10, 30, 50)
SIGMA_GRID = (0.5, 1.0, 2.0)

DEFAULT_CONFIG = (5.0, 0.5, 30, 1.0)
EXPECTED_DEFAULT_ALERT = date(2025, 8, 10)

DAY_NS = 86_400_000_000_000
N_DAYS = (bt.POSTMORTEM_DATE - bt.BASELINE_START).days + 1
MAX_LEAD = (bt.POSTMORTEM_DATE - bt.BUG_DATE).days

_NOISE_NAMES = (
    "BASE_RATE_NOISE",
    "BASE_LEN_NOISE",
    "P1_RATE_NOISE",
    "P1_LEN_NOISE",
    "P2_RATE_NOISE",
    "P2_LEN_NOISE",
)

OUT_DIR = Path(__file__).parent.parent / "docs" / "experiments"
CSV_PATH = OUT_DIR / "sensitivity_grid.csv"
MD_PATH = OUT_DIR / "sensitivity_results.md"
PNG_PATH = OUT_DIR / "sensitivity_heatmap.png"

CSV_FIELDS = (
    "h",
    "k",
    "baseline_samples",
    "sigma_mult",
    "first_alert_date",
    "alert_metric",
    "lead_days_vs_postmortem",
    "missed",
    "pre_onset_alarms",
    "stable_fp_total",
    "stable_fp_neg",
    "stable_fp_pos",
)


# ---------------------------------------------------------------------------
# Generator noise scaling
# ---------------------------------------------------------------------------


@contextmanager
def scaled_noise(mult: float) -> Iterator[None]:
    """Scale the backtest generator's Gaussian noise constants.

    #SG-TRACE: EXP-1B
    #   | assumption: simulate_day reads its noise constants from
    #     module globals on every call, so patching them scales the
    #     noise without duplicating the generator
    #   | test: sigma=1.0 rows match the unpatched backtest exactly
    """
    original = {name: getattr(bt, name) for name in _NOISE_NAMES}
    try:
        for name, value in original.items():
            setattr(bt, name, value * mult)
        yield
    finally:
        for name, value in original.items():
            setattr(bt, name, value)


# ---------------------------------------------------------------------------
# Single-configuration runs
# ---------------------------------------------------------------------------


def run_incident(
    h: float, k: float, baseline: int, sigma_mult: float
) -> tuple[date | None, str | None, int]:
    """Run the incident timeline for one configuration.

    Replicates the observation order of anthropic_backtest.run():
    one simulate_day() call per day, both metrics fed to the
    detector in dict-insertion order.

    Alerts before BUG_DATE are pre-onset false alarms: counted,
    stream reset, never credited as detection.  Detection is the
    first alert on or after BUG_DATE.

    Returns (first_alert_date, first_alert_metric,
    pre_onset_alarms); date/metric are None when no alert fires
    between the bug date and the postmortem date.
    """
    rng = random.Random(bt.SEED)
    detector = CUSUMDetector(h=h, k=k, baseline_samples=baseline)
    first_date: date | None = None
    first_metric: str | None = None
    pre_onset = 0
    with scaled_noise(sigma_mult):
        day = bt.BASELINE_START
        day_num = 0
        while day <= bt.POSTMORTEM_DATE:
            metrics = bt.simulate_day(day, rng)
            ts_ns = day_num * DAY_NS
            for metric_name, value in metrics.items():
                alert = detector.update(
                    bt.MODEL, metric_name, value, timestamp_ns=ts_ns
                )
                if not alert:
                    continue
                if day < bt.BUG_DATE:
                    pre_onset += 1
                    detector.reset(bt.MODEL, metric_name)
                elif first_date is None:
                    first_date = day
                    first_metric = metric_name
            day += timedelta(days=1)
            day_num += 1
    return first_date, first_metric, pre_onset


def run_stable(
    h: float, k: float, baseline: int, sigma_mult: float
) -> tuple[int, int]:
    """Run a stable-only window of N_DAYS days.

    Every day is generated with phase-0 (pre-bug) baseline
    statistics: simulate_day() is called with a date before
    BUG_DATE, so only the phase branch differs from the incident
    run -- the generator and data seed are identical.  After each
    alert the affected stream is reset, so counts are distinct
    alert events, not post-threshold days.

    Returns (fp_negative, fp_positive): degradation-side (S-) and
    improvement-side (S+) false-positive event counts.
    """
    rng = random.Random(bt.SEED)
    detector = CUSUMDetector(h=h, k=k, baseline_samples=baseline)
    fp_neg = 0
    fp_pos = 0
    stable_day = bt.BASELINE_START  # any date < BUG_DATE is phase 0
    with scaled_noise(sigma_mult):
        for day_num in range(N_DAYS):
            metrics = bt.simulate_day(stable_day, rng)
            ts_ns = day_num * DAY_NS
            for metric_name, value in metrics.items():
                alert = detector.update(
                    bt.MODEL, metric_name, value, timestamp_ns=ts_ns
                )
                if alert:
                    if alert.direction == "negative":
                        fp_neg += 1
                    else:
                        fp_pos += 1
                    detector.reset(bt.MODEL, metric_name)
    return fp_neg, fp_pos


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def sanity_gate() -> None:
    """Abort unless the default config reproduces the canonical alert."""
    h, k, baseline, sigma = DEFAULT_CONFIG
    first_date, _, _ = run_incident(h, k, baseline, sigma)
    if first_date != EXPECTED_DEFAULT_ALERT:
        raise SystemExit(
            "SANITY GATE FAILED: default config "
            f"(h={h}, k={k}, baseline={baseline}, sigma={sigma}) "
            f"produced first alert {first_date}, expected "
            f"{EXPECTED_DEFAULT_ALERT}."
        )
    lead = (bt.POSTMORTEM_DATE - first_date).days
    print(
        f"Sanity gate OK: first alert {first_date} "
        f"(lead {lead} days) at default config."
    )


def sweep() -> list[dict[str, object]]:
    """Run the full grid; return one result row per configuration."""
    rows: list[dict[str, object]] = []
    for h in H_GRID:
        for k in K_GRID:
            for baseline in BASELINE_GRID:
                for sigma in SIGMA_GRID:
                    first_date, metric, pre_onset = run_incident(
                        h, k, baseline, sigma
                    )
                    fp_neg, fp_pos = run_stable(h, k, baseline, sigma)
                    missed = first_date is None
                    lead = (
                        (bt.POSTMORTEM_DATE - first_date).days
                        if first_date is not None
                        else None
                    )
                    assert lead is None or lead <= MAX_LEAD
                    rows.append(
                        {
                            "h": h,
                            "k": k,
                            "baseline_samples": baseline,
                            "sigma_mult": sigma,
                            "first_alert_date": first_date,
                            "alert_metric": metric,
                            "lead_days_vs_postmortem": lead,
                            "missed": missed,
                            "pre_onset_alarms": pre_onset,
                            "stable_fp_total": fp_neg + fp_pos,
                            "stable_fp_neg": fp_neg,
                            "stable_fp_pos": fp_pos,
                        }
                    )
    return rows


def write_csv(rows: list[dict[str, object]]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            record = dict(r)
            record["first_alert_date"] = (
                r["first_alert_date"].isoformat()
                if r["first_alert_date"]
                else ""
            )
            record["alert_metric"] = r["alert_metric"] or ""
            record["lead_days_vs_postmortem"] = (
                r["lead_days_vs_postmortem"]
                if r["lead_days_vs_postmortem"] is not None
                else ""
            )
            record["missed"] = str(r["missed"]).lower()
            writer.writerow(record)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _find(
    rows: list[dict[str, object]],
    h: float,
    k: float,
    baseline: int,
    sigma: float,
) -> dict[str, object]:
    for r in rows:
        if (
            r["h"] == h
            and r["k"] == k
            and r["baseline_samples"] == baseline
            and r["sigma_mult"] == sigma
        ):
            return r
    raise KeyError((h, k, baseline, sigma))


def _cfg_str(r: dict[str, object]) -> str:
    return (
        f"h={r['h']}, k={r['k']}, "
        f"baseline={r['baseline_samples']}, "
        f"sigma={r['sigma_mult']}"
    )


def build_markdown(rows: list[dict[str, object]]) -> str:
    detected = [r for r in rows if not r["missed"]]
    missed_rows = [r for r in rows if r["missed"]]
    neg_fp_rows = [r for r in rows if r["stable_fp_neg"] != 0]
    pos_fp_rows = [r for r in rows if r["stable_fp_pos"] != 0]
    fully_fp_free = [r for r in rows if r["stable_fp_total"] == 0]
    pre_onset_rows = [r for r in rows if r["pre_onset_alarms"] != 0]
    leads = sorted(int(r["lead_days_vs_postmortem"]) for r in detected)
    lead_min, lead_max = leads[0], leads[-1]
    neg_fp_short = [r for r in neg_fp_rows if r["baseline_samples"] == 10]
    neg_fp_rest = [r for r in neg_fp_rows if r["baseline_samples"] != 10]
    rest_max_h = max((float(r["h"]) for r in neg_fp_rest), default=0.0)
    rest_max_k = max((float(r["k"]) for r in neg_fp_rest), default=0.0)
    pre_onset_baselines = ", ".join(
        str(b)
        for b in sorted({int(r["baseline_samples"]) for r in pre_onset_rows})
    )

    op = _find(rows, *DEFAULT_CONFIG)
    op_lead = int(op["lead_days_vs_postmortem"])

    slice_all = [
        r
        for r in rows
        if r["baseline_samples"] == 30 and r["sigma_mult"] == 1.0
    ]
    slice_clean = [
        r
        for r in slice_all
        if r["stable_fp_total"] == 0
        and r["pre_onset_alarms"] == 0
        and not r["missed"]
    ]
    best_clean = max(
        slice_clean, key=lambda r: int(r["lead_days_vs_postmortem"])
    )
    best_clean_lead = int(best_clean["lead_days_vs_postmortem"])

    lead_by_h = ", ".join(
        "h={}: {}d".format(
            h, _find(rows, h, 0.5, 30, 1.0)["lead_days_vs_postmortem"]
        )
        for h in H_GRID
    )
    lead_h_lo = int(
        _find(rows, H_GRID[0], 0.5, 30, 1.0)["lead_days_vs_postmortem"]
    )
    lead_h_hi = int(
        _find(rows, H_GRID[-1], 0.5, 30, 1.0)["lead_days_vs_postmortem"]
    )
    lead_by_baseline = ", ".join(
        "baseline={}: {}d".format(
            b, _find(rows, 5.0, 0.5, b, 1.0)["lead_days_vs_postmortem"]
        )
        for b in BASELINE_GRID
    )
    lead_by_sigma = ", ".join(
        "sigma={}: {}d".format(
            s, _find(rows, 5.0, 0.5, 30, s)["lead_days_vs_postmortem"]
        )
        for s in SIGMA_GRID
    )

    md: list[str] = [
        "# EXP-1B -- CUSUM Sensitivity Sweep",
        "",
        "Generated by `scripts/experiment_sensitivity.py` "
        "(deterministic, data seed 42).",
        "",
        f"Grid: h in {list(H_GRID)} x k in {list(K_GRID)} x "
        f"baseline_samples in {list(BASELINE_GRID)} x "
        f"sigma multiplier in {list(SIGMA_GRID)} = "
        f"{len(rows)} configurations.",
        "",
        "## Protocol",
        "",
        "- Generator: `scripts/anthropic_backtest.simulate_day` "
        "(SEED=42), incident window 2025-07-01 .. 2025-09-17 "
        "(79 days); bug 2025-08-05 (~0.8% misrouting), escalation "
        "2025-08-29 (~16%), postmortem 2025-09-17.",
        "- Both metrics (`json_success_rate`, `avg_output_length`) "
        "are fed to `CUSUMDetector` daily; detection is the first "
        "alert on either stream **on or after the bug date**. "
        "Alerts before the bug date are pre-onset false alarms: "
        "counted separately, stream reset, never credited as "
        "detection (maximum honest lead is therefore "
        f"{MAX_LEAD} days).",
        "- Stable-only control: 79 days generated entirely with "
        "phase-0 baseline statistics (same generator, same seed). "
        "False positives are counted as alert events split by "
        "direction (S- degradation-side, S+ improvement-side); "
        "the alerting stream is reset after each event and "
        "re-baselines.",
        "- Sigma multiplier scales the generator's six Gaussian "
        "noise constants; the misrouting shift magnitudes and the "
        "data seed stay fixed. The detector standardises by its "
        "*estimated* baseline sigma, so scaling the noise shrinks "
        "or grows the effective shift-to-noise ratio.",
        "",
        "## Operating point (h=5.0, k=0.5, baseline=30, sigma=1.0)",
        "",
        f"First alert **{op['first_alert_date']}** on "
        f"`{op['alert_metric']}`: a seeded backtest flags it "
        f"**{op_lead} days before the postmortem**. "
        f"Pre-onset alarms: {op['pre_onset_alarms']}. "
        f"Stable-window false positives: "
        f"{op['stable_fp_neg']} degradation-side, "
        f"{op['stable_fp_pos']} improvement-side.",
        "",
        "Trade-off: the operating point detects during the subtle "
        "0.8% phase with zero degradation-side false positives and "
        "zero pre-onset alarms. It is not fully clean on this "
        "seed: one improvement-direction excursion (a run of "
        "high json_success_rate values around stable-window day "
        "49) trips S+ once. If improvement-side alerts are "
        "routed to review rather than paged, (5.0, 0.5) is a "
        "defensible default; the best fully clean config in this "
        f"slice ({_cfg_str(best_clean)}) reaches "
        f"{best_clean_lead}d of lead vs the default's "
        f"{op_lead}d -- on this seed the extra cleanliness costs "
        "no lead, but that is single-seed evidence, not a "
        "recalibration recommendation.",
        "",
        "## h x k slice (sigma=1.0, baseline_samples=30)",
        "",
        "FP column = stable-window false positives, "
        "degradation-side / improvement-side.",
        "",
        "| h | k | first alert | lead (days) | pre-onset | FP (S-/S+) |",
        "|---|---|---|---|---|---|",
    ]

    for h in H_GRID:
        for k in K_GRID:
            r = _find(rows, h, k, 30, 1.0)
            if r["missed"]:
                alert_s, lead_s = "missed", "--"
            else:
                alert_s = str(r["first_alert_date"])
                lead_s = str(r["lead_days_vs_postmortem"])
            fp_s = f"{r['stable_fp_neg']}/{r['stable_fp_pos']}"
            if r["stable_fp_total"]:
                fp_s = f"**{fp_s}**"
            md.append(
                f"| {h} | {k} | {alert_s} | {lead_s} "
                f"| {r['pre_onset_alarms']} | {fp_s} |"
            )

    md += [
        "",
        "## Findings",
        "",
        f"1. **Default confirmed.** (5.0, 0.5, 30, 1.0) alerts on "
        f"{op['first_alert_date']}, {op_lead} days before the "
        "postmortem -- the canonical backtest result -- with zero "
        "degradation-side stable-window false positives.",
        "",
        f"2. **False-positive region.** {len(fully_fp_free)}/"
        f"{len(rows)} configurations are fully FP-free on the "
        f"79-day stable window. Degradation-side (S-) false "
        f"positives split cleanly: {len(neg_fp_short)} of the "
        f"{len(neg_fp_rows)} affected configs have "
        "baseline_samples=10, where the short baseline "
        "underestimates sigma0 and inflates |z| -- these hit "
        "every h in the grid, up to 8.0 (cf. defect D9, which "
        "moved the default from 10 to 30); the remaining "
        f"{len(neg_fp_rest)} all sit in the aggressive corner "
        f"h <= {rest_max_h}, k <= {rest_max_k}. "
        f"Improvement-side (S+) events ({len(pos_fp_rows)} "
        "configs) are dominated by one seeded upward excursion "
        "late in the stable window; at k=0.25 it trips S+ even "
        "at h=8.0.",
        "",
        f"3. **Pre-onset alarms.** {len(pre_onset_rows)} configs "
        "alarm during the 35-day clean warm-up of the incident "
        "timeline, all at baseline_samples="
        f"{pre_onset_baselines}. These were counted as false "
        "alarms and never credited as detections.",
        "",
        f"4. **Lead time vs h** (k=0.5, baseline=30, sigma=1.0): "
        f"{lead_by_h}. Lead degrades gently with h: raising the "
        f"threshold from {H_GRID[0]} to {H_GRID[-1]} costs "
        f"{lead_h_lo - lead_h_hi} lead day(s) on this seed, and "
        "detection stays inside the subtle 0.8% phase at every "
        "h.",
        "",
        f"5. **Lead time vs baseline_samples** (h=5.0, k=0.5, "
        f"sigma=1.0): {lead_by_baseline}. baseline_samples=50 "
        "exceeds the 35-day clean warm-up, so the baseline window "
        "absorbs early Phase-1 days (contaminated mu0/sigma0) and "
        "no alert can fire before day 50 (2025-08-20).",
        "",
        f"6. **Lead time vs sigma** (h=5.0, k=0.5, baseline=30): "
        f"{lead_by_sigma}. Doubling the probe noise halves the "
        "standardised shift of the subtle phase; detection slips "
        "toward the escalation phase.",
        "",
        f"7. **Lead-time range across the grid**: {lead_min} to "
        f"{lead_max} days for all detected configurations "
        f"(maximum honest lead: {MAX_LEAD} days).",
        "",
    ]
    if missed_rows:
        md.append(
            "8. **Missed detections** (no alert between bug date "
            "and postmortem, in this DP-noise-free setting):"
        )
        for r in missed_rows:
            md.append(f"   - {_cfg_str(r)}")
    else:
        md.append(
            "8. **Missed detections**: none. Every configuration "
            "in the grid alerts between the bug date and the "
            "postmortem in this DP-noise-free setting; the severe "
            "16% escalation phase is large enough to trip even "
            "(h=8.0, k=1.0) at doubled noise."
        )
    md += [
        "",
        "## Limitations",
        "",
        "1. **Synthetic data.** All numbers derive from a seeded "
        "Gaussian reconstruction of the public postmortem "
        "timeline, not from recorded probe traffic. This is a "
        "backtest: a seeded backtest flags the incident 38 days "
        "before the postmortem at the default config -- it is "
        "not a live catch.",
        "2. **Single observer.** No AgreementScorer quorum "
        "gating; a real deployment requires >= 2 independent "
        "orgs before a public alert.",
        "3. **No DP noise.** Live probes add Laplace noise "
        "(epsilon=2.0), which would delay alerts by an estimated "
        "1-3 days; the DP sweep is a separate experiment.",
        "4. **Single seed.** One 79-day stable window per config; "
        "FP counts are event counts on that path, not ARL0 "
        "estimates. The improvement-side excursion in finding 2 "
        "is one draw, not a rate.",
        "5. **Sigma proxy.** The sigma multiplier scales all six "
        "noise constants jointly; real probe noise is unlikely "
        "to scale uniformly across metrics and phases.",
        "",
        "*Reproducible: `python3 scripts/experiment_sensitivity.py`*",
        "",
    ]
    return "\n".join(md)


def make_heatmap(rows: list[dict[str, object]]) -> None:
    """h x k lead-time heatmap at sigma=1.0, baseline_samples=30."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    grid: list[list[float]] = []
    for h in H_GRID:
        line: list[float] = []
        for k in K_GRID:
            r = _find(rows, h, k, 30, 1.0)
            line.append(
                float("nan")
                if r["missed"]
                else float(int(r["lead_days_vs_postmortem"]))
            )
        grid.append(line)

    vals = [v for line in grid for v in line if v == v]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or 1.0

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.set_facecolor("0.85")
    im = ax.imshow(grid, cmap="viridis", vmin=vmin, vmax=vmax)

    for i, h in enumerate(H_GRID):
        for j, k in enumerate(K_GRID):
            r = _find(rows, h, k, 30, 1.0)
            fp_total = int(r["stable_fp_total"])
            if r["missed"]:
                ax.text(
                    j,
                    i,
                    "missed",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="black",
                )
            else:
                lead = int(r["lead_days_vs_postmortem"])
                frac = (lead - vmin) / span
                color = "black" if frac > 0.55 else "white"
                label = f"{lead}d"
                if fp_total:
                    label += f"\nFP {r['stable_fp_neg']}/{r['stable_fp_pos']}"
                ax.text(
                    j,
                    i,
                    label,
                    ha="center",
                    va="center",
                    fontsize=10,
                    color=color,
                )
            if fp_total:
                ax.add_patch(
                    Rectangle(
                        (j - 0.5, i - 0.5),
                        1.0,
                        1.0,
                        fill=False,
                        hatch="///",
                        edgecolor="crimson",
                        linewidth=1.2,
                    )
                )

    ax.set_xticks(range(len(K_GRID)), [str(k) for k in K_GRID])
    ax.set_yticks(range(len(H_GRID)), [str(h) for h in H_GRID])
    ax.set_xlabel("k (slack)")
    ax.set_ylabel("h (threshold)")
    ax.set_title(
        "EXP-1B: CUSUM lead time vs postmortem (days)\n"
        "sigma=1.0, baseline_samples=30, seed 42"
    )
    fig.colorbar(im, ax=ax, label="lead time (days)")
    fig.text(
        0.01,
        0.01,
        "hatched = stable-window false positive(s), "
        "S-/S+ counts shown; grey = missed detection",
        fontsize=8,
    )
    fig.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sanity_gate()
    rows = sweep()
    write_csv(rows)
    MD_PATH.write_text(build_markdown(rows), encoding="utf-8")
    make_heatmap(rows)

    detected = [r for r in rows if not r["missed"]]
    missed = [r for r in rows if r["missed"]]
    fp_free = [r for r in rows if r["stable_fp_total"] == 0]
    neg_clean = [r for r in rows if r["stable_fp_neg"] == 0]
    pre_onset = [r for r in rows if r["pre_onset_alarms"] != 0]
    leads = sorted(int(r["lead_days_vs_postmortem"]) for r in detected)
    print("EXP-1B sweep complete")
    print(
        f"  configs: {len(rows)}  detected: {len(detected)}  "
        f"missed: {len(missed)}"
    )
    print(
        f"  stable-window fully FP-free: {len(fp_free)}/{len(rows)}  "
        f"degradation-side clean: {len(neg_clean)}/{len(rows)}"
    )
    print(f"  configs with pre-onset alarms: {len(pre_onset)}")
    print(f"  lead range (detected): {leads[0]}..{leads[-1]} days")
    print("  csv:     docs/experiments/sensitivity_grid.csv")
    print("  report:  docs/experiments/sensitivity_results.md")
    print("  heatmap: docs/experiments/sensitivity_heatmap.png")


if __name__ == "__main__":
    main()
