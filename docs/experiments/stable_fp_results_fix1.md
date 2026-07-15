# EXP-1R: Stable-Window False Positives under FIX-1 (Batch-Aware Sensitivity)

**Script:** `scripts/experiment_stable_fp.py` (`SG_N_BATCH` env var) |
**Detector:** `CUSUMDetector(h=5.0, k=0.5, baseline_samples=30)` |
**Date:** 2026-07-15

Re-run of EXP-1C after FIX-1 (REQ-PRIV-010) merged. This document is
the FIX-1 record; the n=1 historical record is
`stable_fp_results.md` (unchanged).

## Method delta vs EXP-1C

- **FIX-1 semantics.** DP scale is now
  `b = _metric_sensitivity(metric, N_BATCH) / EPSILON` with
  `_metric_sensitivity(m, n) = _METRIC_SENSITIVITY[m] / n`
  (substitution-DP sensitivity of a mean over n records), modeling
  one flush per day of an n=N_BATCH-record canary batch. `N_BATCH`
  comes from env var `SG_N_BATCH`.
- **Backward compatibility.** `SG_N_BATCH` unset (n=1) reproduces
  the published EXP-1C output byte-for-byte except for the new
  `Batch:` header line (verified by diff): FP window rates
  0.400 / 0.600 / 0.620.
- Windows, generator, FP definition, draw order, clamps, rounding,
  and seeding unchanged. Determinism re-verified at n=100 and
  n=200: two consecutive runs, byte-identical stdout.

## Results (FP window rate, 200 windows x 90 days per condition)

| Condition | n=1 (EXP-1C) | n=100 | n=200 |
|---|---|---|---|
| 1. DP OFF, 200 data seeds | **0.400** | 0.400 | 0.400 |
| 2. DP ON, data seed fixed (42), 200 noise seeds | 0.600 | 0.590 | 0.730 |
| 3. DP ON, data+noise varying | 0.620 | **0.510** | **0.525** |

(Condition 1 does not use noise, so it is identical across columns
by construction.)

## Interpretation (honest reading)

**(c) Does DP-ON FP collapse to the DP-OFF floor (~0.40)? No -- it
moves toward it but does not reach it.** Condition 3 is the
apples-to-apples comparison against Condition 1: 0.620 at n=1 drops
to 0.510 (n=100) and 0.525 (n=200), leaving a residual DP excess of
roughly +0.11-0.13 over the 0.400 floor (binomial 95% CI ~ +/-0.07
per condition, so the residual is at the edge of resolution at
N=200 but consistent across both n values).

Why the residual: FIX-1 shrinks the noise by n, but at these batch
sizes it is still comparable to the generator's phase-0 daily
variation. Noise sigma (b*sqrt(2)) vs data sigma:
`json_success_rate` 0.0071 (n=100) / 0.0035 (n=200) vs 0.0055;
`avg_output_length` 57.9 / 29.0 vs 18.3. On the length channel the
DP noise still exceeds natural variation even at n=200, so
borderline stable windows keep getting tipped over threshold.
The EXP-1C failure mode (clamp point-mass at 0, signal-free rate
channel) is gone; what remains is ordinary variance inflation.

**Condition 2 is no longer a DP-cost measure and its 0.730 at n=200
is expected, not a regression.** The fixed seed-42 window is itself
a false positive with DP OFF (`json_success_rate` alerts on day 49,
direction positive). As noise shrinks, the 200 noise-seed outcomes
converge toward that deterministic outcome, so Condition 2 tends to
1.0 as n grows. It measured DP damage at n=1; at n=100+ it measures
the underlying window. Condition 3 is the meaningful DP-ON number.

**The 0.400 DP-OFF floor is a CUSUM/quorum matter, not a DP
matter, and is addressed separately.** EXP-1C established that
h=5.0/k=0.5 with a 30-sample self-starting baseline delivers ~0.40
FP per 90-day window on stable data with no DP in the loop; FIX-1
neither could nor did change that. Remaining work on the floor
belongs to the detector operating point (higher h, longer baseline)
and the AgreementScorer quorum -- tracked outside REQ-PRIV-010.

## Limitations

1. Synthetic, Gaussian-ish generator; real telemetry caveats from
   EXP-1C apply unchanged.
2. n=100/200 are assumed canary batch sizes, not measurements.
3. Residual DP excess (+0.11-0.13) is near the resolution limit of
   200 windows; a larger N would be needed to bound it tightly.
4. Single observer, single metric pair, 90-day horizon -- as in
   EXP-1C.

## Reproduce

```
SG_N_BATCH=100 python3 scripts/experiment_stable_fp.py
SG_N_BATCH=200 python3 scripts/experiment_stable_fp.py
```

Unset `SG_N_BATCH` reproduces the EXP-1C published numbers exactly.
Deterministic: byte-identical stdout across re-runs (verified).
Lint: ruff 0.15.20 `check` + `format --check` clean on the modified
script.
