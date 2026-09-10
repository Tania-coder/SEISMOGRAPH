# KEYSTONE REPORT (SIGNED 2026-09-10) -- REQ-DASH-005
# DASH-3: a leg that has stopped reporting must not publish STABLE
# Authored and gated Session 050, 2026-09-09.
# Base: main @4f7f078 (baseline 325). Branch: seismograph/task-dash-3.
# Contract: agreed with Tatiana in-session before any edit (three-state
# status, 30 h threshold, precedence, scope boundary, both adversarial
# cases). Filed under docs/keystone/ -- see sec 0.

## 0. Provenance

This is the first Keystone report written to `docs/keystone/` instead of
the repository root. The root currently holds about twenty
`KEYSTONE_REPORT_*.md` files, which is the first thing a stranger sees
when the repository is opened. The reports are not the problem; their
placement is. The move of the existing files is a separate task with its
own commit, and this report starts the convention rather than waiting
for it.

Defect id: **D-11**, recorded 2026-09-07 in the project memory, promoted
to top priority 2026-09-09 for a reason that is commercial as much as
technical -- see sec 2.

## 1. What

`GET /v1/weather` gains a third status value and one field.

- `status` becomes `STABLE | DRIFTING | STALE`. `STALE` means the read
  window is empty, or its newest sample is older than
  `gateway.main.STALE_AFTER_HOURS` (30.0).
- Precedence: **DRIFTING > STALE > STABLE**. A quorum-verified alert is
  a positive finding and outranks the age of the data.
- `window_age_hours: float | None` is published beside the status, so a
  reader gets the number the verdict was made from without re-deriving
  it from `window_end` against their own clock.
- `_window_age_hours(window_end, now=None)` is a pure helper: naive
  timestamps are STAMPED UTC, never interpreted in the host's zone.
- The dashboard renders the third state explicitly and says, in words,
  what a stale card does not know.
- `README.md` stops claiming four live models and 291 tests, and states
  plainly that at one observer a public alert cannot fire at all.

Not touched: the metric values, the DP path, the quorum gate, the
ingestion path, the alert tables.

## 2. Why

Before this change the status line read, in full:

    status = "DRIFTING" if recent_alerts else "STABLE"

The field never looked at the data. It looked only at the alert table.
Two consequences followed, and the second is the serious one.

**First:** a leg whose probe had been dead for a week published
`STABLE` with `sample_count: 10`. Measured on the live board
2026-09-09T17:38:24Z: `mistral/mistral-small-latest` carried
`window_end` 2026-09-02T09:38:39.371095Z -- **176.0 hours old** -- and
read `STABLE`. A model tuple that had never emitted a single batch also
read `STABLE`, with `sample_count: 0`.

**Second:** at a single observer, `required_quorum(1) == 3`, so a public
drift alert is unreachable by construction. `recent_alerts` is therefore
permanently empty, and the expression above can evaluate to exactly one
thing. **The green light was produced by the system's own inability to
raise an alarm** -- on the public dashboard of a project whose entire
claim is that it catches failures other monitoring cannot see. This is
not a rendering defect. It is the instrument asserting a conclusion in
the one situation where it holds no evidence at all.

Weather Report #1 (published 2026-09-04) drives readers to that board.
That is what moved D-11 from a technical defect to the highest-value
item in the project: the cost of being discovered is not a bug report,
it is the credibility the report was written to earn.

## 3. Why a third state and not a flag beside STABLE

The considered alternative was to keep `status` two-valued and add
`stale: true` or lean on the DASH-2 window bounds, which already made
staleness *visible*.

Rejected, for a reason DASH-2 itself demonstrated: the window bounds
were shipped on 2026-09-02 and the leg went dark on 2026-09-02, and the
staleness still went unnoticed until a deliberate read on 2026-09-07.
Visible is not legible. A reader takes `status` as the whole verdict,
and the coloured light is driven by that field alone, so any hedge
placed next to it is not read.

`STABLE` is an assertion about the model. When the leg is dark there is
no evidence in either direction, and absence of evidence is not evidence
of stability. The honest value is a third one.

Cost, stated plainly: `/v1/weather` is a public contract and this
widens it. It is cheap today because the only consumer is our own
dashboard; it will not be cheap after the first external consumer, which
is an argument for doing it now rather than a reason to defer.

## 4. Why 30 hours, and why the evidence file set it

The probe is scheduled `17 5,17 * * *` (every 12 h) but Actions fires it
2.5-4.5 h late, so 12 h arithmetic on gaps is unsound (measured at
S049).

The threshold was **not** chosen from that reasoning. It was chosen from
the archived snapshot committed at 4f7f078
(`docs/evidence/weather-2026-09-09T173824Z.json`, SHA-256
`24FA6DF7951411CFDE71668AE325CB21A30C774259E3374F90352C31A576F414`):

    google/gemini-3.5-flash-lite   age  21.65 h   status STABLE
    mistral/mistral-small-latest   age 176.00 h   status STABLE

**Correction, made before signature (2026-09-10).** The first draft of
this section argued that 24 h "would have published a false STALE on a
live leg". Re-measured the next day, that leg stood at **34.56 h with no
new row**: at 21.65 h it had already missed a slot and never emitted
again. A 24 h threshold would have alarmed correctly -- by luck, not by
evidence, since nothing in the window distinguished the two cases at the
time. The claim was wrong; the threshold is not, and it is left at 30 h
deliberately.

The defensible argument is about tolerance, not health. At 21.65 h
"merely late" and "already stopped" are indistinguishable from the
window alone. The threshold must sit above the late case, or an Actions
run that fires 4.5 h behind its slot raises a false alarm on a working
system. The price is explicit: up to ~18 h of delay before a real
outage is flagged. Buying a faster alarm means measuring the real
cadence distribution first, which is a separate task and needs the
telemetry OBS-1 will produce.

`test_threshold_leaves_room_above_a_late_scheduled_run` asserts the
constant against both measured ages, so a future tightening fails the
gate rather than the dashboard. Its docstring states in words that the
21.65 h leg was NOT healthy, so the pin cannot be misread later as a
claim about that leg.

This is the third time in four sessions that a cheap measurement
overturned a plausible number (the first killed CAN-3; the second was
this one, overturned by a read taken for an unrelated reason twenty
minutes earlier). The pattern is now strong enough to state as a rule:
in this project a derived number survives only until someone measures
it, so it is cheaper to measure first.

## 5. Evidence

### Gate (host, 2026-09-09)

    ruff check .              All checks passed!
    ruff format --check .     63 files already formatted
    py -3.10 -m pytest -q     342 passed, 1 warning

Baseline 325 -> **342**. Reconciliation: 325 + 17 new tests in
`tests/test_weather_staleness.py` = 342, exactly. No test was deleted,
skipped or renamed to reach the number.

### The first gate run was RED, and the failure was designed

`test_gateway_same_suite_three_orgs_reach_quorum` holds an EXACT set
equality over the published payload keys, with a comment stating that a
schema change must update it on purpose. `window_age_hours` made it
fail. The guard was updated deliberately, with the date and reason
recorded beside it; it was not relaxed to a subset check.

This is the **second consecutive Keystone** in which that guard caught a
real change (DASH-2 sec 5 records the first). A control that has now
fired twice on genuine schema growth is earning its cost, and the
precedent is worth stating: exact equalities over published payloads
stay exact.

### The frontend landmine, found before shipping rather than after

`dashboard/static/app.js` computed `const drifting = entry.status ===
"DRIFTING"` and painted everything else with `card-stable`. A
backend-only fix would therefore have rendered a **green card carrying
the word STALE** -- the same defect one layer up, and the same failure
class as S049's stale article body: "the change shipped" and "the right
thing is on the public surface" are different claims. The card is now
coloured from an explicit state map, and an unknown future status falls
back to `stale`, never to `stable`.

### Adversarial case (a) -- poisoned / Sybil probe

DASH-3 measures the **presence** of data, not its validity. A probe that
emits garbage on cadence keeps its leg fresh and therefore green; an
attacker who can emit at all can suppress `STALE` indefinitely. Freshness
is spoofable by anyone holding the emission path.

This exposure is **OPEN and UNDEFENDED**, and it is the same shape as the
DASH-2 exposure accepted at S049: inert only while the network has
exactly one member and that member is the operator. It is recorded here
rather than defended because defending it requires per-observer
accounting on the public path, which is the same prerequisite already on
record for a second observer.

### Adversarial case (b) -- provider change with no latency/uptime signal

DASH-3 does not detect such a change and does not claim to. What it
changes is the failure mode when the detector that *would* catch it has
stopped running: the board previously answered "STABLE", i.e. "I looked
and it is fine". It now answers "STALE", i.e. "I am not looking". For an
early-warning system, publishing a confident negative while blind is a
strictly worse failure than publishing an honest gap, and the mistral leg
had been in exactly that state for seven days.

### The outage this fix makes visible (measured 2026-09-10)

Read from GitHub Actions through the Chrome page context, since
`api.github.com` answers 403 to this session's own fetch tool. An
earlier WebFetch summary of the same page was a hallucination ("14 runs,
all successful, 20-45 s each"); the real page carries 137 runs with
durations in minutes. Summaries of JS-rendered pages are not evidence.

    #135  Sep 8 19:54 UTC   4m53s   last google row (window_end 19:59:15Z)
    #136  Sep 9 09:45 UTC   6m29s   both legs exit 1 -- first google loss
    #137  Sep 9 19:45 UTC  15m14s   mistral exit 1; google CANCELLED at
                                    the 15m0s job ceiling

The workflow fires reliably twice a day. This is not a scheduler fault.

`emit (mistral)` #137, emission step 1m12s: `0/50 prompts completed`,
all fifty ids listed. Confirmed **by direct measurement from a second
network and IP** the same day: `GET /v1/models` -> **200**, a single
`POST /v1/chat/completions` -> **429 "Rate limit exceeded", code 1300**.
The credential is valid; the ACCOUNT is rate-limited. No retry or
backoff engineering fixes that.

`emit (google)` #137 was killed by the job ceiling, so `live_emit.py`
never reached its own error print: **a cancelled job publishes no
discard line and no failed ids at all.** The leg that failed hardest is
the one that reported nothing. This adds a requirement to OBS-1 that was
not in its contract: telemetry must be written progressively, not as a
summary at the end, and the probe should bound its own wall clock so it
fails before the job ceiling rather than being cancelled at it.

Two conclusions from S049 are amended by this: H4 ("job timeout --
REFUTED, 0 cancelled") was true on 2026-09-04 and is false now; and
CAN-3's diagnosis was wrong **for the failure of 2026-09-04**, which is
all the measurement showed -- at 0/50 in 72 s the run-wide backoff cap
is binding again. The failure mode moved; neither verdict was permanent.

### Live verification (DONE, 2026-09-10)

Read from the deployed `/v1/weather` through a SECOND client (a browser
page context), deliberately not through the session's own fetch tool,
which caches for fifteen minutes and had been serving the pre-deploy
payload. "On main" and "visible on the public surface" are different
claims and were verified separately.

    google/gemini-3.5-flash-lite   STABLE  window_age_hours   5.72
    mistral/mistral-small-latest   STALE   window_age_hours 197.90

Both branches are therefore verified in production, not just in tests:
the dead leg publishes STALE, and a leg with a fresh window is NOT
false-alarmed. `window_age_hours` is present on the public contract.
No `workflow_dispatch` was used; the probe ran on its own schedule.

**The same read refuted a claim made in this session.** The Executor had
argued from five hand-timed calls (0.58 s to 53.9 s) that at ~20% of
calls exceeding the probe's 30 s timeout the google leg "statistically
cannot complete" a 50-prompt suite -- 0.8^50, about 1 in 70 000. Google
completed a full suite that same morning: `window_end`
2026-09-10T09:49:06Z, a fresh row on the board. Five points do not carry
a rate, a 0.58 s response and a 53.9 s response are not obviously the
same population, and the conclusion was published before the interval
was. It is recorded here rather than deleted, because the failure mode
it illustrates -- an unmeasured number stated as a verdict -- is the
same one that killed CAN-3 and the same one this project exists to warn
other people about. The measurement that would settle it (30 calls with
status, latency, finish_reason and token counts) is queued and is a
prerequisite for touching `n`, the atomicity rule, or CAN-3'.

## 6. Provider ToS compliance

No change. DASH-3 touches only the gateway read path and the dashboard;
no new provider calls, no change to canary volume, pacing, or retained
content.

## 7. Defects found and NOT fixed (out of scope)

1. **Both legs are dark, and only mistral's cause is known.** mistral is
   a measured account-level 429 (sec 5) -- a quota condition, not a code
   defect, and not fixable in this repository. google is undiagnosed and
   currently unobservable, because its job is cancelled before it can
   print. OBS-1 (structured failure telemetry -- status histogram, retry
   and backoff spend, written progressively, with no provider text
   across the privacy perimeter) is what makes google diagnosable, and
   it is also the only thing that can later separate "my fix worked"
   from "the provider stopped 429-ing".
2. **`observer_count: 1` deferred to DASH-4.** It needs a distinct
   observer count at the repository layer -- a different query and a
   different test surface. Weather Report #1 already states the single
   observer in prose, so the disclosure exists.
3. **Naive `last_alert_timestamp`** (DASH-2 sec 7) unchanged: still
   published naive beside three timezone-aware fields.
4. **`requires-python >= 3.11` against a gate on 3.10.11.** The README
   was made self-consistent at 3.11+ in this commit, which is a
   documentation fix, not the real one. The real fix is moving the gate
   to 3.11 or lowering the declaration, and it is still open.
5. **DASH-2 Sybil exposure** unchanged and still accepted as open.

## 8. Known limitations (stated honestly)

- 30 h is a threshold, not a model. A leg failing every other slot stays
  under it and reads STABLE with half its samples missing. Cadence
  monitoring is a different task and is not claimed here.
- `STALE` is computed from the newest sample only. A window holding one
  fresh sample and nine ancient ones reads STABLE; `sample_count` and
  the window bounds are what expose that, as of DASH-2.
- The status still cannot become DRIFTING at one observer. DASH-3
  removes a false green; it does not create the ability to alert. That
  ability is the private fleet path (`fleet_id != None`), and the
  README now says so in plain words rather than implying otherwise.

## 9. Sign-off

- [x] Tatiana: reviewed sec 3 (a third state rather than a flag, and the
      cost of widening a public contract), sec 4 (30 h encodes TOLERANCE
      for a late scheduled run, not a claim that the 21.65 h leg was
      healthy -- it was not), sec 5(a) (**freshness is spoofable by
      anyone who can emit; OPEN and UNDEFENDED**), and sec 7 (defects
      found and deliberately not fixed, including the still-undiagnosed
      google leg and the account-level 429 on mistral).

**SIGNED -- Tatiana Radchenko, 2026-09-10.**

**The merge preceded this signature.** DASH-3 was merged and pushed to
`main` before sec 9 was signed. Recorded, not backdated. This is the
SECOND consecutive occurrence: the DASH-2 Keystone records the same
inversion (deployed 2026-09-02, signed 2026-09-04) and states that a
third occurrence should remove the step from protocol 01 rather than
ask for more diligence, because a control that reliably happens after
the event it is meant to gate is a ritual.

Rather than spend the third occurrence, the control was given a
mechanism in this same session: `tests/test_keystone_signed.py` fails
the standard gate (`py -3.10 -m pytest -q`) if any report under
`docs/keystone/` still carries the unsigned marker in upper case, or
lacks a signature line. Signing is no longer
a promise; from now on an unsigned Keystone cannot pass the gate that
every merge already runs, and no separate CI wiring is needed. If that
test is ever deleted or skipped rather than satisfied, the honest move
is to strike the signing step from protocol 01, not to restore the
promise.

Accepted with sec 5(a) explicitly OPEN and UNDEFENDED: DASH-3 measures
the PRESENCE of data, not its validity, so anyone able to emit can hold
a leg green with noise. Inert only while the network has exactly one
member and that member is the operator -- the same standing condition
recorded for the DASH-2 exposure, and the same reason a second observer
requires quorum-gated published metrics first.
