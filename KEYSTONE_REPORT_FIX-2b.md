# KEYSTONE REPORT — FIX-2b: analytical quorum schedule (the "Seismo bound")

Task: replace the FIX-2 synthetic proportional quorum `q(M)=max(3, ceil(M/2))`
with a schedule derived from an explicit false-positive / detection-power
model, and resolve whether the FIX-2 scaling was correctly motivated.
Date: 2026-07-22 (S039). Status: UNSIGNED — awaiting Tatiana host gate + sign.

This report SUPERSEDES the scaling headline of KEYSTONE_REPORT_FIX-2 (§4.2).
The FIX-2 candidate-TTL, metric-scoping, and observer-population machinery are
unchanged and remain in force; only the q(M) *slope* is recalibrated.

---

## 1. Provenance

AI-generated (Claude/Cowork, lead pass), decision approved by Tatiana:
posture = "gentle hedge" (flat near-term, gentle rise as an honest hedge),
chosen after an adversarial verification pass on the model.

- engine/correlation.py — `QUORUM_FRAC_DEN` 2 -> 3 (the entire code delta);
  module policy note + docstrings rewritten to the Seismo-bound rationale; the
  `BayesianOnlineDetector "(LIVE)"` docstring label corrected to
  "(IMPLEMENTED, not wired)" — the live candidate generator is Page-CUSUM
  (gateway/main.py wires `CUSUMDetector`).
- engine/scorer_redis.py — no code change; the Lua reads `frac_den` from ARGV,
  so the constant flows to both backends and parity holds by construction.
- tests/test_agreement_scorer.py — `test_required_quorum_scaling` rewritten to
  the ceil(M/3) schedule (+ a `frac_den=2` legacy-recovery assertion);
  `test_quorum_scales_with_population` knee moved 7 -> 10, adds a flat-at-M=9
  case. ADV-a / ADV-b tests unchanged.
- tests/test_scorer_redis.py — Lua-eval ARGV `frac_den` 2 -> 3.
- tests/test_gateway.py — q(M=3) comment formula updated (assertion unchanged).
- data/drift_labels/quorum_seismo_bound.md — full derivation + tables + caveats.
- scripts/experiment_quorum_bound.py, scripts/quorum_seismo_pick.py — the
  deterministic derivation (exact binomial tails; no RNG).
- This report.

No git operations performed (hard rule: git only from Tatiana's PowerShell).
Work done on a fresh GitHub clone (base 2fc6108); files delivered to the
working tree via the host bridge, no mount writes.

## 2. Contract (Stage 1 intake)

Goal: the quorum slope must reflect the real objective — minimise false
NEGATIVES subject to a public-FP budget — not the FIX-2 assumption that FP
grows fastest as the network grows.

Acceptance criteria -> test contract:
- Model FP as `Binomial(M, p)` and power as `Binomial(M, d)`; find the feasible
  q-band `[q_min(p,beta), q_max(d,gamma)]` for M=1..20.
- Anchor p to the LIVE detector (CUSUM ARL0), not a guess; derive the TTL band.
- Pick the gentlest schedule expressible in the shipped mechanism that (C1) is
  flat at the floor across the near-term horizon, (C2) holds honest-noise FP,
  (C3) hedges the estimation x correlation worst case, (C4) stays within the
  power ceiling.
- No regression: behaviour for the M the network actually has (<=9) is
  unchanged.

Adversarial cases (Constitution-mandated):
(a) Sybil/poisoned probe — floor=3 keeps one Sybil + one honest false alarm
    below quorum; fabricated observers only RAISE q(M) (defensive). The
    at-the-floor residual (1 Sybil + floor-1 honest) is unchanged from FIX-2
    and remains a Phase-2 reputation-weighting job, NOT this layer. The
    proportional term provides no adversarial headroom — stated explicitly.
(b) Provider-side semantic shift with NO latency/uptime signal — three honest
    orgs agreeing within TTL MUST still promote. ceil(M/3) keeps q=3 across the
    near-term horizon, so ADV-b (`test_semantic_only_shift_promotes`) holds; the
    reversal STRENGTHENS this (ceil(M/2) had raised q to 4 at M=7, a false-
    negative liability the model exposed).

## 3. Verification summary

- Gate on a clean GitHub clone (base 2fc6108): `ruff==0.15.20 check` clean,
  `ruff format --check .` clean (54 files), `pytest -q` = **151 passed**
  (unchanged count; assertions updated, no tests added/removed). Host gate on
  Tatiana's machine remains mandatory pre-commit.
- Independent adversarial review of the MODEL (not just the code): VERDICT
  SURVIVES-WITH-CAVEATS. Pure positive correlation cannot break the reversal at
  the anchored p (beta-binomial FP(M=10,q=3) ceiling 0.040 < 0.05 for all rho).
  The residual risk is p under-estimation (baseline estimation inflates median
  p to ~0.074) combined with common-mode correlation rho~=0.08 at M>=10 — which
  ceil(M/3) hedges (worst-case FP 0.036/0.046/0.032 at M=10/15/20).
- Backend parity: unchanged; the single constant feeds both the in-process
  scorer and the Redis Lua.

## 4. Headline results — honest, unsoftened

1. **FIX-2's scaling was mis-motivated.** The binding constraint is detection
   POWER (false negatives), not FP. At realistic p the shipped `ceil(M/2)`
   suppressed FP to 1e-6..1e-12 while dropping genuine-drift promotion to
   0.34–0.95; it demanded a majority of the whole population agree, unreachable
   under sparse canary coverage.
2. **The schedule is now derived, not guessed.** `q(M)=max(3, ceil(M/3))` is the
   gentlest form passing near-term flatness + honest-noise FP + the worst-case
   FP hedge, inside the power ceiling. Knee at M=10 — exactly where the
   adversarial review located the thin margin.
3. **14-day TTL is now analytically justified** (was synthetic): at ~1/day
   cadence it sits in the feasible band [~5 d, 25.6 d]. Operational rule:
   >~1.5 samples/day/metric pushes 14 d out of band.
4. **A docstring bug was fixed**: correlation.py labelled BOCD "LIVE" while the
   gateway wires CUSUM. The p-anchor is valid only for the wired detector; this
   is now stated in code and here.

## 5. Known limitations / follow-ups

- p (~0.028) and rho (0.1 allowance) are model inputs, not measurements. Real
  probe traffic must size both; the schedule shape holds, the operating point
  does not until then. (Same posture as the CUSUM h/k defaults.)
- The estimation x correlation joint worst case has thin margin at M>=10;
  ceil(M/3) hedges but does not eliminate it. Reputation weighting + Ed25519
  binding (Phase 2) are the real mitigations against a correlated adversary.
- d modelled as iid Bernoulli is a simplification (coverage is structural);
  absolute power numbers are optimistic but the direction reinforces the
  reversal.
- This layer still does not calibrate against a real labelled quorum-FP dataset
  ("the Seismo bound" in the strict sense) — that needs a multi-org network to
  exist first (distribution / reach, tracked separately). FIX-2b is the
  analytical bound available before that data exists.

## 6. Sign-off

- [x] Tatiana: host gate green (ruff x2 + pytest 151) on
      seismograph/task-fix-2b; squash-merged to main (be8dc5f), pushed
      (2fc6108..be8dc5f); signed.
      — Tatiana Radchenko, 2026-07-22 (S039)
      Sandbox clean-clone gate (Claude, base 2fc6108): ruff check + ruff
      format --check clean (54 files), 151 passed; near-term behaviour
      identical to FIX-2 for M<=9 (schedules diverge only at M>=10).
