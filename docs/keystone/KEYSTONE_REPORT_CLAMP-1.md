# KEYSTONE REPORT (SIGNED 2026-09-19) -- REQ-CLAMP-001..004
# CLAMP-1: the clamp measurement becomes an instrument, and the
# instrument immediately corrected the numbers that produced it
# Authored Session 056, 2026-09-19.
# Base: main @cb1194c (host baseline 398).
# Branch: seismograph/task-clamp-1.
# Contract: written S055, accepted by the Guide with amendments
# G-30 (three numbers, operation order named), G-31 (live-leg
# saturation), G-32 (no edits to probe/, engine/, gateway/).

## 0. Provenance

Script, tests and this report were written by Claude (Executor) in a
cloud sandbox and written into the Director's tree through the device
bridge, each file verified by SHA-256 against its source. The Director
ran every git command and every host gate. No provider was contacted;
no network call was made by anything in this task.

G-32 held: not one line changed in `probe/`, `engine/` or `gateway/`.
The clamp itself, the DP sensitivity and the noise helper were
imported, never modified and never restated.

## 1. What

`scripts/measure_clamp_saturation.py` (343 lines) and
`tests/test_clamp_saturation.py` (11 tests). Baseline 398 -> 409.

The instrument reads the pinned FLOOR-1 CSVs as text, applies the
probe's own clamp, prints three numbers for every comparison -- before
the clamp, after the clamp, after the clamp with DP noise -- and
classifies each stream as INTERPRETABLE or UNINTERPRETABLE from its
saturation fraction. It writes one JSON artefact per label and refuses
to overwrite an existing one.

It deliberately does not emit the word "stable". A saturated stream is
not stable, it is unmeasured, and the instrument must not print a word
a reader could mistake for a drift verdict.

## 2. Why

The clamp measurement existed as numbers in a session log. A number in
a log is not a gate: nothing fails when the code underneath it moves.
Keystone BENCH-1 sec 5.5 was left unaccepted by the Director precisely
so that it would require a measurement rather than become an accepted
risk; S055 produced the measurement; this task makes it survive.

The measurement also refuted its author. BENCH-1 sec 5.5 predicted the
clamp would flatten `avg_output_length` on a long-form corpus. It does
not: on the FLOOR-1 corpus the signal survives at nearly ten times the
noise the probe adds. The real failure mode is spread, not length.

## 3. Evidence

All [measured] unless tagged otherwise. Host gate run by the Director
and pasted back in full.

**Positive control, on the pinned CSVs, reproduced identically in the
container and on the Director's Windows host:**

| | value |
|---|---|
| compared n (paired, tool_calling excluded) | 42 |
| saturation, leg a / leg b | 0.214 / 0.167 |
| delta before the clamp | -39.6667 chars |
| delta after the clamp | -31.2857 chars |
| delta after the clamp, with DP noise | -34.2479 chars |
| noise scale at the production flush n=50 | 3.2000 |
| \|d\|/b at flush n | **9.7768** |
| noise scale at the compared n=42 | 3.8095 |
| \|d\|/b at compared n | 8.2125 |
| verdict | INTERPRETABLE |

**Adversarial, low-spread corpora [derived], same seed:**

| mean | CV | saturation | d raw | d clamped | d clamped+noise | verdict |
|---|---|---|---|---|---|---|
| 400 | 0.10 | 0.976 | -94.43 | -20.68 | -14.49 | UNINTERPRETABLE |
| 600 | 0.10 | **1.000** | -141.64 | **+0.00** | **-3.12** | UNINTERPRETABLE |
| 600 | 0.35 | 0.905 | -137.71 | -8.94 | -7.48 | INTERPRETABLE |
| 1000 | 0.10 | 1.000 | -236.07 | +0.00 | +7.33 | UNINTERPRETABLE |

The row that matters is the second. The clamped difference is exactly
zero, and with DP noise on top the stream emits **-3.12** -- not
nothing, but a small non-zero number that reads as "almost stable".
G-30 asked for the third column for exactly this reason: zero looks
like a failed measurement, -3.12 looks like a healthy one.

**Operation order, as G-30 required it named.** `probe/privacy.py`
flush(): clamp each record to [0, MAX_OUTPUT_LENGTH], then take the
mean, then add Laplace noise to the mean. Noise AFTER the clamp, so
G-30's escape clause does not fire.

**The binding to the live constants fires.** Changing
`MAX_OUTPUT_LENGTH` from 320 to 512 in the sandbox turned the gate red
(5 of 11 failed); restoring it returned 11 passed. The pinned numbers
cannot outlive the code they describe.

**Host gate:** ruff check clean, ruff format clean on 73 files,
409 passed.

## 4. Defects caught and fixed

**D6 -- the instrument corrected the numbers that produced it, on its
first run.** The S055 record reports the clamped generation signal as
|d|/b = 9.78. That ratio took its numerator from 42 paired records and
its denominator from a 50-record flush. Both figures are correct and
the ratio is defensible -- 3.20 is the noise on the metric the board
actually publishes -- but assembling a ratio from two different n
without saying so is the kind of thing this project refuses in other
people's work. The instrument now computes and prints both scales,
each labelled with its n, and the headline uses the production flush
because that is what a reader of the board sees.

This was not found by re-reading the log. It was found because the
measurement was expressed as code and the code had to name its inputs.

**D7 -- the first draft imported `probe` without putting the
repository root on the path**, so the instrument only ran when invoked
in a way nobody would invoke it. Fixed by the same bootstrap
`scripts/measure_drift_floor.py` uses. Trivial, recorded because an
instrument that runs only under the author's conditions is not an
instrument.

## 5. Known limitations -- stated plainly

**5.1 The 0.95 threshold is chosen, not measured.**
`UNINTERPRETABLE_AT = 0.95` is a judgement about when a length metric
stops carrying information. Nothing measured it. A measured threshold
would come from sweeping saturation against detector sensitivity on a
real corpus and finding where the change-point detector stops firing
on a known shift. Until then it is a reasonable line drawn by hand,
and a stream at 0.94 is called interpretable on that authority alone.

**5.2 The synthetic shapes are [derived], not observed.** They apply
the measured generation ratio to a Gaussian of chosen mean and spread.
No real low-spread corpus has been run. The zero in the table is a
property of the model, and the model may be wrong about what a real
reasoning benchmark's length distribution looks like.

**5.3 Nothing in production consumes the classification.** The
saturation fraction is computed inside this instrument and stays
there. The probe does not emit it, the gateway does not store it, the
board does not show it. G-32 forbade touching those trees and that was
correct, but it means the silent-failure mode this task documents is
still fully present in the live system. The fix -- emit the saturation
fraction beside the metric, and make `MAX_OUTPUT_LENGTH` a function of
the suite's max_tokens recorded in the batch because it enters the DP
sensitivity -- needs its own contract.

**5.4 G-31 is still unanswered.** The saturation fraction on the LIVE
legs is not measured, only bounded from the published means: <= 42.1%
(google) and <= 28.6% (mistral) on the 2026-09-19 read. Blocked
externally: no working credential exists on the Director's machine for
either leg. One run of `measure_drift_floor.py --max-tokens 64` closes
it.

**5.5 One provider, one model pair, one date.** Everything measured
here comes from two runs of one corpus against Google's endpoint on
2026-09-14. Generalisation beyond that is not supported.

## 6. Provider ToS compliance

No provider was contacted. No prompts were sent, no endpoints called,
no credentials used. The instrument reads two CSV files that are
already committed to this repository and generates numbers. There is
no ToS surface in this task.

## 7. Methodology note

The improvement this task suggests is the one it demonstrates on
itself.

A number written into a session log cannot check itself. The same
number expressed as an instrument has to name its inputs, and naming
them is what exposed D6 within a minute of the first run. The log entry
had been reviewed, recomputed by a second implementation, quoted in a
commit message and merged to main, and the error survived all of it,
because none of those steps required the ratio to state the n it came
from.

Proposed rule, for `business/guide_pack/05`:

> A number that appears in a published artefact has an instrument that
> recomputes it in the gate. Prose recording a measurement is a report
> of a measurement, not the measurement. If it is worth publishing, it
> is worth being recomputable by a stranger with the repository and no
> access to the machine that produced it.

This is not a new idea in the project -- it is what
`measure_drift_floor.py` already does for FLOOR-1. It has simply never
been stated as a rule, and the gap showed the moment a measurement was
recorded any other way.

## 8. Accountability

Four items. Every box left empty carries its reason, so that an
unchecked box is distinguishable from a forgotten one.

### Limitations offered for acceptance

- [x] sec 5.1 -- the 0.95 interpretability threshold is a judgement,
      not a measurement, and the report says so where it is used.
- [x] sec 5.2 -- the adversarial shapes are derived from a model of a
      long-form corpus, not from one that was run.
- [x] sec 5.3 -- the silent-failure mode remains fully present in the
      live system. G-32 held deliberately; the fix needs its own
      contract and is not scheduled by this box.

### Rule offered for adoption

- [x] sec 7 -- a published number gets an instrument that recomputes
      it in the gate. Proposed for guide_pack/05, alongside G-37.

### Held open, deliberately

- [ ] sec 5.4, G-31 -- LEFT EMPTY ON PURPOSE. Ticking it would turn an
      unmeasured quantity into an accepted one. It is blocked by a
      provider-side credential migration, not by a decision, and it
      closes with one probe run whenever a working key exists.

The signature date is the date on which the boxes above were marked.

**SIGNED -- Tatiana Radchenko, 2026-09-19.**
