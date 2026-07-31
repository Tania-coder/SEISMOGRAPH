# KEYSTONE REPORT (DRAFT, unsigned) — SG-FEAT-PACING-001
# CAN-2a: provider pacing + transient-error backoff for the strict runner
# Session 041, 2026-07-31. Base: main @73505b7 (baseline 257).
# Contract: business/CONTRACT_CAN-2a_S041.md

## 1. What

- `ProviderError` gains an optional structured `status_code: int | None`,
  populated in the transport's `HTTPError` branch. The message string is
  byte-identical to before; nothing parses it.
- `execute_canary_strict` gains `delay_ms=0`, `max_retries=2`,
  `backoff_base_ms`, `max_total_backoff_ms` and an injectable `sleeper`,
  all appended after `suite_version` so positional call sites are unaffected.
  Transient failures (HTTP **429** and **503** only) are retried in place
  with exponential backoff; every other error fails the prompt immediately.
- `scripts/live_emit.py` reads `SEISMOGRAPH_PROBE_DELAY_MS` (default 0) and
  `SEISMOGRAPH_PROBE_MAX_RETRIES` (default 2) and passes them through.
- Discard-on-partial is unchanged. Retries happen *within* a prompt attempt;
  a prompt that still fails discards the whole run.

## 2. Why

First production emission of suite v2.0.0, 2026-07-31 09:16 UTC:

| Leg | Result |
|---|---|
| `mistral/mistral-small-latest` | `result_count=50`, accepted, 1m08s |
| `google/gemini-3.5-flash-lite` | **18/50**, discarded, job failed |
| `openai`, `anthropic` | skipped cleanly, secrets absent |

The discard was correct — a batch at `n=18` carries a different DP
sensitivity than the suite declares — but it removed a model tuple from the
public board silently, and the v2.0.0 baseline needs 30 samples by
~2026-08-05. This is CAN-2 caveat 6.7, materialised on first contact.

**Design decision: per-leg pacing, not global.** A fixed delay would tax
`mistral`, which demonstrably sustains 50 calls in 68 seconds, for a
limitation specific to the Gemini free tier. Pacing defaults to zero and is
set per matrix leg.

## 3. Evidence

```
ruff check .            All checks passed!
ruff format --check .   59 files already formatted
python3 -m pytest -q    286 passed in 3.86s
```

**257 -> 286** (+29). Independently re-gated by the main session on the
agent's tree. Whole-suite runtime 3.9 s, which is itself the proof that no
test sleeps for real — the clock is injected everywhere.

Acceptance criteria A1-A8 all met. Load-bearing ones:

- A2 — `test_p2_fifty_prompts_sleep_exactly_forty_nine_times`: the event log
  alternates `call, sleep, …, call`, so nothing sleeps before the first
  prompt or after the last.
- A4 — `test_p5_only_429_and_503_are_transient` parameterised over
  400/401/403/404/418/500/502.
- A8 — `test_p8_google_leg_pacing_budget_fits_actions_timeout`: measured on
  a real 50-prompt run through the fake clock (220.5 s), worst case 280.5 s
  against `PACING_BUDGET_S = 300.0`, with >5 min of job-timeout headroom
  asserted.

### Adversarial case 1 — poisoned / Sybil probe

`test_adv1_always_429_emits_zero_batches_and_cannot_promote`. Five full
emission cycles against a provider that always raises a structured 429.
Asserts zero batches reach the gateway; asserts the *same* five cycles with
`max_retries=0` — literally today's behaviour — also emit zero, so retrying
does not increase the number of batches reaching the gateway; asserts
retrying costs strictly more provider calls and buys zero extra emissions.
Then, with the real `AgreementScorer`, one org ingesting a candidate per
retry cycle still yields `promote_to_public_alert(...) is None` at
`required_quorum(1) == 3`. **Retry did not become an amplifier.**

### Adversarial case 2 — provider change with no latency/uptime signal

`test_adv2_paced_and_unpaced_metrics_are_identical`. A deterministic fixture
provider serves one frozen response per prompt. The same fixture runs paced
(4500 ms) and unpaced: the fake clocks differ (49 sleeps vs 0) while all 50
derived feature tuples, the DP-noised `batch.metrics` under a common seed,
and the `canary_hashes` are equal. Repeated for a semantic-only shifted
fixture, asserting `delta_paced == delta_unpaced` across every metric key,
with non-vacuity pinned on the raw feature delta (144.0 reasoning tokens).
**Pacing changes timing only, never features.**

## 4. Recommended setting

`SEISMOGRAPH_PROBE_DELAY_MS = 4500` on the **google leg only**.

Derivation: mistral served 50 calls in 68 s (~1.36 s/call), so an unpaced
gemini leg issues ~40-45 req/min. It got 18 through before hard-failing,
which is the signature of a **~15 req/min** quota once the initial bucket
drains — a 30 RPM tier would not have blocked at 18, and a 10 RPM tier would
have blocked nearer 12. 4500 ms = 13.3 req/min, ~11% under a 15 RPM quota,
leaving headroom for clock skew and for retry attempts, which also consume
quota. Leg duration ≈ 4 min 51 s, or ≈ 5 min 51 s if the full 60 s retry
budget is spent, against `timeout-minutes: 15`.

**This RPM figure is inferred, not read from the provider console.** If the
actual quota is available in Google AI Studio, it should replace the
inference before the value is committed.

## 5. Compatibility caveats

1. **`status_code` is populated only by the stdlib transport's `HTTPError`
   branch.** Transport failures, non-JSON bodies, schema errors and any
   injected custom `Transport` raising its own type all carry
   `status_code=None` and are therefore never retried. Deliberate — the
   contract bans message-string parsing — but a third-party transport must
   set the keyword itself to get retries.
2. Consequently the pre-existing `_FlakyProvider` in
   `tests/test_canary_suite_v2.py`, which raises
   `ProviderError("provider HTTP 503")` with no keyword, still exercises the
   non-retry path. That is why the 257 baseline is untouched, and it is
   pinned by `test_p7_legacy_provider_error_without_status_is_not_retried`.
3. **New behaviour at default settings:** `max_retries` defaults to 2, so a
   live leg now retries a real 429/503 even with no env var set. Only
   structured-status errors are affected; `max_retries=0` restores the exact
   old path.
4. `PACING_BUDGET_S = 300` caps the usable delay at ~4900 ms for a 50-prompt
   suite. Raising the delay past that fails A8 until the constant is raised
   deliberately — a review gate, not a silent knob.
5. Pacing is honoured in `mock=True` as well; the default of 0 means no
   existing offline test is affected.
6. Retry backoff does not consume the pacing delay: after a retry the next
   prompt still waits the full `delay_ms`, and because the backoff base
   (5 s) exceeds the recommended delay (4.5 s), a retry never issues faster
   than the pacing rate.

## 6. Contract defects found during implementation

- **C4 asked for a run-wide wall-clock ceiling that §5/§6 never tested**, and
  per-prompt bounding alone is insufficient: 50 × (5 s + 10 s) = 12.5 min
  would blow the 15-minute job by itself. A run-scoped
  `max_total_backoff_ms` (60 s) was added to satisfy C4 in substance, covered
  by `test_p4_transient_forever_is_bounded_by_total_budget`. Reviewers should
  note the consequence: per-prompt retry bounds hold only until the run-wide
  budget is exhausted, after which later prompts fast-fail with zero retries.
- **A1's "byte-identical" is not literally attainable** and was not before
  this change: `CanaryResult.timestamp` is `datetime.now()` and differs
  between any two runs. The assertable property is identical derived
  features, which is what the test checks.
- **ADV-1's first clause is vacuous.** Discard-on-partial raises before
  anything is staged, so no code path can emit a partial batch with or
  without retries. The informative assertion is batch-count parity against
  `max_retries=0`, which is what was implemented.
- **R1 conflated the job timeout with the minutes bill.** Each matrix leg is
  a separate job with its own `timeout-minutes: 15`, so multiplying by legs
  is meaningless for the timeout. The real multiplied cost is the Actions
  minutes quota: ~24.5 min/day for the paced google leg. **Moot here — the
  repository is public, so Actions minutes are unbilled** — but the contract
  reasoning was wrong and would matter on a private mirror.

## 7. Sign-off

- [ ] Tatiana — reviewed and accepted

— unsigned draft; requires maintainer signature before release —
