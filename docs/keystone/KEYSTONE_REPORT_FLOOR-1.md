# KEYSTONE REPORT (UNSIGNED) -- REQ-FLOOR-001..006
# FLOOR-1: measure the determinism floor before claiming any drift
# Authored and gated Session 051, 2026-09-14/15.
# Base: main (baseline 345 on host). Branch: seismograph/task-floor-1
# at 97063de, pushed, NOT merged.
# Contract: agreed with Tatiana in-session before any code was written
# (goal, constraints, acceptance criteria, invariants, both adversarial
# cases) -- see sec 1 and sec 5.

## 0. Provenance

This report is the first real test of `tests/test_keystone_signed.py`.
That file's own docstring records that the signature step had produced
exactly two signatures in the project's history, DASH-2 and DASH-3, and
that **both were given after their merge**, and it states: "its first
real test is the next one, not this one." This is the next one.

The order is therefore being observed deliberately: the branch is
pushed and the merge has NOT happened. Adding this report turns the
gate RED by construction, and it stays red until sec 9 is signed.

Task id: **FLOOR-1**, opened 2026-09-14 in response to a question
Tatiana raised while preparing a conference talk -- reproduced verbatim
in sec 2 because it is the whole reason this task exists.

## 1. What

One new standalone instrument and seven runs of evidence. **No engine
code changed.**

- `scripts/measure_drift_floor.py` -- runs `CANARY_SUITE_V2` against any
  OpenAI-compatible endpoint and writes one CSV row per prompt plus a
  summary JSON; and compares two such CSVs.
- `docs/evidence/driftfloor/run_{a1,a2,a3,b1,b2,c1,c2}.csv` and their
  summaries -- 7 runs, 350 calls, one evening, one provider.
- `docs/evidence/2026-09-15-drift-floor.md` -- the measurement writeup.

The instrument does not import the gateway, does not emit telemetry and
does not slide the live weather window. Same posture as
`scripts/measure_google_latency.py`. It is safe to run beside
production.

Not touched: the probe SDK, the DP path, the quorum gate, the detector,
the gateway, the dashboard, the canary corpus.

## 2. Why

Tatiana's words, 2026-09-14:

> "я искренне не понимаю как этот рассказ может помочь другим людям...
> это проблематика случилась раз и только с антропик зачем другим за
> это переживать"

She is right, and the objection is structural rather than rhetorical.
Every public artefact this project has produced -- the README, the
whitepaper, Weather Report #1, the dev.to article -- rests its claim
that silent drift matters on **one incident at one provider**, replayed
synthetically. The project had no measurement of its own that the
problem exists.

Worse, it had no **noise floor**. A drift detector that has never
measured how much its own signal moves when nothing changed cannot
attach meaning to any number it emits. That gap had been open since
Phase 0 and nobody had named it.

FLOOR-1 closes it.

## 3. Why the comparison mode imports nothing from this repository

The first draft imported `probe.canary` at module scope, which meant
`compare` required the whole repository to run. That was caught by a
test on a machine without the package, and it is a design defect rather
than an import bug.

The point of publishing CSVs is that **a stranger can check the
arithmetic**. If checking requires cloning the repository, installing
its dependencies and trusting its code, the evidence is only as
checkable as the project is trusted -- which is exactly backwards for a
project whose product is trustworthy measurement.

`compare` is therefore pure arithmetic over two CSVs on a stdlib
Python. The probe import lives inside `_run()`. (REQ-FLOOR-004)

## 4. Why this runner is resilient where production is all-or-nothing

Production discards an entire suite when any prompt exhausts its
retries (contract CAN-2 s7 R1), because flushing at a reduced *n*
changes the DP sensitivity of the stream. That rule is correct there
and wrong here: an experiment must not lose 49 good observations to one
429, and it has no DP stream to protect.

The two runners therefore disagree **on purpose**, and the disagreement
is stated in the module docstring so a later reader does not "fix" one
to match the other. A failed prompt is written as a row with
`ok=false` and an `error_class`; it is never silently dropped, and it
is excluded from comparison rather than scored as "changed".
(REQ-FLOOR-003)

## 5. Evidence

### Gate (host, 2026-09-15, BEFORE this report was added)

    ruff check .              All checks passed!
    ruff format --check .     66 files already formatted
    py -3.10 -m pytest -q     345 passed, 1 warning in 4.61s

No test was added by FLOOR-1: the instrument is a script, and its
invariants are exercised against real and synthetic CSVs (below) rather
than through pytest. **This is a gap and is recorded as such in sec 7.**

Adding this report is expected to turn the gate RED on two tests in
`tests/test_keystone_signed.py` until sec 9 is signed. That is the
control working, not a regression.

### Result 1 -- the older model is deterministic, the newer one is not

Within a model, nothing changed between runs. Rates exclude
`tool_calling` (sec 5, "the artefact"); every denominator is printed.

    a1 vs a2   3.5-flash-lite      26/41   63.4%   length  +1.8%
    a1 vs a3   3.5-flash-lite      25/42   59.5%   length  -0.9%
    a2 vs a3   3.5-flash-lite      25/41   61.0%   length  -2.6%
    b1 vs b2   flash-lite-latest   21/42   50.0%   length  +1.8%
    c1 vs c2   3.1-flash-lite      42/42  100.0%   length   0.0%

`gemini-3.1-flash-lite` reproduces itself exactly, in every category.
`gemini-3.5-flash-lite` agrees with itself about 60% of the time at
temperature 0.

The 100% row is the instrument's **positive control**: the harness can
measure perfect agreement, therefore the ~60% is a property of the
model and not of the measurement. Without that row the whole result
would be uninterpretable.

### Result 2 -- the alias is not distinguishable from the pinned model

Six cross pairs, pinned 3.5 against the `-latest` alias:

    rate          57.1 - 64.3%      (within pinned 3.5: 59.5 - 63.4%)
    length delta  -1.5 to +2.9%     (within pinned 3.5: -2.6 to +1.8%)

The cross-model range sits inside the within-model range on both
measures. **On this date the alias behaves like the pinned version.**
Negative result, reported as one.

### Result 3 -- a generation change separates only on length

    pinned vs 3.1   41.5 - 45.2%    length  -25.3 to -23.2%

Hash agreement does not separate the floor (50-100%) from the alias
(57-64%). Mean output length separates with no overlap: same-model and
alias stay within +/-3%, the generation change is -24%.

The exact-match fingerprint is the obvious instrument and the wrong
one. The gateway's detector already runs on `avg_output_length` and
`json_success_rate` rather than on hashes; this is the project's first
own evidence that the choice was right, and it was arrived at by
measurement rather than by argument.

### The artefact, found before it reached a conclusion

`tool_calling` showed 0/8 hash-identical in every comparison, which
initially read as a finding. It is not. The tool-call JSON carries a
per-call random id and that id is inside the hashed string.

    a1 vs b1, tool_calling:  length identical 7/8,  hash identical 0/8

Identical content, different hash. A tool canary cannot match itself,
ever. The category is excluded from every rate and reported on length
instead. (REQ-FLOOR-005)

### A conclusion this data killed

After the first three runs (a1, b1, c1) the Executor concluded that
stability is a property of the prompt CATEGORY: `structured_output`
looked stable, `refusal_tone` looked useless as a canary at 0/8 in
every comparison. A practical recommendation was drafted from it.

The c-group refutes it. On `gemini-3.1-flash-lite`, `refusal_tone` is
**8/8 identical**. The same category is perfectly stable on one model
and perfectly unstable on another. Instability is a property of the
**model**. The earlier conclusion was wrong, is withdrawn, and is
recorded here rather than quietly dropped.

This is the fifth Executor conclusion killed by measurement in two
sessions. The standing rule from Session 050 held: verify first, say
nothing until it returns.

### Adversarial case (a) -- a mostly-failed run must not publish a rate

`MIN_COMPARED = 30`. A comparison resting on fewer comparable prompts
refuses to print an agreement rate and exits 3... **exit 1**, verified:

    A: a1  B: x1   shared 50   ok in both 20   excluded 30
    REFUSING to report rates: only 20 prompts are ok in both runs,
    floor is 30. A rate on this base would be a false claim.
    exit=1

Otherwise a poisoned or broken observer could publish a
confident-looking number off a handful of surviving prompts.

### Adversarial case (b) -- a change with no latency signal

Latency is recorded on every row and **is read by no code path that
decides anything**. The signal is hash and length only. Result 3 is the
demonstration: the generation change is invisible to a latency-based
monitor and obvious on output length.

### Invariants, verified

    compare(a, a)            50/50 = 100.0%,  length delta +0.0    PASS
    compare(a, b) 7 differ   43/50 =  86.0%                        PASS
    compare(a, c) 40 differ  10/50 =  20.0%                        PASS
    compare with 30 failed   refuses, exit 1                       PASS
    overwrite guard          exit 3, nothing written                PASS

### The instrument destroyed evidence before the guard existed

Run a2 was executed twice with the same `--label`. The second run
silently overwrote the first, destroying a clean 50/50 run. Only its
printed summary survives (50/50 ok, mean length 184.70).

This is the same class of failure the project already found in
production -- a loss that removes rows entirely and is invisible to any
count. The runner now refuses an existing label and exits 3 before
doing anything else, including before importing the probe, so a typo is
caught instantly. (REQ-FLOOR-006) Verified in production use: the guard
fired twice on 2026-09-15 and nothing was lost.

## 6. Provider ToS compliance

FLOOR-1 **does** add provider calls: 350 to Google's
OpenAI-compatible endpoint over roughly 90 minutes, at the probe's own
4500 ms pacing, temperature 0, `max_tokens=128`. This is ordinary
metered API use of a key held by the operator, well inside the canary
suite cost cap, and no different in kind from a scheduled probe run.

No provider text crossed the privacy perimeter: the CSVs carry
SHA-256 hashes, character counts, a boolean and a latency. No prompt
and no model output is stored in this repository by this task.

`docs/PROVIDER_TOS_CHECKS.md` is unchanged; no new provider was added.

## 7. Defects found and NOT fixed (out of scope)

1. **The nonce contaminates `probe/canary.py`, not just this script.**
   Production hashes `tool_calls_json` the same way, so 8 of 50 canaries
   emit a changing fingerprint on every run, forever. Scoped as its own
   task: strip volatile fields before hashing, with a test. **NOT fixed
   here** -- it changes the meaning of every historical tool-canary
   hash, and a baseline discontinuity introduced two days before a
   public talk is a bad trade.
2. **No pytest coverage for the instrument.** The compare arithmetic,
   the volatile-category exclusion, the MIN_COMPARED refusal and the
   overwrite guard were all verified by running them, and none of that
   is in the gate. If this script ever becomes a product command
   (`seismograph compare`), tests are the precondition, not a follow-up.
3. **The alias floor rests on one pair.** b1 vs b2 is a single
   observation at 50.0%. It is quoted in this report only as a range
   endpoint and must not be published as a rate on its own.
4. Everything still open from DASH-3 sec 7 is still open: both legs,
   `observer_count: 1`, naive `last_alert_timestamp`, the
   `requires-python` mismatch, DASH-2 Sybil exposure.

## 8. Known limitations (stated honestly)

- **One provider, one model family, one evening.** Nothing here
  generalises to OpenAI, Anthropic or anyone else without being
  measured there. The talk must say so.
- **`max_tokens=128` truncates long answers**, which can only inflate
  agreement. The measured floor is an UPPER BOUND on reproducibility;
  the real models may be less reproducible than shown.
- **The floor was measured inside one 90-minute window.** It says
  nothing yet about whether the floor itself is stable across days.
- **One a2 prompt failed with a provider 503** and is excluded from
  every comparison involving a2; `n` is printed on every line.
- **`reasoning_length` is 8/8 everywhere because its answers are 1-5
  characters long.** It carries no information about stability and is
  used in no conclusion here.
- This task measured a floor. It did **not** catch drift, and nothing
  in it should be described as having done so.

## 9. Sign-off

- [ ] Tatiana: reviewed sec 3 (evidence a stranger cannot check is not
      evidence), sec 4 (this runner deliberately disagrees with the
      production all-or-nothing rule), sec 5 "a conclusion this data
      killed" (**the category finding was wrong and is withdrawn**),
      sec 5 "the instrument destroyed evidence" (a clean run was lost
      before the guard existed and is not recoverable), sec 6 (350
      provider calls were made), and sec 7 (defects found and
      deliberately not fixed, above all the nonce still contaminating
      production tool canaries).

**This report is UNSIGNED. The gate is RED until the line below is
completed, by design -- see sec 0.**

To sign: tick the box above, delete the upper-case marker in the
paragraph above, and add the bold signature line in exactly the form
used by `docs/keystone/KEYSTONE_REPORT_DASH-3.md` sec 9, with your name
and today's date. The literal form is deliberately NOT reproduced here:
writing it in an unsigned report would satisfy the positive test in
`tests/test_keystone_signed.py` and let an unsigned document pass the
gate. That was a real defect in this report's first draft, caught by
grepping the file against the test's own markers before it was
committed.

**The merge has not happened.** For the first time in this project's
history the signature is being asked for BEFORE the merge rather than
after it. If it is given in that order, the note in
`tests/test_keystone_signed.py` -- that the control had never yet been
tested by a real task -- can be closed.
