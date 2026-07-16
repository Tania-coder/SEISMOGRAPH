# EXP-1C: Stable-Window False-Positive Verification

**Agent:** Canary (adversarial verification)
**Script:** `scripts/experiment_stable_fp.py` (deterministic; identical stdout on re-run)
**Detector config:** `CUSUMDetector(h=5.0, k=0.5, baseline_samples=30)` — the exact
operating point used by `scripts/anthropic_backtest.py`
**Date:** 2026-07-15

## Verdict up front

**The hypothesis is falsified.** At the default operating point, a stable
provider window alone fires drift alerts in **40%** of 90-day windows, and
DP noise raises that to **60–62%**. The expected result was 0. Nothing was
tuned to change this; the honest rates are reported below and cross-checked
against an independent CUSUM implementation and against CUSUM run-length
theory. The methodology paper must not claim zero false positives for
single-observer, long-horizon monitoring at h=5.0, k=0.5.

## Method

- **Stable data:** 90-day windows synthesized exclusively from the backtest
  generator's phase-0 ("stable baseline") statistics, by importing
  `simulate_day()` / `get_phase()` from `scripts/anthropic_backtest.py` and
  using dates strictly before `BUG_DATE` (2025-05-07 .. 2025-08-04;
  `get_phase(d) == 0` asserted for every day). No generator constants
  duplicated. Metrics: `json_success_rate` (0.990, sigma 0.006, clamped to
  [0,1]) and `avg_output_length` (450.0, sigma 20.0, clamped >= 0).
- **Detector:** fresh `CUSUMDetector(h=5.0, k=0.5, baseline_samples=30)` per
  window; 30 baseline days + 60 monitored days per metric stream.
- **FP definition:** a window is a false positive if ANY of the two streams
  fires at least one alert. A stream is not fed after its first alert
  (production resets post-alert; re-fires would double-count one excursion).
- **DP noise:** replicates `probe.privacy.Aggregator.flush()` verbatim —
  Laplace scale `b = delta_f / EPSILON`, same draw order (length first, then
  rate), same clamps, same 4-decimal rounding. One flush per day.
- **Seeding:** deterministic, disjoint seed bases per condition
  (C1 data 10000+i; C2 noise 20000+i, data fixed at backtest SEED=42;
  C3 data 30000+i, noise 40000+i). 200 runs per condition.

## delta_f provenance

Taken **verbatim** from `probe/privacy.py` (not assumed):

- `EPSILON = 2.0` — line 74
- `_METRIC_SENSITIVITY = {"avg_output_length": 8192.0, "json_success_rate": 1.0}`
  — lines 77–80 (design rationale in module docstring, lines 13–19)
- Resulting Laplace scales: `b = 8192 / 2.0 = 4096.0` for
  `avg_output_length`; `b = 1.0 / 2.0 = 0.5` for `json_success_rate`
  (noise applied in `flush()`, lines 575–594)

No ASSUMPTION flag needed: both sensitivities are defined in code.

## Results (200 windows per condition, 90 days each)

| Condition | FP windows | FP window rate | Alerts: json_success_rate | Alerts: avg_output_length |
|---|---|---|---|---|
| 1. DP OFF, 200 data seeds | 80 / 200 | **0.400** | 44 (22.0% of streams) | 48 (24.0%) |
| 2. DP ON, data seed=42, 200 noise seeds | 120 / 200 | **0.600** | 58 (29.0%) | 84 (42.0%) |
| 3. DP ON, data+noise varying | 124 / 200 | **0.620** | 64 (32.0%) | 85 (42.5%) |

First alerts occur from day 30 (first post-baseline observation) through
day 89; both directions fire. Expected value per task spec was 0 for
conditions 1 and 2.

## Why this is real, not a harness bug

Cross-checked with an independent, hand-rolled Page-CUSUM (no project code):

1. **Known parameters, pure N(0,1), 60 observations, two-sided:** FP rate
   ~0.118 per stream (2000 windows). This matches theory: two-sided
   in-control ARL0 for h=5, k=0.5 is ~465 observations, so
   P(alert in 60 obs) ~ 1 - exp(-60/465) ~ 12%. With two independent
   streams per window, a ~23% window FP rate is the **theoretical floor**
   even with an oracle baseline.
2. **Parameters estimated from 30 samples (the project's actual setup):**
   per-stream FP rate rises to ~0.30 — estimation error in mu0/sigma0
   (chi-squared spread of a 30-sample sigma estimate) roughly doubles the
   false-alarm probability. This is the well-known self-starting CUSUM
   inflation problem.
3. Observed Condition-1 per-stream rate (22–24%) sits between (1) and (2),
   consistent with the additional clamp-at-1.0 truncation of the rate metric.

So Condition 1's 40% is what h=5.0/k=0.5 **actually delivers** over 90 days;
it was invisible in the Anthropic backtest only because that timeline has
just 5 monitored stable days before the bug phase begins (35-day warm-up =
30 baseline + 5 monitored).

## Why DP noise makes it worse (Conditions 2–3, +20 percentage points)

DP noise does **not** merely "add variance the detector standardizes away":

- `avg_output_length`: signal sigma is 20; Laplace b=4096 (noise sigma
  ~5793) swamps it. The post-noise clamp `max(0, .)` sends ~45% of daily
  values to exactly 0 (P(noise < -450) = 0.5*exp(-450/4096)), producing a
  point-mass-plus-heavy-tail distribution. CUSUM with k=0.5 calibrated for
  Gaussian z-scores fires materially more often on Laplace tails
  (excess kurtosis 3): 42% of length streams alerted vs 24% without DP.
- `json_success_rate`: b=0.5 on a [0,1] metric saturates at the clamps;
  the transmitted rate is nearly signal-free at n=1-result flushes.

Conclusion for the paper: at epsilon=2.0 with the current conservative
global-max sensitivity (delta_f=8192), per-day DP noise **does** manufacture
additional false drift alerts at this operating point. The claim "DP noise
alone does not fire alerts" is falsified for the current parameterization.

## Implications for the h=5.0, k=0.5 operating point

- h=5.0, k=0.5 bounds the false-alarm rate per observation, not per window;
  over 60+ monitored days x 2 metrics the cumulative FP probability is
  large by construction. Any paper claim must be phrased per-observation
  (ARL0 ~465 two-sided) or the horizon must be stated.
- `engine/detector.py` already flags the defaults as "starting points only"
  (REQ-ENGINE-006); this experiment quantifies the gap: single-observer,
  90-day, single-metric-pair monitoring needs a higher h, a longer baseline
  (baseline_samples=30 is a major FP contributor), or both.
- The architecture's mitigation is the AgreementScorer quorum
  (`engine/correlation.py`): independent per-org FPs should rarely
  coincide across >= 2 orgs. That defense is NOT tested here and is now
  load-bearing — it should get its own adversarial experiment.
- DP-side mitigations (Phase 1 `delta_f = MAX/n` refinement, larger flush
  batches, per-metric epsilon allocation) directly reduce the +20pp DP
  contribution and are worth prioritizing.

## Limitations

1. **Synthetic, Gaussian-ish generator noise.** Real provider telemetry has
   autocorrelation, weekly seasonality, and heavier tails; the true stable
   FP rate could be higher.
2. **90-day window, one window length.** FP probability grows with horizon;
   these numbers do not transfer to other horizons without rescaling by
   ARL.
3. **Single metric pair.** Production tracks more streams per model tuple;
   window FP rate grows roughly as 1-(1-p)^m in the number of streams m.
4. **Single-observer.** No AgreementScorer quorum gating; these are per-org
   candidate-alert rates, not public-alert rates.
5. **One flush/day at n=1 effective batch.** Larger real batches with
   refined sensitivity (delta_f = MAX/n) would shrink DP noise
   substantially; Conditions 2–3 represent the worst-case Phase-0
   parameterization.

## Reproduce

```
python3 scripts/experiment_stable_fp.py
```

Deterministic: two consecutive runs produce byte-identical stdout
(verified via diff). Lint: ruff 0.15.20 `check` + `format --check` clean.
