# Quorum Schedule Calibration Record — the "Seismo bound"

# FIX-2b — AgreementScorer (engine/correlation.py, engine/scorer_redis.py)

# Date: 2026-07-22

# Session: S039

# Status: ANALYTICALLY DERIVED — supersedes the FIX-2 synthetic frac=1/2.

#         Point-estimate parameters (p, TTL) still pending real-traffic

#         recalibration; the schedule SHAPE is now model-derived, not ad hoc.

## Policy shipped (FIX-2b)

- Quorum: `q(M) = max(QUORUM_FLOOR, ceil(QUORUM_FRAC_NUM * M / QUORUM_FRAC_DEN))`
- Defaults: `QUORUM_FLOOR = 3`, `QUORUM_FRAC_NUM = 1`, `QUORUM_FRAC_DEN = 3`
  -> **`q(M) = max(3, ceil(M/3))`** (FIX-2 shipped `ceil(M/2)`; frac_den 2 -> 3).
- Candidate/observer TTL: `DEFAULT_TTL_NS = 14 days` (unchanged; now validated
  analytically — see §TTL band).
- The only code delta vs FIX-2 is the single constant `QUORUM_FRAC_DEN`.
  Both backends read it (the Redis Lua computes `ceil(fnum*M/fden)` from ARGV),
  so the in-process and Redis scorers stay in parity by construction.

## The model (why a schedule, not a guess)

For one `(model_tuple, metric_name)` stream watched by M distinct observer orgs
inside one candidate-TTL window:

- **Null (no real drift):** each org independently emits a false change-point
  candidate with probability `p` (per-org, per-TTL-window). Coincident false
  candidates `X ~ Binomial(M, p)`. Public false-positive `FP(M,q,p) = P(X>=q)`.
- **Real provider-side drift:** each watching org detects with probability `d`.
  Agreeing detectors `Y ~ Binomial(M, d)`. Detection power `POW = P(Y>=q)`.

A public alert needs `>= q` of M orgs holding a live candidate on the same
metric within TTL. q(M) must satisfy BOTH: `FP <= beta` (suppress coincidental
false alarms) and `POW >= 1-gamma` (still surface genuine minority-detected
drift). Feasible band `q_min(p,beta) <= q <= q_max(d,gamma)`. Hard floor q>=2
(correlation-first: a single org is never promoted).

Derivation script (deterministic, exact binomial tails, no RNG):
`scripts/experiment_quorum_bound.py` and `scripts/quorum_seismo_pick.py`.

## Headline finding — the binding constraint is POWER, not FP

At realistic small p the false-positive side is trivially satisfied; the
shipped `ceil(M/2)` (majority rule) was mis-motivated:

| M | shipped ceil(M/2) | FP(p=0.028) | POW(d=0.7) | ceil(M/3) | POW(d=0.7) |
|---|---|---|---|---|---|
| 3 | 3 | 8e-6 | 0.343 | 3 | 0.343 |
| 5 | 3 | 8e-5 | 0.837 | 3 | 0.837 |
| 7 | 4 | 5e-6 | 0.874 | 3 | 0.971 |
| 10 | 5 | 7e-7 | 0.953 | 4 | 0.998 |
| 15 | 8 | 1e-10 | 0.950 | 5 | 1.000 |
| 20 | 10 | 2e-12 | 0.983 | 7 | 1.000 |

`ceil(M/2)` suppressed FP by 5–10 orders of magnitude below any budget while
eroding detection power: it demanded a MAJORITY of the *whole* watching
population agree, which is structurally unreachable when only a minority of
canaries cover the affected capability. The correct objective flips the FIX-2
framing: minimise false negatives subject to an FP budget, not the reverse.

## Anchoring p to the live detector

- **Live detector is Page-CUSUM** (`engine/detector.py`, wired in
  `gateway/main.py`). ARL0 ~= 500 obs/false-alarm at h=5/k=0.5, two-sided
  (S+ OR S-); an independent simulation put the two-sided ARL0 at 496 — the
  right figure (the one-sided table value ~938 would have halved p and been
  too optimistic). BOCD is implemented but NOT on the live path; if it is
  wired later (hazard 1/200), p must be re-anchored to it.
- `p(window) = 1 - exp(-cadence * TTL / ARL0)`:

  | cadence/day | p(14d) |
  |---|---|
  | 0.5 | 0.014 |
  | 1.0 | 0.028  <- anchored operating point |
  | 2.0 | 0.054 |
  | 4.0 | 0.106 |

## TTL band (14 days is now analytically justified)

- Lower bound: `TTL >= cross-org detection spread` so honest orgs firing on the
  SAME real drift co-occur in-window. Backtest onset->first-alert spread ~5 d.
- Upper bound: `TTL <= ARL0 * ln(1/(1-beta)) / cadence` to hold p under budget.
- At cadence 1/day: band = **[~5 d, 25.6 d]**; 14 d sits mid-band. At 2/day the
  upper bound falls to 12.8 d and 14 d leaves the band -> sampling faster than
  ~1.5/day/metric requires shortening TTL or raising the floor.

## Why ceil(M/3) and not flat q=3 (the adversarial-review caveat)

An independent adversarial review (S039) tried to refute the reversal. Result:
SURVIVES-WITH-CAVEATS. Pure positive correlation, with p correctly anchored,
cannot break flat q=3 (beta-binomial FP(M=10,q=3) ceiling 0.040 < 0.05 for all
rho). BUT p is not a known constant: baseline estimation from 30 samples drops
the *median* per-stream ARL0 to ~182 (p ~= 0.074), and at that inflated p a
common-mode correlation of `rho ~= 0.08` pushes FP(M=10, q=3) past beta=0.05.

`ceil(M/3)` is the gentlest schedule that hedges this worst case while keeping
power. Worst-case beta-binomial FP (p_hi=0.074, rho=0.1):

| M | ceil(M/3) | worst-case FP | POW(d=0.5, conservative) |
|---|---|---|---|
| 10 | 4 | 0.036 | 0.83 |
| 15 | 5 | 0.046 | 0.94 |
| 20 | 7 | 0.032 | 0.94 |

Flat q=3 and ceil(M/4) both breach the worst-case FP at M>=15 (0.084 / 0.086);
`ceil(M/2)` holds FP but collapses power (0.62/0.50/0.59 at d=0.5). `ceil(M/3)`
is the unique gentle form that passes near-term flatness + honest FP + the
worst-case FP hedge, staying inside the power ceiling throughout.

## floor = 3 is retained for an ADVERSARIAL reason, not a statistical one

The FP model does not require the floor (q=2 already holds honest-noise FP).
Floor 3 means one Sybil identity plus a single honest false alarm cannot reach
quorum. The proportional term gives NO additional headroom against a
colluding/correlated adversary as M grows — that is the job of reputation
weighting + Ed25519 one-org-one-key binding (Phase 2), not this layer.

## Known limitations / follow-ups

- **p and rho are still un-measured.** The schedule SHAPE is model-derived; the
  operating p (~0.028) is anchored to CUSUM ARL0 under an assumed ~1/day
  cadence, and rho (correlation allowance 0.1) is a design choice. Real probe
  traffic must measure both; the mechanism (frac_num/frac_den, floor, ttl_ns)
  is fully parameterised so a recalibrated schedule drops in.
- **Estimation x correlation joint worst case has thin margin at M>=10.** The
  point estimate is safe; ceil(M/3) hedges the joint case but does not
  eliminate it. Reputation weighting (Phase 2) is the real mitigation.
- **d as iid Bernoulli is a simplification** (detection is really canary
  coverage, structural). This makes the absolute power numbers optimistic but
  pushes the optimal q DOWN, reinforcing (not weakening) the reversal.
- **Detector identity must stay CUSUM** for the p-anchor to hold; a
  correlation.py docstring bug that labelled BOCD "LIVE" was corrected in
  FIX-2b.

## Verification (S039)

- 151 tests pass on a clean GitHub clone (base 2fc6108); ruff check + ruff
  format --check both clean (54 files). Behavioural tests updated:
  `test_required_quorum_scaling` (ceil(M/3) values + frac_den=2 legacy
  recovery), `test_quorum_scales_with_population` (knee moved to M=10, adds a
  flat-at-M=9 case), `test_scorer_redis` Lua ARGV frac_den 2->3, gateway
  q(M=3) comment. Adversarial invariants (ADV-a Sybil, ADV-b semantic-only
  promote) unchanged and green.
- Near-term behaviour is IDENTICAL to FIX-2 for M<=9 (both q=3); the schedules
  diverge only at M>=10, which the live network will not reach for a long time.
