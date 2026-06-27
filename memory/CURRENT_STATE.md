# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-06-27 (Session 024)

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Lead Technical Co-Pilot.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe (1.0.0).
- Branch convention: seismograph/task-{id}, never main.

## Phase
- Phase 0 thesis VALIDATED (38-day lead vs Anthropic Aug-Sep 2025 postmortem).
- Phases 1-2 core COMPLETE; Phase 3 partial (multi-tenant + audit-export done).
- Now: post-launch + go-to-market. Full phase ledger in archive.

## Baseline (re-verify at session start)
- Tests: 107 passed. Run from repo root: py -3.10 -m pytest -q
  (NOT from home dir — pytest then scans the whole profile and errors).
- Ruff: 0 violations (check + format). line-length 79, target py311, runtime 3.10.
- Sandbox limits: can WRITE/modify mounted files but CANNOT delete them, and git
  commits leave un-removable .lock files. => deletions + git commits cleanest run
  by Tatiana in PowerShell. Large writes via bash heredoc/python (Edit truncates).

## Live assets
- Dashboard: https://seismograph-weather.onrender.com/dashboard (Render, keep-warm)
- Landing:   https://tania-coder.github.io/drift-defense/ (repo Tania-coder/drift-defense)
- PyPI:      https://pypi.org/project/seismograph-probe/1.0.0/
- Fly.io:    backup prepared (fly.toml), machine not raised.

## Open now (full backlog: project_open_tasks.md)
- Technical: P3-002 Webhooks (sign-off unclear — verify); live fleet -> dashboard
  data check; graph.json empty (populate or retire).
- Infra/security: PyPI 1.0.1 sole-author republish (#11202); GitHub 2FA TOTP before
  2026-07-30; dev.to OAuth.
- Go-to-market: PRIVATE — tracked detail kept out of public files; see
  business/ and job_search/ (gitignored) for outreach, landing, CV.

## Last sessions
- S024 (2026-06-27) tech-debt cleanup: Phase A ruff 15->0, 107 green (302a94c);
  Phase B repo hygiene + .gitignore guards + fly.toml/keystone021 (fe9cc2a);
  Phase C this file + backlog compression. Branch seismograph/task-cleanup-024,
  not yet merged/pushed.
- S023 (2026-06-27): dev.to set up + launch article published.
