# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-07-02 (Session 029: E1 facts + dev.to + landing)

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Lead Technical Co-Pilot.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe.
- Branch convention: seismograph/task-{id}.

## Phase
- Phase 0 thesis VALIDATED (38-day lead, backtest). Phases 1-2 core complete;
  Phase 3 partial. Product-realism Tracks 1/1b/2/3 DONE. Narrative arc DONE:
  README + landing + LinkedIn + X (pinned) + dev.to article published.

## Facts canon (E1, fixed S029 — use ONLY these)
- Incident: Anthropic postmortem 2025-09-17, THREE infra bugs, NOT a model
  update (Anthropic explicit). Backtest models bug #1: context-window
  routing error, Claude Sonnet 4 (NOT 3.5 Sonnet), 0.8% from 2025-08-05,
  ~16% from 2025-08-29.
- Model tuple: anthropic/claude-sonnet-4@global.
- Detection (SEED=42): first alert 2025-08-10; lead 38 d over postmortem,
  19 d over escalation. ALWAYS say "reproducible/seeded backtest", never
  imply a live catch. Tests count: 122.
- Zenodo DOI archive still has old wording (immutable) — fixed .zenodo.json
  applies to next version upload.

## Baseline (re-verify at session start)
- Tests: 122 passed. From repo root: py -3.10 -m pytest -q.
- Sandbox runs the FULL suite (install: opentelemetry-sdk fastapi uvicorn
  sqlalchemy cryptography httpx pytest).
- Ruff BOTH gates, pinned: pip install ruff==0.15.20 && ruff check . &&
  ruff format --check . — then pytest. 4 CRLF phantoms trip format-check
  in-sandbox only (LF in git, CI green) — ignore until renormalize.
- NEW HARD RULE (S029): after ANY Edit-tool write through the mount, check
  the file for NUL bytes (Edit appended \x00s twice: mcp.py, landing).
  Prefer bash heredoc for all writes.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock, blocks Tatiana;
  if lock: Remove-Item .git\index.lock -Force).
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- git add -A CAN sweep private notes — 5 files now gitignored; verify
  commit file list before push anyway.

## Live assets
- Dashboard: https://seismograph-weather.onrender.com/dashboard
- Landing:   https://tania-coder.github.io/drift-defense/ (repo clone:
  D:\Dev\Projects\drift-defense)
- dev.to:    https://dev.to/taniacoder/your-llm-didnt-get-worse-it-changed-and-nobody-told-you-4ecl
- PyPI:      https://pypi.org/project/seismograph-probe/1.0.0/
- DOI:       https://doi.org/10.5281/zenodo.21045518 (concept; cite for grant)
- Grant/market pack: docs/ (whitepaper, pitch deck, one-pager, in main).

## Open now (full backlog: project_open_tasks.md)
- PyPI #11202: awaiting support; then new pass + 2FA + recovery codes ->
  delete temp branch lPpHBOqwfdAqYN6j -> republish 1.0.1 sole author.
- CRLF bulk renormalize (deferred S029): on CLEAN tree
  git rm --cached -r . ; git reset --hard (.gitattributes in place).
- Outreach pack ready (business/, fixed facts S029) — Tatiana sends.
- Track 1b nice-to-have: real Mistral emission to LOCAL dashboard (API key =
  long no-dash string from console.mistral.ai -> API Keys, NOT org UUID).
- Zenodo: upload new version to refresh archived description (optional).

## Last sessions
- S029 (2026-07-02): E1 facts fixed everywhere public (commit 0d9c81d,
  main); private-notes near-leak caught pre-push + gitignored; 29 fixes in
  business/social/job_search; dev.to article PUBLISHED (tags OK); landing
  redesigned hero + facts (fb9018b, verified live); X thread pinned.
  Defects: Edit-tool NUL bytes (x2), form_input vs dev.to tags widget.
  122 passed, both ruff gates.
- S028 (2026-07-02): review + security checklist closed; PyPI #11202 reply.
- S027 (2026-06-30): live arc merged to main; first live Mistral probe run.
