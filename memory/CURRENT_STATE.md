# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-08-28 (Session 047: DASH-1 LANDED (PR #26, fd4c561) —
# published JSON validity rate normalised onto the scorable-canary base,
# baseline 293 -> 309, Keystone SIGNED. Live board re-verified after a
# 17-day gap: Neon persistence now proven across 24 days, 2 models STABLE.
# The [0,1] clamp was observed FIRING on live data. New task DASH-2 opened:
# the published rate has no denominator. See "Open now".)
# Prior (S046, 2026-08-11): PRIV-011 + INFRA-3 landed; three defects opened.
# Prior (S045, 2026-08-06): PRIV-011 authored but left uncommitted 5 days.

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Lead Technical Co-Pilot.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe.
- Branch convention: seismograph/task-{id}.

## Phase
- Phase 0 thesis VALIDATED (38-day lead, synthetic-replay backtest).
  Phases 1-2 core complete; Phase 3 partial. GTM PLAN V2 executing.
- INFRA-1 (S044, PR #23 @e128235): Neon free Postgres persistence.
  PROVEN THREE TIMES — the S044 manual restart test, 7 days of live
  autosuspend verified 2026-08-11, and 24 days verified 2026-08-28.
- PRIV-011 (S045 authored / S046 landed, PR #24 @261b63d): probe/privacy.py
  MAX_OUTPUT_LENGTH 8192 -> 320. 291 -> 293. Keystone SIGNED 2026-08-11.
- INFRA-3 (S046, PR #25): probe cron 5x/day -> "17 5,17 * * *".
- DASH-1 (S046 authored / S047 landed, PR #26 @fd4c561): gateway-side
  normalisation of recent_json_success_rate onto the scorable-canary base
  (_JSON_BASE_BY_SUITE + _scorable_json_rate). Read-side only; the detector
  still consumes the raw wire value on purpose. 293 -> **309**.
  Keystone SIGNED 2026-08-28.

## Baseline (re-verify at session start)
- Tests: **309 on MAIN** (DASH-1 @fd4c561; was 293/291/286/257/193).
  Host gate 2026-08-28: ruff check clean, ruff format clean (61 files),
  pytest 309 passed. From repo root: py -3.10 -m pytest -q.
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
- NOTE (S047): the desktop bridge's Linux workspace (device_bash) failed to
  start for the whole session. Fallback that worked: device_stage_files to
  read, edit in the container, device_commit_files to write back, then
  git from PowerShell. Browser automation via Chrome was fully functional
  and did the PR + merge end to end.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock; if lock:
  Remove-Item .git\index.lock -Force). Fresh GitHub clone in /tmp IS safe.
- Web-UI PR merge via Tatiana's Chrome is OK with her explicit approval.
  (S047: done by Claude driving Chrome directly, with approval.)
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- FORMATTING RULE (S046): put ONLY runnable commands in code fences.
  Tatiana pastes fenced blocks straight into PowerShell; evidence and tool
  output in fences get pasted and error. Use plain text or tables for those.

## Live assets
- Board: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  on Neon free Postgres. Verified live 2026-08-28: 2 models STABLE
  (google/gemini-3.5-flash-lite, mistral/mistral-small-latest), no alerts,
  persistence intact across 24 days. Cron 2x/day (05:17, 17:17 UTC).
  OPENAI/ANTHROPIC legs skip until keys added.
- Last raw read 2026-08-28 (PRE-DASH-1 deploy):
  google  json 0.17675  avg_output_length 132.23
  mistral json 0.18317  avg_output_length  89.08
  Normalised: google 98.2%, mistral 100.0% (clamped from 101.8%).
- Landing: https://driftdefense.dev (repo D:\Dev\Projects\drift-defense) —
  v3 live; STALE: says 193 tests (now 309), missing the
  baseline-restart-2026-08-04 line. Brand rule: SEISMOGRAPH = engine,
  Drift Defense = service.
- Guide: driftdefense.dev/guides/detect-silent-llm-change/ (canonical for
  dev.to -1lia). Analytics: driftdefense.goatcounter.com (lower bound).
- PyPI: seismograph-probe 1.1.0. 1.2.0/1.3.0 release warranted.
- DOI: https://doi.org/10.5281/zenodo.21045517 (concept).

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

## Open now (full backlog: project_open_tasks.md)
1. **DASH-2 — the published rate has no denominator. BLOCKS Weather
   Report #1.** /v1/weather exposes neither sample_count nor the age of
   the 10-batch window, so a reader cannot tell whether 98.2% rests on
   10 samples or 2. Publishing a rate without its base is the same defect
   class DASH-1 just fixed, one level up. Add sample_count +
   window_start/window_end to ModelWeatherResponse. Read-side, detector
   untouched. Also resolves item 2 by measurement.
2. **avg_output_length — contamination NOT confirmed cleared.** Arithmetic
   says it aged out (17 days x 2/day = ~34 runs vs a 10-batch window), but
   /v1/weather exposes no timestamps, so this is inference, not
   measurement. The google/mistral spread (132.23 vs 89.08, 48%) is
   equally consistent with real verbosity difference OR residual 8192-era
   rows (Laplace 81.9, sd ~116). Do NOT cite until DASH-2 shows the
   window is 320-era only.
3. **google-leg sample loss** — execute_canary_strict discards the whole
   50-prompt suite when any prompt exhausts retries on the Gemini free
   tier (correct DP reasoning: flushing at reduced n changes sensitivity
   MAX/n). 31% of google samples lost; transient rate limiting, NOT drift.
   Options: raise retry budget/pacing, or a documented reduced-n path
   that recomputes DP sensitivity for the actual n. The 31% figure will
   appear in Weather Report #1 unless fixed first.
4. PRIV-012: avg_output_tokens has the identical defect class
   (MAX_TOKEN_COUNT 8192 vs max_tokens 64 on the wire, ~128x).
   avg_reasoning_tokens is NOT affected (reasoning budgets uncapped,
   CAN-2 finding) — the constant likely splits in two. Needs a contract.
   Note: landing it creates a NEW stream contamination, same as PRIV-011.
5. **Published metrics are not quorum-gated** (DASH-1 Keystone sec 7.1).
   Only DRIFTING status requires cross-observer agreement;
   recent_json_success_rate and recent_avg_output_length are single-org
   aggregates rendered directly. Pre-existing. Worth its own task before
   the board carries more observers.
6. Weather Report #1 — unblocked once (1) lands. mistral has ~69 clean
   samples; state google's coverage honestly; omit avg_output_length
   unless (2) is resolved.
7. **Dependabot PRs #15-#18 open and stale** — actions/checkout 4->7,
   setup-python 5->7, upload-artifact 4->7, download-artifact 4->8.
   All major-version jumps; may break CI. Stale dependency PRs also count
   against the OpenSSF questionnaire on the carried list.
8. `VALID_PAYLOAD` in tests/test_gateway.py is physically impossible
   (v1.0.0 with result_count 10). 38 references; needs its own task.
9. Landing (drift-defense repo): 193 -> 309 + baseline-restart line.
10. probe 1.2.0/1.3.0 release (suite v2 + strict runner + CAN-1).
11. Carried Tatiana clicks: formsubmit activation; OPENAI + ANTHROPIC keys
    -> 4 models; OpenSSF anketa; NLnet recheck ~25.09; optional Neon
    password reset (pasted in-session S044).
