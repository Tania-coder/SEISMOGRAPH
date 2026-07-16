# EXP-1R: DP-Noise-ON Backtest under FIX-1 (Batch-Aware Sensitivity)

**Script:** `scripts/experiment_dp_backtest.py` (`SG_N_BATCH` env var) |
**Data seed:** 42 | **Noise seeds:** N=200 (master seed 1337) |
**CUSUM:** h=5.0, k=0.5, baseline=30 | **Date:** 2026-07-15

Re-run of EXP-1A after FIX-1 (REQ-PRIV-010) merged. This document is
the FIX-1 record; the n=1 historical record is
`dp_backtest_results.md` (unchanged).

## Method delta vs EXP-1A

- **FIX-1 semantics.** `probe/privacy.py` now exposes
  `_metric_sensitivity(metric, n) = _METRIC_SENSITIVITY[metric] / n`
  -- the substitution-DP sensitivity of a mean over n records. The
  experiment models **one flush per day of an n=N_BATCH-record
  canary batch**; `N_BATCH` is read from env var `SG_N_BATCH`.
- **Backward compatibility.** `SG_N_BATCH` unset (n=1) degrades to
  the old worst-case bounds. Verified: stdout is identical to the
  published EXP-1A output except for the new `Batch (FIX-1)` header
  line -- every number matches byte-for-byte (125/200 detected,
  113/200 null, median 2025-08-19).
- Everything else -- data generator, draw order, clamps, 4-decimal
  rounding, seeding, sanity gate (noise-OFF control must reproduce
  2025-08-10) -- is unchanged. Determinism re-verified: each
  condition run twice, stdout byte-identical.

Laplace scales `b = delta_f(n) / epsilon`:

| n | b(json_success_rate) | b(avg_output_length) |
|---|---|---|
| 1 | 0.5 | 4096.0 |
| 100 | 0.005 | 40.96 |
| 200 | 0.0025 | 20.48 |

## Results (200 noise seeds per condition)

| | n=1 (EXP-1A) | n=100 | n=200 |
|---|---|---|---|
| Detected (first alert < 2025-09-17) | 125/200 (62.5%) | **200/200 (100%)** | **200/200 (100%)** |
| -- via `json_success_rate` | 80 | 200 | 200 |
| -- via `avg_output_length` | 71 | 200 | 200 |
| Pre-onset alerts (< 2025-08-05) | 12 | 5 | 2 |
| First alert on 2025-09-17 (not counted) | 5 | 0 | 0 |
| No alert at all | 70 | 0 | 0 |
| **No-bug null control alerting** | 113/200 (56.5%) | 112/200 (56.0%) | 137/200 (68.5%) |

First-alert date distribution (detected seeds only):

| n | min | median | p90 | max | median delay vs noise-OFF 2025-08-10 | median lead vs postmortem |
|---|---|---|---|---|---|---|
| 1 | 2025-07-31 | 2025-08-19 | 2025-09-11 | 2025-09-16 | +9 days | 29 days |
| 100 | 2025-07-31 | 2025-08-11 | 2025-08-27 | 2025-08-29 | +1 day | 37 days |
| 200 | 2025-07-31 | 2025-08-10 | 2025-08-11 | 2025-08-24 | +0 days | 38 days |

Histograms: `dp_backtest_hist_n100.png`, `dp_backtest_hist_n200.png`
(n=1 figure unchanged at `dp_backtest_hist.png`).

## Interpretation (honest reading)

**(a) Detection vs null control.** At n=100 and n=200, detection is
now clearly separated from the null: 100% of seeds alert with the
bug present vs 56.0% / 68.5% on the no-bug series. The EXP-1A
verdict (62.5% vs 56.5%, indistinguishable) does not survive FIX-1:
with batch-aware sensitivity the DP-noised detector finds the
degradation on every noise seed, and the date distribution
concentrates instead of smearing across the horizon (p90 moves
2025-09-11 -> 2025-08-11).

**(b) Alert date.** The DP-ON median first alert is 2025-08-11 at
n=100 (+1 day vs noise-OFF) and 2025-08-10 at n=200 (+0 days; p90
2025-08-11). At n=200 the canonical result -- a seeded backtest
flags it 38 days before the postmortem -- is recovered as the
median over 200 noise seeds.

**The null-control rate is not a DP effect.** The raw null series
(79 phase-0 days, data seed 42, no noise at all) itself fires a
CUSUM alert on 2025-08-19. The null rate therefore measures the
detector's false-alarm behavior on stable data, consistent with the
0.40 per-90-day-window rate in EXP-1C; as DP noise shrinks
(n grows) the per-seed outcomes converge toward that deterministic
false alarm, which is why the null rate *rises* to 68.5% at n=200.
This is a CUSUM/quorum matter (self-starting baseline inflation and
per-window accumulation at h=5.0/k=0.5), not a DP matter, and is
addressed separately.

Mechanically: phase-0 daily sigma is 0.0055 (rate) and 18.3 tokens
(length). DP noise sigma (b*sqrt(2)) at n=100 is 0.0071 / 57.9 and
at n=200 is 0.0035 / 29.0 -- comparable to (rate) or still above
(length) the natural daily variation, but no longer one to three
orders of magnitude above the bug-induced shifts. That is why
detection recovers while residual noise still perturbs borderline
stable windows (see `stable_fp_results_fix1.md`).

## Limitations

1. Synthetic data; same caveat as EXP-1A.
2. One flush/day; the n-record batch is modeled through the
   sensitivity only. Live batch sizes and flush cadence may differ;
   n=100/200 are assumptions about canary volume, not measurements.
3. Single observer, no AgreementScorer quorum.
4. The null control is a single data realization (seed 42) crossed
   with 200 noise seeds; the 56-68.5% rates characterize that
   series, not the population false-alarm rate.

---

*Reproduce: `SG_N_BATCH=100 python3 scripts/experiment_dp_backtest.py`
(and `SG_N_BATCH=200`; unset reproduces EXP-1A numbers exactly).
Deterministic: byte-identical stdout across re-runs, verified.*
