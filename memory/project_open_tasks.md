# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-09-04 (Session 049: FIRST PUBLIC ARTEFACT IN 42 DAYS.
# Weather Report #1 published to dev.to + LinkedIn, archival copy committed
# to docs/reports/ BEFORE publication. Keystone DASH-2 sec 9 SIGNED with
# both dates recorded honestly. CAN-3's diagnosis REFUTED by measurement
# (49/50 and 40/50 prompts completed, never ~4). The collection defect
# MOVED from the google leg to the mistral leg, which is now dark. A = 16
# scheduled runs measured, so the scheduler and timeout hypotheses are
# dead. Protocol 01 gained a signature gate. No engine code changed.)
# Prior: 2026-09-02 (Session 048: DASH-2 recovered from a 5-day
# uncommitted tail of S047, gated to 325, merged PR #27 @09f1563;
# post-deploy measurement CLOSED the avg_output_length contamination
# question and RAISED the google-leg loss estimate 31% -> 45%; landing
# page 193 -> 325; Guide project + three-role protocol established.)
# Prior: 2026-08-28 (Session 047: DASH-1 landed -> 309 tests, Keystone
# signed; Neon persistence 24 days; DASH-2 authored but left uncommitted.)
# Prior: 2026-08-11 (Session 046: S045 recovered; PRIV-011 merged -> 293
# tests + Keystone signed; INFRA-3 cron revert merged.)
# Prior: 2026-08-04 (Session 044: INFRA-1 merged, 291 tests, Neon
# persistence proven). Prior: 2026-07-24 (Session 040, GTM sprint).

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## S049 — 2026-09-04 (publish first, then measure; CAN-3 refuted)

### Verification
- [x] `device_bash` failed on the first action — "Workspace unavailable",
      **third consecutive session**. The deferred trigger for investigating
      the bridge has fired. Session ran in the fallback mode throughout.
- [x] Machine verified: `af8dde9` on main; `git status` clean; **`git show
      --stat af8dde9` = exactly 4 files, +482/-96** as predicted, closing
      the Guide's new G-12 content check green on first use. Host gate:
      ruff x2 clean (62 files), **pytest 325 passed** in 4.31 s.
- [x] **FINDING: gate runs on `Python 3.10.11`, but `pyproject.toml:8` and
      `pyproject_probe.toml:49` both declare `requires-python = ">=3.11"`.**
      The 325 baseline is proven only on a version the package disclaims;
      the declared version has never been gated. New task, not this session.
- [x] **Method finding: the Director's terminal is not needed for Actions
      data.** The GitHub REST API read from the page context of her own
      Chrome returns exactly what `gh run list` returns, including per-job
      conclusions and step timings. This replaces the paste-the-output loop
      the Guide's memo assumed.

### Measurement — this is what changed the plan
- [x] Fresh `/v1/weather` read 2026-09-04. **The Guide's G-10 fork resolved
      in neither direction, because it was watching the wrong leg.**
      google did not hold at 8 days and did not collapse to 5-6: it
      **partially recovered** to 176.2 h (7.34 d), mean interval 19.58 h,
      effective loss 44.96% -> 38.71%. Meanwhile **mistral froze**:
      window bounds and both metrics byte-identical to the 2026-09-02 read,
      no row since 2026-09-02T09:38:39Z, 56 h and four scheduled slots.
      Both legs published 10/10/10 throughout. [measured]
- [x] **Scheduler reconciliation, window 2026-08-24T05:58Z ->
      2026-09-01T10:11Z: A = 16 runs fired, B = 9 success / 7 failure /
      0 cancelled at run level, C = 10 google rows, 6 runs produced no
      row.** The Guide's falsifiable prediction (A = 17 +/- 1, C = 10,
      6-8 losses) HOLDS. [measured]
- [x] **H3 (scheduler gap) and H4 (job timeout) REFUTED** — the runs fired,
      nothing was cancelled, the longest ran 11 m 52 s against a 15 m limit.
- [x] **H1 (total backoff budget) REFUTED, and with it CAN-3 as specified.**
      Run #122 google: `49/50 prompts completed`, one failed id
      (`v2.0.0-reason-01`). Run #118 google: `40/50`, ten failed ids
      interspersed mid-suite with later prompts succeeding after them.
      Never ~4/50. The probe prints its own policy: `pacing: 4500 ms
      between prompts, <= 2 retries on 429/503`. The binding constraint is
      per-prompt retry exhaustion plus `execute_canary_strict`'s
      all-or-nothing discard — **one prompt in fifty destroys the sample.**
      Raising `SEISMOGRAPH_PROBE_MAX_TOTAL_BACKOFF_MS` to 180000 would not
      have saved run #122. **G-02 (do not write CAN-3 before the
      discriminating measurement) paid for itself in full.**
- [x] Per-job conclusions: #121, #122 google failed / mistral succeeded;
      #123, #124, #125, #126 **mistral failed / google succeeded**.
      Run #126 mistral: `0/50 prompts completed`, all fifty ids, dead in
      75 s, "Note missing secret" step SKIPPED so the key is present.
      A different failure class from google's transient 429 bursts.
- [x] Run-level status is a poor proxy for per-leg collection: a run is
      marked failed if ANY leg fails, and a failed run can still carry a
      successful leg — hence 10 rows from 9 run-level successes.
- [x] Scheduled runs fire **2.5-4.5 h after** their cron slot. Any
      arithmetic treating gaps as exact multiples of 12 h is unsound.

### Landed
- [x] **KEYSTONE_REPORT_DASH-2.md sec 9 SIGNED** (@9a8aaa0). Sybil
      exposure accepted OPEN and UNDEFENDED, with the recorded consequence
      that quorum-gating the published metrics is a **prerequisite for a
      second observer, not a follow-up to one**. Deploy 2026-09-02,
      signature 2026-09-04; both dates in the report, not backdated.
- [x] **Protocol 01 amended: SIGNATURE GATE.** Signature precedes merge;
      an unsigned deploy is a STOP CONDITION at step 0 of the next session,
      not a backlog item; both dates always recorded. Removing the step
      stays a legitimate Director decision, but only as an explicit entry
      in 03, never by attrition. (Considered and rejected: removing the
      step — it had just done real work by forcing the Sybil acceptance.)
- [x] **WEATHER REPORT #1 WRITTEN AND PUBLISHED.** Ends six consecutive
      sessions (S044-S049) and 42 days with no public output.
      dev.to: /taniacoder/i-gave-my-drift-monitor-a-denominator-...-5508
      LinkedIn: /feed/update/urn:li:activity:7501709720328753152/
      Archival copy `docs/reports/2026-09-04-weather-report-01.md`
      committed @e8b0e5b **before** publication, so the repository holds
      the earliest timestamp; both URLs recorded @87d5527.
      Written in first person singular after the Director caught an
      unearned editorial "we" — the project has one author and one
      observer, and the text now says so (@e47d182).
- [x] Voice/accuracy pass: added the explanation of 10 rows against 9
      run-level successes before a reader could read it as an
      inconsistency (@2a963c9).

### New hard rule
- [x] **VERIFY THE PUBLIC SURFACE, NOT THE PUBLISH ACTION.** The first
      published version of Weather Report #1 carried a STALE BODY: the
      correct file was on disk, an older copy was in the paste buffer.
      Title was current, body was two revisions behind, and the added
      paragraph was missing. Detected only by reading the live page back
      and diffing it against the archival copy; fixed within minutes, zero
      comments, same URL. Contributing cause, owned by the Executor: three
      different revisions were delivered under one filename.
      **Change the filename on every revision.**

### Open after this session
- [ ] **mistral leg dark** — highest value. `0/50` in 75 s with the key
      present. DO NOT re-run the workflow casually: a successful run slides
      the window and erases the evidence a reader of Weather Report #1 can
      currently verify on the live endpoint.
- [ ] **Observability blocker** — the run log names only failed prompt ids.
      No HTTP status, no body, no retry spend. Ship this BEFORE any
      collection fix or the next failure is equally blind.
- [ ] **CAN-3' replacement contract** — per-prompt retries and/or a
      documented reduced-n path recomputing DP sensitivity for the actual
      n. The old CAN-3 numbers (180000 ms, 1200 s timeout) are void.
- [ ] `requires-python >= 3.11` vs a gate on 3.10.11.
- [ ] `observer_count: 1`; naive `last_alert_timestamp`; PRIV-012;
      quorum-gating of published metrics; Dependabot #15-#18;
      VALID_PAYLOAD; probe 1.2.0/1.3.0; third/fourth legs.
- [ ] `business/` and `social/` exist only on Tatiana's disk — private is
      not backed up. A private GitHub repo would close it.
- [ ] Carried Tatiana clicks: SSH signing key for verified commits; Zenodo
      release to archive `docs/reports/`; formsubmit; OpenSSF anketa;
      NLnet recheck ~25.09; optional Neon password reset.

## S048 — 2026-09-02 (recover DASH-2 tail; land it; open the Guide loop)
- [x] Resume verified: `main` had a modified `KEYSTONE_REPORT_DASH-2.md`
      and two untracked files (`tests/test_weather_provenance.py`,
      the same Keystone) NOT recorded anywhere in the S047 log. Read
      timestamps directly: the S047 close commit `b144e87` landed at
      2026-08-28 07:41 UTC; DASH-2's implementation files were written
      at 07:50 UTC -- nine minutes later, same day, never committed.
      Third occurrence of this exact pattern (precedent: PRIV-011 at
      S045; DASH-2 itself, discovered at S047 open). The working tree
      was trusted over the log, per the S046 hard rule; that call was
      correct.
- [x] DASH-2 audited against its own Keystone claim before touching
      anything: implementation matched sec 1-4 exactly. The ONE
      discrepancy was sec 5's gate claim -- "expect 309+16=325" was
      arithmetic never confirmed by a full-suite run. First real host
      gate: **324 passed, 1 failed** (`test_gateway_same_suite_
      three_orgs_reach_quorum`, an exact-set-equality A6 guard from
      DASH-1 that the authoring run, scoped to 32 weather-path tests,
      never executed).
- [x] Fixed by TIGHTENING the A6 guard to all ten keys (exact equality
      kept), not by relaxing it to a subset check -- a subset check
      would pass silently for every future field. Keystone sec 5/8/9
      corrected to record the red-then-green gate honestly rather than
      quietly overwriting the original claim.
- [x] Host gate green: ruff x2 clean (62 files), **pytest 325 passed**.
- [x] Branch `seismograph/task-dash-2`, PR #27, squash-merged @09f1563,
      5 checks green (Director approved title/body/merge in Chrome,
      driven by Claude). main baseline 309 -> **325**.
- [x] Post-deploy live read, Render #93: both legs now publish
      `sample_count` / `json_sample_count` / `length_sample_count` /
      `window_start` / `window_end`.
      **avg_output_length contamination question CLOSED by measurement**
      -- google window opens 13.25 days after the PRIV-011 cutover,
      mistral 17.73 days after; no 8192-era row can be inside either
      window. The do-not-cite rule is LIFTED.
      **google-leg loss re-measured at 45%, not 31%** -- 10 samples
      span 8.18 days (mean interval 21.8h vs a 12h schedule) while
      BOTH per-metric counts read a clean 10/10, because a discarded
      50-prompt run (`execute_canary_strict` all-or-nothing) writes NO
      row at all. A loss that removes rows entirely is invisible to any
      count; only the window bounds exposed it.
- [x] Landing page (`drift-defense` repo, `759b870`): stale "193 tests"
      corrected to 325 in all three occurrences (stat card, trust
      strip, security-posture line). Found while auditing the launch
      surface for the same class of stale-claim defect DASH-2 had just
      fixed in the engine.
- [x] **Guide project established.** Ten-document pack authored and
      committed to `business/guide_pack/` (gitignored, private): charter,
      roles/protocol, state-of-record, open-decisions register, launch
      status, evidence standard, session-loop formats, paste-ready Guide
      instructions, and a four-part amendment patch for this project's
      own constitution. Purpose: split strategy (Guide, no machine
      access, holds the decision register) from execution (this
      project, holds the machine) so a session cannot drift on strategy
      mid-task the way distribution has drifted for 40 days against a
      compounding engine baseline.
- [x] Guide's first decision memo received and RE-VERIFIED independently
      (never trust a handoff over a check -- 05_EVIDENCE_STANDARD, and
      this is the loop's first real test). Verification result: the
      memo's central claims check out on independent recomputation
      (window-excess arithmetic: google +88.21h / mistral +4.19h against
      a 108h nominal, decomposing to ~7 additional missed 12h slots on
      google -- confirmed to the tenth of an hour). ONE unflagged input
      change caught: the memo's G-03 margin figure ("30s margin at
      300000ms") silently doubled the provider-latency assumption from
      this session's own ~100s draft to ~200s without saying so; at the
      original 100s assumption the margin is ~130s, not 30s. Does not
      change the recommendation (180000ms + 1200s timeout still holds,
      robustly, under either assumption) but the STATED number was
      unsupported -- ironic given the memo's own thesis, and now on
      record as the loop's first caught instance of the failure mode it
      exists to catch.
      The memo's genuine contribution, independently confirmed sound:
      **surviving google samples are a biased sample, not just a sparse
      one** -- discard correlates with 429, 429 correlates with provider
      load, and provider load under stress is the exact mechanism this
      project exists to detect. The -0.27sd google drift reading is
      therefore computed over a sample that systematically excludes
      high-load periods. This goes in Weather Report #1's limitations
      section verbatim, not softened.
- [ ] **CAN-3 contract drafted, NOT implemented.** `max_total_backoff_ms`
      is not threaded through `scripts/live_emit.py` per matrix leg
      (only `delay_ms` and `max_retries` are); it sits at the 60000ms
      default for every leg, which caps a run at 4 fully-retried prompts
      before PartialSuiteError discards all 50. Director-confirmed
      numbers pending a discriminating measurement first (see below) --
      this session declined to write the fix on a diagnosis that was
      [derived] from reading the code, not [measured] from run logs, per
      its own evidence standard.
- [ ] **Discriminating measurement, NOT run this session** (device_bash
      unavailable all session -- "Workspace unavailable" -- gh CLI
      commands handed to Tatiana instead; see S048 log for the exact
      commands). Falsifiable prediction on record: ~17 scheduled runs in
      the google window, ~10 producing a row, 6-8 producing none --
      distinguishing PartialSuiteError/429 (fixable by CAN-3) from a
      scheduler gap or job timeout (CAN-3 would not help, or would make
      it worse).
- [ ] Weather Report #1 -- still NOT published. Every technical blocker
      is now cleared (denominator, window, contamination question); the
      google-leg finding is itself the strongest available lead. Fifth
      consecutive session (S044-S048) with zero public output while the
      test baseline moved 291 -> 325. The Guide's memo independently
      flagged this in the same words used at S047 open.
- [ ] LinkedIn draft for the above written and held pending Director
      approval + channel decision (LinkedIn vs dev.to vs both).
- [ ] `observer_count: 1` field on `/v1/weather` -- new from the Guide's
      memo (G-04): presentational, not architectural (the quorum
      invariant gates the DRIFTING *label*, not the raw numbers beside
      it), but should land before Weather Report #1 cites the numbers it
      would annotate.
- [ ] Carried unchanged: naive `last_alert_timestamp` (found+not-fixed at
      DASH-2); PRIV-012; Dependabot #15-18; third/fourth model legs;
      probe 1.2.0/1.3.0 release.

## S047 — 2026-08-28 (17-day gap; DASH-1 landed, DASH-2 opened)
- [x] Resume verified: branch seismograph/task-dash-1 @04d6034 was pushed
      AND intact — the S046 low-battery stop happened after the push, not
      during it. main unmoved at c771a73, so no rebase needed.
- [x] Host gate re-run on branch: ruff check clean, ruff format clean
      (61 files), pytest **309 passed**. Matches the S046 sandbox claim
      exactly, 17 days later.
- [x] Live board re-verified after the gap: 2 models STABLE, no alerts,
      Neon persistence intact across **24 days** of free-tier autosuspend.
      INFRA-1 now proven three separate ways.
- [x] **The [0,1] clamp was observed FIRING on live data.** mistral raw
      json rate 0.18317 exceeds the v2.0.0 ceiling of 9/50 = 0.18 by
      0.22 sigma of DP noise. Without the clamp the board would have
      published 101.8% validity. Recorded in Keystone sec 4.
- [x] **DASH-1 MERGED** (PR #26, squash @fd4c561, 5 checks green).
      main baseline 293 -> **309**. PR opened and merged by Claude driving
      Tatiana's Chrome directly, with her approval.
- [x] KEYSTONE_REPORT_DASH-1.md sec 9 SIGNED by Tatiana 2026-08-28, after
      review of sec 3 (read-side rationale), sec 5 (both defects), sec 7
      (un-gated metric, duplicated suite table, missing denominator).
- [ ] **DASH-2 — published rate has no denominator. BLOCKS Weather
      Report #1.** /v1/weather exposes neither sample_count nor window
      age. Publishing a percentage without its base is the defect class
      DASH-1 just fixed, one level up. Add sample_count +
      window_start/window_end to ModelWeatherResponse. Read-side only.
      NEXT ENGINE TASK — contract-first.
- [ ] **avg_output_length contamination NOT confirmed cleared.**
      Arithmetic says it aged out (~34 runs vs a 10-batch window) but
      /v1/weather has no timestamps, so that is inference, not
      measurement. The 132.23 vs 89.08 spread fits BOTH a real verbosity
      difference and residual 8192-era rows. DASH-2 settles it. Do NOT
      cite the metric until then.
- [ ] **Dependabot PRs #15-#18 open and stale** — actions/checkout 4->7,
      setup-python 5->7, upload-artifact 4->7, download-artifact 4->8.
      Major-version jumps, may break CI. Also counts against the OpenSSF
      questionnaire already on the carried list.
- [ ] Carried unchanged from S046: google-leg sample loss; PRIV-012;
      published metrics not quorum-gated; VALID_PAYLOAD impossible;
      Weather Report #1; landing 193 -> 309; probe 1.2.0/1.3.0; formsubmit;
      OPENAI + ANTHROPIC keys; OpenSSF anketa; NLnet recheck ~25.09;
      optional Neon password reset.


## S046 — 2026-08-11 (recover S045; PRIV-011 + INFRA-3 landed)
- [x] Live board verified: Neon persistence intact 7 days, 2 models STABLE.
      Independently re-confirmed by Tatiana from PowerShell.
- [x] Sample audit #45-#79: mistral 35/35, google 24/35; all 11 failures
      are google-leg (24 of 25 across all history).
- [x] **S045 RECOVERED.** PRIV-011 had been authored 2026-08-06 and left
      uncommitted on local main for 5 days — unlogged, unbranched.
      Branched (c463905), host-gated (ruff x2 + 293), PR #24 merged
      @261b63d. main baseline 291 -> **293**.
- [x] KEYSTONE_REPORT_PRIV-011.md sec 8 SIGNED by Tatiana 2026-08-11.
- [x] INFRA-3 (PR #25): cron 5x/day -> "17 5,17 * * *"; stale COST header
      (3 prompts / ~24 per day) -> 50 prompts / ~200 per day. Deadline
      2026-08-12 met a day early.
- [x] CURRENT_STATE.md rewritten; S045 + S046 log entries reconstructed.
- [ ] **json_success_rate denominator dilution — BLOCKS Weather Report #1.**
      json_valid scored only for the 9 structured_output canaries but
      averaged over all 50 => ceiling 9/50 = 0.18, not 1.0. Board's
      0.175/0.178 = ~100% validity on scorable prompts, but reads as
      "17% JSON success". Display-layer fix; detection unaffected.
- [ ] **google-leg sample loss.** execute_canary_strict discards the whole
      50-prompt suite on any single prompt's retry exhaustion (correct DP
      reasoning re sensitivity MAX/n). 31% loss; ~1.4 samples/day after
      the cron revert. Options: retry budget/pacing, or a documented
      reduced-n path recomputing DP sensitivity for the actual n.
- [ ] **avg_output_length stream contaminated by the PRIV-011 cutover.**
      DP constant is not in the CUSUM stream key; 8192-era and 320-era
      rows share one stream. Board value is a blend until 10 post-merge
      samples exist. Contained publicly (M=1, quorum 3). Do NOT cite.
- [ ] PRIV-012: avg_output_tokens same defect class (MAX_TOKEN_COUNT 8192
      vs max_tokens 64, ~128x). avg_reasoning_tokens NOT affected.
      Needs its own contract.
- [ ] Weather Report #1 — unblocked once the JSON fix lands. mistral has
      35 clean samples; state google's 24/35 honestly; omit
      avg_output_length entirely.
- [ ] Landing (drift-defense repo): 193 -> 293 + baseline-restart line.
- [ ] probe 1.2.0/1.3.0 release (suite v2 + strict runner + CAN-1).
- [ ] Carried: formsubmit activation; OPENAI + ANTHROPIC keys -> 4 models;
      OpenSSF anketa; NLnet recheck ~25.09; optional Neon password reset.


## S044 — 2026-08-04 (INFRA-1: Neon Postgres persistence + close-out)
- [x] Verified state via fresh clone: S041-S043 landed but UNLOGGED;
      baseline 286; main not ruff-format-clean; /v1/weather EMPTY again.
- [x] INFRA-1 MERGED (PR #23, e128235): dialect-aware DatabaseSession +
      Neon free Postgres via SEISMOGRAPH_DB_URL; 286 -> **291**.
      PERSISTENCE PROVEN (board survived manual Render restart).
      v2.0.0 baseline restart date = 2026-08-04.
- [x] Cron warm-up revert extended to 2026-08-12 (34af93e).
  - [ ] TATIANA ~10-12.08: revert cron to "17 5,17 * * *" once ~30
        samples collected on Neon.
- [x] Keystones INFRA-1 + CAN-2a SIGNED (this close commit).
- [x] Session log: S041-S043 reconstructed entries + S044 entry appended;
      CURRENT_STATE + backlog refreshed; README 193 -> 291.
- [x] GitHub 2FA fixed (Authenticator re-scanned; recovery codes refreshed).
- [ ] Landing (drift-defense repo): "193" -> "291" + baseline-restart
      2026-08-04 line (PowerShell replace, separate repo).
- [x] Dependabot PR #22 RESOLVED without merge (post-close): bot closed
      it as up-to-date after @dependabot rebase (floating @v4).
- [ ] PRIV-011 clamp fix — NEXT ENGINE TASK (contract-first; see
      auto-memory project_dp_clamp_defect.md).
- [ ] probe 1.2.0/1.3.0 release (suite v2 + strict runner + CAN-1).
- [ ] Optional hygiene: Neon DB password reset (was pasted in-session).


## S040 — 2026-07-24 (GTM sprint: CAN-1 + distribution + packaging)
- [x] State verified via fresh GitHub clone (auto-memory lagged one session).
- [x] CAN-1 MERGED (PR #19, c439105): tool-calling canaries +
      output/reasoning token metrics; **main baseline 193** (host + fresh
      sandbox clone both gated). KEYSTONE_REPORT_CAN-1.md at root.
  - [ ] TATIANA: sign Keystone CAN-1 §6 after review.
  - [ ] probe 1.2.0 release (CAN-1 features) + tool-calling-drift post.
- [x] probe_weather multi-provider cron LIVE (2x daily): board shows
      google/gemini-3.5-flash-lite + mistral/mistral-small-latest STABLE.
      Secrets: MISTRAL/GEMINI/SEISMOGRAPH_ID_B64. Gemini lesson: 2.5-flash
      closed to new users; 3.5-flash 503 free tier; -> 3.5-flash-lite.
  - [ ] OPENAI_API_KEY + ANTHROPIC_API_KEY (paid ~$5 each) -> 4 models.
- [x] Landing v3 LIVE (75e5999): 193, backtest-first card, trust row + DOI,
      security §, alert-signup form, early-observer line, guide page at
      /guides/detect-silent-llm-change/ (canonical for dev.to -1lia).
  - [ ] TATIANA one-click: formsubmit.co activation email (else signups drop).
- [x] CONTRIBUTING.md (d0244d7); README 134->193 (this commit).
- [x] GTM packs in business/ (gitignored): GTM_30DAY_S040 (goal ~23.08:
      >=5 scans, >=1 Baseline €2,500; kill criteria end-Oct),
      targets_15_S040 + snapshot_template (9 Claude targets; top: Robin AI,
      Lovable, Hebbia), dist_S040/ (GitHub Action llm-drift-check +
      MCP server — publish next), openssf_badge_checklist, NLnet draft.
- [ ] OpenSSF anketa (bestpractices.dev, ~1-1.5h, checklist ready).
- [ ] NLnet: general call closed until ~01.10; check nlnet.nl/propose ~25.09.
- [ ] Snapshot offensive: Claude targets can start now; rest after ~2wk
      of board baseline. Briefing #1 unblocked (fill after a few days).


## S039 — 2026-07-22 (FIX-2b: analytical quorum schedule, the "Seismo bound")
- [~] FIX-2b AUTHORED on a clean clone (base 2fc6108); NOT yet on a branch/
      merged. Replaces FIX-2 synthetic frac=1/2 with a model-derived schedule.
  - [x] Finding: binding constraint is detection POWER (false negatives), NOT
        FP. Shipped ceil(M/2) suppressed FP 1e-6..1e-12 while eroding power
        (majority rule unreachable under sparse canary coverage).
  - [x] q(M)=max(3, ceil(M/3)) — ONE constant: engine/correlation.py
        QUORUM_FRAC_DEN 2->3 (flows to Redis Lua too). Flat q=3 for M<=9
        (= near-term optimum + old policy, no regression), gentle knee at M=10.
  - [x] p anchored to LIVE detector (CUSUM ARL0~=500; gateway wires CUSUM).
        14d TTL validated analytically (band [~5d, 25.6d] at 1/day cadence).
  - [x] Adversarial verify of the MODEL: SURVIVES-WITH-CAVEATS. Pure
        correlation can't break it at anchored p; residual = estimation-
        inflated p (~0.074) x rho~0.08 at M>=10, which ceil(M/3) hedges
        (worst-case FP 0.036/0.046/0.032). floor=3 kept for Sybil, not FP.
  - [x] Fixed repo doc bug: correlation.py BOCD "(LIVE)" -> "(IMPLEMENTED,
        not wired)"; CUSUM is the live candidate generator.
  - [x] Gate: ruff x2 clean + 151 pass on clean clone (count unchanged).
        NEW: data/drift_labels/quorum_seismo_bound.md, KEYSTONE_REPORT_FIX-2b.md
        (UNSIGNED), scripts/experiment_quorum_bound.py + quorum_seismo_pick.py.
- [ ] TATIANA (S039 close): create branch seismograph/task-fix-2b, host gate
      (ruff x2 + 151), squash-merge, SIGN Keystone FIX-2b §6, bump memory.
- [~] #6 distribution/reach STARTED (same session): approach = incident
      ride-along. STANDING drift-radar scheduled task created
      (trig_01PPnjrGBoCzYD5MDFwAhZYQ, daily 09:00 Berlin, push on) — surfaces
      live waves + drafts; NEVER recreate it. Pack + templates:
      business/reach_incident_ridealong_S039.md. Evergreen guide drafted
      business/content_evergreen_guide_S039.md (published:false -> Tatiana to
      publish on dev.to). Live-wave scan 2026-07-24: none live (GPT-5.5 past
      peak). NEXT: optional HTML guide for driftdefense.dev; #5-empirical still
      needs orgs -> real drift_labels.


## S037 — 2026-07-19 (FIX-2: engine candidate TTL + metric-scoped, scaled quorum)
- [x] FIX-2 SHIPPED on branch seismograph/task-fix-2 (commit b5c8621,
      pushed; host gate 151 passed, ruff x2 clean). Closes the EXP-2 engine
      gap in the ENGINE (not the harness):
  - [x] G1: ChangePointResult += metric_name + timestamp_ns; agreement now
        per (model_tuple, metric_name) in both scorers.
  - [x] G2: per-candidate 14d TTL — window (now-ttl, now]. In-process dict
        of {org: latest_ts}; Redis rewritten to per-stream ZSETs scored by
        event-time (ms, since ns exceeds IEEE-754 double precision).
  - [x] G3: population-scaled quorum q(M)=max(3, ceil(M/2)) over the live
        observer population M (new observe() on the gateway public path).
        floor=3, frac=1/2 configurable; SYNTHETIC EXP-2-backed defaults.
  - [x] +14 new tests (tests/test_agreement_scorer.py) — metric scoping,
        TTL expiry, q(M) scaling, Sybil resistance, semantic-only-promote;
        + test_two_orgs_below_floor_stay_stable regression; Redis tests
        rewritten to ZSET/Lua wiring. 134 -> 151.
  - [x] data/drift_labels/quorum_fix2_calibration.md (synthetic defaults +
        EXP-2 provenance); KEYSTONE_REPORT_FIX-2.md (unsigned).
- [x] FIX-2 PR (S038): squash-merged seismograph/task-fix-2 -> main (4fdca91);
      §6 of KEYSTONE_REPORT_FIX-2.md SIGNED; main baseline bumped to 151.
      Independent clean-clone re-verify pre-merge (ruff x2 + 151), conflict-free.
- [~] Phase-1 FIX-2 follow-up: ANALYTICAL q(M)+TTL DONE in FIX-2b (S039,
      awaiting merge). REMAINS (Phase-2, needs real traffic): measure p and
      rho from live probes -> recalibrate; Sybil residual mitigations
      (reputation weighting + Ed25519 binding).
- [x] Landing driftdefense.dev "127 tests" -> RESOLVED: live already shows
      134 (S036 note was stale; no action needed).
- [ ] Deferred (carried): invites Sigge/Martin/Lars if Pending; GoatCounter
      week-1 review; Model Weather Briefing #1 [FILL] /v1/weather refresh;
      HN "Show HN:" repost ~21-22.07 if mod silent.


## S036 — 2026-07-18 (PyPI recovery + first Trusted-Publishing release)
- [x] PyPI #11202 CLOSED: account Kapibara recovered (pwd reset + 2FA TOTP
      + 7 recovery codes). Full access verified (project manageable).
- [x] Temp branch lPpHBOqwfdAqYN6j DELETED (was the #11202 proof branch).
- [x] PyPI Trusted Publishing (OIDC) configured: publisher
      Tania-coder/SEISMOGRAPH -> release.yml, env pypi.
- [x] .github/workflows/release.yml added (build swap + hatchling +
      twine check -> gh-action-pypi-publish via id-token write).
- [x] seismograph-probe 1.1.0 PUBLISHED (commit df4b900; GitHub Release
      v1.1.0 -> workflow Success 40s). providers.py feature + REQ-PRIV-010.
- [x] Baseline 134 + ruff both gates re-verified on a clean GitHub clone.
- [ ] Landing driftdefense.dev "127 tests" -> 134 (separate drift-defense
      repo; one-line index.html fix, PowerShell replace ready).
- [ ] Invites Sigge/Martin/Lars: withdraw if still Pending (deferred).
- [ ] GoatCounter week-1 review (deferred).
- [ ] Model Weather Briefing #1: [FILL] needs /v1/weather numbers (deferred).
- [ ] FIX-2 engine decision (candidate TTL + quorum scaling) — pending.

## S035c — 2026-07-15 (interim, paper evidence sprint)
- [x] EXP-1 (3 parallel agents): DP-ON backtest + (h,k,baseline,sigma)
      grid (180 cfg) + stable-FP. FALSIFIED: zero-FP claim (0.400/90d
      single obs) and old DP bounds (detection 62.5% vs null 56.5%).
      Default (5.0,0.5,30) confirmed: 2025-08-10 / 38d.
- [x] FIX-1 REQ-PRIV-010: delta_f=MAX/n in probe/privacy.py + 7 tests
      (134 total). EXP-1R: 100% detection at n>=100; median alert
      2025-08-10 at n=200 — canon 38d recovered under DP noise.
- [x] EXP-2 quorum sim (real AgreementScorer): M=3/q=3+TTL14d ->
      FP 0.015 at 36d lead. Invariant held (burst/Sybil-alone never
      promote). Design gap: NO candidate expiry in engine; fixed q=2
      degrades with network size (M=5/q=2 FP 0.86).
- [x] Outline updated (secs 4.2/5/6/7/8/10); Keystones EXP-1 +
      PRIV-010 drafted.
- [x] TATIANA: host gate 134 passed -> PR #14 squash-merged (90fda54)
      -> Keystones SIGNED + README 134 (4057b33) -> branches cleaned
      (incl. stale task-E1/task-infra-1; lPpHBOqwfdAqYN6j kept).
      CI 4/4 green on 4057b33.
- [ ] DECISION (Tatiana): FIX-2 candidate — engine-side candidate TTL +
      quorum scaling (+ metric name in ChangePointResult) in
      AgreementScorer. Threshold decision needs drift_labels datum
      per Seismo bound. Blocks nothing for the paper (TTL documented
      as harness-enforced), but is the right engine fix.

## DO NEXT — S036 (reminder fires 17.07 09:00)
- [ ] 17.07: PyPI reply check (NO touches) + withdraw Sigge/Martin/Lars
      if Pending. On acceptance: locked phrasing.
- [x] TATIANA 14.07: CUSUM explainer POSTED 2026-07-14 (LinkedIn + X
      thread of 2, chart attached, UTM linkedin/post):
      LI: linkedin.com/feed/update/urn:li:activity:7482823133020794880
      X:  x.com/tatyanti/status/2077057793144610885
- [x] 14.07 interim (Claude): methodology paper outline DONE
      (docs/methodology_paper_outline.md, was STRETCH); Briefing #1
      drafted (business/content_briefing1_S036.md, [FILL 17.07] marks);
      arch doc stale rows fixed (BOCD live, auth.py live — verified vs
      code); social/posts_dashboard_live.md marked DEPRECATED (pre-canon
      phrasing).
- [ ] 17.07: Model Weather Briefing #1; live-run post READY too
      (screenshot live_run_S034.png exists; slot 22.07, may go early).
- [ ] HN repost ~21-22.07 if mod silent (pack ready).
- [ ] If PyPI resolves: recovery chain -> republish 1.0.1 -> OIDC.
- [ ] Batch 2 (Zendesk AI, Parloa) after 17.07 cleanup.
- [x] Second GitHub verified email — DONE 2026-07-14 (S035b).
- [ ] GoatCounter week-1 review (17.07, week completes).
- [ ] STRETCH: methodology paper outline.

## ARCHIVE — S035 items (2026-07-13, early content sprint)
- [x] CUSUM explainer drafted + chart generated from fresh SEED=42
      backtest run (alert 2025-08-10 re-confirmed). 2 defects caught
      (chart scale hid alert; "error rate" -> "JSON success rate").
- [x] Auto-memory zenodo ref FIXED (concept = ...21045517; ...518
      marked stale version DOI). Closes the S034 addendum follow-up.

## ARCHIVE — S034 items (all closed)
- [x] SEC-1b (alert #6) CLOSED S034: PR #13 squash-merged (b6388b8).
      gateway/auth.py InvalidSignature branch logs
      sha256(pub_bytes).hexdigest()[:12] (key_sha256=..., digest over
      PARSED key bytes = canonical identity). _sanitize_for_log kept for
      exc branch (SL3). SL2 rewritten. Host gate: ruff x2 + 127 passed.
      Post-merge CodeQL scan #17 (5218f50) VISUALLY CONFIRMED:
      0 Open / 6 Closed -- SAST fully clean. (codeql #16 on the merge
      commit was cancelled by concurrency when the memory push landed;
      #17 scanned the tree incl. the fix -- expected behavior.)
- [ ] KEYSTONE_REPORT_SEC-1.md fully amended (sections 2/4/7, dated
      07-12). REMAINS ONLY: Tatiana signature (section 5).
- [ ] (DONE 07-10) memory/* S033 + Keystone committed to main (0433f44);
      this correction commit pending.
- [~] PyPI #11202: re-reply to verification email SENT 07-12 09:01
      (Tatiana chose to send ahead of the ~07-17 plan). HARD RULE now:
      NO further touches (no emails, no issue pings) until they respond.
      If total silence persists, next escalation ~end of July via
      admin@pypi.org (different channel), not another follow-up.
      On resolution: new pass + 2FA + recovery codes -> delete temp
      branch lPpHBOqwfdAqYN6j -> republish 1.0.1 -> Trusted Publishing.
- [ ] Sebastian (Legora): single follow-up SENT 07-10. Do NOT message
      again unless a trigger event (provider incident / Legora news / his
      post) makes it relevant.
- [ ] Sigge/Martin/Lars invites: if still Pending ~07-17, withdraw. On ANY
      acceptance, first message uses locked phrasing (their notes carry
      old "caught" wording).
- [ ] HN 48773957: waiting on mod reply to the 07-06 email. Else proper
      "Show HN:" repost in 2-3 weeks.
- [x] Stale hn@ Gmail draft DELETED (verified S034: drafts search for
      to:hn@ycombinator.com returns zero).
- [x] DOI discrepancy RESOLVED S034 addendum: verified live --
      ...21045517 = concept DOI (resolves to latest v1.0.1/21139614);
      ...21045518 = v1.0.0 VERSION DOI (stale record, old wording).
      Fixed to concept DOI in README (badge + docs line + bibtex ->
      v1.0.1), SECURITY.md, ROADMAP.md, CITATION.cff (doi: added,
      version 1.0.1). NOTE: auto-memory reference_zenodo_doi.md says
      concept = ...518 -- WRONG, fix next session. Session-log line
      S026 "concept DOI ...518 minted" was the original error
      (append-only, stands corrected here).
- [ ] TATIANA: dev.to article -- 2 edits in the editor (122 tests ->
      127; footer DOI ...21045518 -> ...21045517 x2). Instructions
      given S034.
- [x] drift-defense landing "122 tests" -> 127 FIXED S034 addendum
      (folder mounted mid-session; single occurrence in index.html;
      no DOI references on the landing).
- [x] (S034 addendum) LICENSE added (052918d): GitHub now detects
      Apache-2.0 (was Other/NOASSERTION -- no LICENSE file existed).
      README refreshed: 127 tests, CodeQL line, roadmap rows 2/3.

## DONE S033 (detail in log)
- [~] SEC-1: PR #12 squash-merged; 127 passed host & CI, ruff/format
      green. Post-merge CodeQL: 4 audit.py alerts CLOSED (int() barrier),
      but auth.py path re-opened as alert #6 (custom sanitizer not
      recognized). Functionally fixed (SL2 proves it) but not CodeQL-clean
      -- see DO NEXT follow-up. Keystone written (needs #6 amendment +
      signature).
- [x] dependabot.yml security-only pip policy merged (PR #10, squash).
- [x] Dependabot codeql-action 3->4 bump merged (PR #11); no pip version
      PRs opened under the new policy (correct behavior).
- [x] PyPI #11202 gentle ping posted in issue (07-10).
- [x] Sebastian single light-touch follow-up sent (LinkedIn, 07-10 15:11).

## DONE S031 -> S032 (history)
- [x] drift-defense Pages build FIXED S032: transient GitHub Pages infra
      error on 9c1e9fb deploy (build was green), NOT a repo defect. Fixed
      via empty commit 3aceaf0 -> run #7 green. Live landing verified.
- [x] hn@ycombinator.com mod email SENT by Tatiana 07-06 15:03.
- [x] GitHub infra hardening S032: ruleset protect-main ACTIVE (no
      force-push/delete); PR #1 (workflow permissions contents:read +
      dependabot.yml); PR #9 (CodeQL SAST py+js, security-extended,
      weekly); Dependabot actions bumps #2/#3 merged, floor bumps #4-#8
      closed by library policy.

## OPEN — Admin / Security (deadline)
- [x] GitHub 2FA TOTP — DONE 2026-07-02.
- [~] PyPI recovery #11202 IN PROGRESS: proof sent 2026-07-02 10:46; issue
      moved to "Verification in Process"; gentle ping posted 07-10. If
      silent ~1 week, re-reply to the verification email. Then: new pass +
      2FA + recovery codes -> delete temp branch lPpHBOqwfdAqYN6j ->
      republish 1.0.1 -> Trusted Publishing (OIDC).
- [x] Add a second verified email on GitHub — DONE 2026-07-14 (S035b;
      closed the account-loss scenario that hit PyPI).

## OPEN — Hygiene
- [x] Bulk CRLF renormalize — DONE S030 (sandbox-mount read artifact, not
      a repo defect; ignore permanently, CI is ground truth).

## OPEN — Growth (PRIVATE detail in business/, gitignored)
- [~] Outreach batch 1 (2026-07-03): 6 invites still Pending as of S034
      (07-12, verified in Invitation Manager)
      (Jose/Joel/Delphine; Sigge/Martin/Lars). Sebastian ACCEPTED 07-03,
      single follow-up sent 07-10 (no reply yet). PAUSED per playbook;
      batch 2 (Ultimate/Zendesk AI, Parloa; then Tier B) waits for replies.
      LESSON LOCKED: notes say "a seeded backtest flags it 38 days before
      the postmortem" — never "caught ... early".
- [x] Void Stitch triage (S031): likely bot — disengage.
- [x] Zenodo v1.0.1 published S030 (DOI 10.5281/zenodo.21139614).

## NICE-TO-HAVE
- [x] Track 1b DONE S034 (afternoon sprint): 3 live emissions
      mistral/mistral-small-latest -> local gateway, all accepted
      (Ed25519 key d0d81dfe86d9..., batches 420d6f59/bd1e2a3a/f3ebca96).
      Rolling json_rate converged 0.203 -> 0.252 -> 0.291 (DP noise
      averaging as designed). New Mistral key seismograph-probe-local in
      business/mistral_key.txt (gitignored); OLD key untouched (Render).

## DONE S034 afternoon sprint (marketing/infra)
- [x] Landing v2 LIVE on https://driftdefense.dev (8f2a07c + 9b6b055):
      topbar CTA, client-path section, mid-CTA, mailto mini-form,
      JSON-LD, canonical on new domain. Enforce HTTPS ON.
- [x] Domain driftdefense.dev bought (Porkbun, ~$8.75/yr, WHOIS privacy,
      auto-renew, exp 2027-07-12). DNS: 4xA GitHub Pages IPs + CNAME www.
      Strategy: SEISMOGRAPH = engine brand, Drift Defense = service brand.
- [x] GoatCounter analytics LIVE (driftdefense.goatcounter.com, email
      verified, site domain set): pageviews + 5 CTA click events
      (cta-topbar/hero/baseline/mid/final). Tatiana's ABP blocks own
      visits -- stats are a lower bound.
- [x] README -> landing funnel link (df235d6, utm_source=github).
- [x] Marketing pack: business/marketing_pack_S034.md (HN repost draft,
      batch 2 notes, 2-week content plan w/ weekly "Model Weather
      Briefing", UTM registry, paid-spend rules: NO ads until analytics
      2wk + HN repost + 1 organic scan request).
- [ ] TATIANA: dashboard screenshot -> business/live_run_S034.png, then
      post business/portfolio_post_live_run_S034.md (LinkedIn+X drafts
      ready; may post early, else slot Wed 22.07).

## DEFERRED — Phase 3 future
- [ ] SSO/RBAC, SOC 2, in-VPC probe, SLAs / canary-gated rollback, hires.
- [ ] Branch protection: add required status checks + PR-flow when a
      second contributor appears (ruleset exists, deliberately light now).

---

## COMPLETED — index (full detail in log + archive)
Phase 0-2 + Phase 3 (multi-tenant, audit): see archive.
S025: README badges, dep-graph generator, P3-002 webhooks.
S026: re-verification; grant/market pack; Zenodo DOI; ROADMAP.md;
  SECURITY.md; README nav + citation; live-probe code.
S027: live-probe arc merged; first live Mistral run; probe hardening;
  Track 1b/2/3; LinkedIn + X published. 122 passed, main green.
S028-S033: see log (E1 canon fix, dev.to publish, Show HN, Zenodo v1.0.1,
  outreach batch 1, drift-defense Pages fix, GitHub infra hardening
  (ruleset + workflow perms + Dependabot + CodeQL), SEC-1 log-injection
  fix -> 127 passed).
