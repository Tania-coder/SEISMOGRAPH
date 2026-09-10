# KEYSTONE REPORT (SIGNED) — SG-ENG-SUITESCOPE-001
# ENG-1: suite-scoped detector streams and agreement buckets
# Session 041, 2026-07-29. Base: main @5966c19 (baseline 193).
# Contract: business/CONTRACT_ENG-1_S041.md

## 1. What

`suite_version` is now part of the identity of every CUSUM stream, every
agreement bucket, and every persisted telemetry row.

- `engine/detector.py` — stream key `(model_tuple, metric_name)` becomes
  `(model_tuple, suite_version, metric_name)`. `CUSUMDetector.update()`,
  `_MetricState.update()` and the `DriftAlert` dataclass take a defaulted
  `suite_version: str = ""`. `reset()` gains `suite_version: str | None =
  None` (None = every suite, preserving the legacy two-argument meaning).
  `tracked_streams` returns 3-tuples.
- `engine/correlation.py` — `ChangePointResult` gains
  `suite_version: str = ""` (appended last). `_agree` / `_observers` and
  `observe` / `ingest` / `promote_to_public_alert` / `clear` all scope on the
  3-tuple.
- `engine/scorer_redis.py` — ZSET keys become
  `sg:quorum|observers:{model_tuple}:{suite}:{metric}`. The Lua script and
  the millisecond score domain are byte-identical to FIX-2 (verified by diff:
  zero changed lines touching `redis.call`, `ZCOUNT`, `math.floor`,
  `_NS_PER_MS`).
- `engine/models.py` / `engine/repository.py` — `TelemetrySignal.suite_version`
  nullable `String(64)`; `SignalRow.suite_version: str = ""`; `save_batch`
  persists `batch.suite_version`; an idempotent additive `ALTER TABLE ... ADD
  COLUMN` runs after `create_all()`, wrapped in a logged try/except.
- `engine/clickhouse.py` — same column in the DDL plus an idempotent
  `ADD COLUMN IF NOT EXISTS` in `setup_tables()`; both SELECT projections
  carry it; `_to_signal_row()` maps pre-ENG-1 short tuples and NULLs to `""`.
- `gateway/main.py` — the public path threads `batch.suite_version` into
  `scorer.observe`, `detector.update`, the `ChangePointResult` construction,
  `promote_to_public_alert` and `clear`; the private-fleet path threads it
  into `fleet_detector.update`; `bootstrap_detector()` re-warms per suite and
  logs a `model_suite_streams=N` fan-out line.

## 2. Why

Two defects, both verified on main @5966c19 before any code was written.

**B1 — the CAN-2 cutover would have produced a false alert.** With the suite
absent from the stream key, replacing a 4-prompt corpus with a 50-prompt one
writes a step change into the same CUSUM stream. The detector cannot
distinguish "the corpus changed" from "the provider changed". The first
public artefact of the suite expansion would have been a drift alert we
caused ourselves.

**B2 — latent, and it breaks federation.** Two organisations running
different suite versions were counted as *agreeing* on one
`(model_tuple, metric)` stream, although their corpora are not comparable.
This violates the correlation-first invariant directly. It is invisible at
M=1 and becomes a correctness bug the moment the first design partner joins —
which is precisely the moment the network's central claim is first tested.

B2 is why this shipped as an engine change rather than an operational
work-around (clearing detector state by hand at cutover would have fixed B1
and left B2 in place).

## 3. Evidence

Gate on the merged tree, sandbox clean clone:

```
ruff check .            All checks passed!
ruff format --check .   58 files already formatted
python3 -m pytest -q    257 passed
```

ENG-1 alone: **193 -> 234** (+41). Merged with CAN-2: 257.

Acceptance criteria A1..A7 of the contract are all met. Representative tests:

| Criterion | Test |
|---|---|
| A1 independent streams | `test_suite_scoped_streams_are_independent`, `..._do_not_share_cusum_score` |
| A2 scorer parity both backends | `test_three_orgs_split_suites_do_not_reach_quorum`, `test_redis_scorer_t4_t5_verdict_parity` |
| A3 split suites never reach quorum | `test_gateway_two_suites_do_not_reach_quorum` (+ same-suite positive control) |
| A4 persistence + bootstrap | `test_bootstrap_rewarms_per_suite_version`, CH parity CU8-CU10 |
| A5 legacy DB safety | `test_legacy_db_without_suite_column_bootstraps` (real pre-ENG-1 SQLite file, not a mock) |
| A6 `/v1/weather` unchanged | `test_gateway_same_suite_three_orgs_reach_quorum` asserts the exact key set |

### Adversarial case 1 — poisoned / Sybil probe

`test_adv1_sybil_suite_fanout_no_public_alert`. One org ingests 40 real
candidates spread round-robin over 6 fabricated suite labels on a single
`(model_tuple, metric)`. Asserts: no bucket promotes; each bucket's org set
is exactly `{"org-sybil"}` (40 replays collapse to one vote — distinct-org
counting is still the gate *per bucket*); and all 6 buckets were really
created, so the fan-out is exercised rather than swallowed. The companion
`test_adv1_sybil_fanout_does_not_dilute_honest_quorum` proves the flood is
inert against an honest quorum. **The widened key space did not become a
cheaper way to manufacture agreement.**

### Adversarial case 2 — provider change with no latency/uptime signal

`test_adv2_silent_provider_change_alerts_unchanged`. `json_success_rate` is
pinned at 0.99 and `result_count` at 10.0 on every step (asserted never to
alert — there is no infrastructure signal), while `avg_output_length` steps
from a jittered ~500 baseline to a flat 505. The identical sequence runs
twice: once through the pre-ENG-1 call form (`suite_version` defaulting to
`""`, the on-main reference) and once with `suite_version="v1.1.0"`. Equal
first-alert index (26), equal `cusum_score` (5.0150), equal `window_count`,
`threshold` and `direction`. **The new key costs no detection power and no
delay.**

## 4. Compatibility caveats

1. **Redis quorum state is orphaned across the upgrade.** Key names gained a
   suite segment, so candidates and observer populations written by a
   pre-ENG-1 gateway are unreachable to the new one. They self-evict via the
   existing 2xTTL GC backstop (28 days). In-flight quorum accrual resets once
   at deploy and M is briefly under-counted — which makes promotion *harder*,
   never easier. Do not roll back mid-window; a rollback orphans the new keys
   symmetrically.
2. **`QUORUM_BACKEND=redis` multi-node deploys must be upgraded together.**
   During a rolling deploy, old and new replicas write to different key
   spaces for the same logical stream and a quorum can split across both.
   Drain rather than roll if that matters.
3. **Key-space growth is intended but uncapped.** Every new `suite_version`
   string starts a cold baseline. A probe minting a fresh label per run would
   silently never reach `baseline_samples`. Bootstrap now logs
   `model_suite_streams=N` so the fan-out is visible at start-up; there is no
   cap and no alert on it.
4. **`suite_version` is caller-asserted, not verified.** It sits inside the
   signed payload so it is not attacker-mutable in transit, but a probe may
   assert any string. Content-hash scoping (contract D1) remains the correct
   fix and is deferred.
5. **Alerts and audit exports do not carry the suite label.** Contract §7 put
   `LocalDriftAlert` / `PublicDriftAlert` out of scope, so two public alerts
   on the same `(model, metric)` under different corpora are
   indistinguishable in `public_drift_alerts` and in
   `/v1/alerts/{id}/export`. Same limitation class as CAN-1 caveat 2.
6. **ClickHouse received an in-place `ALTER` the contract did not require.**
   Without it an existing cluster would reject every `save_batch` INSERT on
   the unknown column — a harder failure than the SQLite case C4 covers. It
   is `ADD COLUMN IF NOT EXISTS`, metadata-only, idempotent.
7. **`CUSUMDetector.reset(mt, metric)` now spans suites.** A legacy two-arg
   call clears that metric under every suite. `reset()` has no production
   caller today; a future caller wanting one bucket must pass
   `suite_version=`.
8. **Legacy `ChangePointResult`s without `timestamp_ns` are only meaningful
   against real wall-clock `now`.** The scorer stamps arrival time on ingest,
   so such a candidate lands in the future relative to any synthetic `now_ns`
   a test supplies and silently fails the TTL liveness window. This is
   pre-existing FIX-2 behaviour, not an ENG-1 regression, but the contract's
   T3 wording implied it was testable without one. It is not.

## 5. Loose end found, not fixed

`gateway/main.py:697` carries a pre-existing trace comment
`#SG-TRACE: REQ-ENGINE-012 | test: test_gateway_quorum_scoped` referring to a
test that exists nowhere in the suite. Present at `5966c19`, left alone
rather than widen scope. A reviewer should reconcile it.

## 6. Sign-off

- [x] Tatiana: merged to main via PR #20 (61433b1) 2026-07-29; host gate
      green (ruff x2 + pytest 257); caveats 3, 4, 5, 7, 8 accepted;
      caveats 1, 2, 6 dormant for this deployment. Signed.
      — Tatiana Radchenko, 2026-07-30 (S041)
      (signature entered by Claude at Tatiana's explicit instruction)
      Independent verification (Claude, S041): fresh-clone gate on main
      @adcdf82 green (ruff x2, 257 passed). Deployment audit at signing
      time: render.yaml pins QUORUM_BACKEND=memory and STORAGE_BACKEND=
      sqlite on a single free-plan instance with one uvicorn worker and no
      persistent disk; the code default is also memory. Caveats 1-2 (Redis
      key orphaning, rolling-deploy quorum split) and caveat 6 (ClickHouse
      ALTER) therefore cannot bind unless the deployment topology changes,
      and are accepted as dormant provisions. Caveat 5 — public alerts not
      carrying the suite label — is live, has consequences for the public
      board across the v2.0.0 cutover, and is queued.
