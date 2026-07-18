# FIX-2 — Engine candidate TTL + quorum scaling (decision memo)

**Status:** awaiting Tatiana's decision on three calibration parameters.
**Blocks:** nothing for the paper (EXP-2 enforced the TTL in the harness and
documented it as harness-enforced). This is the right *engine* fix so the
code matches the honest quorum numbers.
**Owner of decision:** Tatiana — the three parameters below are threshold
choices and per `engine/correlation.py` (module docstring) "all threshold
decisions must be documented as labelled data in `data/drift_labels/` before
any production deployment." So each needs a drift_labels datum, not a guess.

---

## The gap, precisely (grounded in current code)

`engine/correlation.py :: AgreementScorer`:

- `self._pending: dict[model_tuple, list[ChangePointResult]]` accumulates
  **every** result ever ingested for a model tuple, with **no time bound**.
- `promote_to_public_alert()` counts distinct agreeing orgs across the
  **entire** pending list; nothing expires. `clear()` only wipes after an
  explicit alert decision.
- `ChangePointResult` has **no timestamp** and **no metric name** — only
  `model_tuple, change_detected, score, threshold, contributing_orgs`.

Three consequences:

1. **No candidate TTL.** An org's `change_detected=True` from 60 days ago
   counts equally with one from today. Quorum can be assembled from signals
   spread arbitrarily far apart in time. This is exactly why the sim shows
   fixed q=2 degrading as the network grows (M=5/q=2 → public-FP 0.86): with
   more observers and an unbounded history, the probability that *some* q
   orgs each fired *at some point* approaches 1. EXP-2's honest 0.015 number
   assumed a 14-day TTL the engine does not implement.

2. **No metric agreement.** With no metric field, two orgs firing on
   *different* features can form a spurious quorum on the same model tuple.
   Cross-observer agreement should mean "agree about the same drifting
   metric," not merely "both alarmed about the model."

3. **Quorum does not scale with network size.** `quorum` is an absolute
   constant. As M grows, a fixed q=2 is a weaker and weaker guarantee
   (the fraction q/M shrinks). Sim: q=2 collusion 0.82 → q=3 0.34.

## Proposed change (three coupled edits)

- **(a) Data:** add `timestamp: float` and `metric: str` to
  `ChangePointResult` (both currently absent). Backfill call sites; add to
  the OTel emission so it round-trips.
- **(b) TTL + metric gate in `AgreementScorer`:** when counting agreeing
  orgs in `promote_to_public_alert()`, include a result only if
  `now - result.timestamp <= TTL` **and** it matches the metric under
  evaluation. Prune expired entries on ingest to bound memory.
- **(c) Quorum scaling:** replace the constant with
  `q_eff = max(QUORUM_MIN, ceil(FRACTION * active_observers))`, where
  `active_observers` = distinct orgs seen within the TTL window. Keeps the
  guarantee from decaying as the fleet grows.

## The three parameters you decide (each needs a drift_labels datum)

| Param | What it controls | Sim signal | Candidate default |
|---|---|---|---|
| **TTL** (candidate window) | how long an org signal stays eligible | EXP-2 used 14d → FP 0.015 @ 36d lead | 14 days |
| **FRACTION** (quorum scaling) | q_eff as a share of active observers | q=2→0.82, q=3→0.34 collusion | ~0.5 (so M=5→q=3), floor QUORUM_MIN=3 |
| **metric-agreement** | must orgs agree on the same metric? | not yet simulated | yes (exact metric match for Phase 0) |

## Recommendation

Ship (a)+(b) with **TTL=14d** and **exact metric match** — these are the
minimal changes that make the engine reflect the paper's honest numbers,
and 14d is already the value EXP-2 validated. Treat **(c) FRACTION** as the
one genuinely open calibration: adopt `q_eff = max(3, ceil(0.5*M))` as the
starting rule but gate the exact FRACTION on a `data/drift_labels/` entry
built from the quorum sim sweep, per the Seismo bound. That keeps QUORUM_MIN
rising to 3 (the Phase-1 "raise to 3?" open decision in the code) without
hard-coding a fraction we haven't labelled.

## Test contract (add alongside the change)

- `test_candidate_ttl_expires`: two orgs, signals 20 days apart, TTL=14 →
  quorum NOT met (was met before FIX-2).
- `test_metric_agreement_required`: two orgs same model, different metric →
  not promoted.
- `test_quorum_scales_with_fleet`: M=5, FRACTION=0.5 → q_eff=3; 2 agreeing
  orgs within TTL do not promote.
- Adversarial (per constitution): (a) Sybil burst of N results from one org
  inside TTL still counts as one org; (b) a provider change that shifts
  output with no latency/uptime signal still routes through metric-matched
  quorum.
- Invariants preserved: single-org never promotes; burst-alone never
  promotes.

## If you defer

Paper is unaffected (TTL documented as harness-enforced). The engine keeps
the known-optimistic behavior; do NOT quote the engine's live quorum FP as
if the TTL were in place — cite the harness-enforced EXP-2 number instead.
