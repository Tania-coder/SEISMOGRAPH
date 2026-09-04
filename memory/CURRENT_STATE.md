# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-09-04 (Session 049: FIRST PUBLIC ARTEFACT IN 42 DAYS.
# Weather Report #1 written from measured data and published to dev.to +
# LinkedIn, with an archival copy committed to docs/reports/ BEFORE
# publication so the repository holds the earliest timestamp. Keystone
# DASH-2 sec 9 SIGNED (deploy 09-02, signature 09-04, both dates recorded).
# CAN-3's diagnosis REFUTED by measurement. The collection defect MOVED
# from the google leg to the mistral leg. Protocol 01 gained a signature
# gate. No engine code changed this session.)
# Prior (S048, 2026-09-02): DASH-2 landed (PR #27, 09f1563), 309 -> 325.
# Prior (S047, 2026-08-28): DASH-1 landed (PR #26, fd4c561), 293 -> 309.
# Prior (S046, 2026-08-11): PRIV-011 + INFRA-3 landed.

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Lead Technical Co-Pilot.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe.
- Branch convention: seismograph/task-{id}.

## Three-role protocol (S048; amended S049 — read business/guide_pack/01)
- DIRECTOR (Tatiana): decides, signs Keystones, runs git, publishes, spends.
- EXECUTOR (this Cowork project): has the machine. Builds, measures,
  verifies, lands. Never signs, never publishes, never runs the
  Director's git.
- GUIDE (separate Claude web project): no machine, no repo. Holds strategy
  and the open-decision register. Consulted BETWEEN sessions.
- Evidence standard: tag every claim [measured] / [derived] / [assumed];
  a scoped test run is never a gate; arithmetic is a prediction, not a
  measurement, until observed. business/guide_pack/05.
- **SIGNATURE GATE (NEW, S049).** The signature precedes the merge. An
  unsigned deploy BLOCKS step 0 of the next session — a stop condition,
  not a backlog item. Both dates always recorded, never backdated.
  Removing the step is a legitimate Director decision but only as an
  explicit entry in 03, never by attrition.

## Phase
- Phase 0 thesis VALIDATED (38-day lead, synthetic-replay backtest).
  Phases 1-2 core complete; Phase 3 partial.
- INFRA-1 (S044, PR #23 @e128235): Neon free Postgres persistence.
  PROVEN THREE TIMES (S044 restart; 7 days at S046; 24 days at S047).
- PRIV-011 (S045/S046, PR #24 @261b63d): MAX_OUTPUT_LENGTH 8192 -> 320.
  291 -> 293. Keystone SIGNED 2026-08-11.
- INFRA-3 (S046, PR #25): probe cron 5x/day -> "17 5,17 * * *".
- DASH-1 (S046/S047, PR #26 @fd4c561): recent_json_success_rate normalised
  onto the scorable-canary base. 293 -> 309. Keystone SIGNED 2026-08-28.
- DASH-2 (S047/S048, PR #27 @09f1563): /v1/weather publishes sample_count,
  json_sample_count, length_sample_count, window_start, window_end.
  309 -> **325**. Keystone sec 9 **SIGNED 2026-09-04** (@9a8aaa0) — deploy
  2026-09-02 preceded the signature by two days; both dates in the report.

## Baseline (re-verify at session start — do not trust this file)
- Tests: **325 on MAIN**. Host gate 2026-09-04: ruff check clean, ruff
  format clean (62 files), pytest 325 passed, in 4.31 s.
- **FINDING (S049, open): the gate runs on `Python 3.10.11`, but BOTH
  `pyproject.toml:8` and `pyproject_probe.toml:49` declare
  `requires-python = ">=3.11"`.** The whole 325 baseline is proven only
  on a version the package says it does not support; the declared version
  has never been gated. Needs its own task.
- Sandbox full-suite install: opentelemetry-sdk fastapi uvicorn sqlalchemy
  cryptography httpx pytest (+ redis clickhouse-connect). Ruff pinned
  0.15.20, BOTH gates: ruff check . && ruff format --check .
- HARD RULE (S029/S030): after ANY write through the mount, verify via the
  Read tool / git — sandbox mount reads pad NULs and serve stale cache.
- HARD RULE (S035): NEVER append to an existing memory/log file via
  sandbox heredoc through the mount — build full content, write, re-verify,
  or append natively from PowerShell.
- HARD RULE (S037): bridge can drop mid-session; after reconnect re-verify
  writes landed BEFORE committing.
- HARD RULE (S046): NEVER end a session with uncommitted work. Broken
  twice since written (PRIV-011 at S045; DASH-2 at S047).
- HARD RULE (S048): a scoped/subset test run is NEVER a gate result.
- **HARD RULE (S049, new): verify the PUBLIC SURFACE, not just that the
  publish action succeeded.** Weather Report #1 went out with a stale
  body — the correct file was on disk, an older copy was in the paste
  buffer. Caught only by reading the live page back and diffing it against
  the archival copy. Contributing cause: three different versions were
  delivered under one filename. **Change the filename on every revision.**
- NOTE (S047, S048, S049): `device_bash` failed to start THREE sessions in
  a row — "Workspace unavailable". The deferred trigger to investigate has
  now fired. Fallback that works and is now the standing mode:
  device_stage_files to read, edit in the container, device_commit_files to
  write back, git from PowerShell, and **Chrome + the GitHub REST API read
  from the page context** — which fully replaces `gh run list` and needs
  nothing from the Director.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock; if lock:
  Remove-Item .git\index.lock -Force). Fresh GitHub clone in /tmp IS safe.
- Web-UI PR merge via Tatiana's Chrome is OK with her explicit approval.
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- FORMATTING RULE (S046): put ONLY runnable commands in code fences.

## Live assets
- Board: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  on Neon free Postgres. Cron 2x/day scheduled (05:17, 17:17 UTC) — but
  **scheduled runs actually fire 2.5-4.5 h late** [measured S049], so any
  arithmetic treating gaps as exact multiples of 12 h is unsound.
- **Last raw read 2026-09-04 18:00 UTC:**
    google   json 0.96961 (norm)  length 130.398  10/10/10
             window 2026-08-28T01:34:25Z -> 2026-09-04T09:46:39Z
             span 176.2 h (7.34 d) vs 108 h nominal; mean interval 19.58 h
    mistral  json 0.97856 (norm)  length  89.42253  10/10/10
             window 2026-08-28T17:27:23Z -> 2026-09-02T09:38:39Z
             **FROZEN — byte-identical to the 2026-09-02 read.**
             Last row 56 h old, four scheduled slots missed.
  avg_output_length CLEAR of the PRIV-011 cutover on both legs — CITABLE.
- **PUBLIC ARTEFACT — Weather Report #1, published 2026-09-04:**
    dev.to   https://dev.to/taniacoder/i-gave-my-drift-monitor-a-denominator-the-first-thing-it-exposed-was-a-hole-in-my-own-data-5508
    LinkedIn https://www.linkedin.com/feed/update/urn:li:activity:7501709720328753152/
    Archival copy of record: docs/reports/2026-09-04-weather-report-01.md
    (committed @e8b0e5b BEFORE publication; both URLs recorded @87d5527)
- Landing: https://driftdefense.dev (repo D:\Dev\Projects\drift-defense) —
  says 325. Brand rule: SEISMOGRAPH = engine, Drift Defense = service.
- Guide pack: business/guide_pack/ (gitignored, private, **and therefore
  not backed up anywhere** — open item).
- PyPI: seismograph-probe 1.1.0 (18 Jul, 48 days stale).
- DOI: https://doi.org/10.5281/zenodo.21045517 (concept; ...518 is the
  stale v1.0.0 version DOI — do not cite).

## Facts canon (E1, fixed S029; wording upgraded S043 — use ONLY these)
- Incident: Anthropic postmortem 2025-09-17, THREE infra bugs, NOT a model
  update. Backtest models bug #1: context-window routing error, Claude
  Sonnet 4 (NOT 3.5 Sonnet), 0.8% from 2025-08-05, ~16% from 2025-08-29.
- Model tuple: anthropic/claude-sonnet-4@global.
- Detection (SEED=42): first alert 2025-08-10; lead 38 d over postmortem.
- LOCKED PHRASING: "a seeded backtest flags it 38 days before the
  postmortem"; prefer "synthetic replay / would-have flagged".
  NEVER "caught ... early" (implies live catch).
- Live board baseline: RE-ESTABLISHED 2026-08-04 (v2.0.0 on Neon).
- M = 1 observer. Quorum requires 3. **No public alert can fire, by
  construction.** Central strategic fact.

## Open now (full backlog: project_open_tasks.md; ranked: guide_pack/03)
1. **mistral leg is DARK.** No row since 2026-09-02T09:38:39Z. Jobs
   `emit (mistral)` failed in runs #123-#126; run #126 log reads
   `0/50 prompts completed`, all fifty ids, job dead in 75 s, with the
   "Note missing secret" step SKIPPED (so the key is present). Zero
   completions in 75 s is a hard endpoint/credential/quota condition, not
   the transient 429 bursts google shows. **Highest-value open task.**
   DO NOT re-run the workflow casually: a successful run slides the window
   and erases the evidence a reader of Weather Report #1 can currently
   verify on the live endpoint.
2. **OBSERVABILITY BLOCKER — the run log names only the failed prompt
   ids.** No HTTP status, no response body, no retry/backoff spend. Root
   cause is not diagnosable from the logs on EITHER leg. This must ship
   before any collection fix, or the next failure is equally blind.
3. **CAN-3 is DEAD as written — do not implement it.** [measured S049]
   Its premise ("60000 ms total backoff caps a run at ~4 fully-retried
   prompts") is refuted: run #122 completed **49/50** prompts and run #118
   **40/50**, with failures interspersed mid-suite rather than monotone
   from an exhaustion point. The binding constraint is the printed policy
   `pacing: 4500 ms, <= 2 retries on 429/503` applied PER PROMPT, plus
   `execute_canary_strict`'s all-or-nothing discard. One prompt in fifty
   losing three attempts destroys the whole sample. Replacement contract
   (CAN-3'): more retries per prompt and/or a documented reduced-n path
   that recomputes DP sensitivity for the actual n.
4. `observer_count: 1` field on /v1/weather (G-04) — presentational.
5. Naive `last_alert_timestamp` — renders shifted by the viewer's offset.
6. `requires-python >= 3.11` vs a gate run on 3.10.11 (see Baseline).
7. PRIV-012 (avg_output_tokens, ~128x) — DASH-2 makes the cutover
   measurable for the first time.
8. Published metrics are not quorum-gated (DASH-1 Keystone sec 7.1) —
   accepted as OPEN and UNDEFENDED in the DASH-2 signature; it is a
   PREREQUISITE for a second observer, not a follow-up to one.
9. Dependabot PRs #15-#18 stale. VALID_PAYLOAD impossible in tests.
10. probe 1.2.0/1.3.0 release; third/fourth model legs — both deferred
    behind the collection fix so a new leg does not inherit the defect.
11. business/ and social/ exist only on Tatiana's disk. Private is not
    backed up. A private GitHub repo would close it.
12. Carried Tatiana clicks: SSH signing key for verified commits; Zenodo
    release to archive docs/reports/; formsubmit activation; OpenSSF
    anketa; NLnet recheck ~25.09; optional Neon password reset.

## Scheduler reconciliation [measured 2026-09-04]
Window 2026-08-24T05:58Z -> 2026-09-01T10:11Z, workflow probe_weather.yml:
  A = 16 scheduled runs fired (#105-#120)
  B = 9 success / 7 failure / 0 cancelled, at RUN level
  C = 10 google rows on the board  =>  6 runs produced no google row
The Guide's falsifiable prediction (A = 17 +/- 1, C = 10, 6-8 losses)
HOLDS. H3 (scheduler gap) and H4 (job timeout) are both REFUTED: the runs
fired and nothing was cancelled. Run-level status is a poor proxy for
per-leg collection — a run is marked failed if ANY leg fails, and a failed
run can still carry a successful leg (10 rows from 9 run-level successes).
