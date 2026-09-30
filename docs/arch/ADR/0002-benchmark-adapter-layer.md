# ADR 0002 -- Benchmark adapter layer: the probe runs suites, it is not one

Status: PROPOSED, revision 2 (Session 058, 2026-09-30).
Not accepted until the Director signs the contracts in section 9.
Task ids: BENCH-2 (adapters, registry), BENCH-3 (outcomes).
Depends on: G-33 (decided 2026-09-19), CLAMP-1, D12.
Review: revision 1 was reviewed by an independent agent against the
code; 6 blockers and 18 major findings. Every one is either fixed in
this revision or listed in section 10 as open. See section 11.

Evidence tags: [measured] = read from code on main @44404f8 or from a
live system this session, with file:line; [derived] = computed from
measured values; [assumed] = believed, unchecked, with what would
check it.

## 1. Decision

The probe stops owning a corpus. It owns a runner and a suite
interface. A suite is loaded through one entry point, is identified by
a hash of everything that makes two runs comparable, declares how its
answers are scored, how long they may be and how its length is
clamped, and is chosen by the operator by name. Our fifty prompts
become one registered suite (`canary-v2`). The first external suite is
a pinned, seeded 200-item sample of a public multiple-choice
benchmark, as proof that the path works end to end.

Companies run the probe inside their own infrastructure. Therefore:
nothing in this design may widen what leaves their perimeter, every
public number must stay defensible, and anything that cannot yet be
made sound is refused rather than approximated.

## 2. What exists today [measured]

| Piece | Where | What it gives |
|---|---|---|
| Corpus as data | `probe/suite_spec.py`, `probe/suites/canary_v2.json` | schema `seismograph.suite/1`, mandatory `license`/`source`, 200 cap, digest recomputed at load (BENCH-1) |
| Corpus digest | `probe/canary.py:729-749` `suite_content_hash` | SHA-256 over canonical JSON of prompts + tools |
| Runner | `probe/canary.py` `execute_canary(_strict)` | any `[{prompt_id, category, system, user}]`, raw output hashed then discarded |
| Clamp | `probe/privacy.py:674-677` | output length clamped to 320 before averaging |
| Saturation instrument | `scripts/measure_clamp_saturation.py` | INTERPRETABLE / UNINTERPRETABLE (CLAMP-1) |
| Two-tier rule | G-33 | only a registered public suite may enter correlation |

## 3. What breaks in the current architecture [measured unless tagged]

**B1. Suite identity on the wire is a label, not a hash.** The batch
carries `suite_version` (`privacy.py:481,534`); the digest lives only
in `ProbeConfig` and the OTel span (`sdk.py:201,374`). Quorum and
detectors key on `(model_tuple, suite_version, metric)`
(`gateway/main.py:973-977,1017-1021`). Two different corpora under one
label would be counted as agreement.

**B2. The prompt schema has no place for an answer key.** Exact key
set `{prompt_id, category, system, user}` (`suite_spec.py:52-54,128`).

**B3. No correctness, and no finish reason.** `CanaryResult` has no
outcome field (`canary.py:796-810`), and `finish_reason` is never
parsed (`providers.py:349-381`), so truncation is invisible.

**B4. Scoring is hard-wired to our category names.** `json_valid` only
for `structured_output` (`canary.py:1397-1401`). A benchmark batch
would send `json_success_rate` = 0 + noise; the board already excludes
it (`main.py:500-502`), but the gateway still feeds it to a detector
as a noise-only stream (`main.py:980`).

**B5. Per-suite normalisation is a constant table in the gateway.**
`_JSON_BASE_BY_SUITE` (`main.py:455-459`). Every new suite needs a
gateway edit.

**B6. One global clamp for every suite -- a utility failure.** The
clamp bounds sensitivity whatever `max_tokens` is, so privacy holds;
but a long-answer suite saturates the 320 clamp and reads "stable"
while measuring nothing (CLAMP-1), and raising the clamp globally
raises the noise on every short-answer suite at the same epsilon. A
clamp must be per suite.

**B7. The runner is pinned to one suite.** `live_emit.py:77-80,284,
302-305`: imports `CANARY_SUITE_V2`, sizes pacing on it, no selector.

**B8. 200 prompts cannot run in the current job.** `timeout-minutes:
15` (`probe_weather.yml:52`); google paced at 4.5 s (`yml:86`).
`pacing_budget_ms(200, 4500)` = 955 s > 900 s at ZERO latency
[derived], before the gateway warm-up (`yml:105-111`) and spool drain.

**B9. Two digest schemes.** `canary.py:729-749` vs
`canary_suite.py:81-85`.

**B10. No registry.** G-33 is a decision, not code.

**B11. The weather view and public alerts ignore the suite.**
`get_recent_signals(model_tuple, limit=10)` averages across whatever
suites arrived (`main.py:590-607`); `save_public_alert` stores no
suite (`main.py:1023-1027`). With a second public suite both become
meaningless.

**B12. Per-item response hashes leave the probe un-noised.**
`canary_hashes = {prompt_id: sha256(output)}` (`privacy.py:773-775`).
For a one-letter answer, `sha256("B")` is reversed by a ten-entry
table: every item's answer, and therefore its correctness, would be
public in the clear. The DP guarantee today covers `metrics` only.

**B13. The privacy budget is spent per metric and not charged.** Each
metric is noised at the full EPSILON = 2.0 (`privacy.py:112,687,697,
733,767`); up to five metrics per flush is ~10 under basic
composition [derived]. The production path builds a bare
`Aggregator()` (`live_emit.py:127`) and charges no accountant.

**B14. Quorum identity is per run, not per organisation.** `client_id`
is a fresh UUID per `Aggregator` (`privacy.py:571`), created every run
(`live_emit.py:127`); the workflow generates a fresh signing key per
run (`probe_weather.yml:20-22`). [assumed: how `engine/correlation.py`
counts distinct orgs -- not in this snapshot; must be read before
any quorum claim.] A `suite_id` check does not stop a Sybil.

## 4. Suite identity

`suite_id` is the hash of everything that makes two runs comparable:

    suite_id = SHA-256(canonical JSON of {
        corpus_id,          # today's suite_content_hash(prompts, tools)
        max_tokens, temperature,
        length_clamp,
        scorer, scorer_version, parser_version
    })

`corpus_id` keeps today's digest unchanged, so `canary-v2` stays
pinned at `d4fbb0a0...9aba14` as its `corpus_id`. `reference` enters
the corpus JSON only when not None; the native adapter omits the key,
so the native `corpus_id` does not move (test).

## 5. Interface

```python
class SuiteAdapter(Protocol):
    name: str
    def load(self) -> Suite: ...          # never touches the network

@dataclass(frozen=True)
class Suite:
    name: str
    suite_version: str
    corpus_id: str
    suite_id: str
    tier: Literal["public", "private"]
    license_spdx: str
    license_sha256: str | None           # upstream LICENSE at pinned rev
    source: str                          # dataset, revision, file sha256,
                                         # sort key, seed, template
    max_tokens: int
    temperature: float                   # 0.0
    length_clamp: int
    scorer: Literal["none", "choice_letter"]
    scorer_version: str
    parser_version: str
    items: tuple[SuiteItem, ...]         # <= 200

@dataclass(frozen=True)
class SuiteItem:
    prompt_id: str
    category: str
    system: str
    user: str
    n_options: int | None                # letters beyond this -> unparseable
    reference: str | None                # never serialised off-box
```

Adapters: `NativeSuiteAdapter("canary-v2")` over the existing JSON;
`PinnedBenchmarkAdapter(name)` over a committed file produced by the
sampler (section 8). The operator selects with `--suite <name>`;
`--suite` wins over `SEISMOGRAPH_PROBE_SUITE`; an unknown name fails
closed and lists the registered names. Each additional suite is a
separate flush and a separate privacy-budget charge.

## 6. Outcomes: what "wrong" consists of

Right/wrong does not say what broke. Each scored item gets exactly one
outcome, decided inside the probe; the raw output is then discarded.

| outcome | rule | points at |
|---|---|---|
| `filtered` | `finish_reason` in {content_filter, SAFETY, RECITATION} or provider filter flag | provider safety layer |
| `empty` | 200, content is `""` or null without a filter reason | provider fault reported as success |
| `correct` | parser extracts exactly one letter, within `n_options`, equal to reference | -- |
| `wrong` | parser extracts exactly one letter, within `n_options`, not the reference | capability / knowledge |
| `refused` | no letter and refusal pattern matched (versioned list) | safety tuning |
| `truncated` | no letter and `finish_reason = length` | verbosity; clamp risk |
| `unparseable` | anything else, incl. several letters or a letter beyond `n_options` | instruction following / format |

Precedence is the order of the table, top to bottom, and is tested
with a fixture table. A truncated answer that still contains exactly
one clear letter is `correct`/`wrong`, not `truncated`.

Parser `choice_letter@1`: case-insensitive ladder -- bare letter with
optional brackets/period at start; "answer is (X)"; "Answer: X";
`**X**`; first match wins; two distinct letters anywhere -> 
`unparseable`. Frozen with a fixture corpus of at least 30 real
formats. Changing it changes `parser_version` and therefore `suite_id`.

Needs from the transport (B3, D12): `finish_reason`, and `content:
null` / empty `choices` returned as data rather than raised.

Infrastructure failures (401, 429, 5xx, timeouts, ...) are not
outcomes and never enter this table (D12).

## 7. Privacy and the budget

**7.1 One budget per flush, split explicitly.** `EPSILON_FLUSH` is
divided across the released queries, e.g. outcome histogram `eps_h`,
length `eps_l`, tokens `eps_t`, with the sum equal to `EPSILON_FLUSH`
and charged to the accountant in `live_emit` (fixes B13). The split is
part of the registered suite, so it is public and identical across
observers.

**7.2 The outcome histogram.** Neighbouring datasets: substitution
with public n (as REQ-PRIV-010). Over counts the L1 sensitivity is 2;
over shares it is 2/n. Each bin gets independent Laplace noise of
scale 2/(n * eps_h) on shares. `accuracy` and any clamping or
renormalisation are post-processing of the noised histogram only --
never computed from raw counts, never noised separately.

**7.3 Hashes (B12).** For any suite with `scorer != none`, per-item
hashes are NOT transmitted. The batch carries one
`suite_output_digest` = SHA-256 over the per-item hashes in suite
order, so "identical run" is still detectable and no item is exposed.
Native suites keep today's per-item hashes; the documentation states
plainly that the DP guarantee covers `metrics` only.

**7.4 Per-suite clamp (B6).** `length_clamp` comes from the registry
entry, never from the probe's own claim; `_metric_sensitivity` reads
it from there.

**7.5 Known limit.** Laplace noise is drawn from `random.Random()`
(`privacy.py:574`), not a CSPRNG, with floating-point sampling. Not
introduced here; becomes public-facing with benchmark metrics. Listed,
not fixed in this contract.

## 8. Registry, sampler, admission

**8.1 Registry** `registry/suites.json`, keyed by `suite_id`:
`{name, suite_version, corpus_id, tier, n_items, length_clamp,
epsilon_split, admitted_on, evidence, retired: bool}`.
- Append-only. Entries are never edited or deleted; retirement is a
  flag.
- The file hash is pinned in the probe release and the gateway deploy;
  a gateway that sees a batch stamped with a different registry hash
  rejects it.
- A change is a PR with Director sign-off, one second reviewer, and
  the admission evidence attached.
- Replaces `_JSON_BASE_BY_SUITE` (B5).

**8.2 Gateway behaviour.** New batch schema `seismograph.batch/2`
adds `suite_id`, `registry_hash`, `suite_output_digest`. A batch whose
`(name, suite_version)` maps to a different registered `suite_id` is
rejected with a logged error and no partial ingestion. A public-path
batch with an unregistered `suite_id` is persisted but gets no
detector, no quorum observation, and does not appear in `/v1/weather`.
The fleet path is unchanged. Weather rows and public alerts are keyed
by `(model_tuple, suite_id)` (B11).

**8.3 Backward compatibility and migration.** The new gateway accepts
`batch/1` for a stated window and maps the three known
`suite_version`s to registered ids through a one-off table applied in
`bootstrap_detector`; an unknown `batch/1` suite is fleet-only. A test
proves detector state after migration equals state before. New probes
read the gateway's schema version before emitting and refuse to emit
`batch/2` fields to a `batch/1` gateway.

**8.4 Sampler** `scripts/build_benchmark_suite.py` records, in
`source`: dataset id, pinned revision (commit), data file SHA-256, row
sort key applied before sampling, RNG (`random.Random(seed)`, stated
Python version), NFC normalisation, the option-rendering template,
stratification. CI rebuilds from these inputs and must reproduce
`corpus_id`.

**8.5 Admission of a public suite** requires all of:
(a) licence: SPDX id and the upstream LICENSE file hash at the pinned
revision recorded; every upstream sub-source checked;
(b) CLAMP-1 on at least one live leg: INTERPRETABLE at the declared
`max_tokens`/`length_clamp`; `reasoning_tokens` and the `empty` share
recorded per leg (reasoning models can spend the whole budget);
(c) time: warm-up + drain + `pacing_budget_ms(n, delay)` +
n x measured p95 latency <= 0.8 x job timeout on every leg; otherwise
the suite runs as its own scheduled job, never appended to the canary
job.

## 9. Contracts for the Director

**Contract A -- identity and registry (G-33, B1/B5/B10/B11).**
- `canary-v2` through `NativeSuiteAdapter` has `corpus_id`
  `d4fbb0a0...9aba14`; the existing pin test is unchanged and green.
- `suite_id` changes when any of max_tokens, temperature,
  length_clamp, scorer/parser version changes; `corpus_id` does not.
- Registered `(name, suite_version)` with a different `suite_id` ->
  rejected, logged, nothing ingested.
- Unregistered `suite_id` on the public path -> persisted, no detector
  update, no quorum observation, absent from `/v1/weather`.
- Weather and public alerts are per `(model_tuple, suite_id)`.
- `batch/1` from today's probe is still accepted and lands on the same
  detector stream as before (migration test).
- Stale registry: batch stamped with another `registry_hash` ->
  rejected.

**Contract B -- adapters and selection (B2/B7).**
- `live_emit --suite canary-v2` emits a batch whose key set equals
  today's plus `{suite_id, registry_hash}`.
- Unknown suite name -> exit non-zero, registered names listed.
- `--suite` overrides the env variable.

**Contract C -- outcomes and privacy (B3/B4/B6/B12/B13).**
- Every scored record lands in exactly one outcome (property test);
  the precedence table is tested with fixtures.
- Parser fixture corpus (>= 30 formats) passes; parser change alters
  `suite_id`.
- Histogram noise scale equals `2/(n*eps_h)` (test); accuracy is
  derived from the noised histogram only.
- Sum of per-query epsilons equals the accountant charge (test).
- For `scorer != none`, the serialised batch contains no per-item
  hash; mutating any `reference` leaves the serialised batch unchanged
  under a fixed noise seed (test).

Adversarial cases (constitution Stage 1):
- Mislabelled corpus: a batch labelled `v2.0.0` from a different
  corpus -> rejected. (This is NOT a Sybil defence; see 10.1.)
- Silent semantic shift: mock provider identical in length and latency
  flips 10% of letters -> `wrong` rises; `unparseable`, `refused`,
  length and latency do not. Second mock answers in prose -> 
  `unparseable` rises, `wrong` does not.
- Content filter: 200 with `finish_reason=content_filter` -> outcome
  `filtered`, not an infrastructure failure.
- Single-org correlated burst on `accuracy` -> no public alert.
- Replay of a known-stable window -> zero false alerts on the new
  metric.

Out of scope for A-C: the sampler run, the MMLU-Pro file, any live
run, any publication.

## 10. Open, stated rather than hidden

10.1 **Sybil resistance is unsound today (B14).** Quorum distinct-ness
rests on per-run identifiers. A real defence needs registered,
persistent observer keys (G-33 follow-up). Until then no quorum claim
is made about benchmark metrics.
10.2 **Contamination.** Public benchmarks are in training data; a
model can drift in ways a memorised benchmark does not show. This
suite complements the canaries, it does not replace them.
10.3 **Per-category accuracy** would localise drift but n per
category is ~15 in a 200-item stratified sample [derived]; at the
current epsilon the noise swamps it. Fleet-only until n supports it.
10.4 **Answer-letter distribution** (position bias) is a known
signature of a changed model; costs one more histogram and one more
budget slice. Not in contracts A-C.
10.5 **RNG** (7.5).

## 11. First public benchmark: MMLU-Pro, provisionally

| Need | MMLU-Pro |
|---|---|
| Licence permits committing a subset | MIT on the dataset card [assumed; admission 8.5(a) requires the LICENSE file hash and a check of each sub-source -- MMLU, STEM web, TheoremQA, SciBench] |
| Short answers | one letter, A-J |
| Not at ceiling | 10 options |
| Deterministic scoring | `choice_letter@1`, `n_options` per item (some items have fewer than 10) |
| Enough rows | 12,000 test rows, 14 categories [assumed from the card] |

Fallback: MMLU (MIT on the card, 4 options, 14,042 test rows) --
simpler, nearer ceiling on current models.

With one-letter answers `avg_output_length` is nearly constant; for
this suite the signal is the outcome histogram. That is why section 6
is on the critical path.

## 12. Build order

1. D12 (transport returns status, provider code, finish_reason; error
   classes; ops channel). Everything below depends on it.
2. Contract A.
3. Contract B.
4. Contract C.
5. Sampler; build `mmlu-pro-s200`; licence evidence.
6. Admission 8.5 (b) and (c) on both legs.
7. Own scheduled job for the benchmark suite.
8. Only then a published number from it.

## 13. Review record

Revision 1 was reviewed on 2026-09-30 by an independent agent that had
not written it, against the code. Blockers fixed here: budget
accounting (7.1), histogram sensitivity (7.2), wrong DP reasoning in
B6 (now a utility argument + per-suite clamp), per-item hash leak
(B12, 7.3), and -- in D12 -- the public ops channel and the error
taxonomy. Majors fixed: comparability hash (4), reference in the
digest (4), registry key (8.1), unregistered-suite routing (8.2),
Sybil relabelled (9, 10.1), weather per suite (B11, 8.2),
compatibility and migration (8.3), outcome precedence and parser (6),
reasoning models (8.5b), time budget (8.5c), licence (8.5a), registry
governance (8.1).
