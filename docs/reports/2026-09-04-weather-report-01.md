<!--
SEISMOGRAPH — Weather Report #1
Copyright 2026 Tatiana Radchenko (tatyan.radchenko@gmail.com)
Licensed under the Apache License, Version 2.0, as part of the
SEISMOGRAPH project. See LICENSE and COPYRIGHT at the repository root.
-->

**SEISMOGRAPH — Weather Report #1**

| | |
|---|---|
| Author | Tatiana Radchenko — Independent, Aarhus, Denmark |
| Written | 2026-09-04 |
| Data as of | 2026-09-04 18:00 UTC |
| Project | SEISMOGRAPH (engine) / Drift Defense (service) |
| Repository | https://github.com/Tania-coder/SEISMOGRAPH |
| Software DOI | https://doi.org/10.5281/zenodo.21045517 |
| Copyright | (c) 2026 Tatiana Radchenko. Apache-2.0, see LICENSE. |

This file is the archival copy of record. It is committed to the
repository **before** the text appears on any external platform, so the
repository history carries the earliest timestamp for it. External
publication URLs are appended below as they happen.

**Published:**

- dev.to — _URL pending_
- LinkedIn — _URL pending_

---

# We published a denominator. The first thing it exposed was a hole in our own data collection.

SEISMOGRAPH is an open-source early-warning network for silent drift in
third-party LLM APIs -- the 2am question of whether the model changed
underneath you or your prompt is simply worse today. It runs a fixed
canary suite against provider endpoints on a schedule, ships only hashes
and differentially-private aggregates, and publishes a public board.

Two things about its current state, up front, because everything below
depends on them:

- **There is exactly one observer, and it is us.** A public drift alert
  requires cross-observer agreement from three independent observers. At
  one observer, no public alert can fire *by construction*. That is a
  property of the design, not a gap in it: a single organisation seeing
  a wobble is not evidence that a provider changed.
- **The live board's baseline was re-established on 2026-08-04.** There
  is no continuous history before that date. Separately, on historical
  replay of a known incident, a seeded backtest flags it 38 days before
  the postmortem. That is a synthetic replay, not a live catch, and we
  do not describe it as one.

Last week we shipped a small read-side change: `/v1/weather` now
publishes, alongside each metric, the number of samples it rests on and
the time bounds of the window those samples came from. Publishing a rate
without its base is a defect; we had been doing it.

This is what the denominator found.

## The board, read 2026-09-04

| | google/gemini-3.5-flash-lite | mistral/mistral-small-latest |
|---|---|---|
| status | STABLE | STABLE |
| `sample_count` | 10 | 10 |
| `json_sample_count` | 10 | 10 |
| `length_sample_count` | 10 | 10 |
| `window_start` | 2026-08-28T01:34:25Z | 2026-08-28T17:27:23Z |
| `window_end` | 2026-09-04T09:46:39Z | **2026-09-02T09:38:39Z** |
| window span | **176.2 h** | **112.2 h** |
| mean inter-sample interval | **19.6 h** | 12.5 h |

The probe is scheduled twice a day. Ten samples should therefore span
about **108 hours**. The google leg's ten samples span 176.2 hours: it
is emitting at 61% of its own cadence. And the mistral leg's window
ends on 2026-09-02 -- as of the read at **2026-09-04 18:00 UTC** that
row is **56 hours old**, four scheduled slots ago. Both figures are
recomputable from the bounds in the table by anyone reading this.

**Every count on that table reads 10.** Both legs. The whole time.

## Why the counts could never have found it

The probe runs a 50-prompt canary suite and flushes one aggregated row
per run. If any single prompt exhausts its retries, the runner discards
the entire suite: flushing at a reduced *n* would change the
differential-privacy sensitivity of the stream (`MAX/n`), so a partial
batch is not a smaller sample, it is a differently-calibrated one.

The consequence is that a lost run writes **no row at all**.

A class of loss that removes rows entirely is invisible to any count,
however many counts you publish. `sample_count` answers *how many rows
survived into this metric*. Only the window bounds answer *how long it
took to collect them* -- and it was the second question that found the
defect. We did not anticipate this when the change was scoped.

## Then it moved legs

The interesting part is what happened between two reads 48 hours apart.

| leg | 2026-09-02 | 2026-09-04 |
|---|---|---|
| google window span | 196.2 h | 176.2 h |
| google `avg_output_length` | 131.060 | 130.398 |
| mistral window span | 112.2 h | 112.2 h |
| mistral `avg_output_length` | 89.42253 | **89.42253** |

google partially recovered. mistral froze -- byte-identical values,
byte-identical bounds, because not one new row arrived. The leg we were
about to describe as the clean one is the leg that is currently dark.

Both still publish `10 / 10 / 10`.

## What the run logs actually say

We reconciled the board against the scheduler for the window
2026-08-24T05:58Z to 2026-09-01T10:11Z:

- **16** scheduled runs fired.
- **9** succeeded, **7** failed, **0** were cancelled at the run level.
- **10** rows reached the board from the google leg.
- So **6** runs produced no google row.

That kills the comfortable explanations. The scheduler ran. Nothing hit
a job timeout. The rows were lost *inside* runs that happened.

Per-run detail, from the emission logs:

| run | leg | outcome |
|---|---|---|
| #118 | google | `40/50 prompts completed`, 10 failed ids scattered mid-suite |
| #122 | google | `49/50 prompts completed`, **one** failed id |
| #126 | mistral | `0/50 prompts completed`, all fifty failed, job dead in 75 s |

The emission policy is printed by the probe itself: `pacing: 4500 ms
between prompts, <= 2 retries on 429/503`.

So the mechanism on the google leg is not a budget running out. It is
**one prompt out of fifty losing three attempts to a transient 429, and
taking the other forty-nine with it.** In run #122 the suite was 98%
complete and published nothing.

The mistral leg is a different failure entirely: zero completions in 75
seconds is not rate-limit turbulence, it is a hard condition at the
endpoint. We do not yet know which, and that is its own finding -- the
run log records the failed prompt ids and nothing else. No status code,
no response body, no retry spend. **We built a drift detector whose own
collection failures are not diagnosable from its own logs.** That gets
fixed before the collection logic does.

One more thing worth stating because it invalidates arithmetic we had
been doing: scheduled runs fire **2.5 to 4.5 hours after** their cron
slot. Any reasoning that treats missing samples as exact multiples of
the 12-hour interval is unsound.

## The part that matters: the surviving samples are biased, not just sparse

This is the finding we would most want a reader to take away, and it is
uncomfortable.

A run is discarded when prompts exhaust retries on 429. 429 correlates
with provider load. And provider load under stress is precisely the
condition under which a provider is most likely to shift behaviour --
it is the mechanism this project exists to detect.

So the samples that survive systematically exclude the periods most
worth measuring. The google leg's drift readings are computed over a
**censored sample**, censored by a variable correlated with the thing
being measured. This is not a footnote about data quality. It changes
what the number means.

For completeness: across the two reads neither leg shows a drift
signal. google's normalised JSON validity moved +0.0016 in raw units
(+0.12 sd of the per-batch DP noise) and its average output length
-0.66 characters (-0.33 sd); mistral moved by exactly zero because it
has no new data. **Read those as "nothing to report from a sample we
have just told you is compromised", not as "the providers are stable".**

## Limitations, stated rather than buried

1. **One observer.** No public alert can fire. Everything above is
   single-organisation fleet data.
2. **The censoring above.** The google leg's numbers are not a random
   sample of provider behaviour.
3. **Overlapping windows.** The last-10 window slides; two successive
   reads share rows, so a difference between them is not a difference
   between independent samples. The sd figures are indicative.
4. **The window is last-10-by-id, not time-bounded.** Publishing the
   bounds makes its age visible; it does not change what it selects.
5. **Counts do not say why a row was excluded.** Enough for a
   denominator, not enough for a diagnosis.
6. **No staleness signal.** mistral's 56-hour-old row is visible on the
   board but not flagged, because "stale after N hours" is a judgement
   that needs its own defence. The timestamps are published; the reader
   concludes.
7. **Publishing volume is not authenticated.** Sample counts on the
   public payload are not yet quorum-gated, so forged volume would
   raise apparent support for an average. Open, tracked, undefended.

## Why publish this

Because the honest version is more useful than the polished one, and
because the bottleneck is structural rather than technical: at one
observer this network is correct and silent. It becomes an early-warning
system at three.

If you run a canary suite against a provider API -- any provider, any
suite -- and would consider contributing observations, or just want to
tell us the collection design is wrong, the code and the board are open.

Engine: **SEISMOGRAPH** (Apache-2.0). Service: **Drift Defense**.

- Board: https://seismograph-weather.onrender.com/dashboard
- Repo: https://github.com/Tania-coder/SEISMOGRAPH
- Probe: `pip install seismograph-probe`
- DOI: https://doi.org/10.5281/zenodo.21045517

All figures above are measured, dated, and reproducible from the public
endpoint and the public Actions history at the time of writing.
