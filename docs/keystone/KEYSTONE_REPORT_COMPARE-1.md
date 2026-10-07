# KEYSTONE REPORT (SIGNED 2026-10-07) -- REQ-COMPARE-001..009, REQ-COMPARE-020..023
# COMPARE-1: `python -m probe.compare` -- two models, your prompts,
# verdicts against each model's own repetition noise
# Authored Session 060, 2026-10-07.
# Base: main @7bf07a3 (host baseline 446).
# Branch: seismograph/task-compare-1 (f889e2f step 1, 154c099 step 2).
# Contract: docs/arch/COMPARE-1-contract.md (accepted 2026-10-01).

## 0. Provenance

All code, tests, docs and this report written by Claude (Executor) in a
cloud sandbox, linted there against the repo's own pyproject.toml
(ruff, line length 79), and written to the Director's disk through the
device bridge. Git, the host gate and the live run are the Director's,
from her PowerShell. Nothing was human-edited before this report.

## 1. What

- `probe/compare.py` (new): suite loader, per-side caller with retries
  and the temperature fallback, the noise-floor statistics, evidence
  writer, self-contained HTML report, CLI.
- `probe/providers.py` (additive, defaults unchanged for every
  existing caller): `CompletionResult.finish_reason`, `.returned_model`,
  `.content_null`; `complete_ex(send_temperature=, allow_null_content=)`;
  `system=None` omits the system message; `ProviderError.error_code`
  (sanitised token, max 64 chars, `[A-Za-z0-9_.-]`) and
  `.failure_kind` (http / timeout / network / bad_body / bad_schema /
  transport).
- `scripts/compare_preflight.py`: one real call per model at
  temperature 0, prints status, returned model, finish_reason; no text.
- `tests/test_compare.py` (29), `tests/test_providers_compare.py` (15).
- `docs/compare.md`, `docs/examples/compare_suite_example.jsonl`.
- `.gitignore`: `compare-*/` (output holds answer text).

## 2. How the verdict is computed

For each metric and each item, mean pairwise distance within A's
repeats, within B's repeats, and across A and B (hash: 0/1; numbers and
flags: absolute difference). Per item `t = cross - (within_a +
within_b)/2`; the test statistic is the mean `t` over items.

`CHANGED` iff BOTH:
1. mean cross > max(mean within A, mean within B) -- the contract's
   "outside both within-model ranges", literally; and
2. a within-item permutation test (labels A/B shuffled inside each
   item's pooled repeats, exact split tables, 999 Monte Carlo draws,
   seed = sha256(suite, models, repeats)) gives p <= 0.01.

`NOT MEASURED` when a side exceeds 10% infrastructure failures, or
fewer than 5 items have >=2 valid repeats on each side.

## 3. Evidence

### 3.1 Gates [measured, Director's PowerShell]
| point | result |
|---|---|
| session start, main @7bf07a3 | 446 passed |
| after transport (step 1) | 459 passed, GATE GREEN |
| after compare.py | 489 passed, GATE GREEN |
| after D16-D18 fixes, committed as 154c099 | 490 passed, GATE GREEN |

### 3.2 Contract acceptance list (section 9) -> tests
| # | case | test |
|---|---|---|
| 1 | identical deterministic -> WITHIN NOISE, 100% | test_c1_... |
| 2 | 10 known items changed -> exactly those listed, CHANGED | test_c2_... |
| 3 | adversarial noise floor, A ~40% unstable, B same process | test_c3_... (6 seeds) |
| 4 | adversarial silent shift: broken JSON, same length and latency | test_c4_... |
| 5 | refusals on 20% -> rises, flagged heuristic | test_c5_... |
| 6 | finish_reason=length on 30% -> truncated rises | test_c6_... |
| 7 | 401 every call -> auth, all NOT MEASURED, exit != 0 | test_c7_... |
| 8 | temperature 400 -> one retry, header states it | test_c8_..., test_c8b_... |
| 9 | report offline, only homepage link | test_c9_... |
| 10 | evidence has no prompt/answer, no 8-char key window | test_c10_... |
| 11 | 201 items refused | test_c11_..., test_suite_200_items_accepted |
| 12 | evidence byte-identical apart from timestamps | test_c12_... |

Also: only the two configured hosts contacted, real sockets blocked
(test_section8_...); `--yes` required (72 calls announced, none made);
retry/backoff and fatal-quota paths; classification table; property
test (item statistic symmetric; mean of `t` over all splits exactly 0;
identical data p = 1; null false-positive rate bounded).

Constitution case (a), Sybil probe: does not apply -- compare is a
single-organisation local tool and publishes nothing. Case (b): test c4.

### 3.3 Calibration on synthetic null [measured, sandbox py3.13]
300 runs, A and B the same noisy process (50 items x 3 repeats, ~40%
variation): 1 run had any CHANGED (agreement); per-metric p <= 0.01
rate 0.33% (agreement), 0% (length). An earlier 60-run sample gave
2/60; pooled 3/360 = 0.8%, consistent with alpha = 0.01.

Runtime of the statistics, worst case 200 items x 5 repeats with
random lengths, latencies and tokens: 1.0 s [measured, sandbox].

### 3.4 Live run [measured, Director's machine, 2026-10-07 16:59-17:02Z]
Preflight: mistral-small-latest and mistral-medium-latest both accept
temperature 0 (HTTP 200, finish_reason stop); both return the alias as
`model`, not a dated version.

`docs/examples/compare_suite_example.jsonl` (12 items, 5 JSON), small
vs medium, 3 repeats, 72/72 calls, 0 infrastructure failures,
evidence.json sha256 c57df87477ab037ae11cc7aa779a9aa6e8d6c4ebdb546504d32ded5b9442108c.

| metric | within A | within B | A vs B | p | verdict |
|---|---|---|---|---|---|
| answers differ | 13.9% | 19.4% | 75.0% | 0.001 | CHANGED |
| length (chars) | 10.2 | 1.1 | 43.1 | 0.001 | CHANGED |
| JSON valid | 0 | 0 | 0 | 1.000 | WITHIN NOISE (5 items) |
| truncated / empty / refusal | 0 | 0 | 0 | 1.000 | WITHIN NOISE |
| latency (ms) | 162.7 | 165.0 | 219.0 | 0.004 | CHANGED |
| output tokens | 1.7 | 0.3 | 10.9 | 0.001 | CHANGED |
| reasoning tokens | - | - | - | - | NOT MEASURED |

Self-agreement: small 86.1%, medium 80.6%. This run predates the
D16-D18 fixes; the statistics code did not change after it.

## 4. Defects caught and fixed

- D15 (test): c7 asserted the string `v-CHANGED` was absent; it is in
  the CSS. Now asserts the rendered badge `class="v v-CHANGED"`.
- D16 (found by the live run): a run printed nothing for minutes after
  the plan. Progress line every 10% of calls; test asserts 5..11 lines
  ending at 72/72.
- D17 (found in the live evidence): `git_commit` recorded HEAD f889e2f,
  which did not yet contain compare.py -- the code that ran was
  uncommitted. Evidence now carries `source_sha256` of compare.py,
  providers.py, canary.py and a note that HEAD may differ.
- D18 (found on the rendered page): the row "answer identity" showed
  the disagreement share. Renamed "answers differ".
- D19 (design): timeout vs network was only visible in the message
  text, which CAN-2a C3 forbids parsing. Added
  `ProviderError.failure_kind` at each raise site.

## 5. Decisions beyond the contract (need the Director's approval)

5.1 `--repeats` capped at 5 (contract: min 2, no max), so the exact
    permutation tables stay <= 252 splits per item in pure Python.
5.2 Failure classes added: `bad_request` (a 400 other than the
    temperature rejection, or a 404) and `not_attempted`. After `auth`
    or `quota` a side stops calling; the skipped calls count as
    failures, so the side is NOT MEASURED. `param_rejected` is not a
    failure class: the rejection is handled by the one retry and stated
    in the header.
5.3 The verdict rule in sec 2 is the formalisation of contract
    section 4 (alpha 0.01, 999 permutations, min 5 items per metric).
5.4 Retries: 2, waits 1 s then 2 s, only for rate_limit and 5xx.
5.5 Refusal list `refusal@1`: 17 English phrases in the first 300
    characters.

## 6. Known limitations

6.1 One live pair only, one provider, both accepting temperature 0.
    The temperature-fallback path is tested with mocks only; no real
    provider rejecting temperature has been observed by us.
6.2 Nine metrics are each tested at alpha 0.01, with no correction for
    multiplicity. Measured on synthetic noise: 1 false CHANGED in 300
    runs. Real noise (provider load changing during a run) may be less
    exchangeable than the synthetic null.
6.3 Latency verdicts reflect network and provider load at run time as
    much as the model. The live CHANGED on latency is not a model
    property claim.
6.4 "Answers differ" is exact hash identity: a whitespace change
    counts as a different answer.
6.5 evidence.json stores SHA-256 of each answer. For short answers
    ("Canberra", "391") the hash can be reversed by guessing. It holds
    no text, but it is not anonymous for trivially short answers;
    treat it as local unless the answers are long.
6.6 The returned model name can be an alias (Mistral: `-latest`), so
    the report cannot prove which dated version answered.
6.7 Repetition noise is estimated from 2-5 repeats per item.
6.8 Different is not worse: no correctness scoring (out of scope,
    ADR 0002).
6.9 Host gate runs py3.10 while pyproject_probe.toml declares
    >=3.11; the code avoids 3.11-only features but the declared floor
    is untested here.

## 7. Provider ToS compliance

The tool calls endpoints with the user's own key on the user's own
prompts. The live run used the Director's Mistral key on 12 neutral
example prompts, 72 calls plus 2 preflight calls. No canary probe was
designed or changed.

## 8. Methodology note

A live end-to-end run before the Keystone found two defects (D16,
D17) that 490 green offline tests could not, because both live in what
a human sees and what the file claims about its own origin. Make "one
live run, its evidence read back" a required step of any task whose
output is a user-facing file.

## 9. Accountability

- [x] sec 3 -- evidence accepted (gates, calibration, live run).
- [x] sec 5.1-5.5 -- decisions beyond the contract accepted.
- [x] sec 6.1-6.9 -- limitations accepted, in particular 6.2 and 6.5.
- [x] sec 8 -- live end-to-end run becomes a required step (backlog).

**SIGNED -- Tatiana Radchenko, 2026-10-07.**
