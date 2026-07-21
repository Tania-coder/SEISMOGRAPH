# KEYSTONE REPORT — FIX-2: engine-side candidate TTL + metric-scoped, population-scaled quorum

Task: close the FIX-2 engine gap left open by EXP-2 — the AgreementScorer had
no candidate expiry, no metric matching, and a fixed absolute quorum that
degrades as the network grows (M=5/q=2 -> public-alert FP 0.86).
Date: 2026-07-19 (S037). Status: UNSIGNED — awaiting Tatiana host gate + signature.

---

## 1. Provenance

AI-generated (Claude/Cowork, lead pass), decisions approved by Tatiana
(scope = all three gaps; q(M) shape and TTL delegated to Claude):
- engine/correlation.py — `required_quorum()` helper + policy constants
  (QUORUM_FLOOR=3, QUORUM_FRAC_NUM/DEN=1/2, DEFAULT_TTL_NS=14d);
  `ChangePointResult` gains `metric_name` + `timestamp_ns`; `AgreementScorer`
  rewritten (metric-scoped buckets, per-candidate TTL, `observe()` population,
  q(M) promotion, auto-clear on promote).
- engine/scorer_redis.py — `RedisAgreementScorer` rewritten to per-(mt,metric)
  Sorted Sets scored by event-time (ms), a two-key atomic Lua prune+scale+DEL
  script, and a mirrored `observe()`/`ingest()`/`promote()`/`clear()` surface.
- gateway/main.py — public path now calls `scorer.observe(...)` per metric
  (population M) and passes `metric_name` to ingest/promote/clear.
- tests/test_agreement_scorer.py (NEW, 14 tests) — behavioural + adversarial.
- tests/test_scorer_redis.py — rewritten to the ZSET/Lua wiring.
- tests/test_gateway.py — quorum test updated to 3 orgs; two-orgs-below-floor
  regression added.
- data/drift_labels/quorum_fix2_calibration.md — synthetic-defaults record.
- This report.

No git operations performed (hard rule: git only from Tatiana's PowerShell).
All work done on a fresh GitHub clone in the sandbox; final files written to
the working tree via the host bridge (device_commit_files), no mount writes.

## 2. Contract (Stage 1 intake)

Goal: agreement must mean "the same drift, seen recently, by enough of the
watching population" — not "any two orgs, ever, on any metric".

Acceptance criteria -> test contract:
- G1 metric-scoped: agreement is per (model_tuple, metric_name).
  Invariant test: orgs drifting on different metrics never agree.
- G2 candidate TTL: a candidate counts only within (now-TTL, now].
  Invariant test: candidates weeks apart never form a coincidental quorum.
- G3 population-scaled quorum: q(M)=max(3, ceil(M/2)) over the live observer
  population M. Invariant test: 3 agreeing orgs promote at M=3 but not at M=7.
- Privacy: only pseudonymous org_id in quorum/observer state (unchanged).
- Atomicity: multi-node promotion stays race-free (Redis Lua, preserved).

Adversarial cases (Constitution-mandated):
(a) Sybil/poisoned probe — a single controlled identity cannot manufacture
    quorum (dedup); fabricated OBSERVERS only raise q(M) (defensive), never
    promote. Forging DISTINCT org_ids is out of scope (Ed25519 one-org-one-key
    upstream). Documented residual at exactly the floor: 1 Sybil + (floor-1)
    honest false alarms can promote — the unweighted-quorum residual from
    EXP-2 C2, mitigated by reputation weighting (Phase 2), not this layer.
(b) Provider-side semantic shift with NO latency/uptime signal — three honest
    orgs agreeing on json_success_rate within the TTL MUST promote (guard
    against over-tightening q into false negatives). Covered by
    test_semantic_only_shift_promotes.

## 3. Verification summary

- Gate on a clean GitHub clone (752b9c2 base): `ruff==0.15.20 check` clean,
  `ruff format --check` clean, `py -3.10 -m pytest -q` = **151 passed**
  (was 134; +17). Host gate on Tatiana's machine remains mandatory pre-commit.
- Backend parity: in-process AgreementScorer and RedisAgreementScorer share
  identical semantics — per-(mt,metric) keys, window (now-TTL, now], M =
  max(observers, agreeing), q(M)=max(floor, ceil(M/2)), auto-DEL agree on
  promote, observers retained. In-process carries the logic tests; the Redis
  file locks the exact Redis command/Lua wiring (MagicMock, no live server).
- Precision note (caught in design): ZSET scores and Redis Lua numbers are
  IEEE-754 doubles (< 2**53 ~ 9.0e15); wall-clock ns (~1.7e18) would lose
  precision, so the Redis backend stores event-time in MILLISECONDS. The
  public interface still speaks ns; conversion is internal.
- Behaviour change (intended): default public-alert quorum floor rises from 2
  to 3. The Phase-2 "two orgs promote" gateway test is replaced by a 3-org
  test plus a `test_two_orgs_below_floor_stay_stable` regression guard.

## 4. Headline results — honest, unsoftened

1. The three EXP-2 engine gaps are closed in the engine, not the harness:
   metric scoping, per-candidate 14-day TTL, and population-scaled quorum
   q(M)=max(3, ceil(M/2)). Defaults are SYNTHETIC (EXP-2-backed), same posture
   as CUSUM h/k; recorded in data/drift_labels/quorum_fix2_calibration.md.
2. The correlation-first invariant is strengthened, not just preserved: a
   fixed q no longer erodes as M grows (EXP-2: q=2 -> 0.86 FP at M=5). The
   floor+proportional form holds the boundary while still surfacing genuine
   3-org semantic drift (ADV-b test).
3. scripts/experiment_quorum.py (the EXP-2 harness) is now SUPERSEDED for the
   TTL/scaling behaviour it emulated externally — its hard invariants still
   hold, but its printed FP rates reflect the pre-FIX-2 harness and should be
   read as historical evidence, not current engine behaviour.

## 5. Known limitations / follow-ups

- No production q(M) schedule yet: needs a labelled quorum-FP dataset (the
  "Seismo bound") in data/drift_labels/ — Phase 1. Mechanism is parameterised
  (frac_num/frac_den, floor, ttl_ns) so a calibrated table drops in later.
- Sybil residual at the floor (see §2a) is unchanged by this layer; reputation
  weighting + Ed25519 binding are the planned mitigations.
- Observer population M is tracked per gateway process/Redis; a coarse GC
  backstop EXPIRE (~2x TTL) bounds idle-stream memory in Redis.

## 6. Sign-off

- [ ] Tatiana: host gate green (ruff x2 + pytest 151) on
      seismograph/task-fix-2, then squash-merge, then sign here.
