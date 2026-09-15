# KEYSTONE REPORT (UNSIGNED) -- REQ-BUF-001..010
# BUF-1: a signed batch that cannot be delivered is kept, not lost
# Authored Session 052, 2026-09-15.
# Base: origin/main @66ecd6b (sandbox baseline 345).
# Branch: seismograph/task-buf-1.
# Contract: agreed with Tatiana in-session before any edit (timing,
# scope, dedup in the same task, 30 h lifetime).

## 0. Provenance

All code, tests and this report were written by Claude (Executor) in a
cloud sandbox cloned from `origin/main`, then written into the Director's
working tree through the device bridge. The Director set four decisions:

1. Build now and merge BEFORE the 2026-09-17 talk. The Executor's
   recommendation was to merge after the talk. The Director overruled
   it, and that is recorded here.
2. Scope: the probe SDK and `scripts/live_emit.py`, with the buffer on
   disk.
3. The gateway duplicate guard ships in the same task.
4. Buffer lifetime: 30 h, equal to `STALE_AFTER_HOURS`.

No line was edited by hand. The host gate has NOT been run yet (see
sec 3).

## 1. What

- **`probe/spool.py` (new).** A directory-backed FIFO of signed batches.
  - `put` stores only bytes that rebuild into a valid `SignalBatch` and
    are identical to their canonical JSON, together with the two signing
    headers.
  - Writes are atomic: temp file, fsync, then `os.replace`.
  - The number of stored files is capped (100, oldest evicted first).
    Entries older than 30 h are removed with a log line.
  - `drain` handles responses as follows:

    | Response | Action |
    |---|---|
    | 202 | delete |
    | 409 | delete |
    | other 4xx | quarantine, never retried |
    | 5xx or exception | stop and keep the rest |
    | unreadable file | quarantine without sending |
- **`gateway/main.py`.** A new step 3b runs after the signature check and
  schema parse, and before `save_batch` and any detector update. If
  `repo.has_batch(batch_id)` is true, the gateway returns
  **409 `duplicate_batch`** and ingests nothing.
- **`engine/repository.py` / `engine/clickhouse.py`.** `has_batch` is
  **abstract** on `BaseRepository`. The SQLite/Postgres version is an
  index lookup; the ClickHouse version uses a parameterised `count()`.
- **`scripts/live_emit.py`.**
  - The backlog is drained FIRST, before the provider is probed.
  - A new batch that fails with no HTTP status or with a 5xx is spooled.
    The exit code stays 1, so the failure remains visible.
  - A 409 counts as delivered. A 4xx is not spooled.
  - `SEISMOGRAPH_SPOOL_DIR` (default `.seismograph_spool`, `off`
    disables).
  - The unused `_post` is replaced by `_post_status` + `deliver`.
- **`probe/sdk.py`.**
  - `ProbeConfig.spool_dir`, default `None`. With `None`, the pre-BUF-1
    contract is byte-for-byte unchanged.
  - When set, `flush()` drains first. It spools on a transport error or
    5xx and continues with the remaining model tuples. A 4xx still
    raises.
  - A 409 is reported as `duplicate`. `dry_run` never drains.
- `.gitignore`: `.seismograph_spool/`.

Not touched: DP noise, the epsilon accounting, canary execution, the
quorum gate, the weather read path and the workflow.

## 2. Why

Before this change, `live_emit.py` discarded a fully executed, noised
and signed 50-prompt batch when its POST failed. `ProbeSDK.flush()`
also spent the epsilon and cleared the aggregator BEFORE the POST, so
a failed POST lost both the data and the budget. Resending the same
noised bytes is DP post-processing, so it costs no further epsilon.

The duplicate guard is a precondition, not an extra. Suppose a POST
times out AFTER the gateway has written the row. Without the guard, the
re-send enters CUSUM twice, and the network manufactures its own drift
signal.

## 3. Evidence

All results below are **[measured] in the cloud sandbox** (Linux).
Host numbers are pending.

- Baseline, unchanged `origin/main`:
  - Python 3.11: 345 passed.
  - Python 3.10: 345 passed.
  - ruff check: clean. ruff format: 65 files.
- With BUF-1:
  - Python 3.11: **378 passed**.
  - Python 3.10: **378 passed** (+33, all in `tests/test_spool.py`).
  - ruff check: clean.
  - ruff format --check: 67 files already formatted.
  - NUL bytes: 0. CRLF: 0.
- With this UNSIGNED report on disk: **376 passed, 2 failed** on both
  interpreters. The two failures are `tests/test_keystone_signed.py`,
  and they are RED by design until sec 8 is signed.
- Adversarial cases, each against the real FastAPI app with real Ed25519
  signing:
  - **(a) Sybil / tampered spool file.** A metric was changed after
    signing, and the body is still a valid canonical batch. The gateway
    returned 401. The file was quarantined, a second drain sent
    nothing, and no row was stored
    (`test_tampered_spool_file_is_quarantined_not_resent`). A file that
    no longer parses is quarantined without being sent.
  - **(b) Replay.** The same signed batch was sent twice. The responses
    were 202 then 409. `detector.update` was called once per metric and
    one row was stored
    (`test_duplicate_batch_id_returns_409_and_skips_cusum`). The
    timeout-after-write case, delivered through the spool, produced
    `duplicate` and one row (`test_drain_treats_409_as_delivered`). A
    forged signature on a known id returns 401, not 409, so the guard
    cannot be used to enumerate ids.
  - **(c) Silent provider shift.** The spool never alters values: the
    stored `avg_output_length` / `json_success_rate` equal the signed
    ones (`test_put_then_drain_delivers_exact_signed_bytes`).
- **Property test** (`test_drain_accounting_property`): 60 seeded random
  trials over outcomes {202, 409, 400, 401, 422, 500, 503, exception}
  and ages {0, 20 h, 31 h}. In every trial, every file lands in exactly
  one bucket, and the files left on disk equal `remaining`. It is
  seeded rather than using hypothesis, so CI needs no new dependency.
- **Mutation check.** Each mutation was applied by hand, run against
  `tests/test_spool.py`, then reverted. All four were killed:

  | Mutation | Result |
  |---|---|
  | Guard disabled | 2 failed |
  | 4xx retried instead of quarantined | 1 failed |
  | Expiry disabled | 1 failed |
  | Body validation on `put` bypassed | 1 failed |
- **Flakiness.** The tamper and round-trip tests were run 60 times in a
  loop with no failure.

## 4. Defects caught and fixed

1. **Two existing gateway tests had been re-sending a batch_id all
   along.** In `_warm_and_drift` (tests/test_gateway.py), the warm-up id
   `{prefix}{i:02d}0000` equals the drift id `{prefix}{n:02d}{i:02d}00`
   when n=0 and i=0. The new guard answered 409 and both suite-scope
   tests went red. **The guard was not widened. The test ids were
   corrected** (warm-up ids now carry `ff`). Consequence: until now,
   those two tests fed one batch into CUSUM twice without anyone
   noticing. Both still pass with distinct ids.
2. **A replay hole in production, now closed** [derived from the
   code; never observed in use]. Before BUF-1, anyone
   holding a captured signed batch could POST it again and have it
   counted again: the signature stays valid and nothing checked the id.
   Mutation 1 shows the new tests fail without the guard.
3. **The first version of the tamper test could pass vacuously.** It set
   `json_success_rate = 0.0`. The DP-noised, clamped original can itself
   be 0.0, and on such a draw the body is unchanged and the gateway
   correctly returns 202. That flake was observed once. The test now
   always changes the value and asserts that the bytes differ.
4. A mutation that was meant to bypass validation was a silent no-op
   because the indentation did not match, so the first reading
   ("survived") was wrong. The mutation was re-applied correctly and
   killed.

## 5. Known limitations -- stated plainly

1. **The project's own public legs are NOT covered.** GitHub Actions
   runners are ephemeral, so `.seismograph_spool/` disappears with the
   job. The sentence "there is no local buffer yet, so a result that
   cannot be sent is lost" therefore stays TRUE for our live board. The
   buffer helps someone who runs the probe on a machine that keeps its
   disk. Covering the runner would need `actions/cache` or an artifact
   and was deliberately left out of scope.
2. **The buffer does not address the September losses.** Those were a
   partial-suite discard (#122: 49 of 50), a job cancelled at 15 min
   (#137) and a mistral account-level 429. None of them produced a
   signed batch. Whether any production run was ever lost at the POST
   stage is **[assumed] unknown**. To check, search the Actions logs for
   `Emission failed:`.
3. **A late batch looks fresh -- this weakens DASH-3.** [measured from
   code] The gateway stamps each row with ARRIVAL time
   (`save_batch: timestamp=now`), and `window_end` / `window_age_hours`
   are computed from those stamps. A batch collected 29 h ago and
   delivered now reads as 0 h old. Worst case, the board shows data up
   to ~59 h old without STALE, instead of the 30 h DASH-3 guarantees.
   Today it is inert on the public board because of limitation 1.
   **It must be decided before any external probe with a spool emits
   to the public gateway.** The fix is to store the signed `window_end`,
   clamped to arrival time. That is an architectural change and needs
   Director approval. It is not made here.
4. **The duplicate guard is check-then-insert.** It is safe in one
   process, because no `await` separates the check from the insert.
   Multi-worker deployments need a UNIQUE constraint on
   `telemetry_signals.batch_id`. The existing Neon table has not been
   checked for historic duplicates, so a migration is not a blind step.
5. The ClickHouse `has_batch` is a filtered scan, because `batch_id` is
   not in the sort key.
6. Expiry uses the probe's wall clock. Clock skew shifts the 30 h.
7. A second process sharing one spool directory is not coordinated.
8. **Not on PyPI.** `pip install seismograph-probe` does not get the
   buffer until the Director cuts a release.
9. `live_emit.py` now drains before probing. If the gateway is cold, the
   drain stops at the first 5xx and the new batch is still attempted.

## 6. Provider ToS compliance

No new provider calls, prompts or endpoints. The spool never contacts a
provider. No ToS surface changes.

## 7. Methodology note

A new guard should be run against the WHOLE existing suite before its
own tests are written. Here the full suite exposed a latent test
defect (sec 4.1) that none of the new tests would have found. Proposed rule: "a new invariant is first a filter over the
existing corpus".

## 8. Accountability

Items to accept or reject:

- [ ] sec 5.1 -- the public legs stay unbuffered, and slide 9 must say
      so precisely
- [ ] sec 5.3 -- a late batch reads as fresh; decision on storing the
      signed `window_end` is deferred to a follow-up task
- [ ] sec 5.4 -- no UNIQUE constraint yet
- [ ] merge before the 2026-09-17 talk, as decided by the Director

Signature pending. This report is UNSIGNED, so
`tests/test_keystone_signed.py` keeps the gate RED until the Director
signs it. That is the intended control, not a regression.
