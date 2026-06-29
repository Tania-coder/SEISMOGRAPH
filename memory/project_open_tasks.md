# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Completed-task detail + diffs:
#   memory/archive/completed_tasks_archive.md
# Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-06-27 (Session 024)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## OPEN — Technical
- [x] P3-002 Webhooks & Alerting — VERIFIED & CLOSED (S025, 2026-06-29).
      test_webhooks.py 8/8 green; engine/webhooks.py complete (fail-safe, Bearer
      auth never logged, privacy-safe payload); dispatch gated on private-fleet
      path only (fleet_id not None), never to AgreementScorer / /v1/weather.
      Correlation-first + privacy invariants hold. "Unclear" status was docs lag.
- [ ] Live fleet -> hosted dashboard — confirm fleet writes data and dashboard
      shows live models (localhost:8000 + Render).
- [~] graph.json — generator memory/ast_graph.py written (S025, ruff-clean,
      stdlib-only AST dep-graph builder). Populate by running it on real disk:
      py -3.10 memory/ast_graph.py (sandbox mount corrupts correlation.py, so
      run is Tatiana's). Then commit ast_graph.py + graph.json.

## OPEN — Infra / Security
- [ ] PyPI recovery #11202 -> republish seismograph-probe 1.0.1 as sole author
      (rotate password, recovery codes, API token).
- [ ] GitHub 2FA — add TOTP backup before 2026-07-30 deadline.
- [ ] dev.to OAuth — connect GitHub (Tania-coder) + Twitter (@tatyanti).

## OPEN — Growth (PRIVATE detail in business/ & job_search/, gitignored)
- [ ] Consulting outreach follow-ups + new targets — see business/ (names/sales
      kept out of this tracked/public file).
- [ ] Landing: og-card.png as og:image + Post Inspector refresh.
- [ ] CV + job application flow — see job_search/.
- [ ] Zenodo DOI; HN karma for Show HN repost; second project.

## IN PROGRESS — Session 024 cleanup (branch seismograph/task-cleanup-024)
- [x] Phase A — ruff 15 -> 0, 107 green (302a94c)
- [x] Phase B — repo hygiene, .gitignore guards personal notes, fly.toml +
      keystone021 tracked (fe9cc2a)
- [~] Phase C — CURRENT_STATE.md + backlog compression (this change)

## DEFERRED — Phase 3 future (not started)
- [ ] SSO/RBAC, SOC 2, in-VPC probe option, SLAs / canary-gated rollback,
      first 2-3 hires.

---

## COMPLETED — index (full detail in archive)
Phase 0: P0-001 scaffold | P0-002 canary suite | P0-003 privacy+DP |
  P0-004 ingestion gateway | P0-005 CUSUM + BayesianOnlineDetector (456bc0c) |
  P0-006 backtest (38d lead) | P0-007 architecture doc | P0-008 OTel stub.
Phase 1: P1-001 FastAPI gateway | P1-002 SQLite storage | P1-003 weather API |
  P1-004 dashboard | P1-005 federated quorum | P1-006 e2e demo | P1-007 launch.
Phase 2: P2-001 Ed25519/Sybil | P2-002 ClickHouse | P2-003 Redis state |
  P2-004 DP composition | P2-005 OTel/MCP adapters | P2-006 containerization.
Phase 3: P3-001 multi-tenant isolation | P3-004-C audit-export auth.
Growth/launch: PyPI packaging | first-party fleet | landing+routes |
  repo migration to Tania-coder | social launch (LinkedIn/X/dev.to) |
  provider ToS reviews (5/5).
