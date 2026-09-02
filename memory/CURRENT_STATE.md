# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-09-02 (Session 048: recovered a 5-day uncommitted
# DASH-2 tail from S047 (written 9 min after S047's own close commit),
# audited it against its own Keystone claim, found the claimed gate
# ("expect 325") was never run full-suite, ran it (324/1 fail), fixed by
# TIGHTENING the A6 guard rather than relaxing it, merged PR #27 @09f1563.
# 309 -> 325. Post-deploy measurement CLOSED the avg_output_length
# contamination question and RAISED the google-leg loss estimate from
# 31% to 45%. Landing page 193 -> 325. Guide project + three-role
# protocol established; Guide's first decision memo received and
# independently re-verified — one unflagged-assumption error caught in
# it, conclusion unaffected. Session left OPEN pending CAN-3 and Weather
# Report #1; this entry closes S048's own bookkeeping only.)
# Prior (S047, 2026-08-28): DASH-1 landed (PR #26, fd4c561), 293 -> 309.
# Prior (S046, 2026-08-11): PRIV-011 + INFRA-3 landed.
# Prior (S045, 2026-08-06): PRIV-011 authored but left uncommitted 5 days.

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Lead Technical Co-Pilot.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe.
- Branch convention: seismograph/task-{id}.

## Three-role protocol (NEW, S048 — read business/guide_pack/01 in full)
- DIRECTOR (Tatiana): decides, signs Keystones, runs git, publishes, spends.
- EXECUTOR (this Cowork project): has the machine. Builds, measures,
  verifies, lands. Never signs, never publishes, never runs the
  Director's git.
- GUIDE (separate Claude web project "SEISMOGRAPH Guide"): no machine, no
  repo. Holds strategy and the open-decision register
  (business/guide_pack/03_OPEN_DECISIONS.md, mirrored in that project).
  Consulted BETWEEN sessions via a closing-packet / decision-memo loop
  (business/guide_pack/06_SESSION_LOOP.md), never mid-session.
- Evidence standard (binding on all three): tag every claim [measured] /
  [derived] / [assumed]; a scoped test run is never a gate; arithmetic is
  a prediction, not a measurement, until observed. Full doc:
  business/guide_pack/05_EVIDENCE_STANDARD.md. This is not decoration —
  S048 used it to catch its own gate-claim error AND to catch an
  unflagged assumption change inside the Guide's first memo.

## Phase
- Phase 0 thesis VALIDATED (38-day lead, synthetic-replay backtest).
  Phases 1-2 core complete; Phase 3 partial.
- INFRA-1 (S044, PR #23 @e128235): Neon free Postgres persistence.
  PROVEN THREE TIMES (S044 manual restart; 7 days at S046; 24 days at S047).
- PRIV-011 (S045/S046, PR #24 @261b63d): MAX_OUTPUT_LENGTH 8192 -> 320.
  291 -> 293. Keystone SIGNED 2026-08-11.
- INFRA-3 (S046, PR #25): probe cron 5x/day -> "17 5,17 * * *".
- DASH-1 (S046/S047, PR #26 @fd4c561): recent_json_success_rate normalised
  onto the scorable-canary base. 293 -> 309. Keystone SIGNED 2026-08-28.
- DASH-2 (S047 authored / S048 landed, PR #27 @09f1563): /v1/weather now
  publishes sample_count, json_sample_count, length_sample_count,
  window_start, window_end. Read-side only; detector untouched. 309 ->
  **325**. Keystone written; **sec 9 NOT YET SIGNED by the Director** —
  code is live in production ahead of the signature (flagged, not hidden).

## Baseline (re-verify at session start — do not trust this file)
- Tests: **325 on MAIN** (DASH-2 @09f1563; was 309/293/291/286/257/193).
  Host gate 2026-09-02: ruff check clean, ruff format clean (62 files),
  pytest 325 passed. From repo root: py -3.10 -m pytest -q.
- Sandbox full-suite install: opentelemetry-sdk fastapi uvicorn sqlalchemy
  cryptography httpx pytest (+ redis clickhouse-connect). Ruff pinned
  0.15.20, BOTH gates: ruff check . && ruff format --check .
- HARD RULE (S029/S030): after ANY write through the mount, verify via the
  Read tool / git — sandbox mount reads pad NULs and serve stale cache.
- HARD RULE (S035): NEVER append to an existing memory/log file via
  sandbox heredoc through the mount — build full content, write, re-verify.
- HARD RULE (S037): bridge can drop mid-session; after reconnect re-verify
  writes landed BEFORE committing.
- HARD RULE (S046): NEVER end a session with uncommitted work in the
  working tree. Session-end protocol must run `git status` and show clean.
  BROKEN TWICE SINCE IT WAS WRITTEN (PRIV-011 at S045; DASH-2, authored
  9 minutes after S047's own close commit, discovered at S048 open).
- HARD RULE (S048, new): a scoped/subset test run is NEVER reported as a
  gate result. Only a full `pytest -q` from repo root is a gate. (DASH-2's
  Keystone stated "expect 325" from a 32-test scoped run; the real first
  gate was 324/1 fail.)
- NOTE (S047, S048): the desktop bridge's Linux workspace (device_bash)
  failed to start BOTH sessions — "Workspace unavailable". Fallback that
  works: device_stage_files to read, edit in the container,
  device_commit_files to write back, git from PowerShell, gh CLI commands
  handed to Tatiana to run directly when Actions-log data is needed.
  Browser automation via Chrome is fully functional and does PR + merge
  end to end with explicit approval each time.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock; if lock:
  Remove-Item .git\index.lock -Force). Fresh GitHub clone in /tmp IS safe.
- Web-UI PR merge via Tatiana's Chrome is OK with her explicit approval.
  (S047, S048: done by Claude driving Chrome directly, with approval.)
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- FORMATTING RULE (S046): put ONLY runnable commands in code fences.
  Tatiana pastes fenced blocks straight into PowerShell; evidence and tool
  output in fences get pasted and error. Use plain text or tables for those.

## Live assets
- Board: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  on Neon free Postgres. Verified live 2026-09-02 (Render deploy #93):
  2 models STABLE, no alerts. Cron 2x/day scheduled (05:17, 17:17 UTC) —
  google's ACTUAL mean interval measures 21.8h, not 12h (see below).
  OPENAI/ANTHROPIC legs skip until keys added.
- Last raw read 2026-09-02 (POST-DASH-2 deploy):
  google  json 0.96050 (norm)  length 131.06  window 8.18d  10/10/10
  mistral json 0.97856 (norm)  length  89.42  window 4.67d  10/10/10
  google mean interval 21.80h (55% of schedule, ~45% effective loss).
  mistral mean interval 12.47h (~4% loss, on schedule).
  avg_output_length CLEAR of the PRIV-011 cutover on both legs (windows
  open 13-18 days after the 2026-08-11 constant change) — CITABLE.
- Landing: https://driftdefense.dev (repo D:\Dev\Projects\drift-defense) —
  CORRECTED 2026-09-02 (759b870): 193 -> 325 in all three occurrences.
  Brand rule: SEISMOGRAPH = engine, Drift Defense = service.
- Guide pack (strategy/protocol docs): business/guide_pack/ (gitignored,
  private) — also uploaded to the separate "SEISMOGRAPH Guide" Claude
  web project. See "Three-role protocol" above.
- PyPI: seismograph-probe 1.1.0 (18 Jul, 46 days stale). 1.2.0/1.3.0
  release warranted, deferred behind CAN-3.
- DOI: https://doi.org/10.5281/zenodo.21045517 (concept).
- Social, measured 2026-09-02: LinkedIn 183 followers, last post ~1mo ago
  (1 reaction). dev.to 4 posts + 1 draft, last 24 Jul (40 days), <500
  total views across everything, 1 reaction, 2 comments. GitHub: 3 stars,
  0 watchers, 0 forks. FIVE consecutive sessions (S044-S048) with zero
  public output while the test baseline moved 291 -> 325.

## Facts canon (E1, fixed S029; wording upgraded S043 — use ONLY these)
- Incident: Anthropic postmortem 2025-09-17, THREE infra bugs, NOT a model
  update. Backtest models bug #1: context-window routing error, Claude
  Sonnet 4 (NOT 3.5 Sonnet), 0.8% from 2025-08-05, ~16% from 2025-08-29.
- Model tuple: anthropic/claude-sonnet-4@global.
- Detection (SEED=42): first alert 2025-08-10; lead 38 d over postmortem.
- LOCKED PHRASING: "a seeded backtest flags it 38 days before the
  postmortem"; prefer "synthetic replay / would-have flagged".
  NEVER "caught ... early" (implies live catch).
- Live board baseline: RE-ESTABLISHED 2026-08-04 (v2.0.0 on Neon) —
  landing must state this; never claim continuous history.
- M = 1 observer. Quorum requires 3. **No public alert can fire, by
  construction** — the engine is correct and the network is silent. This
  is the project's central strategic fact (business/guide_pack/00).

## Open now (full backlog: project_open_tasks.md; ranked: guide_pack/03)
1. **CAN-3 — google-leg retry budget, contract drafted, NOT implemented.**
   `max_total_backoff_ms` isn't threaded per-leg through live_emit.py
   (only delay_ms/max_retries are); stuck at 60000ms default, which caps
   a run at ~4 fully-retried prompts before the whole 50-prompt suite is
   discarded. DO NOT implement before the discriminating measurement
   below — the diagnosis is [derived] from code reading, not [measured].
2. **Discriminating measurement, not yet run** (device_bash down; gh CLI
   commands are with Tatiana). Falsifiable prediction: ~17 scheduled
   google runs in the 8.18-day window, ~10 producing a row, 6-8 producing
   none. Distinguishes retry-budget exhaustion (CAN-3 fixes it) from a
   scheduler gap or job timeout (CAN-3 would not help, or would hurt).
3. **Weather Report #1 — still not published.** Every technical blocker
   is cleared. Lead with mistral (clean, 3.73% loss); disclose google's
   45% as a window-span fact, not a headline percentage, until cause is
   measured; limitations section must state the SELECTION BIAS finding
   from the Guide's memo — surviving google samples systematically
   exclude high-load periods (discard correlates with 429, 429 correlates
   with load, load is the mechanism this project exists to detect) — so
   the -0.27sd google drift reading is computed over a censored sample.
4. `observer_count: 1` field on /v1/weather — presentational (the quorum
   invariant gates the DRIFTING label, not the raw numbers), should land
   before Weather Report #1 cites those numbers.
5. Naive `last_alert_timestamp` (found+not-fixed at DASH-2) — renders
   shifted by the viewer's UTC offset; invisible today only because no
   alert has fired.
6. PRIV-012: avg_output_tokens has the identical defect class as PRIV-011
   (MAX_TOKEN_COUNT 8192 vs 64 on the wire, ~128x). Landing it creates a
   new stream contamination — but DASH-2 now makes that MEASURABLE
   instead of inferred, so the cutover can be verified for the first time.
7. Published metrics are not quorum-gated (DASH-1 Keystone sec 7.1) —
   pre-existing, worth its own task before the board carries more
   observers.
8. Dependabot PRs #15-#18 open and stale (actions/checkout, setup-python,
   upload-artifact, download-artifact — all major bumps). Counts against
   the OpenSSF questionnaire already on the list.
9. `VALID_PAYLOAD` in tests/test_gateway.py is physically impossible
   (v1.0.0 with result_count 10). 38 references; needs its own task.
10. probe 1.2.0/1.3.0 release — deferred behind CAN-3.
11. Third/fourth model legs (OPENAI/ANTHROPIC keys) — deferred behind
    CAN-3 so a new leg doesn't inherit a known collection defect.
12. Carried Tatiana clicks: Keystone DASH-2 sec 9 signature; LinkedIn
    draft approval + channel decision; formsubmit activation; OpenSSF
    anketa; NLnet recheck ~25.09; optional Neon password reset.
