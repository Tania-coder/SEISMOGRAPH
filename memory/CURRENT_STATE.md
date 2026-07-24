# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-07-24 (Session 040, GTM sprint: CAN-1 MERGED to main
# (c439105, PR #19) — tool-calling canaries + output/reasoning token metrics,
# baseline 151 -> 193; probe_weather multi-provider cron LIVE, /v1/weather
# shows 2 models STABLE (google/gemini-3.5-flash-lite + mistral/
# mistral-small-latest); landing v3 LIVE (193, trust row/DOI, security §,
# alert-signup form, guide page); CONTRIBUTING.md added; README 134->193.
# Prior (S039, merged+signed same day): FIX-2b analytical quorum
# q(M)=max(3,ceil(M/3)) (be8dc5f squash, c277740 sign); evergreen guide
# published on dev.to; drift-radar daily task live.
# Prior (S038): FIX-2 MERGED (4fdca91), baseline 151, Keystone signed.
# Prior (S036): seismograph-probe 1.1.0 PUBLISHED on PyPI (OIDC).

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
- FIX-2 (S037, MERGED to main S038 @4fdca91): AgreementScorer engine gap
  closed — metric-scoped agreement, per-candidate 14d TTL, population-scaled
  quorum. Keystone signed.
- FIX-2b (S039, MERGED be8dc5f + Keystone SIGNED c277740 same day):
  recalibrated the quorum SLOPE from an FP/power model. Binding constraint
  was POWER, not FP -> q(M)=max(3,ceil(M/3)) (frac_den 2->3), flat q=3 for
  M<=9, knee at M=10. floor=3 kept (Sybil). Supersedes FIX-2 §4.2 scaling.
- CAN-1 (S040, MERGED c439105 via PR #19, Keystone at root UNSIGNED):
  tool-calling canaries (suite v1.1.0 = frozen v1.0.0 + frozen tool-schema
  canary; tool_call_validity_rate) + per-canary output/reasoning token
  metrics (avg_output_tokens / avg_reasoning_tokens, DP-treated, additive
  gateway allowlist). engine/ untouched. 151 -> 193 tests. Caveats: deploy
  gateway before new probes (422 otherwise); new metrics feed live CUSUM but
  are not column-persisted by save_batch / not re-warmed on restart.
  Market driver: agentic workloads (tool-calling drift) + reasoning-token
  shifts (GPT-5.5-type episodes). Probe 1.2.0 release WARRANTED, not done.

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
- Tests: **193 on MAIN** (CAN-1 merged S040 @c439105; was 151). Verified
  S040 on Tatiana host AND independent fresh sandbox clone (193 + ruff x2).
  From repo root: py -3.10 -m pytest -q.
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
- Dashboard: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  NON-EMPTY since S040: google/gemini-3.5-flash-lite + mistral/
  mistral-small-latest, both STABLE, fed by probe_weather cron (2x daily,
  .github/workflows/probe_weather.yml; secrets MISTRAL_API_KEY +
  GEMINI_API_KEY + SEISMOGRAPH_ID_B64; OPENAI/ANTHROPIC legs skip until
  keys added). Gemini note: 2.5-flash closed to new users, 3.5-flash 503s
  on free tier -> pinned gemini-3.5-flash-lite. Google keys now "AQ."-format.
- Landing:   https://driftdefense.dev (Porkbun, auto-renew, exp 2027-07-12;
  repo D:\Dev\Projects\drift-defense) — **landing v3 LIVE (75e5999, S040)**:
  193 tests, backtest-first 38-days card, trust row (DOI/CodeQL/OIDC),
  security-posture §, alert-signup form (formsubmit.co -> GoatCounter event
  cta-alert-signup; ACTIVATION EMAIL pending Tatiana's one click),
  early-observer line, guide links. Brand rule: SEISMOGRAPH = engine,
  Drift Defense = service.
- Guide (owned canonical): https://driftdefense.dev/guides/detect-silent-llm-change/
  (live S040; dev.to article -1lia sets it as canonical_url).
- Analytics: https://driftdefense.goatcounter.com (GoatCounter, free
  tier, code driftdefense). Adblockers undercount — lower bound only.
- dev.to:    https://dev.to/taniacoder/your-llm-didnt-get-worse-it-changed-and-nobody-told-you-4ecl
- dev.to guide (S039, evergreen how-to, PUBLISHED 2026-07-24):
  https://dev.to/taniacoder/did-the-model-get-worse-or-is-it-just-you-how-to-tell-when-an-llm-api-silently-changes-1lia
  (a duplicate "...how-to-actually-tell...-305b" was unpublished to Draft same day)
  (reply posted to Void Stitch's comment)
- Show HN:   https://news.ycombinator.com/item?id=48773957 (posted + first comment)
- PyPI:      https://pypi.org/project/seismograph-probe/ (1.1.0 LIVE, published
  S036 2026-07-18 via Trusted Publishing/OIDC; account Kapibara, 2FA TOTP on;
  releases now = GitHub Release tag vX.Y.Z -> .github/workflows/release.yml)
- DOI:       https://doi.org/10.5281/zenodo.21045517 (concept; cite for grant) ->
  currently resolves to v1.0.1 (10.5281/zenodo.21139614), Sonnet-4 wording fixed
- Grant/market pack: docs/ (whitepaper, pitch deck, one-pager, in main).

## Open now (full backlog: project_open_tasks.md)
- Tatiana one-click: formsubmit.co ACTIVATION email (else landing signups
  are dropped). Sign Keystone CAN-1 §6 when reviewed.
- OpenSSF Best Practices anketa (~1-1.5h; checklist
  business/openssf_badge_checklist_S040.md; CONTRIBUTING.md gap closed S040).
- OPENAI_API_KEY + ANTHROPIC_API_KEY secrets (paid accounts ~$5 each) ->
  board goes to 4 models automatically.
- probe 1.2.0 release (CAN-1 features) + "tool-calling drift monitoring"
  post — next content hook.
- GTM 30-day plan EXECUTING (business/GTM_30DAY_S040.md): >=5 scan requests
  + >=1 paid Baseline €2,500 by ~23.08; 90-day kill criteria end-October.
  Snapshot offensive: targets business/targets_15_S040.md (Claude targets
  can start now; others after ~2 weeks of board baseline). Dist pack
  (GitHub Action + MCP server) in business/dist_S040/ — publish next.
- NLnet: general call CLOSED until ~2026-10-01 (only TALER/Fediversity open
  to 01.08, poor fit). Draft ready business/nlnet_application_draft_S040.md;
  check nlnet.nl/propose ~25.09.
- Model Weather Briefing #1: now UNBLOCKED (board live) — fill from
  /v1/weather after a few days of data.
- PyPI download stats: pypistats 429 (4 sessions) — retry.
- Phase-1/2 engineering PARKED during GTM (calibrated q(M)/TTL from real
  drift_labels; reputation weighting; Ed25519 binding).

## Last sessions
- S040 (2026-07-24, GTM sprint): verified state via fresh clone (caught
  auto-memory lagging a session); market audit (niche confirmed: no rigorous
  public silent-change detector; daily-bench=hobby, Artificial Analysis=
  levels not change); strategy set (NO app; distribution = GitHub Action +
  MCP + alert subscriptions; trust ladder = OpenSSF + design-partner
  testimonials, SOC 2 deferred; 90-day kill criteria). 4 parallel agents:
  CAN-1 engine work (193 tests, adversarial cases pass, independently
  re-gated), dist pack, 15 verified targets + snapshot template, NLnet
  draft. Tatiana merged CAN-1 (PR #19), shipped multi-provider cron
  (4 runs: #1 green mistral-only, #2 google 503 gemini-3.5-flash, #3 404
  gemini-2.5-flash closed-to-new-users, #4 GREEN with gemini-3.5-flash-lite
  — model verified live via /v1beta/models + OpenAI-compat test calls in
  her browser), landing v3 + guide page live (75e5999), CONTRIBUTING.md
  (d0244d7), README 134->193. GEMINI secret added via remote Chrome
  (form_input + JS dispatch of Run-workflow — GitHub dropdown resists
  ref-clicks; details.open=true + button click works). Board: 2 models
  STABLE. GTM docs in business/ (plan, fixpack, targets, template, NLnet,
  OpenSSF checklist, dist_S040/).
- S039 (2026-07-22): FIX-2b — analytical quorum schedule ("Seismo bound").
  #5-analytical route (real-data #5 impossible pre-network). Model (exact
  binomial, scripts/experiment_quorum_bound.py): binding constraint is POWER,
  not FP; shipped ceil(M/2) was mis-motivated (FP 1e-6..1e-12, power eroded).
  Anchored p to LIVE CUSUM (ARL0~500); 14d TTL validated (band [~5d,25.6d]).
  Adversarial verify of the model: SURVIVES-WITH-CAVEATS (correlation can't
  break it at anchored p; residual = estimation-inflated p x rho~0.08 at
  M>=10). Tatiana chose "gentle hedge" -> q(M)=max(3,ceil(M/3)), one constant
  QUORUM_FRAC_DEN 2->3, knee at M=10, flat=3 near-term (no regression <=M9).
  Fixed docstring bug (BOCD "LIVE"->not-wired; CUSUM is live). ruff x2 + 151
  on clean clone. NEW: quorum_seismo_bound.md, KEYSTONE_REPORT_FIX-2b.md
  (unsigned), 2 scripts. git on Tatiana (branch fix-2b to create).
  #6 reach kicked off SAME session: STANDING drift-radar scheduled task
  (trig_01PPnjrGBoCzYD5MDFwAhZYQ, daily 09:00 Berlin) — do NOT recreate.
  Ride-along pack + evergreen guide in business/ (guide published:false,
  pending Tatiana dev.to publish). Live-wave scan: GPT-5.5 episode past-peak,
  no live wave 2026-07-24. /v1/weather board currently EMPTY ([]).
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
