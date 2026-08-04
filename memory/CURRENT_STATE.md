# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-08-04 (Session 044: INFRA-1 MERGED (PR #23, e128235) —
# weather board on Neon free Postgres, PERSISTENCE PROVEN (survived a
# manual Render restart with data intact); baseline 193 -> 291 across
# S041-S044 (ENG-1+CAN-2 257, CAN-2a 286, INFRA-1 291); Keystones CAN-1/
# ENG-1/CAN-2/CAN-2a/INFRA-1 ALL SIGNED; cron warm-up 5x/day extended,
# revert by 2026-08-12; v2.0.0 baseline restart date = 2026-08-04).
# Prior (S041-S043, 07-29..08-01, reconstructed in log): ENG-1+CAN-2
# merged PR #20 (suite-scoped streams + suite v2.0.0/50 prompts);
# CAN-2a merged PR #21 (pacing+backoff); METHODOLOGY freeze; backtest
# 3-tuple key fix + "synthetic replay" wording.

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Lead Technical Co-Pilot.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe.
- Branch convention: seismograph/task-{id}.

## Phase
- Phase 0 thesis VALIDATED (38-day lead, synthetic-replay backtest).
  Phases 1-2 core complete; Phase 3 partial. GTM PLAN V2 executing.
- ENG-1 + CAN-2 (S041, MERGED PR #20 @61433b1): suite_version in every
  CUSUM stream key / agreement bucket / persisted row; canary suite
  v2.0.0 = 50 prompts (append-only), execute_canary_strict. 193 -> 257.
  Keystones signed (09dcf3e, 73505b7).
- CAN-2a (S042 addendum, MERGED PR #21 @ba4c1c0): per-leg pacing +
  transient backoff in strict runner; google leg 4500ms. 257 -> 286.
  Keystone signed S044.
- INFRA-1 (S044, MERGED PR #23 @e128235): dialect-aware DatabaseSession
  (REQ-STORE-007) — weather board persists to Neon free Postgres via
  SEISMOGRAPH_DB_URL (Render dashboard env var, render.yaml sync:false);
  pool_pre_ping for non-sqlite; psycopg2-binary in Docker image only.
  286 -> 291. Keystone signed S044. PERSISTENCE PROVEN 2026-08-04:
  board survived a manual Render restart with data intact.
- KNOWN DEFECT (deferred, NEXT ENGINE TASK): PRIV-011 — privacy.py
  MAX_OUTPUT_LENGTH=8192 vs live max_tokens=64 wire cap -> ~32x excess
  DP noise; avg_output_length has never carried signal in production.
  Do NOT cite avg_output_length as working drift evidence until fixed.

## Facts canon (E1, fixed S029; wording upgraded S043 — use ONLY these)
- Incident: Anthropic postmortem 2025-09-17, THREE infra bugs, NOT a model
  update. Backtest models bug #1: context-window routing error, Claude
  Sonnet 4 (NOT 3.5 Sonnet), 0.8% from 2025-08-05, ~16% from 2025-08-29.
- Model tuple: anthropic/claude-sonnet-4@global.
- Detection (SEED=42): first alert 2025-08-10; lead 38 d over postmortem.
- LOCKED PHRASING: "a seeded backtest flags it 38 days before the
  postmortem"; since S043 (ebff22e) prefer "synthetic replay / would-have
  flagged" framing. NEVER "caught ... early" (implies live catch).
- Zenodo: cite concept DOI 10.5281/zenodo.21045517 (resolves to v1.0.1).
- Live board baseline: RE-ESTABLISHED 2026-08-04 (v2.0.0 on Neon) —
  landing must state this; history before that date was lost to free-tier
  restarts (never say the board has continuous history).

## Baseline (re-verify at session start)
- Tests: **291 on MAIN** (INFRA-1 @e128235; was 286/257/193). Host + fresh
  sandbox clone both gated S044. From repo root: py -3.10 -m pytest -q.
- Sandbox full-suite install: opentelemetry-sdk fastapi uvicorn sqlalchemy
  cryptography httpx pytest (+ redis clickhouse-connect). Ruff pinned
  0.15.20, BOTH gates: ruff check . && ruff format --check .
- HARD RULE (S029/S030): after ANY write through the mount, verify via the
  Read tool / git — sandbox mount reads pad NULs and serve stale cache
  (re-confirmed S044 after device_commit_files: byte sizes matched, mount
  read showed old content).
- HARD RULE (S035): NEVER append to an existing memory/log file via
  sandbox heredoc through the mount — build full content in /tmp, write
  via device_commit_files, re-verify NUL-free.
- HARD RULE (S037): bridge can drop mid-session (dropped twice S044);
  after reconnect re-verify writes landed BEFORE committing.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock; if lock:
  Remove-Item .git\index.lock -Force). Fresh GitHub clone in /tmp IS safe.
- Web-UI PR merge via Tatiana's Chrome is OK with her explicit approval
  (S044 precedent: PR #23; new GitHub UI needs the second button
  "Confirm squash and merge").
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.

## Live assets
- Board: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  on **Neon free Postgres** since 2026-08-04 (project seismograph-weather,
  eu-central-1, direct non-pooler DSN; autosuspend 5min is absorbed by
  pool_pre_ping + keep-demo-warm cron). 2 models STABLE: google/
  gemini-3.5-flash-lite + mistral/mistral-small-latest. Cron warm-up
  "17 1,6,11,16,21" UTC — REVERT to "17 5,17" by 2026-08-12 (~30 samples
  by ~10.08). OPENAI/ANTHROPIC legs skip until keys added.
- Landing: https://driftdefense.dev (repo D:\Dev\Projects\drift-defense) —
  v3 live; STALE: says 193 tests, missing baseline-restart-2026-08-04
  line. Brand rule: SEISMOGRAPH = engine, Drift Defense = service.
- Guide: driftdefense.dev/guides/detect-silent-llm-change/ (canonical for
  dev.to -1lia). Analytics: driftdefense.goatcounter.com (lower bound).
- PyPI: seismograph-probe 1.1.0 (OIDC via GitHub Release vX.Y.Z ->
  release.yml). 1.2.0/1.3.0 release warranted (CAN-1/CAN-2 features).
- DOI: https://doi.org/10.5281/zenodo.21045517 (concept).

## Open now (full backlog: project_open_tasks.md)
- PRIV-011 clamp fix (next engine task, full contract).
- probe 1.2.0/1.3.0 release + tool-calling-drift post.
- Landing: 193 -> 291 + baseline-restart line (drift-defense repo).
- Tatiana one-click: formsubmit.co activation email; OPENAI_API_KEY +
  ANTHROPIC_API_KEY secrets (~$5 each) -> 4 models; OpenSSF anketa;
  Dependabot PR #22 (codeql-action bump) merge; NLnet recheck ~25.09.
- Weather Report #1: fill from /v1/weather after ~30 samples (~10.08).
- GTM PLAN V2 (business/GTM_PLAN_V2_S040.md): KPIs by ~23.08 >=5 scans,
  >=1 paid Baseline EUR 2,500, >=20 signups; kill criteria end-Oct;
  Show HN week 3-4 only. Snapshot offensive: Claude targets can start;
  others after ~2wk board baseline (counting from 08-04 now).
- Phase-1/2 engineering PARKED during GTM (calibrated q(M)/TTL from real
  drift_labels; reputation weighting; Ed25519 binding).

## Last sessions (detail in log)
- S044 (2026-08-04): INFRA-1 — Neon cutover, persistence proven; 291;
  all keystones signed; 2FA incident fixed; memory catch-up commit.
- S041-S043 (07-29..08-01): ENG-1+CAN-2 (257), CAN-2a (286), METHODOLOGY
  freeze, backtest key fix + honest wording. Logged retroactively S044.
- S040 (2026-07-24): GTM sprint — CAN-1 merged (193), multi-provider cron,
  landing v3, GTM packs, PLAN V2.
- S039 and earlier: see log/archive.
