# KEYSTONE REPORT — EXP-1: DP-noise backtest + CUSUM sensitivity + stable-window FP

Task: close the methodology paper's "THE missing experiment" gap
(docs/methodology_paper_outline.md §5, §6, §10.1).
Date: 2026-07-15 (S035c, interim session). Status: SIGNED.

---

## 1. Provenance

AI-generated (three parallel subagents + lead verification pass, Claude/Cowork):
- scripts/experiment_dp_backtest.py (EXP-1A, 396 lines)
- scripts/experiment_sensitivity.py (EXP-1B, 713 lines)
- scripts/experiment_stable_fp.py (EXP-1C, 260 lines)
- docs/experiments/: dp_backtest_results.md + dp_backtest_hist.png,
  sensitivity_results.md + sensitivity_grid.csv + sensitivity_heatmap.png,
  stable_fp_results.md
- This report.

Human-edited: none yet. No existing file modified (verified via mtime sweep:
only the three new scripts + docs/experiments/ carry 2026-07-15 timestamps).
No git operations performed (hard rule: git only from Tatiana's PowerShell).

## 2. Verification summary

- Reproducibility: each script run twice by its agent (byte-identical output),
  then re-run independently by the lead — all headline numbers reproduced
  exactly (62.5%/56.5% for 1A; sanity gate 2025-08-10 + 71/180 FP-free for 1B;
  0.400/0.600/0.620 for 1C).
- Sanity gates: both 1A and 1B hard-fail unless the noise-OFF default config
  reproduces first alert 2025-08-10 (38-day lead). Both passed.
- Lint: ruff==0.15.20 check + format --check clean on all three scripts
  (agent pass on /tmp copies + independent lead pass). CI/host pytest not run:
  zero existing files touched; suite (127) unaffected by construction.
  HOST gate before any commit remains mandatory.
- delta_f provenance: taken verbatim from probe/privacy.py
  (EPSILON=2.0 L74; _METRIC_SENSITIVITY avg_output_length=8192.0,
  json_success_rate=1.0 L77-80; scale b=delta_f/EPSILON). No assumptions.
  1A reuses _laplace_noise itself plus flush()'s draw order/clamps/rounding.

## 3. Headline results — honest, unsoftened

1. **EXP-1B (DP OFF).** Default operating point (h=5.0, k=0.5, baseline=30,
   sigma=1.0) confirmed: first alert 2025-08-10 — a seeded backtest flags it
   38 days before the postmortem. Grid: 180/180 configs detect before the
   postmortem; lead range 19-43 d; 71/180 fully FP-free on the stable window;
   baseline_samples=10 causes 42/51 S- FPs (re-validates the D9 10->30 fix);
   baseline=50 overruns the clean warm-up and craters lead to 22 d.
2. **EXP-1C (stable window, 200 seeds).** The per-window zero-FP claim is
   **falsified** at the default operating point over 90 days: FP window rate
   0.400 (DP OFF), 0.600 (DP ON, noise seeds), 0.620 (DP ON, both varying).
   Cross-checked against known CUSUM theory (ARL0 ~ 465 per stream at h=5,
   k=0.5 => ~23% two-stream/90-day floor; 30-sample self-starting baseline
   inflates further). Detector behaviour, not a harness bug. 1B's single-seed
   "clean" stable window is consistent — single-seed FP counts are not ARL0.
3. **EXP-1A (DP ON incident backtest, 200 noise seeds).** Detection 62.5%
   vs no-bug null control 56.5% — statistically indistinguishable at N=200.
   **The 38-day single-probe result does not survive Phase-0 DP noise.**
   Cause: worst-case sensitivity bounds (b_len=4096 vs signal sigma ~20;
   b_rate=0.5 on a [0,1] metric) drown the signal. The outline's prior
   "1-3 day expected delay" estimate is falsified (median conditional delay
   +9 d, and detection ~= noise floor).

**Net implication for the paper:** the honest claim set is (a) 38-day lead is
a DP-OFF, default-config seeded result — robust across the (h,k) grid;
(b) single-observer/single-window claims are untenable — the correlation-first
quorum gate (already an architectural invariant) is now LOAD-BEARING and must
be demonstrated, making the multi-observer quorum simulation (outline §10.2)
mandatory, not optional; (c) Phase-0 DP sensitivity bounds need the
REQ-PRIV-010 refinement (delta_f = MAX/n; n=100 => b_len~41, b_rate=0.005)
and/or multi-flush aggregation before single-probe DP-ON detection is viable.
This strengthens, not weakens, the paper: the system's own design (quorum)
is exactly what the failure mode requires.

## 4. Defects caught and fixed

- 1B: initial version credited baseline-phase alerts as detections (fake
  "64-day lead"). Fixed: pre-onset alarms counted separately + stream reset;
  detection defined as first alert on/after BUG_DATE; lead asserted <= 43.
- 1B: flat FP count hid that the default's only single-seed stable FP is
  improvement-direction (S+). Fixed: FP split by direction in CSV/table/map.
- 1A: initial design lacked a false-alarm control; the added no-bug null
  (same 200 noise seeds on phase-0 series) became the load-bearing result.
- 1C: initial ruff I001/format violations; fixed, output unchanged.
- Mount coherence (process): an Edit-tool host write left the sandbox with a
  stale truncated view (script silently ran zero lines) — earlier diffs were
  comparing stale artifacts. Recovered via full heredoc rewrite + re-run.
  RULE-1 (heredoc for large writes) re-confirmed the hard way.

## 5. Known limitations

- Synthetic seeded reconstruction of one incident (one bug of three);
  Gaussian-ish noise; single metric pair; 79/90-day windows.
- Single observer throughout — quorum/AgreementScorer path NOT exercised;
  it is now the critical untested component.
- 1B FP counts are single-seed (not ARL0 estimates); 1C provides the
  multi-seed rates.
- Sigma multiplier scales all six generator noise constants jointly.
- DP-ON results use Phase-0 worst-case sensitivity bounds by design.

## 6. Accountability statement

Experiments executed by Claude (Cowork; three parallel subagents, lead
verification pass). No git ops; all repo mutations are new files only.

Signed: Tatiana Radchenko Date: 2026-07-15
(signature entered by Claude at Tatiana's explicit instruction,
post-merge of PR #14)

## 7. Methodology note (process improvement)

Parallel-agent adversarial pairing worked: 1C independently falsified the
zero-FP assumption that 1A/1B alone would have left implicit. Suggested
improvement: for every future statistical claim, spawn the null-hypothesis /
falsification agent FIRST (before the headline experiment), so the control
defines the bar the headline result must clear — this session it was
retrofitted mid-flight by 1A only after 1C's design surfaced the issue.
