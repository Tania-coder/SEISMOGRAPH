# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-08-11 (Session 046: PRIV-011 LANDED (PR #24, 261b63d) —
# DP clamp 8192 -> 320, baseline 291 -> 293, Keystone SIGNED; INFRA-3 cron
# revert LANDED (PR #25) — probe back to 2x/day. Three new defects found
# while verifying the live board: google-leg sample loss, json_success_rate
# denominator dilution, avg_output_length stream contaminated by the DP
# constant cutover. See "Open now".)
# Prior (S045, 2026-08-06): PRIV-011 AUTHORED but never committed — it sat
# as uncommitted working-tree changes on local main for 5 days and was
# absent from this file and the session log. Recovered in S046.

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
  PROVEN TWICE — the S044 manual restart test, and 7 days of live
  free-tier autosuspend cycles verified 2026-08-11.
- PRIV-011 (S045 authored / S046 landed, PR #24 @261b63d): probe/privacy.py
  MAX_OUTPUT_LENGTH 8192 -> 320 (= max_tokens 64 * 5 chars/token, a
  documented +25% margin over the naive 4 chars/token). Value chosen by
  100-seed Monte Carlo: 99/100 detection at 320 vs 43/100 at 8192.
  291 -> 293. Keystone SIGNED 2026-08-11.
- INFRA-3 (S046, PR #25): probe cron 5x/day -> "17 5,17 * * *"; stale COST
  header corrected (said 3 prompts / ~24 completions per day; actual 50
  prompts / ~200 per day across the two legs with keys).

## Baseline (re-verify at session start)
- Tests: **293 on MAIN** (PRIV-011 @261b63d; was 291/286/257/193).
  Host gate 2026-08-11: ruff check clean, ruff format clean (60 files),
  pytest 293 passed. From repo root: py -3.10 -m pytest -q.
- Sandbox full-suite install: opentelemetry-sdk fastapi uvicorn sqlalchemy
  cryptography httpx pytest (+ redis clickhouse-connect). Ruff pinned
  0.15.20, BOTH gates: ruff check . && ruff format --check .
- HARD RULE (S029/S030): after ANY write through the mount, verify via the
  Read tool / git — sandbox mount reads pad NULs and serve stale cache.
- HARD RULE (S035): NEVER append to an existing memory/log file via
  sandbox heredoc through the mount — build full content, write, re-verify.
- HARD RULE (S037): bridge can drop mid-session; after reconnect re-verify
  writes landed BEFORE committing.
- HARD RULE (S046, NEW): NEVER end a session with uncommitted work in the
  working tree. S045 authored a full verified task and left it unbranched
  and uncommitted on main; it survived only by luck. Session-end protocol
  must include `git status` and must show a clean tree.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock; if lock:
  Remove-Item .git\index.lock -Force). Fresh GitHub clone in /tmp IS safe.
- Web-UI PR merge via Tatiana's Chrome is OK with her explicit approval.
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- FORMATTING RULE (S046): put ONLY runnable commands in code fences.
  Tatiana pastes fenced blocks straight into PowerShell; evidence and tool
  output in fences get pasted and error. Use plain text or tables for those.

## Live assets
- Board: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  on Neon free Postgres. Verified live 2026-08-11: 2 models STABLE
  (google/gemini-3.5-flash-lite, mistral/mistral-small-latest), no alerts,
  persistence intact across 7 days. Cron now 2x/day (05:17, 17:17 UTC).
  OPENAI/ANTHROPIC legs skip until keys added.
- Landing: https://driftdefense.dev (repo D:\Dev\Projects\drift-defense) —
  v3 live; STALE: says 193 tests (now 293), missing the
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
1. **json_success_rate denominator dilution** — BLOCKS Weather Report #1.
   json_valid is scored only for the 9 structured_output canaries but
   averaged over all 50, so the metric's ceiling is 9/50 = 0.18, not 1.0.
   Board shows 0.175 / 0.178 = ~100% validity on scorable prompts, but
   reads publicly as "17% JSON success". Fix at the display layer
   (normalise by scorable-canary count) or rename the public field.
   Detection is unaffected (a collapse still moves ~18 sigma).
2. **google-leg sample loss** — 11 of 35 post-Neon runs emitted nothing.
   execute_canary_strict discards the whole 50-prompt suite when any
   prompt exhausts retries on the Gemini free tier (correct DP reasoning:
   flushing at reduced n changes sensitivity MAX/n). Failed prompt ids
   differ per run => transient rate-limit, NOT a persistent refusal and
   NOT drift. Post-revert google gets ~1.4 samples/day. Options: raise
   retry budget/pacing, or a documented reduced-n path that recomputes
   DP sensitivity for the actual n.
3. **avg_output_length stream contaminated by the PRIV-011 cutover.**
   The DP constant is not part of the CUSUM stream key and suite_version
   did not change, so 8192-era rows (Laplace scale 81.9, std ~116 chars)
   and 320-era rows (scale 3.2, std ~4.5) share one stream. Board's
   recent_avg_output_length averages the last 10 batches => a blend until
   10 post-merge samples exist. Contained publicly: M=1, required_quorum
   (1)==3, so no single-org candidate can promote. Do NOT cite
   avg_output_length until the stream is 320-era only.
4. PRIV-012: avg_output_tokens has the identical defect class
   (MAX_TOKEN_COUNT 8192 vs max_tokens 64 on the wire, ~128x).
   avg_reasoning_tokens is NOT affected (reasoning budgets uncapped,
   CAN-2 finding) — the constant likely splits in two. Needs a contract.
5. Weather Report #1 — unblocked once (1) is fixed. mistral has 35 clean
   samples; state google's 24/35 coverage honestly; omit
   avg_output_length entirely per (3).
6. Landing (drift-defense repo): 193 -> 293 + baseline-restart line.
7. probe 1.2.0/1.3.0 release (suite v2 + strict runner + CAN-1).
8. Carried Tatiana clicks: formsubmit activation; OPENAI + ANTHROPIC keys
   -> 4 models; OpenSSF anketa; NLnet recheck ~25.09; optional Neon
   password reset (pasted in-session S044).
