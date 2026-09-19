# KEYSTONE REPORT (SIGNED 2026-09-19) -- REQ-BENCH1-001..014
# BENCH-1: the canary corpus becomes data, and its identity becomes
# something the gate can check
# Authored Session 054, 2026-09-19.
# Base: main @45d7846 (host baseline 378).
# Branch: seismograph/task-bench-1.
# Commits: c2017e5 (pin), f880249 (loader + spec + tests).
# Contract: agreed with Tatiana in-session before any edit -- five
# acceptance criteria, three adversarial cases, branch name.

## 0. Provenance

All code, tests, the spec file and this report were written by Claude
(Executor) in a cloud sandbox and written into the Director's working
tree through the device bridge. The Director ran every git command and
every host gate; the Executor ran none.

`probe/suites/canary_v2.json` was generated programmatically from
`CANARY_SUITE_V2`. No prompt was retyped by hand, and the digest of the
generated file was checked against the literal before the file reached
the disk.

Director decisions recorded:

1. Start with BENCH-1 without waiting for the BENCH-0 tier decision,
   on the Executor's argument that the loader is required under either
   answer. The Director accepted.
2. The contract as proposed, unamended.

One deviation from the contract, found by the Executor and closed
before the commit: criterion 5 named `execute_canary_strict`, and the
first implementation established equality through `execute_canary`
only. Reported rather than counted as met; see sec 4, D2.

## 1. What

**c2017e5 -- `tests/test_suite_corpus_pinned.py`, 7 tests.**
Three literal digests of the shipped corpora, checked into the
repository, plus three adversarial cases and a determinism case.

**f880249 -- three files, 781 insertions.**

- `probe/suite_spec.py`: `SuiteSpec` and `load_suite_spec`. Validates
  schema id, mandatory `license` and `source`, the 200-prompt cap, an
  exact per-prompt key set, non-empty values, and `prompt_id`
  uniqueness. A `suite_id` recorded inside a spec file is recomputed
  from the corpus and a mismatch raises.
- `probe/suites/canary_v2.json`: the v2.0.0 corpus as data, carrying
  its own digest.
- `tests/test_suite_spec.py`: 13 tests.

The digest function did not change. `probe.canary.suite_content_hash`
remains the single content address; this task added a loader, not a
second scheme.

## 2. Why

Post-talk feedback from Augustin Gottlieb (Claude Code Meetup #3,
2026-09-17): a 50-prompt canary suite does not look strong, and the
project should build the infrastructure around benchmarks rather than
compete with them, letting the user choose the corpus.

Reading the code before agreeing with him [measured]:
`execute_canary` and `execute_canary_strict` already take `suite` as a
parameter, and `suite_content_hash` already content-addresses an
arbitrary corpus including its frozen tool schemas. The corpus was
pluggable everywhere except at the point where a corpus can arrive.
It was a Python literal, so a suite could not be chosen -- only edited.

The strategic reason is narrower than "support benchmarks". The
project's binding constraint is a second observer, and a team already
running an evaluation suite in CI is the cheapest on-ramp that exists:
it has a corpus and a schedule already, and no drift monitoring.

## 3. Evidence

All figures below were observed this session. Host gates were run by
the Director in PowerShell and pasted back in full.

**Digests, measured on main @45d7846:**

- v2.0.0 corpus + tool schemas:
  `d4fbb0a0ee7f704accc2b91c2832a4905cdf7b5cb175785490eabe878b9aba14`
- v2.0.0 corpus, no tools:
  `2fa1bb7bc9c2b43636fcf80eb5b76b20ce861c24a729bac07badf4953b37422b`
- v1.1.0 corpus + tool schemas:
  `62422b5875d6ec785829d715f7155305cb322bb0a85c5525ab73f20bf86808c8`

**Host gates [measured, Director's PowerShell]:**

| After | ruff check | ruff format | pytest |
|---|---|---|---|
| pin | clean | 69 files | 385 passed |
| loader (first delivery) | clean | 71 files | 397 passed |
| strict-runner test added | clean | 71 files | 398 passed |

Baseline moves 378 -> 398, +20 tests.

**The pin actually fires.** One prompt in `probe/canary.py` was
reworded in the sandbox (`capital city` -> `capital`): 2 failed. The
file was restored: 7 passed. The test detects a corpus edit rather
than its own self-consistency.

**Round trip through the Director's disk.** The spec file was written
to `D:\`, read back, and its digest recomputed from the bytes as they
sit on that disk: equal to the pin. The corpus survives serialisation,
transport and NTFS unchanged.

**Equality with the literal, twice.** `spec.as_suite() ==
CANARY_SUITE_V2` field for field, and mock runs through both
`execute_canary` and `execute_canary_strict` compared result by
result, excluding `timestamp` and `latency_ms` -- properties of a run,
not of a corpus.

**Adversarial cases, all passing at both levels.** A one-character
edit, a two-prompt reordering, and a tool-schema rename with prompts
untouched each move the digest; at file level each is rejected at load
with the recorded `suite_id` named in the error.

## 4. Defects caught and fixed

**D1. The content-addressed-baseline invariant was not gated.**
Pre-existing, found before any code was written.
`test_canary_suite_v2.py` asserts the suite hash is stable and that
v2.0.0 differs from v1.1.0, but both sides of every such assertion are
recomputed from the corpus present at run time, so an edit to a prompt
moves them together and the suite still passes. Prompt ids, category
counts, entry key shape and prefix identity were pinned; the prompt
text was not. A silent corpus edit would have made every historical
time-series incomparable without failing a single test.
Fixed by c2017e5.

**D2. Acceptance criterion 5 was met with the wrong runner.**
The contract named `execute_canary_strict`, the production path with
discard-on-partial, pacing and retries. The first implementation
compared runs through `execute_canary` instead, which no observer
calls. Caught by the Executor re-reading the contract against the
delivery before the commit, and closed by
`test_strict_run_from_spec_matches_strict_run_from_literal`. Had it
gone unnoticed, the commit message would have claimed production-path
equality that no test established.

**D3. The device bridge wrote stale content, silently.**
`device_commit_files` was called twice with the same output filename.
The second call reported success, the file's mtime on the Director's
disk advanced, and the content did not change: the old revision was
written. Detected by comparing the file size reported by
`device_list_dir` against the container's and searching the file read
back for `execute_canary_strict`, which was absent. Worked around by
writing under a new output filename.

This is a process defect, not a code defect, and it is the third
member of its family: S029 (mount reads pad NULs and serve stale
cache), S049 (three revisions under one filename; the wrong one was
published). A successful tool response is not evidence of a write.

**D4. A signed report signed the wrong revision.**
The Director adjudicated section 8 item by item and required three
changes: split the fact from the plan in 5.2, replace the size-based
bridge rule in sec 7 with a digest-based one, and give every empty
checkbox a reason line. The Executor made all three and wrote the new
revision to disk. The Director's editor had been opened on the
previous revision -- by a command the Executor supplied -- and saving
from that buffer restored the old text under a valid signature.

Measured: the file on disk was 11680 bytes, SHA-256
`1dc83142d69bf5f15726784cf74def506b681ef33c7ebb3dd44f1931595ffc9a`,
against the authored revision's 14428 bytes and
`49743d199752f4dfe7918acb35f9c6e7715a9ca006999a9d1891ff6ea1bb1068`.
The absence of the string `SHA-256 against the source` confirmed by
content, not by size, that the older revision was on disk.

The signature gate passed. It searches for two substrings and cannot
distinguish which revision carries them, so the control reported a
correctly signed report while the signed text asserted the opposite of
what had been decided -- item 5.2 in particular accepted, under a
signature, the very plan the Director had ruled must not be bundled
into that acceptance.

This is S049 in a third form: the correct file on disk, a stale copy
in a buffer. The Executor had applied the change-the-filename rule to
its own output directory and not to the file on the Director's disk,
and supplied the command that opened the editor without saying to
close it before the file was rewritten. The first signature was
declared void by the Executor rather than repaired, because editing
the body beneath an existing signature would fabricate what was
signed.

## 5. Known limitations -- stated plainly

**5.1 The wheel ships the loader without the corpus.**
`pyproject_probe.toml` does not declare `probe/suites` as package
data, so `pip install seismograph-probe` gets `load_suite_spec` and no
default spec file. Does not affect the repository gate. Fix belongs
with the probe 1.2.0 release, already in the backlog.

**5.2 Two content-addressing schemes coexist.**
`probe/canary.py::suite_content_hash` (prompts + tool schemas,
canonical JSON) is production and is what this task pinned.
`probe/canary_suite.py::CanarySuiteVersion.from_prompts` uses a
different prompt shape (`prompt_id` + `text`, no `system`, no
`category`) and omits tool schemas. It is marked in its own docstring
as a Phase-0 stub. `SuiteSpec` was deliberately placed in a new module
rather than folded into it: reconciling the two is an architectural
decision, not a cleanup, and editing the live registry for tidiness
would have put 378 tests at risk for no measured gain.

The decision is open. The Executor's recommendation is to declare
`canary_suite.py` legacy and rebase it onto `SuiteSpec`, but that work
sits inside BENCH-2 and is not scheduled. Accepting the limitation in
sec 8 does not schedule it; the two are kept apart there on purpose.

**5.3 Nothing in production consumes a spec file yet.**
Both live legs still run the literal corpus. No observer behaviour
changed this session, no probe ran, and no published number moved.
BENCH-1 makes a chosen corpus loadable; it does not yet let anyone
choose one.

**5.4 There is no sampler, so no real benchmark is usable yet.**
A corpus larger than 200 prompts is rejected, not reduced. Public
benchmarks are thousands of items, so a deterministic, seed- and
revision-pinned sampler is a precondition for the feature this task
exists to enable. BENCH-2.

**5.5 Differential-privacy calibration is still tuned to our corpus,
and this is a prediction, not a measurement.**
PRIV-011 clamps output length at 320 characters. A corpus whose
answers are long -- which most reasoning benchmarks are -- would clamp
flat, and `avg_output_length` is the single feature that separated
model generations with no overlap in FLOOR-1. The Executor expects
this to break on the first long-form corpus and has not measured it.
Nothing here should be read as evidence that a benchmark-derived
corpus will produce a usable signal.

**5.6 The pins are correct only while v2.0.0 is the live corpus.**
A legitimate new suite version requires a new pin, added
deliberately. Editing a pinned digest to make a red gate go green
would invert the control into a rubber stamp.

## 6. Provider ToS compliance

No provider was contacted in this task. No new prompts, endpoints,
models or call patterns were introduced; every test runs in mock mode
offline. No third-party corpus was ingested, so no upstream terms were
accepted or relied upon.

The mandatory `license` field is introduced here precisely because
that will stop being true in BENCH-2. A benchmark-derived corpus
carries upstream terms with it, several of the lists circulating are
non-commercial or prohibit redistribution, and a corpus whose terms
are unrecorded cannot be audited after the fact. Enforcing the field
at load time makes the omission fail immediately instead of at
publication.

## 7. Methodology note

One improvement to the process itself.

The project's hard rules about the device bridge address READ
staleness (S029) and filename reuse at PUBLICATION (S049). D3 is
neither: the WRITE path returned success and wrote a stale revision
under a reused output filename. The existing rules would not have
caught it.

The first rule drafted here was to compare file SIZE after every
bridge write. That rule fails the test the evidence standard requires
of any completeness measure: ask what failure would produce a perfect
score. Two revisions of equal length are indistinguishable by size,
and a same-length substitution is precisely the case a corpus gate
exists to catch. The size check worked this session only because the
appended test happened to lengthen the file; what actually confirmed
D3 was searching the file read back for a token that had to be
present. That is a digest check performed by hand.

Proposed rule, for `memory/CURRENT_STATE.md`:

> Never reuse an output filename between revisions within a session.
> After every write through the bridge, read the file back and compare
> its SHA-256 against the source before running the gate. Size is not
> sufficient: two revisions of equal length are indistinguishable by
> size. A successful tool response is not evidence of a write.
>
> Never rewrite a file through the bridge while the Director may have
> it open in an editor. Say so before the write, and confirm the
> editor is closed and reopened afterwards: a stale buffer saves the
> old revision over the new one and leaves a valid mtime behind
> (D4).

The method is not new to this session. It is the round trip already
used on `probe/suites/canary_v2.json`, where the digest recomputed
from the bytes on the Windows disk was compared against the pin. The
rule generalises to every file the bridge writes what was already done
for the corpus.

A second proposal, which changes the signing protocol and is therefore
the Director's to accept or reject rather than the Executor's to
adopt: **the signature line should carry the SHA-256 of the body it
signs.** Ask of the present control what failure would produce a
perfect score, and the answer is D4 -- signing a stale revision. A
digest in the signature makes that failure visible instead of silent,
and costs one command at signing time. The Executor recommends it and
has not implemented it; it is not part of this task.

The general form is one this project keeps rediscovering: the
confirmation an action returns describes the request, not the result.
It has now cost a published report body (S049), a false claim in a
commit message that was caught in time (D3), and a signature on the
wrong revision that was caught only by reading the signed file back
(D4).

## 8. Accountability

Six items, and they are not homogeneous: four ask the Director to
accept a limitation as known, one asks her to adopt a rule, one is not
an acceptance at all. Every box left empty carries its reason, so that
a month from now an unchecked box is distinguishable from a forgotten
one.

### Limitations offered for acceptance

- [x] sec 5.1 -- the wheel ships without the default corpus until the
      probe release. The repository gate is unaffected and the fix is
      already in the backlog as D-10, so accepting this opens nothing.
- [x] sec 5.3 -- no production consumer. No published number moved, no
      probe ran, no observer behaviour changed. Accepting this is the
      record that Session 054 was an engine-only session, which the
      closing packet must also state in words per Amendment 4 item 4.
- [x] sec 5.2 -- two content-addressing schemes coexist. The
      LIMITATION is accepted; the rebase is NOT scheduled and this box
      does not schedule it. The standing safeguard is the test from
      G-23. Recorded as a drafting defect: the first version of this
      item bundled the fact with a plan that depends on BENCH-2, which
      depends in turn on G-21, so a tick would have read as a decision
      with no one committed to executing it.

### Rule offered for adoption

- [x] sec 7 -- adopt the bridge-write rule into `CURRENT_STATE.md` in
      the digest form stated there, not the size form first drafted.

### Held open, deliberately

- [ ] sec 5.5 -- the DP clamp on long-form corpora. LEFT EMPTY ON
      PURPOSE. This is the one item where a tick would change the
      status of a risk rather than record one: empty, it requires a
      measurement before BENCH-2; ticked, it becomes accepted and
      requires nothing. Held pending G-21.
- [ ] BENCH-0 -- the two-tier decision. LEFT EMPTY ON PURPOSE. This is
      not a limitation of this task but an open decision, and it
      belongs in the decision register as its own entry rather than as
      a checkbox inside another task's report. Open decision, tracked
      separately.

The signature date is the date on which the boxes above were marked.
If either held item closes later, the date moves and this report
records why -- as was done for the deploy-before-signature gap of
2026-09-04.

**SIGNED -- Tatiana Radchenko, 2026-09-19.**
