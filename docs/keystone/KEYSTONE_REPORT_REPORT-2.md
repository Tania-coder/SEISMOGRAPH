# KEYSTONE REPORT (SIGNED 2026-09-22) -- REQ-REPORT2-001..003
# REPORT-2: the published report is pinned to its own instrument
# Authored Session 057, 2026-09-22.
# Base: main @fdbbfb7 (host baseline 409).
# Branch: seismograph/task-report-2.
# Material set by the Guide's opening prompt for S057: F3, F4 in its
# corrected form, and 12a. F3 is read as the clamp finding; the
# guide_pack is gitignored and carries no definition this tree can
# read, so that reading is [assumed] and is recorded as such.

## 0. Provenance

Instrument, tests and the report text were written by Claude
(Executor) in a cloud sandbox and written into the Director's tree
through the device bridge. Every file was read back and verified by
SHA-256 against its source before any gate was run:

    scripts/weather_window_stats.py        f8df38e3..78ef3
    tests/test_weather_window_stats.py     8c7d6522..47825
    docs/reports/2026-09-22-...-02.md      542c2d4d..4ddbb

The board read, every git command and every gate run are the
Director's, from her own PowerShell. The evidence snapshot
`docs/evidence/weather-2026-09-22T104310Z.json` was written by the
Director's own read of the public board; the Executor's independent
copy of it hashed identically, which is the only reason this report
may quote figures derived from it.

Publication is the Director's act. Nothing in this task was posted.

## 1. What

`scripts/weather_window_stats.py` (319 lines) derives, from an
archived `/v1/weather` snapshot: window span, mean inter-sample
interval, the nominal interval, the collection rate against it, the
age of the newest row, whether the published status agrees with that
age, and the upper bound on clamp saturation. It classifies collection
NOMINAL / DEGRADED / DARK / UNDETERMINED and never re-labels a leg
with a word the board itself publishes.

`tests/test_weather_window_stats.py` (22 tests) pins those derivations
against the two committed snapshots the report cites, and pins the
report text to the instrument.

`docs/reports/2026-09-22-weather-report-02.md` is the archival copy of
record for Weather Report #2, committed before publication so that the
repository holds the earliest timestamp for it.

## 2. Why

Keystone CLAMP-1 sec 7 established, by signature, that a number in a
published artefact has an instrument that recomputes it in the gate.
Weather Report #1 did not meet that rule: its span, its mean interval,
its 61% cadence figure and its 56-hour row age were arithmetic done
once, in prose, by hand. They were correct. They were also
unrepeatable, and the project's own evidence standard says prose
recording a measurement is a report of one, not the measurement.

This task is the first artefact produced under that rule, and it
extends it one step: not only is the instrument bound to the live
constants, the ARTEFACT is bound to the instrument.

## 3. Evidence

### 3.1 Bindings, verified by breaking them

Each was changed, the suite run, and the change reverted. `git diff`
was empty afterwards and the full suite returned to green.

| change | result |
|---|---|
| `45.32 h` -> `45.99 h` in the report text | 1 failed: the report test |
| `MAX_OUTPUT_LENGTH` 320 -> 512 | 2 failed, incl. the report test |
| `STALE_AFTER_HOURS` 30.0 -> 200.0 | 5 failed, incl. the report test |

The nominal cadence is parsed from the single cron line in
`.github/workflows/probe_weather.yml`; a schedule the parser cannot
interpret raises `WorkflowScheduleError` rather than defaulting. Two
unparsable forms are pinned.

### 3.2 The figures the report quotes [measured / derived]

Snapshot 2026-09-22T10:43:10Z [measured, Director's read, 731 bytes,
SHA-256 AF57CFA9..7AA123]:

    google   span 119.97 h  interval 13.33 h  rate 0.9003  NOMINAL
             age 0.68 h (published field)  status STABLE, agrees
             saturation bound <= 0.4193
    mistral  span 407.88 h  interval 45.32 h  rate 0.2648  DARK
             age 73.19 h (published field)  status STALE, agrees
             saturation bound <= 0.2856

Snapshot 2026-09-09T17:38:24Z [measured, committed S050-era evidence],
age derived from the read time in its filename:

    mistral  span 112.19 h  interval 12.47 h  rate 0.9627  NOMINAL
             age 176.00 h  status STABLE, DOES NOT agree

All spans, intervals and rates are [derived] from the published
window bounds and sample counts; the bounds, counts, statuses and
means are [measured] fields of the snapshots.

### 3.3 Gates

    container, py3.11, ruff 0.15.11:  ruff clean, 75 formatted, 429
    host, py3.10.11, ruff 0.15.20:    ruff clean, 75 formatted, 429
    container, after the report test: 431

The host gate at 429 is the Director's, run on the branch before the
report and its test were added. The 431 figure is the container's and
is NOT a gate result; the host gate for 431 is run before the merge.

## 4. Defects caught and fixed

**D8 -- the test loaded the instrument by path, as CLAMP-1's test
loads its own, and failed at collection rather than at use.**
`@dataclass` resolves its module out of `sys.modules` while the class
body executes, and a module loaded by `spec_from_file_location` is not
there unless it is put there. CLAMP-1's script has no dataclass, so
the precedent it set was silently incomplete. Fixed by registering the
module before `exec_module`; the reason is recorded at the fix, not
only here.

**D9 -- Report #1 stated two independent defects as one.** "The
mistral row is 56 hours old" and "the mistral leg is losing runs" were
written as a single finding. The instrument separates them: on
2026-09-09 that leg was stale while collecting at 0.9627 of nominal,
and on 2026-09-22 it is stale AND collecting at 0.2648. DASH-3 closed
the first and does not touch the second. This was not caught by
review; it was caught by computing both quantities side by side, which
is the same shape as D6 in CLAMP-1.

**Not a defect, recorded to prevent a false one:** the saturation
bound for the google leg reads 0.4193 here against 42.1% in
CURRENT_STATE. Both are correct. The 42.1% came from the 2026-09-19
mean of 134.691; this is the 2026-09-22 mean of 134.17486. The record
will be updated at close-out to state which read each bound came from.

## 5. Known limitations -- stated plainly

5.1 **The report test matches substrings.** It proves that each
figure appears somewhere in the file, not that it appears in the
sentence that claims it. A figure moved into the wrong paragraph would
pass. This is the same weakness the signature gate has, noted at S056:
a substring match cannot see meaning. It is a real control against the
failure that actually happens -- a constant moving and the report not
following -- and not a proofreader.

5.2 **The collection bands (0.75, 0.40) are judgement.** They were
chosen so that the measured 2.5-4.5 h scheduler lateness cannot push a
healthy leg out of NOMINAL. They are not swept against a cost of false
flags. The report quotes rates, not band names, so nothing published
rests on them; the classification in the instrument does.

5.3 **The 2026-09-09 snapshot carries no `window_age_hours`.** It
predates DASH-3, so its ages come from a `--read-at` supplied by hand
from the read time in its filename. The filename is the provenance.
When the field is present it is preferred and the hand-supplied value
is not used.

5.4 **G-31 is still not measured.** The live saturation fraction is
bounded, not observed. The instrument publishes the bound and labels
it as one.

5.5 **Why the mistral leg stopped on 2026-09-19 is not diagnosed.**
The report says so. A prior stoppage on that leg was an account-level
rate limit; assuming the same cause is exactly the move this project
exists to refuse.

5.6 **One observer.** Unchanged and central. Nothing in this task
advances the quorum; publishing is the only thing that can, and this
task exists to make publishing possible.

## 6. Provider ToS compliance

No canary probe was designed or changed. No provider endpoint was
called by anything in this task. The single network read was the
Director's own `GET` of her own public board, from her own machine.
The instrument makes no network calls and reads only committed files.

## 7. Methodology note

One improvement, offered for adoption:

**Extend the CLAMP-1 rule to the artefact.** The rule as written binds
a published number to an instrument. It does not stop the instrument
and the artefact from drifting apart -- a report is a file that never
re-runs, published on a platform that will certainly never re-run it.
The test added here pins the artefact's text to the instrument's
output, so that moving a live constant names the report file in the
failure. Proposed for guide_pack/05 as the second half of the CLAMP-1
rule: a published artefact is checked against its instrument in the
same gate that checks the instrument against the code.

## 8. Accountability

Six items. Every box left empty carries its reason, so an unchecked
box is distinguishable from a forgotten one.

### Limitations offered for acceptance

- [x] sec 5.1 -- the report test matches substrings and cannot see
      whether a figure sits in the sentence that claims it.
- [x] sec 5.2 -- the collection bands are reasoned, not swept.
- [x] sec 5.3 -- the 2026-09-09 ages rest on a read time taken from a
      filename.

### Rule offered for adoption

- [x] sec 7 -- a published artefact is checked against its instrument
      in the same gate. Proposed for guide_pack/05.

### Publication decisions taken by the Director this session

- [x] F4 is published in its corrected form, including the statement
      that a generation call has not been made.
- [x] The mistral stoppage is published as not diagnosed, rather than
      held for investigation.

### Held open, deliberately

- [ ] sec 5.4, G-31 -- LEFT EMPTY ON PURPOSE, as in CLAMP-1. Ticking
      it would convert an unmeasured quantity into an accepted one. It
      closes with one probe run whenever a working credential exists,
      and the native Gemini provider is what produces one.

The signature date is the date on which the boxes above were marked.

**SIGNED -- Tatiana Radchenko, 2026-09-22.**
