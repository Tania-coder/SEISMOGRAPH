<!--
SEISMOGRAPH -- Weather Report #2
Copyright 2026 Tatiana Radchenko (tatyan.radchenko@gmail.com)
Licensed under the Apache License, Version 2.0, as part of the
SEISMOGRAPH project. See LICENSE and COPYRIGHT at the repository root.
-->

**SEISMOGRAPH -- Weather Report #2**

| | |
|---|---|
| Author | Tatiana Radchenko -- Independent, Aarhus, Denmark |
| Written | 2026-09-22 |
| Data as of | 2026-09-22 10:43:10 UTC |
| Project | SEISMOGRAPH (engine) / Drift Defense (service) |
| Repository | https://github.com/Tania-coder/SEISMOGRAPH |
| Software DOI | https://doi.org/10.5281/zenodo.21045517 |
| Copyright | (c) 2026 Tatiana Radchenko. Apache-2.0, see LICENSE. |

This file is the archival copy of record. It is committed to the
repository **before** the text appears on any external platform, so the
repository history carries the earliest timestamp for it. External
publication URLs are appended below as they happen.

**Published:**
- dev.to -- (pending)
- LinkedIn -- (pending)

**Provenance.** Every figure below is recomputed from two committed
snapshots of the public board by `scripts/weather_window_stats.py`,
which runs in the project's test gate. The snapshots are
`docs/evidence/weather-2026-09-09T173824Z.json` and
`docs/evidence/weather-2026-09-22T104310Z.json`. Nothing here is
arithmetic done once in prose.

---

# My drift board learned to say "I don't know". Here is what it still cannot say.

SEISMOGRAPH is an open-source early-warning network for silent drift in
third-party LLM APIs -- the 2am question of whether the model changed
underneath you or your prompt is simply worse today. It runs a fixed
canary suite against provider endpoints on a schedule, ships only
hashes and differentially-private aggregates, and publishes a public
board.

The same two things, up front, because everything below depends on
them:

- **There is exactly one observer, and it is me.** A public drift alert
  requires cross-observer agreement from three independent observers.
  At one observer, no public alert can fire *by construction*. That is
  a property of the design, not a gap in it.
- **The live board's baseline was re-established on 2026-08-04.** There
  is no continuous history before that date. Separately, on historical
  replay of a known incident, a seeded backtest flags it 38 days before
  the postmortem. That is a synthetic replay, not a live catch, and I
  do not describe it as one.

[Report #1](https://dev.to/taniacoder/i-gave-my-drift-monitor-a-denominator-the-first-thing-it-exposed-was-a-hole-in-my-own-data-5508)
ended with a list of limitations. The sixth read:

> **No staleness signal.** mistral's 56-hour-old row is visible on the
> board but not flagged, because "stale after N hours" is a judgement
> that needs its own defence. The timestamps are published; the reader
> concludes.

That one is now closed, and closing it turned out to be the smaller
half of the story.

## The same leg, eighteen days apart

| mistral/mistral-small-latest | 2026-09-09 17:38 UTC | 2026-09-22 10:43 UTC |
|---|---|---|
| `sample_count` | 10 | 10 |
| `window_end` | 2026-09-02T09:38:39Z | 2026-09-19T09:31:44Z |
| age of newest row | **176.00 h** | **73.19 h** |
| published `status` | **STABLE** | **STALE** |
| status agrees with age | **no** | yes |

Nothing about that leg got better. A third status did.

The board's `status` used to read one table: `DRIFTING` if a
quorum-verified alert existed, `STABLE` otherwise. At one observer no
alert can exist, so `STABLE` was not a finding. **The green light was
produced by the system's own inability to raise an alarm.** A leg whose
probe had been dead for a week published it with a healthy-looking
count of ten.

There are now three states, and a leg whose newest sample is older than
30 hours publishes `STALE` regardless of what the alert table says. The
threshold is not a guess in a report: the probe fires twice a day and
was measured running 2.5 to 4.5 hours behind its own cron slot, so 30
hours is one missed slot plus that observed lateness. Below it, "merely
late" and "already stopped" are not separable, and I would rather the
board say nothing than say the wrong one.

`STALE` does not hide or alter the leg's published metrics, and it does
not attempt to say *why* the leg stopped. It is a statement about the
data, not about the provider.

## What the counts still cannot see

Here is the part I got wrong in Report #1, and the instrument is what
showed me.

Report #1 treated "the mistral row is 56 hours old" and "the mistral
leg is losing runs" as one defect. They are two, they are independent,
and only one of them is now visible on the board.

Recomputed from the snapshots:

| | 2026-09-09 | 2026-09-22 |
|---|---|---|
| window span | 112.19 h | 407.88 h |
| mean interval between samples | 12.47 h | **45.32 h** |
| nominal interval (twice daily) | 12.00 h | 12.00 h |
| collection rate | 0.9627 | **0.2648** |

On 2026-09-09 that leg was **stale but collecting normally** -- 12.47
hours between samples against a 12.00 hour schedule. Today it is
**flagged stale and collecting at a quarter of its own cadence**: ten
rows spread across seventeen days. Its `window_start` is still
2026-09-02T09:38:39Z, the frozen timestamp from the September outage,
because ten rows in seventeen days is not enough to evict it from a
last-ten window.

So the published "recent average output length" for that leg covers
**seventeen days**, and the google leg's covers five. The board does
not say so. Both legs print `10 / 10 / 10`.

This is the same shape as Report #1's finding, one level up. A run that
exhausts its retries writes no row at all, so a count can never witness
its own losses. Adding a third status fixed the *age* of the newest
row. It did not make the *rate* visible, and the rate is what tells you
whether a number means anything.

The cadence figures above are not prose. `nominal interval` is parsed
out of the cron line in the probe's own workflow file, so if I change
the schedule and forget a report, the test suite fails instead of the
report quietly lying. That parse refuses anything it cannot interpret
rather than guessing.

## The second way a stream can look stable

There is a failure mode in this design that no staleness flag reaches,
and it is worse than a dark leg because it is not dark.

The probe clamps each output length to 320 characters before averaging,
because the differential-privacy noise is calibrated to that bound. On
the corpus I measure with, that clamp removes about a third of the
mean, and the signal that separates two model generations survives it
at roughly ten times the noise. I had predicted the clamp would destroy
that signal. It did not, and the prediction was wrong for an
interesting reason: what matters is not the mean length but the
**fraction of records above the cap**, which depends on spread.

Take a corpus with a tight spread and a mean above the cap. Every
record saturates. Both legs then report exactly 320, a difference of
exactly 0.00 where the unclamped difference would have been -141.6
characters -- and with the DP noise applied, the stream emits **-3.12**.

That number is the dangerous one. It does not read as "not measured".
It reads as "almost perfectly stable".

A saturated stream is not a stable model. It is an unmeasured one, and
in every field the board publishes, the two are identical. I do not
have this measured on the live legs; from the published means I can
only bound it -- at most 41.9% of google's records and at most 28.6% of
mistral's can be at the cap. Near-total saturation is ruled out on both.
The exact fraction is not measured, and I am not going to state it as
though it were.

The rule I took from this, and now apply: **a number that appears in a
published artefact has an instrument that recomputes it in the test
gate.** Prose recording a measurement is a report of a measurement, not
the measurement. Every figure in this report satisfies that rule; the
script that produces them is in the repository and runs in the gate.

## Where a benchmark comes in, and why not yet

The feedback I keep getting on the 50-prompt canary suite is the
correct feedback: don't build your own benchmark, build the
infrastructure around the ones that exist and let the operator pick.
That is the direction, and it is decided: only a suite registered in a
pinned public registry can ever enter cross-observer correlation, while
private corpora stay fleet-only. Naive pluggability would make the
observer count one *per suite* and quietly destroy the quorum that
makes a public alert mean anything.

What the clamp finding adds is a prerequisite I did not see before.
External benchmarks have wildly different output profiles -- a
multiple-choice suite sits far below the cap, a code or essay suite may
sit entirely above it. Running one of those through this probe today
could produce exactly the -3.12 shape above. So before any external
suite enters the network, its stream has to be classified interpretable
by the saturation instrument. That is a direction and a constraint, not
a shipping date, and no external benchmark has been run through this
probe yet.

## I was wrong about the Google leg

Worth recording because the correction only happened because someone
asked the right question.

The google leg authenticates with a key in a format the provider is
migrating to. Two auth paths were tested; both failed; I wrote down
that the observer could not be restored, and started reasoning about
which of three bad options to take.

Then I was asked what had actually been tested, as against what was
being claimed. Four paths, with the response body read rather than the
status code alone:

| | native endpoint | OpenAI-compatible layer |
|---|---|---|
| provider-specific key header | **200** | 400, missing or invalid Authorization header |
| `Authorization: Bearer` | 401 | 400 |

The key is live. The account is live. What is incompatible is the auth
*scheme* -- the compatible layer demands a header the new key format is
rejected in, and my provider code speaks only that layer. The leg needs
code, not a new credential, and the model tuple and board history are
preserved.

Two tested paths were generalised into a property of the world. To be
precise about what is still inferred: the 200 was against a model
listing, not against a completion. That a generation call with the same
header also succeeds is expected and **not yet measured**.

## Limitations, stated rather than buried

1. **One observer.** No public alert can fire. Everything above is
   single-organisation fleet data.
2. **The collection rate is still not on the board.** `STALE` flags the
   age of the newest row. A leg collecting at a quarter of its cadence
   with a fresh newest row would publish `STABLE` and be within its
   rights.
3. **The censoring described in Report #1 is unfixed.** Runs are
   discarded when prompts exhaust retries on 429; 429 correlates with
   provider load; provider load is when a provider is most likely to
   shift behaviour. The surviving samples systematically exclude the
   periods most worth measuring.
4. **The window is last-10-by-id, not time-bounded.** Publishing the
   bounds makes its age visible; it does not change what it selects.
   The mistral leg above is the consequence.
5. **The live saturation fraction is bounded, not measured.** See above.
6. **Why the mistral leg stopped on 2026-09-19 is not diagnosed.** An
   earlier stoppage on that leg was an account-level rate limit. This
   one has not been investigated, and I am not assuming it is the same
   cause.
7. **The 30-hour threshold is reasoned, not optimised.** It was chosen
   from the measured scheduler lateness, not swept against a cost of
   false flags.
8. **Overlapping windows.** The last-10 window slides; two successive
   reads share rows, so a difference between them is not a difference
   between independent samples.

The board is at https://seismograph-weather.onrender.com/dashboard and
the probe is `pip install seismograph-probe`. If you run agents or
evals against a third-party API on a schedule, you already have the
data this network needs; a second observer is the only thing that turns
any of this into an alert anyone can act on.
