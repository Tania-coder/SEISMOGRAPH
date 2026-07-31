# KEYSTONE REPORT (DRAFT, unsigned) — SG-FEAT-CANARY-V2-001
# CAN-2: canary suite v2.0.0 — corpus expansion 4 -> 50 prompts
# Session 041, 2026-07-29. Base: seismograph/task-eng-1 (ENG-1 must land first).
# Contract: business/CONTRACT_CAN-2_S041.md

## 1. What

- `CANARY_SUITE_V2` = 50 prompts, append-only:
  `[*CANARY_SUITE_V1_1, *CANARY_SUITE_V2_NEW]`. The first four entries are
  the *same objects* as v1.1.0 (identity, not equality — asserted).
  `SUITE_VERSION_V2 = "v2.0.0"`.
- Categories: logic_reasoning 9 (1+8), structured_output 9 (1+8),
  refusal_tone 8 (1+7), tool_calling 8 (1+7), reasoning_length 8 (0+8),
  multilingual 8 (0+8).
- 46 new frozen mock responses (`_MOCK_RESPONSES_V2`, `_MOCK_TOOL_CALLS_V2`),
  so the offline `mock=True` path stays fully exercised. The frozen v1 dicts
  are untouched.
- `PartialSuiteError` + `execute_canary_strict(...)`: runs every prompt in
  isolation so one 503 does not abandon the leg, then returns **nothing**
  unless all 50 completed. Failure records carry prompt ids only — never
  provider error text, which can quote request/response fragments.
- **Cutover wired**: `scripts/live_emit.py` (the cron entry point) now calls
  `execute_canary_strict(suite=CANARY_SUITE_V2,
  suite_version=SUITE_VERSION_V2, ...)`.
- `.github/workflows/probe_weather.yml`: cron `17 5,17 * * *` ->
  `17 1,6,11,16,21 * * *` (warm-up, see §5).

Content hashes (`suite_content_hash(..., tools=[FROZEN_TOOL_SCHEMA_V1])`):

- v1.1.0 `62422b5875d6ec785829d715f7155305cb322bb0a85c5525ab73f20bf86808c8`
- **v2.0.0 `d4fbb0a0ee7f704accc2b91c2832a4905cdf7b5cb175785490eabe878b9aba14`**

Stability is asserted across a real `subprocess` re-computation, so a
PYTHONHASHSEED-dependent iteration order cannot make the hash drift.

## 2. Why now, quantified

Metrics are flat means over the n records in a flush, so the intuitive fear
is that 4 -> 50 dilutes a single-prompt drift by 12.5x. It does not, because
DP sensitivity is also `MAX/n`: signal from a one-prompt shift is `Delta/n`
and the Laplace scale is `b = (MAX/n)/epsilon`, so **the DP-limited component
of SNR is invariant in n**, while sampling noise falls as `1/sqrt(n)` — which
means correlated drift gains `sqrt(n)`. The expansion is a 12.5x reduction in
DP noise, consistent with EXP-1R (100% detection at n>=100).

Timing was the other half of the argument. Verified 2026-07-29: the cron had
produced 10 scheduled runs since 24.07, i.e. ~10 of the 30 `baseline_samples`
CUSUM needs. **The v1.x baseline had never warmed.** Cutting over now cost
zero history; the cost would only have risen.

## 3. Evidence

```
ruff check .            All checks passed!
ruff format --check .   58 files already formatted
python3 -m pytest -q    257 passed
```

CAN-2 alone: **193 -> 216** (+23), verified by
`pytest --ignore=tests/test_canary_suite_v2.py` returning 193. Merged with
ENG-1: 257.

Acceptance criteria A1..A10 all met. Notable ones:

- **A7 cost cap.** `test_v2_cost_model_under_daily_cap` computes
  3706 input + 3200 output tokens per suite run x 5 flushes/day at
  gemini-flash-lite list price -> **$0.008253/day**, 12x under the $0.10 cap.
  The test additionally asserts that a 10x token-estimate error, or a full
  200-prompt suite, still fits.
- **A8 DP.** `_metric_sensitivity("avg_output_length", 50) == 8192/50`,
  exactly 1/12.5 of the n=4 value.
- **A6 ASCII.** The whole corpus and every mock satisfy `str.isascii()`;
  multilingual drift is probed by ASCII English instructions requesting
  non-English output, so the invariant holds.

Sequenced end-to-end check on the wired cutover (mock provider, real signing
path): `suite_version=v2.0.0`, `result_count=50`, 50 canary hashes on the
wire.

### Adversarial case 1 — poisoned / Sybil probe

`test_adv1_single_org_sybil_cannot_promote_at_n50`. Real `Aggregator`, real
`CUSUMDetector`, real `AgreementScorer`, no mocks. One org runs 12 honest
baseline windows, then 78 attack windows of fabricated results with every
metric driven to its clamp extreme. Asserts `promoted is None`,
`required_quorum(1) == 3`, `local_alert_fired is True` — and, the load-bearing
assertion, that the verdict tuple at n=50 is **identical** to the same attack
at n=4. A 200-candidate replay under one `org_id` still returns `None`.
**The corpus expansion did not open a cheaper Sybil path.**

### Adversarial case 2 — provider change with no latency/uptime signal

`test_adv2_semantic_only_shift_visible_in_reasoning_tokens`, with a control
and an explicit negative result (below). Two 50-result windows with
byte-identical `latency_ms` per index, identical `result_count`, identical
`json_valid` / `tool_call_valid` / `prompt_id` vectors. Only 16 records
differ: the 8 multilingual prompts shorten, the 8 reasoning_length prompts
drop `reasoning_tokens` 900 -> 0.

`delta(avg_reasoning_tokens) == 144.0` exactly (`8*900/50`), against a DP
floor of `sqrt(2)*b == 115.852` at n=50 — and `144 < 1448`, the n=4 floor,
so **this drift is visible at n=50 and was mathematically invisible at n=4.**
A seeded `Aggregator` + `CUSUMDetector(baseline_samples=30)` then raises a
`negative` candidate on `avg_reasoning_tokens` at window 5; the control feeds
70 stable windows through the identical seeded pipeline and asserts zero
alerts.

## 4. Negative result — `avg_output_length` cannot carry this signal, at any n

The contract asked ADV-2 to clear the DP floor for `avg_output_length` too.
It cannot, and no corpus size fixes it. This was found by disproving the
contract, and it is the most important thing in this report.

`scripts/live_emit.py` constructs the provider with
`max_tokens = SEISMOGRAPH_PROBE_MAX_TOKENS or 64`, so a live canary answer
cannot exceed roughly 256 characters on the wire. But
`probe/privacy.py::MAX_OUTPUT_LENGTH = 8192` — and DP sensitivity is set by
the *declared* clamp, not by what the probe can actually emit. The probe is
therefore paying **~32x more Laplace noise than its own wire contract
requires**.

Concretely: the best case for a multilingual-only shift at n=50 is
`8 * 256 / 50 = 41` characters, against a floor of `sqrt(2)*b = 115.85`.
2.8x below, before any realistic answer lengths are considered (the actual
shift in the test batch is 4.4 characters). At n=3, the size the board has
actually been running, the floor is 1930 characters against a metric whose
entire dynamic range is 0-256.

**`avg_output_length` has never carried signal in production**, and it is one
of only two metrics `bootstrap_detector()` re-warms. The arithmetic is pinned
in code, not prose, by
`test_adv2_output_length_shift_is_below_the_single_flush_dp_floor`.

The constant was deliberately **not** changed here: it is a privacy-layer
semantics change, outside this contract's boundary, and it moves every
assertion in `tests/test_dp_sensitivity.py`. Recommended as the next task
(PRIV-011): clamp to a bound consistent with the probe's configured
`max_tokens`. Clamping *is* enforcement, so DP validity is preserved; the
only cost is saturation for outputs above the bound, which the probe's own
`max_tokens` already makes unreachable.

## 5. Cutover and warm-up (operational)

- Hard cut. The probe emits v2.0.0 only. No dual emission: with ENG-1 the two
  suites are independent streams, and v1.x's 10-sample partial baseline is
  not worth the epsilon.
- Warm-up: `probe_weather` cron raised from 2 to **5 flushes/day for 6 days**,
  then reverted. Five is the exact ceiling of the DP budget
  (`daily_budget=10.0 / EPSILON=2.0`). 30 samples land ~2026-08-05 instead of
  ~2026-08-14.
- **Safe only while M=1.** The S039 Seismo bound (>~1.5 probes/day/metric
  pressures the 14d candidate TTL toward the FP ceiling) binds under
  multi-org quorum. The revert date is written into the workflow file as a
  comment. Revert before the first design partner joins.
- Landing needs an honest line: baseline re-established on the cutover date.

## 6. Compatibility caveats

1. **CAN-1's tool-calling canary was inert in production until this
   commit; its token metrics were not.** The cron called
   `execute_canary(model_tuple, mock=False, provider=provider)` with the
   *default* suite — `CANARY_SUITE_V1`, 3 prompts, `suite_version="v1.0.0"`
   — so the tool canary and `tool_call_validity_rate` never reached the
   wire, and **suite v1.1.0 was never deployed at all**: production went
   v1.0.0 -> v2.0.0 directly. The token metrics DID ship from the first cron
   run after `c439105`: `execute_canary` routes text canaries through
   `provider.complete_ex` whenever the provider exposes it, and
   `scripts/live_emit.py` constructs exactly such a provider, so
   `avg_output_tokens` (and `avg_reasoning_tokens` on providers returning
   `completion_tokens_details`) were emitted on every usage-reporting leg.
   CAN-1's own caveat 1 anticipated this ("or usage-reporting providers").
   The dispositive observable for the suite question is `result_count`,
   persisted un-noised as a column by `save_batch` — 3.0 vs 4.0. A
   `json_success_rate` argument (0.33 vs 0.25) does NOT discriminate: at
   n=3 the single-batch Laplace SD is 0.236 against a 0.083 separation of
   means, and even the board's 10-batch rolling mean classifies at only
   ~77.5% from one model row. This commit is the first time any suite past
   v1.0.0 reaches the wire; the first production v2.0.0 emission was the
   cron fire following `61433b1`.
2. **`execute_canary_strict` is a new entry point, not a change to
   `execute_canary`.** Existing callers keep fail-fast semantics; all 193
   pre-existing tests pass unmodified.
3. `scripts/live_probe.py` (local developer demo) still calls the old entry
   point with the default suite. Deliberate — it is not on the cron path.
4. Per-prompt isolation means the strict runner stamps 50 slightly different
   timestamps rather than one shared timestamp. Harmless — it removes the
   `window_start == window_end` +1 microsecond fixup — but visible in
   `window_start` / `window_end`.
5. The mock path carries no `usage`, so a flush of an unmodified mock run
   yields four metric keys, not six. A property of the mocks, not the corpus.
6. Mock-run `avg_output_length` drops from ~330 (v1.1.0) to 123.3, because
   the reasoning_length and multilingual mocks are deliberately short. Any
   snapshot keyed to the old mock mean will read differently.
7. **Live rate limits are the real deployment risk.** 50 sequential calls per
   provider leg per run, 5 runs/day. Gemini's free tier returned 503/404
   during S040. Discard-on-partial converts a rate-limit hit into a skipped
   window rather than a corrupted batch — correct, but it means a
   rate-limited provider contributes nothing at all rather than something
   degraded. Watch the first few runs.

## 7. Sign-off

- [ ] Tatiana — reviewed and accepted

— unsigned draft; requires maintainer signature before release —
