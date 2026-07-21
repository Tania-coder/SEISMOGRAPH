# Quorum Scaling + Candidate TTL Calibration Record
# FIX-2 -- AgreementScorer (engine/correlation.py, engine/scorer_redis.py)
# Date: 2026-07-19
# Session: S037
# Status: SYNTHETIC DEFAULTS -- pending real-traffic recalibration

## Policy shipped
- Quorum:      q(M) = max(QUORUM_FLOOR, ceil(QUORUM_FRAC_NUM * M / QUORUM_FRAC_DEN))
- Defaults:    QUORUM_FLOOR = 3, QUORUM_FRAC_NUM = 1, QUORUM_FRAC_DEN = 2
               -> q(M) = max(3, ceil(M/2))
- Candidate/observer TTL: DEFAULT_TTL_NS = 14 days
- M = distinct observer population for a (model_tuple, metric_name) stream
  within the TTL window (via observe() + ingest()); effective population is
  max(observers, agreeing) so a caller that never observes degrades safely to
  the fixed floor.

## Provenance (why these numbers)
Derived from EXP-2 (scripts/experiment_quorum.py, 200 trials, DP ON n=100,
CUSUM h=5.0/k=0.5):
- Fixed quorum=2 gives a 0.86 stable-window PUBLIC-alert FP rate at M=5 --
  an absolute threshold does not hold the boundary as the network grows.
- M=3 / q=3 / TTL=14d -> public FP 0.015 at 36-day incident lead; the
  correlation-first invariant held (single-org burst and Sybil-alone never
  promote).
- Residual: unweighted q=2 collusion (Sybil + 1 honest false alarm) 0.82;
  raising to q=3 pulls it to 0.34.  Reputation weighting + Ed25519 one-org-
  one-key binding are the planned Phase 2 mitigations, out of scope here.

In EXP-2 the 14-day candidate expiry was enforced in the HARNESS because the
engine had no time-window logic.  FIX-2 moves that expiry, plus the metric
scoping and population-scaled quorum, into the engine itself.

## Known limitations
- Defaults are SYNTHETIC (EXP-2 seeded/backtest data), the same posture as the
  CUSUM h=5.0/k=0.5 defaults.  Phase 1 must recalibrate q(M) and the TTL on
  real probe traffic before production tuning.
- A production q(M) schedule against a target public-FP bound (the "Seismo
  bound") requires a labelled quorum-FP dataset that does not yet exist in
  data/drift_labels/.  Until then the floor+proportional form is the interim.
- frac=1/2 is a single proportional term; a per-M calibrated table may replace
  it once labelled data is available (mechanism already parameterised via
  frac_num/frac_den).

## Verification (S037)
- 151 tests pass on a clean GitHub clone (was 134; +17):
  tests/test_agreement_scorer.py (new, 14) covers q(M) scaling, metric
  scoping, TTL expiry, Sybil resistance, and the semantic-only-shift promote
  path; tests/test_gateway.py adds the two-orgs-below-floor regression;
  tests/test_scorer_redis.py rewritten to the ZSET/Lua wiring.
- ruff check + ruff format --check both clean.
