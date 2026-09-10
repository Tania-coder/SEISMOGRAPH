# KEYSTONE REPORT (SIGNED) -- REQ-DASH-003
# DASH-1: scorable-base normalisation of the published JSON validity rate
# Authored Session 046, 2026-08-11. Base: main @c771a73 (baseline 293).
# LANDED Session 047, 2026-08-28: PR #26 squash-merged @fd4c561,
# 5 checks green. main baseline 293 -> 309.
# Contract: agreed with Tatiana in-session before any edit (goal,
# constraints, formula, 7-case test contract, both adversarial cases).

## 0. Provenance

100% AI-generated (Claude, claude-opus-5): the defect finding, the
contract, the implementation, all 16 tests, and this report. Tatiana
chose the fix shape from four costed options (A/B/C/A-then-C), selecting
Option A -- gateway-side normalisation -- and approved the contract
before implementation began.

## 1. What

`GET /v1/weather` now publishes `recent_json_success_rate` on a true
[0, 1] scale instead of the raw batch mean.

New in `gateway/main.py`: `_JSON_BASE_BY_SUITE` (suite_version ->
(total prompts, scorable prompts)) and `_scorable_json_rate()`.
`_compute_model_weather()` normalises per row, then averages.

  published = raw_rate * total / scorable, clamped to [0, 1]

Suite bases: v1.0.0 (3, 1), v1.1.0 (4, 1), v2.0.0 (50, 9).

## 2. Why

`json_valid` is scored only for `structured_output` canaries
(probe/canary.py:381) but averaged over the whole batch
(probe/privacy.py:679). For suite v2.0.0 that is 9 scorable prompts of
50, so the metric's ceiling is 0.18, not 1.0.

The live board was publishing 0.17497 (google) and 0.17815 (mistral).
This is not DP noise -- at n=50, eps=2.0 the Laplace scale is
1/(50*2) = 0.01. Both models were at ~100% validity on every prompt
that can score, and the public dashboard read as "17% JSON success".
Post-fix: 97.2% and 99.0%.

Detection was never impaired: a full format collapse still moves the
raw metric 0.18 -> 0, roughly 18 sigma against that noise scale. This
was a presentation defect with a GTM consequence, not a statistical one.

## 3. Why the READ side and not the probe

The detector keeps consuming the raw wire value. Rescaling a live CUSUM
input mid-stream contaminates the accumulated baseline -- precisely the
failure mode the PRIV-011 constant cutover produced on
`avg_output_length` hours earlier in this same session (the DP constant
is not part of the stream key, so 8192-era and 320-era rows now share
one stream). Option C (making `json_valid` None-safe, matching the
existing `tool_call_valid` convention, and computing the rate over
scorable records only) is semantically the cleanest fix and is
recommended for the next canary suite version bump, where a fresh
stream key avoids contamination by construction.

## 4. Evidence

- Gate (sandbox, 2026-08-11): `ruff check .` clean,
  `ruff format --check .` clean (61 files), `pytest -q` **309 passed**
  (293 base + 16 new).
- Gate (host, 2026-08-28, on branch @04d6034): `ruff check .` clean,
  `ruff format --check .` clean (61 files), `py -3.10 -m pytest -q`
  **309 passed**. Matches the sandbox claim exactly.
- CI on PR #26: 5 checks green (ci/lint-and-test 3.10 and 3.11,
  codeql/analyze python and javascript-typescript, plus summary).
- Files touched: `gateway/main.py`, `gateway/schema.py` (docstring only),
  `tests/test_weather_json_rate.py` (new), `tests/test_gateway.py`
  (one fixture, see sec 6). Plus this report. +497/-5.
- Live-value check (2026-08-11): raw 0.17497 -> 0.9721;
  raw 0.17815 -> 0.9897.

### Adversarial case (a) -- poisoned / Sybil probe

A forged batch claiming `suite_version=v2.0.0` at `result_count=1,
rate=1.0` is rejected outright by the completeness guard and never
reaches the published average. A forged COMPLETE batch is still
accepted -- signature verification and reputation weighting are the
defence there, not this function -- but remains bounded in [0, 1].
`test_adv_forged_batch_cannot_exceed_the_clamp`.

### Adversarial case (b) -- provider change with no latency/uptime signal

Normalisation is a positive constant multiply per suite, therefore
monotone: a real collapse in JSON validity still moves the published
number, and the detector path is untouched regardless.
`test_adv_real_validity_collapse_still_moves_the_number`,
`test_normalisation_does_not_mutate_the_stored_row`.

### Ingestion-gateway case -- uninterpretable rows

Unknown suite_version, legacy-empty suite_version, missing rate, and
non-positive `result_count` all return None and are excluded from the
average rather than published on a guessed base. If no row is
interpretable the field is None, not a number.

### Post-merge live verification (2026-08-28, Session 047)

Production `/v1/weather` read 17 days after the S046 authoring session,
immediately before the merge:

  google/gemini-3.5-flash-lite   raw 0.17675 -> 98.2%
  mistral/mistral-small-latest   raw 0.18317 -> 100.0%

**The clamp fires on live data.** mistral's raw 0.18317 exceeds the
v2.0.0 ceiling of 9/50 = 0.18 by 0.00317, which is 0.22 sigma against
the DP noise scale (Laplace 1/(50*2) = 0.01, sd 0.0141). Without the
[0, 1] clamp the board would have published 101.8% JSON validity. The
clamp asserted in `test_scorable_json_rate_clamps_dp_overshoot` is
load-bearing in production, not defensive decoration.

Drift since the 2026-08-11 reading is +0.13 sigma (google) and
+0.36 sigma (mistral) -- both inside DP noise. No drift signal.

## 5. Defects caught and fixed

1. **Partial-batch base error (found in Stage 3, before merge).** The
   first implementation divided by the suite's scorable count without
   checking that the batch was a complete suite run. A 3-record partial
   labelled v2.0.0 whose single scorable prompt was valid (true rate
   100%) published 1/9 = 11%. Fixed by keying the table on
   `(total, scorable)` and excluding any row whose `result_count` does
   not equal the suite total. Note the dependency this exposes:
   correctness rests on `execute_canary_strict` (CAN-2) emitting only
   complete runs -- the same all-or-nothing behaviour responsible for
   the open google-leg sample loss. The guard enforces it independently
   rather than trusting every probe on the public ingest path.
2. **Latent fixture inconsistency in `tests/test_gateway.py`.** The
   shared `VALID_PAYLOAD` pairs `suite_version: "v1.0.0"` with
   `result_count: 10`; v1.0.0 is a 3-prompt suite, so no real run can
   produce that batch. The completeness guard failed it closed. Fixed
   locally in `test_weather_returns_stable_when_no_alerts` (override to
   3) rather than mutating a fixture 37 other assertions depend on.
   The shared fixture remains physically impossible and is flagged
   below.

## 6. Provider ToS compliance

Not applicable. No new canary probe design, prompt, or request pattern.
This is a read-side projection over already-stored aggregates; no
provider is contacted.

## 7. Known limitations (stated honestly)

1. **The published metric is not quorum-gated.** Only DRIFTING status
   requires cross-observer agreement; `recent_json_success_rate` and
   `recent_avg_output_length` are single-org aggregates rendered
   directly. Pre-existing, NOT introduced here, but it means a single
   malicious complete batch can move a displayed number. Worth its own
   task before the board carries more observers.
2. **The gateway now duplicates suite composition knowledge.** Option A
   was chosen deliberately for zero detector risk, but `_JSON_BASE_BY_
   SUITE` must be updated whenever a suite version is added, or that
   suite's rows silently drop out of the published average. Option B
   (probe emits the scorable count) removes the duplication; Option C
   removes the need entirely.
3. **`VALID_PAYLOAD` remains physically impossible** (v1.0.0 with
   result_count 10). Not fixed here -- 38 references, out of scope, and
   changing it belongs in its own task with its own gate.
4. **Historical rows are reinterpreted, not migrated.** Stored values
   are unchanged; the rescaling is applied at read time, so the board's
   history becomes correctly scaled retroactively. No data was rewritten.
5. No `bouncer.py` file-lock utility exists in this repository; writes
   followed the established RULE-1 write-then-verify pattern.
6. **The published figure carries no denominator.** `/v1/weather`
   exposes neither the sample count nor the age of the 10-batch window,
   so a reader cannot tell whether 98.2% rests on 10 samples or 2, or
   how old they are. Opened as DASH-2 in Session 047: publishing a rate
   without its base is the same class of defect this task just fixed,
   one level up. Weather Report #1 must not go out before it lands.

## 8. Methodology note

The partial-batch defect (sec 5.1) was found by executing the formula
against a hand-built hostile input, not by reading it. The code and its
docstring both looked correct, and the 14 tests written from the agreed
contract all passed -- the contract itself had not anticipated the case.
Suggest that Stage 3 always include at least one input constructed to
violate an assumption the contract did not name, rather than only
exercising the contract's own enumerated cases. A test suite derived
solely from the contract inherits the contract's blind spots.

## 9. Sign-off

- [x] **Tatiana, 2026-08-28.** Reviewed sec 3 (read-side rationale and
      the Option C recommendation for the next suite bump), sec 5 (both
      defects), and sec 7 (esp. #1 the un-gated published metric, #2 the
      duplicated suite table, and #6 the missing denominator). Host gate
      re-run on branch: ruff x2 clean, 309 passed. PR #26 squash-merged
      @fd4c561 with 5 checks green. Accepted.
