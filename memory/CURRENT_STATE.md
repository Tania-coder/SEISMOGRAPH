# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-07-02 (Session 030: dev.to follow-up + Zenodo 1.0.1 + CRLF closed)

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
- Zenodo DOI archive: v1.0.1 published S030 (DOI 10.5281/zenodo.21139614,
  concept DOI unchanged 10.5281/zenodo.21045517) with corrected "Claude
  Sonnet 4" wording. v1.0.0 record itself stays immutable/stale, but the
  concept DOI now resolves to the fixed version.

## Baseline (re-verify at session start)
- Tests: 122 passed. From repo root: py -3.10 -m pytest -q.
- Sandbox runs the FULL suite (install: opentelemetry-sdk fastapi uvicorn
  sqlalchemy cryptography httpx pytest).
- Ruff BOTH gates, pinned: pip install ruff==0.15.20 && ruff check . &&
  ruff format --check . — then pytest. 4 files (correlation.py,
  gateway/main.py, first_party_fleet.py, test_privacy.py) trip ruff
  in-sandbox only. CONFIRMED S030: this is a sandbox-mount READ artifact
  (extra trailing NUL bytes), not a repo defect — host file and git blob
  are byte-identical and correct (verified via Read tool + git cat-file).
  pytest is unaffected (122 passed). Ignore permanently; CI is ground truth.
- HARD RULE (S029, refined S030): after ANY write through the mount
  (Edit tool OR bash/python heredoc), don't trust sandbox reads (cat/wc/
  grep/ruff) to check for corruption -- the sandbox mount itself pads
  trailing NUL bytes on read for recently-touched files (confirmed S030
  on README.md, drift-defense/index.html, project_open_tasks.md; none
  were actually corrupted on the real host disk). ALWAYS verify via the
  Read tool (host path) or `git cat-file -p HEAD:<path>` -- those are
  ground truth. Prefer bash heredoc for writes (still fewer surprises),
  but the verification step is the part that actually matters.

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
  (1 comment awaiting reply -- draft in social/S030_dev_to_reply_and_show_hn.md)
- PyPI:      https://pypi.org/project/seismograph-probe/1.0.0/ (1.0.1 republish pending #11202)
- DOI:       https://doi.org/10.5281/zenodo.21045517 (concept; cite for grant) ->
  currently resolves to v1.0.1 (10.5281/zenodo.21139614), Sonnet-4 wording fixed
- Grant/market pack: docs/ (whitepaper, pitch deck, one-pager, in main).

## Open now (full backlog: project_open_tasks.md)
- PyPI #11202: awaiting support reply (Tatiana already replied 2026-07-02
  10:46 with pushed-branch proof); then new pass + 2FA + recovery codes ->
  delete temp branch lPpHBOqwfdAqYN6j -> republish 1.0.1 sole author.
- dev.to: post the drafted reply to Void Stitch's comment (Tatiana, manual;
  draft in social/S030_dev_to_reply_and_show_hn.md).
- Show HN: post the drafted title + first comment, AM US time (Tatiana,
  manual; same file).
- Outreach pack ready (business/, fixed facts S029) — Tatiana sends.
- Track 1b nice-to-have: real Mistral emission to LOCAL dashboard (API key =
  long no-dash string from console.mistral.ai -> API Keys, NOT org UUID).

## Last sessions
- S030 (2026-07-02): CRLF sandbox-mount artifact fully diagnosed and closed
  (not a repo bug); dev.to link added to README + landing (a30a604 /
  9c1e9fb); dev.to reply + Show HN drafts written; PyPI #11202 status
  checked (waiting on support); Zenodo v1.0.1 published with Sonnet-4
  wording fix (DOI 10.5281/zenodo.21139614). 122 passed.
- S029 (2026-07-02): E1 facts fixed everywhere public (commit 0d9c81d,
  main); private-notes near-leak caught pre-push + gitignored; 29 fixes in
  business/social/job_search; dev.to article PUBLISHED (tags OK); landing
  redesigned hero + facts (fb9018b, verified live); X thread pinned.
  Defects: Edit-tool NUL bytes (x2), form_input vs dev.to tags widget.
  122 passed, both ruff gates.
- S028 (2026-07-02): review + security checklist closed; PyPI #11202 reply.
- S027 (2026-06-30): live arc merged to main; first live Mistral probe run.
