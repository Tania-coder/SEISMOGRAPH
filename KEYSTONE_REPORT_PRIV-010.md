# KEYSTONE REPORT — FIX-1 / REQ-PRIV-010: batch-aware DP sensitivity

Task: implement the REQ-PRIV-010 refinement (delta_f = MAX/n) that
EXP-1A/1C identified as the root cause of single-probe DP-ON detection
failure. Branch (to be created by Tatiana): seismograph/task-priv-010.
Date: 2026-07-15 (S035c). Status: DRAFT — awaiting signature.

---

## 1. Provenance

AI-generated (Claude/Cowork, Aegis profile; EXP-1R re-run via subagent):
- probe/privacy.py — MODIFIED: new _metric_sensitivity(metric, n)
  (substitution-DP sensitivity of a bounded mean, delta_f = base/n);
  flush() now scales noise by n = len(results); module docstring +
  REQ-PRIV-010 trace updated. EPSILON=2.0 and draw order unchanged.
- tests/test_dp_sensitivity.py — NEW: 7 tests (DS1-DS6), property +
  adversarial.
- scripts/experiment_dp_backtest.py, experiment_stable_fp.py —
  MODIFIED: SG_N_BATCH env parameter (default 1 keeps EXP-1 numbers
  byte-reproducible); figures suffixed per n.
- docs/experiments/dp_backtest_results_fix1.md,
  stable_fp_results_fix1.md, dp_backtest_hist_n100.png, _n200.png — NEW.
Human-edited: none yet.

## 2. Verification summary

- Full suite: 134 passed (127 existing + 7 new) on a verified-clean
  sandbox copy; ruff==0.15.20 check + format --check clean on all
  touched Python. HOST gate (py -3.10 -m pytest -q; ruff x2) is
  MANDATORY before PR — sandbox is advisory (mount served corrupted
  reads of privacy.py this session; recovered via in-context
  reconstruction; every delivered file Read-tool-verified on host).
- DP math: substitution DP, n fixed and public (result_count is
  transmitted in the clear). Replacing one record moves a bounded mean
  by <= MAX/n. n=1 degrades exactly to the former worst-case bounds —
  the fix can only tighten noise, never weaken the guarantee. Privacy
  budget semantics (epsilon=2.0/flush, DPAccountant) untouched.
- Tests: DS1 exact inverse-n scaling; DS2 n=1 == legacy bounds;
  DS3/DS4 invalid n / unknown metric rejected; DS5a Laplace MAD == b*ln2
  at the n=1 worst-case scale (mechanism-level, clamp-free); DS5b flush
  MAD matches delta_f/eps at n=100; DS6 adversarial 100x noise-floor
  collapse, flushed rate MAD < 0.01 (below a 0.8%-scale drift signal).
- EXP-1R (backward compat + effect):
  - SG_N_BATCH unset: EXP-1 published numbers reproduced byte-for-byte.
  - Incident detection (200 noise seeds): 62.5% (n=1) -> 100% (n=100,
    n=200). Median first alert: 2025-08-19 -> 2025-08-11 (n=100) ->
    2025-08-10 (n=200). At n=200 the canon result — a seeded backtest
    flags it 38 days before the postmortem — is recovered as the median
    under DP noise.
  - Stable-window FP: DP-ON excess over the DP-OFF floor shrinks from
    +0.22 to +0.11-0.13 (C3). The 0.400 DP-OFF floor itself is a
    CUSUM/quorum matter (EXP-2), not a DP matter.

## 3. Defects caught and fixed

- Test-design defect (caught by failing gates, then root-caused):
  first version of DS5/DS6 measured noise scale through flush()'s
  clamps; max(0,.) and [0,1] truncation understate the scale — at
  raw_rate=1.0 the clamp zeroes every positive draw (median |dev|
  exactly 0.0). Fixed: mechanism-level assertions use _laplace_noise
  directly; flush-level assertions operate at raw_rate=0.5 / n=100
  where clamping is negligible. The defect and rationale are recorded
  in the test module docstring.
- Incidental: experiment script overwrote dp_backtest_hist.png on
  every run; non-default n now writes suffixed figures, preserving the
  EXP-1 historical figure.
- Process: sandbox mount served corrupted reads of freshly-edited
  privacy.py (stable-but-wrong truncated snapshot; also 14 trailing NUL
  bytes on a gateway/auth.py copy). All gates were run on a
  reconstructed clean copy; all deliverables verified via host-side
  Read tool.

## 4. Known limitations

- Substitution-DP model assumes n is fixed and public per flush; n is
  probe-controlled. If a deployment treats individual canary responses
  as add/remove-adjacent secrets, the bound differs — documented in
  the docstring; acceptable for canary aggregates (no user data).
- Residual DP-ON stable-window FP excess (~+0.12 at n=200) is at the
  edge of resolution at 200 seeds; not fully collapsed to the DP-OFF
  floor because length-channel noise sigma still exceeds data sigma.
- The 0.400 DP-OFF FP floor stands (CUSUM/ARL0); single-observer
  claims remain untenable — EXP-2 (multi-observer quorum) is the
  required follow-up and is now unblocked.
- Live Track-1b flushes have tiny n (result_count=3): near-worst-case
  noise persists there until the live suite grows.

## 5. Accountability statement

Implementation and verification by Claude (Cowork, Aegis profile).
Git operations, host gate, and merge: Tatiana (PowerShell).

Signed: ______________________ (Tatiana Radchenko) Date: __________

## 6. Methodology note (process improvement)

The failing first version of DS5/DS6 was caught because the gate ran
the NEW tests before delivery, not just the pre-existing 127. Standing
suggestion: for statistical tests, always derive the expected estimator
analytically under the SYSTEM's transformations (clamps, rounding),
not the raw mechanism — or test the mechanism directly. Clamp-aware
test design is now documented in the test module for reuse.
