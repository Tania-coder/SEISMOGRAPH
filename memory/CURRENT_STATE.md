# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-07-14 (Session 035b: CUSUM POSTED (LI+X), methodology
# outline + Briefing #1 draft done via parallel agents, arch-doc stale
# statuses fixed, posts_dashboard_live.md DEPRECATED, 2nd GitHub email
# added. Timer tasks untouched — next session S036 on the 17.07 reminder.)

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
- Tests: 127 passed (was 122; +5 from SEC-1). From repo root: py -3.10 -m pytest -q.
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
- HARD RULE (S035, write-path counterpart): NEVER append to an EXISTING
  memory/log file via sandbox heredoc — a stale mount cache made a
  heredoc append OVERWRITE the S034 log entry (restored same session
  from in-context copy; git had it too). Appends/edits to existing
  files: host-side Edit tool ONLY. Heredoc remains fine for NEW files.

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
  click-events, JSON-LD. Brand rule: SEISMOGRAPH = engine,
  Drift Defense = service.
- Analytics: https://driftdefense.goatcounter.com (GoatCounter, free
  tier, code driftdefense). Adblockers undercount — lower bound only.
- dev.to:    https://dev.to/taniacoder/your-llm-didnt-get-worse-it-changed-and-nobody-told-you-4ecl
  (reply posted to Void Stitch's comment)
- Show HN:   https://news.ycombinator.com/item?id=48773957 (posted + first comment)
- PyPI:      https://pypi.org/project/seismograph-probe/1.0.0/ (1.0.1 republish pending #11202)
- DOI:       https://doi.org/10.5281/zenodo.21045517 (concept; cite for grant) ->
  currently resolves to v1.0.1 (10.5281/zenodo.21139614), Sonnet-4 wording fixed
- Grant/market pack: docs/ (whitepaper, pitch deck, one-pager, in main).

## Open now (full backlog: project_open_tasks.md)
- SEC-1 arc FULLY CLOSED S034: PR #12 (sanitize/int) + PR #13 (SEC-1b:
  key_sha256 hash-prefix logging, digest over parsed key bytes). CodeQL
  0 Open / 6 Closed visually confirmed on scan #17. 127 passed host & CI.
  Keystone SEC-1 signed (2026-07-12). No SAST debt.
- S036 PLAN (scheduled reminder fires 17.07 09:00):
  1. TIMERS 17.07: check PyPI #11202 for a reply (re-reply SENT 07-12 —
     HARD no-touch until they answer); withdraw Sigge/Martin/Lars
     invites if still Pending (3 clicks, also removes old bad-phrasing
     notes). On ANY acceptance: locked phrasing first message.
  2. CONTENT: Tue 14.07 CUSUM explainer POSTED S035b (URLs in
     open_tasks). Fri 17.07 "Model Weather Briefing #1" — DRAFTED
     S035b (business/content_briefing1_S036.md), refresh [FILL]
     marks from /v1/weather on the morning, then post.
     Live-run post READY incl. screenshot
     (business/portfolio_post_live_run_S034.md + live_run_S034.png),
     slot 22.07, may go early.
  3. HN repost ~21-22.07 Tue/Wed 14-15 UTC if mod still silent (title +
     first comment ready in the pack). Meet it with GoatCounter open.
  4. IF PyPI resolves: new pass + 2FA + recovery codes -> delete temp
     branch lPpHBOqwfdAqYN6j -> republish 1.0.1 -> Trusted Publishing.
  5. Batch 2 outreach (Zendesk AI, Parloa) AFTER 17.07 cleanup; notes
     ready, 2-3/week max.
  6. [DONE S035b] Second GitHub verified email added 2026-07-14.
  7. GoatCounter week-1 review (visitors, CTA clicks, sources).
     [S035 DONE: auto-memory zenodo ref fixed — concept ...517.]
  8. [DONE S035b] Methodology paper outline: docs/
     methodology_paper_outline.md. Next step = DP-noise-ON backtest.
- PyPI #11202: proof sent 2026-07-02 10:46; issue moved to "Verification
  in Process"; gentle ping posted 07-10. If silent ~1 wk, re-reply to the
  verification email. Then: new pass + 2FA + recovery codes -> delete temp
  branch lPpHBOqwfdAqYN6j -> republish 1.0.1 -> Trusted Publishing (OIDC).
- HN item 48773957: first comment still [flagged]. Mod email SENT 07-06
  15:03 (stale 07-06 14:32 draft still to delete). Plan B: "Show HN:"
  repost in 2-3 weeks.
- Outreach: Sebastian (Legora) ACCEPTED 07-03; single light-touch
  follow-up SENT 07-10 15:11 (no reply yet) -- no more messages unless a
  trigger event. Other 6 invites Pending (Sigge/Martin/Lars withdraw
  ~07-17 if silent). On ANY acceptance: first message uses locked
  phrasing. Batch 2 PAUSED.
- Second GitHub verified email ADDED 2026-07-14 (S035b) -- account-loss
  scenario closed.
- Track 1b nice-to-have: real Mistral emission to LOCAL dashboard (API key =
  long no-dash string from console.mistral.ai -> API Keys, NOT org UUID).

## Last sessions
- S035b (2026-07-14): CUSUM explainer POSTED by Tatiana (LI activity
  7482823133020794880; X 2077057793144610885, thread of 2, chart, UTM).
  Parallel subagents (first use): docs/methodology_paper_outline.md
  (STRETCH closed; gap = DP-noise-ON backtest + (h,k) sensitivity) +
  business/content_briefing1_S036.md (Briefing #1 for 17.07, [FILL]
  markers, /v1/weather fields listed; dashboard unreachable via fetch).
  Arch doc fixed vs code (BOCD LIVE, auth.py live post-SEC-1, 4 status
  edits, Tatiana approved). social/posts_dashboard_live.md DEPRECATED
  (pre-canon phrasing hazard). 2nd GitHub email added. No code changes;
  git on Tatiana.
- S035 (2026-07-13, early content sprint): CUSUM explainer post drafted
  (business/content_post_cusum_S035.md, LinkedIn + X) + chart generated
  (chart_cusum_S035.png) from a FRESH SEED=42 backtest run — alert
  2025-08-10 / S-=7.278 / leads 38 & 19 d re-confirmed live; plot
  script asserts the alert date. Canon locked phrasing verbatim, no
  live-catch implication. 2 defects caught+fixed (chart y-scale hid the
  alert; "error rate" -> "JSON success rate"). Auto-memory zenodo ref
  fixed (concept ...517). Noted live_run_S034.png present — live-run
  post fully unblocked. No repo code changes; git untouched by Claude;
  memory commit on Tatiana.
- S034b (2026-07-12, afternoon sprint): driftdefense.dev bought + live
  (HTTPS, www redirect, old URL redirects); landing v2 (client path,
  mid-CTA, 5 CTA events, JSON-LD); GoatCounter analytics live; README->
  landing UTM bridge; marketing pack (HN repost + batch 2 notes +
  2-week content plan, weekly "Model Weather Briefing" anchor; NO paid
  ads until analytics 2wk + HN + 1 organic request); Track 1b DONE —
  3 live Mistral emissions accepted, json_rate converging 0.203->0.291
  (DP averaging demo); portfolio post drafted. dev.to fixed by Tatiana
  (127 + concept DOI, API-verified). PyPI re-reply sent 07-12 (Tatiana
  chose early send) — no-touch rule until reply. hn@ stale draft
  deleted. Scheduled reminder 17.07 09:00 created (one-time).
- S034 (2026-07-12): SEC-1b -- alert #6 closed via key_sha256 hash-prefix
  logging (digest over PARSED key bytes = canonical identity;
  _sanitize_for_log kept for exc branch). SL2 rewritten. Host gate 127
  passed; PR #13 squash-merged (b6388b8). codeql #16 cancelled by
  concurrency (memory push) -- #17 scanned tree incl. fix: 0 Open /
  6 Closed VISUALLY CONFIRMED. Keystone SEC-1 amended (sections 2/4/7)
  and SIGNED. Mount corruption artifact recurred (stale length + NUL
  padding); gate run on clean /tmp copy, host = ground truth. Deferred:
  PyPI + invites to ~07-17; second GitHub email; hn@ draft.
- S033 (2026-07-10): S033 timers sent (PyPI #11202 gentle ping posted;
  Sebastian single light-touch follow-up 15:11) -- both authorized, canon
  respected. dependabot security-only pip policy merged (PR #10); Dependabot
  codeql-action 3->4 bump merged (PR #11), no pip version PRs (correct).
  SEC-1 COMPLETE (PR #12): fixed 5 CodeQL py/log-injection alerts --
  _sanitize_for_log in gateway/auth.py (root cause: bytes.fromhex ignores
  ASCII whitespace -> newline-injected key reached raw log call) + int()
  taint break in engine/audit.py + 5 tests (SL1-SL5). 127 passed host & CI;
  ruff/format green. Post-merge CodeQL: 4 audit.py alerts closed, auth.py
  path re-opened as alert #6 (custom sanitizer unrecognized) -- functionally
  fixed (SL2) but not CodeQL-clean; S034 follow-up. Two CI fails caught +
  fixed (ruff I001 import
  order via --fix; ruff format on audit.py). Keystone written
  (KEYSTONE_REPORT_SEC-1.md, needs signature). Lesson: run the full gate
  (ruff format/check + pytest) on HOST before opening a PR -- sandbox mount
  served truncated reads of freshly-written files this session.
- S032 (2026-07-06): status sweep (PyPI silent; hn@ mod email sent by
  Tatiana 15:03, stale draft left to delete; Sebastian accepted invite
  07-03 but no reply; all 6 invites Pending; HN comment still flagged);
  drift-defense Pages build FIXED — transient Pages infra error on the
  9c1e9fb deploy (build was green, NOT a repo defect); UI re-run stuck
  in queue, fixed via empty commit 3aceaf0 (Tatiana, PowerShell), run #7
  green in 48s; live landing verified showing the dev.to Evidence link.
  No code changes.
- S031 (2026-07-03..06): Sebastian follow-up sent (07-03, authorized);
  invite statuses swept twice -- all 6 Pending, Delphine's note found to
  carry old "caught" wording (4/6 total imprecise, mitigation = correct
  first message); Void Stitch classified as likely bot (disengage); HN
  comment still [flagged], mod email drafted in Gmail (Tatiana to send);
  PyPI silent since 07-02 (ping 07-09/10); GitHub Jul-2 security events
  (2FA/password/new email) confirmed as Tatiana's own -- false alarm;
  found drift-defense Pages build failure on 9c1e9fb. No code changes.
- S030 (2026-07-02/03): CRLF sandbox-mount artifact fully diagnosed and
  closed (not a repo bug); dev.to link added to README + landing (a30a604 /
  9c1e9fb); Zenodo v1.0.1 published with Sonnet-4 wording fix (DOI
  10.5281/zenodo.21139614); dev.to reply posted; Show HN posted (item
  48773957); PyPI #11202 status checked (waiting on support); outreach
  batch 1 sent to 4/5 Tier-A targets (paused for replies per playbook).
  Lesson: locked the "seeded backtest flags... 38 days" phrasing after 3
  connection notes went out with an imprecise "caught... early" variant.
  122 passed.
- S029 (2026-07-02): E1 facts fixed everywhere public (commit 0d9c81d,
  main); private-notes near-leak caught pre-push + gitignored; 29 fixes in
  business/social/job_search; dev.to article PUBLISHED (tags OK); landing
  redesigned hero + facts (fb9018b, verified live); X thread pinned.
  Defects: Edit-tool NUL bytes (x2), form_input vs dev.to tags widget.
  122 passed, both ruff gates.
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           