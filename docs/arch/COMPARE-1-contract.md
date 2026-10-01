# COMPARE-1 -- Intake contract: `seismograph compare`

Status: ACCEPTED by the Director, 2026-10-01 (Session 059, in
session: "принимаю"). Code starts in Session 060.
Supersedes in priority: D12 implementation (D12 stays designed; the
subset of its failure classes needed here is included in section 5).
Origin: market research 2026-10-01 (reports/Ниши надёжности ИИ для
Европы.md): the most realistic first product is a private, local
"old model vs new model on your own prompts" report with dated
evidence. Outreach on 2026-10-01 offered this to two companies.

## 1. Goal, in one sentence

A team runs one command on its own prompts against two models and gets
one page that says what will change if it switches, with a dated
evidence file -- and nothing leaves its machine except the calls to
the two model endpoints it chose.

## 2. User story

    python -m probe.compare --suite my_prompts.jsonl \
        --a openai/gpt-4o --b openai/gpt-5-mini --repeats 3

-> `compare-<timestamp>/report.html` and `evidence.json`.

## 3. Input

- `--suite`: JSONL, one item per line:
  `{"id": "q017", "user": "...", "system": "...", "expect_json": true}`
  `id` and `user` required; `system`, `expect_json` optional. Max 200
  items (constitution cap); more is refused, not truncated.
- `--a`, `--b`: `provider/model`. Endpoint and key per side from
  environment (`SEISMOGRAPH_A_BASE_URL`, `SEISMOGRAPH_A_API_KEY`, same
  for B). Same provider on both sides is the common case; different
  providers allowed.
- `--repeats k` (default 3, min 2): each item is asked k times per
  model. Needed for section 4.
- `--max-tokens` (default 512), `--delay-ms` per side.
- Before any call: print the number of calls (items x k x 2) and
  require `--yes` to proceed.

## 4. The rule that keeps it honest: compare against the noise floor

FLOOR-1 (2026-09-15) measured that one model can repeat its own answer
42/42 times and another only ~60% of the time. So "A and B answered
differently" means nothing unless it is larger than how differently A
answers A, and B answers B. Every comparison metric is reported three
ways: within A, within B, A vs B. The verdict per metric is one of:

- `CHANGED` -- A vs B outside both within-model ranges;
- `WITHIN NOISE` -- not distinguishable from repetition noise;
- `NOT MEASURED` -- too few valid responses (section 5).

The report never says "stable" (CLAMP-1 rule).

## 5. Metrics

Per side, over valid responses:

| metric | how |
|---|---|
| self-agreement | share of item pairs with identical output hash across repeats |
| A-vs-B agreement | share of items whose modal output hash matches |
| length | median and p90 characters; per-item change |
| JSON validity | only items with `expect_json: true` |
| truncated | `finish_reason == "length"` |
| empty | 200 with empty or null content |
| refusal (heuristic) | versioned pattern list `refusal@1`; labelled "heuristic" in the report |
| latency | p50, p95 |
| tokens | output and reasoning tokens when the API reports them |

Infrastructure failures are NOT responses: classified as `auth` (401,
403 key errors), `quota` (402, 429 with quota code), `rate_limit`
(429 after retries), `provider_error` (5xx after retries), `timeout`,
`network`, `param_rejected` (400 on a sampling parameter). Listed in
their own section of the report with counts; never counted as a
behaviour change. A side with more than 10% infrastructure failures
gets `NOT MEASURED` on every metric.

## 6. Temperature

Requests are sent with `temperature: 0`. If a provider rejects it
(400 on the parameter -- newer Claude models are reported to do this,
[assumed, not yet observed by us]), the run retries that side ONCE
without `temperature` and the report states, in its header, "side B
ran at provider default temperature". Never silent.

## 7. Output

`report.html` -- one self-contained file (no external scripts, fonts
or images; opens offline):
1. Header: both models (as requested AND as returned in the API's
   `model` field), date, item count, repeats, temperature per side.
2. Verdict table: each metric, within A / within B / A vs B, verdict.
3. The 10 items with the largest change, with both answers' text side
   by side (local file only; `--no-text` omits all text).
4. Infrastructure failures.
5. Limits, stated: what the tool cannot tell (e.g. "different" is not
   "worse" unless `expect_json` or a future scorer says so).

`evidence.json` -- tool version and git commit, suite file SHA-256,
models requested/returned, timestamps, per-item output hashes per
repeat, all aggregates and verdicts. No prompt or answer text. SHA-256
of the file itself printed at the end of the run.

## 8. Privacy and network

- Network calls only to the two configured endpoints. No gateway, no
  telemetry, no board. Test asserts no other host is contacted.
- Answer text exists only in memory and in the local `report.html`
  (unless `--no-text`). Never in `evidence.json`, never in logs.
- API keys never written anywhere; redacted from error messages.

## 9. Acceptance (tests, mock providers, no network)

1. Identical deterministic A and B -> every A-vs-B metric `WITHIN
   NOISE`, agreement 100%.
2. B changes exactly 10 known items -> exactly those 10 listed as top
   changes; agreement metric `CHANGED`.
3. Noise floor (adversarial): A is non-deterministic (answers vary
   ~40% between repeats) and B == A -> NOT reported as `CHANGED`.
4. Silent semantic shift (adversarial, constitution case b): B has
   the same latency and length distribution as A but returns broken
   JSON on half of the `expect_json` items -> JSON verdict `CHANGED`,
   latency and length `WITHIN NOISE`.
5. B refuses on 20% of items -> refusal rate rises, flagged heuristic.
6. B returns `finish_reason=length` on 30% -> truncated rate rises.
7. B returns 401 on every call -> infra section shows `auth`, all
   metrics `NOT MEASURED`, exit code non-zero, no "changed" claim.
8. B rejects temperature with 400 -> one retry without it; header
   states provider default temperature.
9. `report.html` contains no `http(s)://` resource reference except
   the tool's own homepage link; opens offline.
10. `evidence.json` contains no prompt or answer substring (test scans
    bytes for every prompt and answer of the run) and no 8+ character
    window of either API key.
11. Suite of 201 items -> refused with a clear message.
12. Same inputs and same mock outputs -> byte-identical
    `evidence.json` apart from timestamps.

Constitution case (a), Sybil probe, does not apply: compare is a
single-organisation local tool and publishes nothing. Stated, not
skipped silently.

## 10. Out of scope

Correctness against reference answers (ADR 0002 outcome classes),
scheduled `watch` mode, the public board, any hosted service,
benchmark suites, cost in money (needs a user-supplied price table;
next iteration).

## 11. Files

`probe/compare.py`, `tests/test_compare.py`, `docs/compare.md`
(usage), Keystone `KEYSTONE_REPORT_COMPARE-1.md`. Reuses
`probe/providers.py` (transport, `CompletionResult`) and the hashing
in `probe/canary.py`; transport changes needed: return
`finish_reason` and the API `model` field, and treat null content as
data. Estimated 2-3 sessions.

## 12. Provider ToS

The tool calls endpoints with the user's own keys on the user's own
prompts; compliance with the provider's terms is the user's. The
documentation says so. No new canary probe is designed here.
