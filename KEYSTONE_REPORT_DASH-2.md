# KEYSTONE REPORT (UNSIGNED) -- REQ-DASH-004
# DASH-2: sample provenance for the published weather numbers
# Authored Session 047, 2026-08-28. Recovered and gated Session 048,
# 2026-09-02. Base: main @b144e87 (baseline 309).
# Contract: agreed with Tatiana in-session before any edit (goal,
# constraints, field granularity, scope boundary, both adversarial cases).

## 0. Provenance

100% AI-generated (Claude, claude-opus-5): the defect finding, the
contract, the implementation, all 16 tests, and this report. Tatiana
chose the field granularity (per-metric counts over a single count) and
set the scope boundary (raw provenance only, no staleness flag), and
approved the contract before implementation began.

## 1. What

`GET /v1/weather` now publishes the base its numbers rest on.

New on `ModelWeatherResponse` (all additive, all defaulted, so existing
callers are unaffected):

  sample_count         batches in the read window (at most 10)
  json_sample_count    of those, how many fed recent_json_success_rate
  length_sample_count  of those, how many fed recent_avg_output_length
  window_start         oldest batch timestamp, timezone-aware UTC
  window_end           newest batch timestamp, timezone-aware UTC

New in `gateway/main.py`: `_as_published_utc()`, and provenance
computation inside `_compute_model_weather()`. No new database query --
every value is derived from the `signals` list the function already
holds.

## 2. Why

DASH-1 made `recent_json_success_rate` a true [0, 1] rate. It did not
say what that rate rests on. The board published 98.2% with no
indication of whether it came from ten batches or two, or how old they
were.

Publishing a percentage without its denominator is the same defect
class DASH-1 had just fixed, one level up -- and it would have shipped
in Weather Report #1, the network's first public artefact. That is the
GTM consequence; the operational one is that the open google-leg sample
loss (31% of runs discarded) was invisible to any reader of the board.

It also blocked a standing question. The PRIV-011 stream contamination
on `avg_output_length` was believed to have aged out by arithmetic --
17 days at 2 runs/day against a 10-batch window -- but `/v1/weather`
exposed no timestamps, so that was inference, not measurement. The
observed google/mistral spread (132.23 vs 89.08) fits a real verbosity
difference AND residual 8192-era rows equally well. `window_start` now
settles it by observation.

## 3. Why two counts and not one

`_compute_model_weather` builds its two metric lists with different
filters. `lengths` takes rows with a non-null `avg_output_length`;
`rates` takes rows that `_scorable_json_rate` could interpret, which
excludes partial runs and unknown suite versions (the DASH-1
completeness guard). The sets diverge in general, and neither equals
`len(signals)`.

A single `sample_count` would therefore misstate at least one metric --
reporting 10 when the rate actually rests on 7. Three counts are
published: the window size, and one true denominator per metric.
`test_counts_diverge_when_a_row_is_uninterpretable` pins the case.

## 4. Why the timestamps gained an offset

Signal and alert rows are stored as naive UTC by construction
(`datetime.now(timezone.utc).replace(tzinfo=None)`), and that invariant
is load-bearing for the naive-to-naive comparisons in this module. It
is not load-bearing for what gets published.

A naive datetime serialises to an ISO 8601 string with no offset, and
ISO 8601 reads an offset-less timestamp as LOCAL time. `_as_published_
utc` attaches the offset the stored value already implies. It never
shifts the instant, and internal comparisons stay naive.

## 5. Evidence

- Gate (container, 2026-08-28): `ruff check .` clean,
  `ruff format --check .` clean, `pytest -q` **32 passed** on the
  weather read path (16 DASH-1 + 16 new). Host gate pending: expect
  309 + 16 = **325**.
- **Host gate, first run (2026-09-02, Session 048): 324 passed,
  1 FAILED.** The count was right and the projection was wrong. The
  container run had been scoped to the weather read path, so it never
  executed the guard that the change actually collides with:
  `tests/test_gateway.py::test_gateway_same_suite_three_orgs_reach_quorum`
  asserts EXACT set equality on the `/v1/weather` payload keys (the A6
  backward-compatibility guard from DASH-1). Five additive fields break
  an exact-equality assertion by construction.

  Finding, recorded rather than smoothed over: a scoped subset run
  cannot see a cross-file guard, so "expect 325" was arithmetic, not
  evidence. Only the full-suite host gate is evidence.

  Resolved by TIGHTENING the guard, not relaxing it: the expected set
  was extended to all ten keys, keeping exact equality so an internal
  field still cannot leak into the public payload unnoticed. A subset
  check would have made the guard pass silently for every future field.
  The change is observable in the test, not in the schema; the response
  contract itself is unchanged from what sec 1 describes.
- **Host gate, second run (2026-09-02): `ruff check .` clean,
  `ruff format --check .` clean (62 files), `pytest -q` **325 passed**.**

### Pre-deploy live baseline (2026-09-02, DASH-1 in production, DASH-2 not yet)

Read from `/v1/weather` before this branch ships, so that a post-deploy
reading can separate a DASH-2 effect from real provider drift.

  google/gemini-3.5-flash-lite   json 0.96050   length 131.06035
  mistral/mistral-small-latest   json 0.97856   length  89.42253

Both STABLE, no alerts. Against 2026-08-28 (raw google 0.17675,
mistral 0.18317; normalised 0.98194 and 1.01761 -- the latter above
1.0 before the clamp):

  json rate, in raw units, per-batch DP sd 0.014142:
    google   -0.00386  = -0.27 sd (batch), -0.61 sd (window difference)
    mistral  -0.00703  = -0.50 sd (batch), -1.11 sd (window difference)

  avg_output_length, 320-era per-batch DP sd 4.5255:
    google   -1.16965  = -0.58 sd (window difference)
    mistral  +0.34253  = +0.17 sd (window difference)

No drift signal on either leg across five days.

**The clamp is intermittent, which is the stronger version of the
DASH-1 finding.** On 2026-08-28 mistral's raw rate exceeded the
v2.0.0 ceiling of 9/50 and `_scorable_json_rate` clamped 1.0176 to
1.0000. Today it does not fire (0.97856). A guard that fires
sometimes is load-bearing in exactly the way a guard that never
fires is not.

**Corroboration on the PRIV-011 contamination question -- still not
the measurement.** Five days at two runs per day is ten runs: one
complete turnover of a ten-batch window. If the 2026-08-28 window had
still held 8192-era rows (per-batch sd 115.85, ~36.6 on a ten-batch
mean), a full turnover would have moved the published length by tens
of characters. It moved 1.17 and 0.34 -- 0.58 and 0.17 sd on the
320-era scale alone. The google/mistral spread also survived the
turnover almost unchanged (+48.4% -> +46.6%), which fits a real
verbosity difference between the two models and not a decaying
contamination.

This is strong corroboration and it is still inference. Two things
keep it from being proof: the endpoint publishes no timestamps, so
'ten runs' is assumed rather than observed, and the google leg drops
~31% of its samples, so its window may span more calendar days than
mistral's and may not have fully turned over. DASH-2 resolves both by
publishing `window_start`, `window_end` and `length_sample_count`.
The do-not-cite rule on `avg_output_length` stands until the
post-deploy read.
- Files touched: `gateway/schema.py` (5 fields + docstring),
  `gateway/main.py` (`_as_published_utc`, provenance in
  `_compute_model_weather`), `tests/test_weather_provenance.py` (new).
- Ruff in the container was 0.15.11, not the pinned 0.15.20. The host
  gate is authoritative.

### Adversarial case (a) -- poisoned / Sybil probe

**DASH-2 widens this exposure and does not defend against it. Stated
plainly rather than buried.** Before DASH-2, a forged complete batch
could only move the published average. Now it also raises the apparent
support for that average, so forged VOLUME acquires a value it did not
have. At M=1 there is no per-organisation accounting on this path.

What does hold: the DASH-1 completeness guard means forged PARTIAL
batches raise `sample_count` but can never pad `json_sample_count`
(`test_adv_forged_partial_cannot_pad_the_json_denominator`). The real
mitigation is signature verification plus quorum-gating the published
metrics -- sec 7.1 of the DASH-1 Keystone, still open.
`test_adv_sybil_volume_inflates_the_count_and_is_not_defended` exists
so the exposure is pinned, not so it looks solved.

### Adversarial case (b) -- provider change with no latency/uptime signal

The detector path is untouched; it consumes the raw wire value exactly
as before. A real validity collapse reads the same after DASH-2 as
before it (`test_adv_provenance_does_not_alter_the_published_metrics`),
and the read remains a projection that never mutates a stored row
(`test_adv_stored_rows_are_not_mutated_by_the_read`).

DASH-2 improves this case rather than degrading it: a leg that has gone
quiet -- which is what a provider-side block or a rate-limit collapse
looks like from here -- now shows an old `window_end` instead of
silently averaging stale rows
(`test_stale_window_is_visible_rather_than_hidden`).

### Post-deploy verification (2026-09-02, PR #27, squash @09f1563)

Merged with 5 checks green; Render deployment #93 live. First read of
the new fields:

  google/gemini-3.5-flash-lite
    window 2026-08-24T05:58:25Z -> 2026-09-01T10:11:09Z
    sample_count 10 | json_sample_count 10 | length_sample_count 10
  mistral/mistral-small-latest
    window 2026-08-28T17:27:23Z -> 2026-09-02T09:38:39Z
    sample_count 10 | json_sample_count 10 | length_sample_count 10

**(1) The PRIV-011 contamination question is CLOSED by measurement.**
PRIV-011 merged 2026-08-11. The google window opens 13.25 days after
that date and the mistral window 17.73 days after it. No 8192-era row
can be inside either window. The five-day corroboration in the section
above was correct, but it is now redundant: the bounds are published.
**The do-not-cite rule on `avg_output_length` is lifted.** The metric is
fit to quote in Weather Report #1.

**(2) The google-leg sample loss is worse than the 31% on record: it is
45%.** Ten samples span 8.1755 days, a mean inter-sample interval of
21.80 h against the scheduled 12 h (cron "17 5,17 * * *"). Ratio 1.8168,
so the leg is emitting at 55% of its cadence -- an effective loss of
44.96%. mistral for comparison: interval 12.47 h, ratio 1.0388, loss
3.73%. At the time of the read, google's last sample was 29.6 h old
(the 2026-09-01 17:17 and 2026-09-02 05:17 runs both missing), which is
inside its own ragged cadence rather than evidence of an outage -- but
that state was simply unobservable before this task.

**(3) Why the counts alone could never have found (2).** Both legs
publish `json_sample_count == sample_count == 10`: the DASH-1 filter is
currently discarding nothing. The google losses are therefore not
partial rows -- `execute_canary_strict` discards the whole 50-prompt
suite on any single prompt's retry exhaustion, so a lost run writes no
row at all. A class of loss that removes rows entirely is invisible to
any count, however many counts are published; only the window bounds
expose it. The counts answer "how many rows survived into the metric";
the bounds answer "how long it took to collect them", and it was the
second question that caught the defect. This is the strongest argument
for the field granularity Tatiana chose, and it was not anticipated
when the contract was agreed.

## 6. Provider ToS compliance

Not applicable. No new canary probe design, prompt, or request pattern.
Read-side projection over stored aggregates; no provider is contacted.

## 7. Defect found and NOT fixed (out of scope)

**`last_alert_timestamp` is published naive and renders wrong in the
browser.** The field has always been naive UTC. The dashboard parses it
with JavaScript `new Date(...)`, which treats an offset-less ISO string
as local time -- so alert timestamps display shifted by the viewer's UTC
offset (two hours, for Tatiana in Europe/Berlin).

This is pre-existing and real, not introduced here. It is deliberately
NOT fixed in DASH-2: changing an existing published field is an
observable API change with a dashboard consequence, and it belongs in
its own task with its own gate -- the same discipline applied to
`VALID_PAYLOAD` in DASH-1. Logged to the backlog.

Note the consequence for this report: `/v1/weather` now publishes two
timezone-aware timestamps next to one naive one. That inconsistency is
the honest state of the API until the follow-up task lands.

## 8. Known limitations (stated honestly)

1. **The Sybil exposure above is widened, not mitigated.** See sec 5(a).
2. **No staleness signal.** Tatiana scoped this out deliberately: a
   threshold ("stale after 36h") is a judgement that needs its own
   defence. DASH-2 publishes the raw timestamps and lets the reader
   conclude. Revisit when the board carries more legs.
3. **The window is still last-10-by-id, not time-bounded.** DASH-2
   makes the window's age visible but does not change what it selects.
   `get_recent_signals` orders by insertion id, a proxy for time; the
   bounds are computed with min/max rather than positionally so that
   out-of-order rows cannot invert the window
   (`test_window_bounds_do_not_assume_row_order`).
4. **Counts do not distinguish why a row was excluded.** A row dropped
   for an unknown suite_version and one dropped for being partial both
   simply fail to increment `json_sample_count`. Sufficient for a
   denominator; insufficient for diagnosis.
5. `sample_count` is 0 rather than None for an unseen model. A hard
   zero is a claim ("nothing observed"); None would be an absence of
   claim. Zero was chosen because the window genuinely is empty.
6. **The A6 payload guard now requires deliberate maintenance.** Exact
   set equality was kept on purpose (sec 5), so every future field on
   `ModelWeatherResponse` will fail `test_gateway.py` until that test is
   updated. That friction is the feature: a published payload should not
   be able to grow by accident.
7. **This task was authored outside its own session boundary.** The
   implementation and this report were written on 2026-08-28 at 07:50
   UTC, nine minutes AFTER the Session 047 close commit `b144e87`, and
   left uncommitted on `main` for five days -- so the S047 log records
   DASH-2 as open rather than authored, and the session-start protocol
   would have missed it. Second occurrence of the pattern (precedent:
   PRIV-011 at S045). Recovered at Session 048 by reading the working
   tree before trusting the log. See the process finding in the S048
   session log.

## 9. Sign-off

- [ ] Tatiana: review sec 3 (two counts, not one), sec 4 (timestamps
      gained an offset), sec 5(a) (**the Sybil exposure is widened and
      undefended**), and sec 7 (the naive `last_alert_timestamp` defect
      found but deliberately not fixed), and sec 5 (**the first host
      gate was RED; the A6 guard was tightened, not relaxed**). If
      accepted: sign here. Gate, commit, push, PR #27 and squash-merge
      @09f1563 are DONE (2026-09-02); the post-deploy verification in
      sec 5 is the result.
