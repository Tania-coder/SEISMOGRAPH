# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-07-19 (Session 037: FIX-2 SHIPPED on branch
# seismograph/task-fix-2 (b5c8621, pushed, host gate 151 green) — engine
# candidate TTL + metric-scoped, population-scaled quorum q(M)=max(3,ceil(M/2)).
# Awaiting PR review + squash-merge to main + Keystone signature. Landing
# "127 tests" note was STALE — live site already shows 134.
# Prior (S036): PyPI #11202 CLOSED, seismograph-probe 1.1.0 PUBLISHED (OIDC).)

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
- FIX-2 (S037): AgreementScorer engine gap closed on branch
  seismograph/task-fix-2 — awaiting PR merge to main.

## Facts canon (E1, fixed S029 — use ONLY these)
- Incident: Anthropic postmortem 2025-09-17, THREE infra bugs, NOT a model
  update (Anthropic explicit). Backtest models bug #1: context-window
  routing error, Claude Sonnet 4 (NOT 3.5 Sonnet), 0.8% from 2025-08-05,
  ~16% from 2025-08-29.
- Model tuple: anthropic/claude-sonnet-4@global.
- Detection (SEED=42): first alert 2025-08-10; lead 38 d over postmortem,
  19 d over escalation. ALWAYS say "reproducible/seeded backtest", never
  imply a live catch. Tests count: 122.
- LOCKED PHRASING (S030, Tatiana caught it mutating in LinkedIn notes): the
  ONLY approved short form is "a seeded backtest flags it 38 days before the
  postmortem" (or equivalent explicit "backtest/flags" wording). NEVER
  compress to "caught ... 38 days early" or "caught ... before the
  postmortem" -- even though it reads punchier, it implies a live catch and
  is false. This applies everywhere, including char-limited contexts like
  LinkedIn connection notes (300 char) -- trim other words, not this one.
- Zenodo DOI archive: v1.0.1 published S030 (DOI 10.5281/zenodo.21139614,
  concept DOI unchanged 10.5281/zenodo.21045517) with corrected "Claude
  Sonnet 4" wording. v1.0.0 record itself stays immutable/stale, but the
  concept DOI now resolves to the fixed version.

## Baseline (re-verify at session start)
- Tests: 134 on MAIN; 151 on seismograph/task-fix-2 (+17 from FIX-2).
  After the FIX-2 PR merges, main = 151. From repo root: py -3.10 -m pytest -q.
- Sandbox runs the FULL suite (install: opentelemetry-sdk fastapi uvicorn
  sqlalchemy cryptography httpx pytest).
- Ruff BOTH gates, pinned: pip install ruff==0.15.20 && ruff check . &&
  ruff format --check . — then pytest. (S030-era in-sandbox trailing-NUL
  ruff artifact on 4 files was a mount READ artifact, not a repo defect;
  host + CI are ground truth. S037 clean-clone + host both fully green.)
- HARD RULE (S029, refined S030): after ANY write through the mount
  (Edit tool OR bash/python heredoc), don't trust sandbox reads (cat/wc/
  grep/ruff) to check for corruption -- the sandbox mount itself pads
  trailing NUL bytes on read for recently-touched files. ALWAYS verify via
  the Read tool (host path) or `git cat-file -p HEAD:<path>` -- ground truth.
- HARD RULE (S035, write-path counterpart): NEVER append to an EXISTING
  memory/log file via sandbox heredoc through the mount -- a stale mount
  cache once made a heredoc append OVERWRITE the S034 log entry. Appends to
  existing files: build the full new content in /tmp (clean) then write via
  device_commit_files (a clean host overwrite), and re-verify NUL-free.
- HARD RULE (S037): the desktop bridge can drop mid-session; device_commit_files
  during the outage fails and files never reach disk. Symptom: host gate shows
  the OLD test count + `git add` "pathspec did not match" for new files. After
  any reconnect, re-run device_commit_files and confirm the host gate shows the
  NEW count BEFORE committing.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock, blocks Tatiana;
  if lock: Remove-Item .git\index.lock -Force).
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- git add -A CAN sweep private notes — 5 files now gitignored; verify
  commit file list before push anyway.

## Live assets
- Dashboard: https://seismograph-weather.onrender.com/dashboard
- Landing:   https://driftdefense.dev (custom domain S034, Porkbun,
  auto-renew, exp 2027-07-12; old github.io URL redirects; repo clone:
  D:\Dev\Projects\drift-defense) — landing v2: client path, 5 CTA
  click-events, JSON-LD. Shows "134 tests" (verified live S037). Brand rule:
  SEISMOGRAPH = engine, Drift Defense = service.
- Analytics: https://driftdefense.goatcounter.com (GoatCounter, free
  tier, code driftdefense). Adblockers undercount — lower bound only.
- dev.to:    https://dev.to/taniacoder/your-llm-didnt-get-worse-it-changed-and-nobody-told-you-4ecl
  (reply posted to Void Stitch's comment)
- Show HN:   https://news.ycombinator.com/item?id=48773957 (posted + first comment)
- PyPI:      https://pypi.org/project/seismograph-probe/ (1.1.0 LIVE, published
  S036 2026-07-18 via Trusted Publishing/OIDC; account Kapibara, 2FA TOTP on;
  releases now = GitHub Release tag vX.Y.Z -> .github/workflows/release.yml)
- DOI:       https://doi.org/10.5281/zenodo.21045517 (concept; cite for grant) ->
  currently resolves to v1.0.1 (10.5281/zenodo.21139614), Sonnet-4 wording fixed
- Grant/market pack: docs/ (whitepaper, pitch deck, one-pager, in main).

## Open now (full backlog: project_open_tasks.md)
- [S037 SHIPPED, awaiting merge] FIX-2 on branch seismograph/task-fix-2
  (b5c8621): G1 metric-scoped agreement + G2 per-candidate 14d TTL (both
  scorers) + G3 population-scaled quorum q(M)=max(3,ceil(M/2)). Host gate
  151 green. NEXT: review + squash-merge to main; sign §6 of
  KEYSTONE_REPORT_FIX-2.md; then update this baseline to 151.
  Synthetic/EXP-2-backed defaults; Phase-1 calibrated q(M) table + TTL from
  real drift_labels still pending (data/drift_labels/quorum_fix2_calibration.md).
- Landing "127 tests" -> RESOLVED S037 (live already 134; note was stale).
- Invites Sigge/Martin/Lars: withdraw if still Pending (LinkedIn).
- GoatCounter week-1 review (visitors, CTA clicks, sources).
- Model Weather Briefing #1: business/content_briefing1_S036.md [FILL] marks
  need /v1/weather numbers (dashboard /v1/weather robots-blocked to WebFetch
  and curl policy-blocked -> pull via browser or Tatiana reads).
- HN "Show HN:" repost ~21-22.07 if mod still silent (pack ready).
- Outreach: Sebastian (Legora) ACCEPTED 07-03, single follow-up sent 07-10
  (no reply); no more messages unless a trigger event. Batch 2 (Zendesk AI,
  Parloa) PAUSED until 07-17 cleanup done.

## Last sessions
- S037 (2026-07-19): FIX-2 SHIPPED. Read engine cold; framed Stage-1
  contract for 3 gaps (metric-blind quorum, no candidate TTL, fixed q that
  degrades with M — EXP-2: M=5/q=2 FP 0.86). Tatiana: do all three, q(M)+TTL
  delegated. Implemented q(M)=max(3,ceil(M/2)) over live observer population
  M + per-candidate 14d TTL + (model_tuple, metric_name) scoping, in BOTH the
  in-process AgreementScorer and the Redis backend (rewritten to per-stream
  ZSETs + two-key atomic Lua; ns->ms because ZSET/Lua doubles cap at 2^53).
  Gateway now observe()s population per metric. +14 new scorer tests
  (metric scoping, TTL expiry, q(M) scaling, Sybil resistance, semantic-only
  promote) + 2-orgs-below-floor regression. Clean-clone gate + HOST gate both
  151 passed, ruff x2 clean. Committed b5c8621, pushed to
  seismograph/task-fix-2. KEYSTONE_REPORT_FIX-2.md drafted (unsigned) +
  data/drift_labels/quorum_fix2_calibration.md. Bridge dropped mid-commit
  once (files didn't land -> host showed 134 + empty branch); fixed on
  reconnect. Landing "127->134" found already-live. git on Tatiana.
- S036 (2026-07-18): PyPI saga CLOSED. Account Kapibara recovery finished
  (pwd reset, 2FA TOTP, 7 recovery codes). Deleted temp branch
  lPpHBOqwfdAqYN6j. PyPI Trusted Publishing (OIDC): publisher
  Tania-coder/SEISMOGRAPH -> release.yml, env pypi. Added
  .github/workflows/release.yml. Bumped pyproject_probe.toml 1.0.0->1.1.0,
  CHANGELOG 1.1.0. Commit df4b900; GitHub Release v1.1.0 -> workflow Success
  -> seismograph-probe 1.1.0 LIVE on PyPI, zero tokens. Verify-pass: 134
  tests + ruff both gates on a clean GitHub clone. git on Tatiana.
- S035c (2026-07-15): paper evidence sprint, 5 subagents. EXP-1 falsified
  zero-FP + old DP bounds. FIX-1 REQ-PRIV-010 (delta_f=MAX/n, +7 tests =134):
  EXP-1R recovers canon under DP noise. EXP-2 (real AgreementScorer):
  M=3/q=3+TTL14d -> public FP 0.015 @36d; ENGINE GAP: no candidate TTL, q=2
  degrades with M (M=5 FP 0.86) -> FIX-2 (now shipped S037). PR #14 merged
  (90fda54), Keystones EXP-1 + PRIV-010 signed, README 134.
- S035b (2026-07-14): CUSUM explainer POSTED by Tatiana (LI + X). Parallel
  subagents: methodology_paper_outline.md + content_briefing1_S036.md.
  Arch doc fixed vs code. 2nd GitHub email added. No code changes.
- S034b (2026-07-12 pm): driftdefense.dev bought + live; landing v2;
  GoatCounter live; marketing pack; Track 1b DONE (3 live Mistral emissions).
- S034 (2026-07-12): SEC-1b closed (PR #13 b6388b8); CodeQL 0 Open/6 Closed;
  Keystone SEC-1 SIGNED. 127 passed.
- S029-S033: E1 canon fix, dev.to publish, Show HN, Zenodo v1.0.1, outreach
  batch 1, drift-defense Pages fix, GitHub infra hardening, SEC-1 log-injection
  fix (->127). See log/archive.
