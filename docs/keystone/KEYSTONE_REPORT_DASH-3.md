# KEYSTONE REPORT (UNSIGNED) -- REQ-DASH-005
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

    google/gemini-3.5-flash-lite   age  21.65 h   ALIVE   status STABLE
    mistral/mistral-small-latest   age 176.00 h   DEAD    status STABLE

The obvious threshold -- 24 h, one missed slot -- **would have published
a false STALE on a live leg the same day it shipped.** The healthy leg
was simply late. 30 h clears the measured lateness with room and still
flags a two-slot outage on the first read after it.

`test_threshold_leaves_room_above_a_late_scheduled_run` asserts the
constant against both measured ages, so a future tightening to 24 h
fails the gate rather than the dashboard.

This is the second time in three sessions that a cheap measurement
overturned a plausible derived number (the first killed CAN-3). The
snapshot was archived twenty minutes before it was needed, for an
unrelated reason.

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

### Live verification (pending)

Deploy is on Render from `main`. Post-merge verification is a READ of
`/v1/weather` and of `/dashboard` after the deploy, expecting
`mistral/mistral-small-latest` to carry `status: "STALE"` with
`window_age_hours` above 190, and the google leg to stay `STABLE`. This
verification is a public-surface read, not a deploy log. It is NOT
performed by triggering the probe: a `workflow_dispatch` would slide the
window, erase the evidence a reader of Weather Report #1 can check, and
destroy the natural experiment now running on the two legs.

## 6. Provider ToS compliance

No change. DASH-3 touches only the gateway read path and the dashboard;
no new provider calls, no change to canary volume, pacing, or retained
content.

## 7. Defects found and NOT fixed (out of scope)

1. **The mistral leg is still dark and still undiagnosed.** `0/50`
   prompts in 75 s with the key present. DASH-3 makes the outage
   legible; it says nothing about its cause. OBS-1 (structured failure
   telemetry -- status histogram, retry and backoff spend, no provider
   text across the privacy perimeter) remains the next engine task and
   is the only thing that can separate "my fix worked" from "the
   provider stopped 429-ing" -- a live confound, since the google leg
   has self-healed from ~38.7% to ~17% derived loss with zero code
   change.
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

- [ ] Tatiana: reviewed sec 3 (a third state rather than a flag, and
      the cost of widening a public contract), sec 4 (30 h is set by the
      measured 21.65 h live leg -- 24 h would have false-alarmed), sec
      5(a) (**freshness is spoofable by anyone who can emit; OPEN and
      UNDEFENDED**), and sec 7 (five defects found and deliberately not
      fixed, including the still-undiagnosed mistral leg).

**UNSIGNED.** Gate is green (342). Merge does not happen before this
signature.
