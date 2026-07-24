# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-22 (Session 039: FIX-2b analytical quorum schedule
# authored — q(M)=max(3,ceil(M/3)), QUORUM_FRAC_DEN 2->3; 151 pass on clean
# clone; Keystone FIX-2b UNSIGNED; awaiting Tatiana branch/host-gate/merge)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## S039 — 2026-07-22 (FIX-2b: analytical quorum schedule, the "Seismo bound")
- [~] FIX-2b AUTHORED on a clean clone (base 2fc6108); NOT yet on a branch/
      merged. Replaces FIX-2 synthetic frac=1/2 with a model-derived schedule.
  - [x] Finding: binding constraint is detection POWER (false negatives), NOT
        FP. Shipped ceil(M/2) suppressed FP 1e-6..1e-12 while eroding power
        (majority rule unreachable under sparse canary coverage).
  - [x] q(M)=max(3, ceil(M/3)) — ONE constant: engine/correlation.py
        QUORUM_FRAC_DEN 2->3 (flows to Redis Lua too). Flat q=3 for M<=9
        (= near-term optimum + old policy, no regression), gentle knee at M=10.
  - [x] p anchored to LIVE detector (CUSUM ARL0~=500; gateway wires CUSUM).
        14d TTL validated analytically (band [~5d, 25.6d] at 1/day cadence).
  - [x] Adversarial verify of the MODEL: SURVIVES-WITH-CAVEATS. Pure
        correlation can't break it at anchored p; residual = estimation-
        inflated p (~0.074) x rho~0.08 at M>=10, which ceil(M/3) hedges
        (worst-case FP 0.036/0.046/0.032). floor=3 kept for Sybil, not FP.
  - [x] Fixed repo doc bug: correlation.py BOCD "(LIVE)" -> "(IMPLEMENTED,
        not wired)"; CUSUM is the live candidate generator.
  - [x] Gate: ruff x2 clean + 151 pass on clean clone (count unchanged).
        NEW: data/drift_labels/quorum_seismo_bound.md, KEYSTONE_REPORT_FIX-2b.md
        (UNSIGNED), scripts/experiment_quorum_bound.py + quorum_seismo_pick.py.
- [ ] TATIANA (S039 close): create branch seismograph/task-fix-2b, host gate
      (ruff x2 + 151), squash-merge, SIGN Keystone FIX-2b §6, bump memory.
- [~] #6 distribution/reach STARTED (same session): approach = incident
      ride-along. STANDING drift-radar scheduled task created
      (trig_01PPnjrGBoCzYD5MDFwAhZYQ, daily 09:00 Berlin, push on) — surfaces
      live waves + drafts; NEVER recreate it. Pack + templates:
      business/reach_incident_ridealong_S039.md. Evergreen guide drafted
      business/content_evergreen_guide_S039.md (published:false -> Tatiana to
      publish on dev.to). Live-wave scan 2026-07-24: none live (GPT-5.5 past
      peak). NEXT: optional HTML guide for driftdefense.dev; #5-empirical still
      needs orgs -> real drift_labels.


## S037 — 2026-07-19 (FIX-2: engine candidate TTL + metric-scoped, scaled quorum)
- [x] FIX-2 SHIPPED on branch seismograph/task-fix-2 (commit b5c8621,
      pushed; host gate 151 passed, ruff x2 clean). Closes the EXP-2 engine
      gap in the ENGINE (not the harness):
  - [x] G1: ChangePointResult += metric_name + timestamp_ns; agreement now
        per (model_tuple, metric_name) in both scorers.
  - [x] G2: per-candidate 14d TTL — window (now-ttl, now]. In-process dict
        of {org: latest_ts}; Redis rewritten to per-stream ZSETs scored by
        event-time (ms, since ns exceeds IEEE-754 double precision).
  - [x] G3: population-scaled quorum q(M)=max(3, ceil(M/2)) over the live
        observer population M (new observe() on the gateway public path).
        floor=3, frac=1/2 configurable; SYNTHETIC EXP-2-backed defaults.
  - [x] +14 new tests (tests/test_agreement_scorer.py) — metric scoping,
        TTL expiry, q(M) scaling, Sybil resistance, semantic-only-promote;
        + test_two_orgs_below_floor_stay_stable regression; Redis tests
        rewritten to ZSET/Lua wiring. 134 -> 151.
  - [x] data/drift_labels/quorum_fix2_calibration.md (synthetic defaults +
        EXP-2 provenance); KEYSTONE_REPORT_FIX-2.md (unsigned).
- [x] FIX-2 PR (S038): squash-merged seismograph/task-fix-2 -> main (4fdca91);
      §6 of KEYSTONE_REPORT_FIX-2.md SIGNED; main baseline bumped to 151.
      Independent clean-clone re-verify pre-merge (ruff x2 + 151), conflict-free.
- [~] Phase-1 FIX-2 follow-up: ANALYTICAL q(M)+TTL DONE in FIX-2b (S039,
      awaiting merge). REMAINS (Phase-2, needs real traffic): measure p and
      rho from live probes -> recalibrate; Sybil residual mitigations
      (reputation weighting + Ed25519 binding).
- [x] Landing driftdefense.dev "127 tests" -> RESOLVED: live already shows
      134 (S036 note was stale; no action needed).
- [ ] Deferred (carried): invites Sigge/Martin/Lars if Pending; GoatCounter
      week-1 review; Model Weather Briefing #1 [FILL] /v1/weather refresh;
      HN "Show HN:" repost ~21-22.07 if mod silent.


## S036 — 2026-07-18 (PyPI recovery + first Trusted-Publishing release)
- [x] PyPI #11202 CLOSED: account Kapibara recovered (pwd reset + 2FA TOTP
      + 7 recovery codes). Full access verified (project manageable).
- [x] Temp branch lPpHBOqwfdAqYN6j DELETED (was the #11202 proof branch).
- [x] PyPI Trusted Publishing (OIDC) configured: publisher
      Tania-coder/SEISMOGRAPH -> release.yml, env pypi.
- [x] .github/workflows/release.yml added (build swap + hatchling +
      twine check -> gh-action-pypi-publish via id-token write).
- [x] seismograph-probe 1.1.0 PUBLISHED (commit df4b900; GitHub Release
      v1.1.0 -> workflow Success 40s). providers.py feature + REQ-PRIV-010.
- [x] Baseline 134 + ruff both gates re-verified on a clean GitHub clone.
- [ ] Landing driftdefense.dev "127 tests" -> 134 (separate drift-defense
      repo; one-line index.html fix, PowerShell replace ready).
- [ ] Invites Sigge/Martin/Lars: withdraw if still Pending (deferred).
- [ ] GoatCounter week-1 review (deferred).
- [ ] Model Weather Briefing #1: [FILL] needs /v1/weather numbers (deferred).
- [ ] FIX-2 engine decision (candidate TTL + quorum scaling) — pending.

## S035c — 2026-07-15 (interim, paper evidence sprint)
- [x] EXP-1 (3 parallel agents): DP-ON backtest + (h,k,baseline,sigma)
      grid (180 cfg) + stable-FP. FALSIFIED: zero-FP claim (0.400/90d
      single obs) and old DP bounds (detection 62.5% vs null 56.5%).
      Default (5.0,0.5,30) confirmed: 2025-08-10 / 38d.
- [x] FIX-1 REQ-PRIV-010: delta_f=MAX/n in probe/privacy.py + 7 tests
      (134 total). EXP-1R: 100% detection at n>=100; median alert
      2025-08-10 at n=200 — canon 38d recovered under DP noise.
- [x] EXP-2 quorum sim (real AgreementScorer): M=3/q=3+TTL14d ->
      FP 0.015 at 36d lead. Invariant held (burst/Sybil-alone never
      promote). Design gap: NO candidate expiry in engine; fixed q=2
      degrades with network size (M=5/q=2 FP 0.86).
- [x] Outline updated (secs 4.2/5/6/7/8/10); Keystones EXP-1 +
      PRIV-010 drafted.
- [x] TATIANA: host gate 134 passed -> PR #14 squash-merged (90fda54)
      -> Keystones SIGNED + README 134 (4057b33) -> branches cleaned
      (incl. stale task-E1/task-infra-1; lPpHBOqwfdAqYN6j kept).
      CI 4/4 green on 4057b33.
- [ ] DECISION (Tatiana): FIX-2 candidate — engine-side candidate TTL +
      quorum scaling (+ metric name in ChangePointResult) in
      AgreementScorer. Threshold decision needs drift_labels datum
      per Seismo bound. Blocks nothing for the paper (TTL documented
      as harness-enforced), but is the right engine fix.

## DO NEXT — S036 (reminder fires 17.07 09:00)
- [ ] 17.07: PyPI reply check (NO touches) + withdraw Sigge/Martin/Lars
      if Pending. On acceptance: locked phrasing.
- [x] TATIANA 14.07: CUSUM explainer POSTED 2026-07-14 (LinkedIn + X
      thread of 2, chart attached, UTM linkedin/post):
      LI: linkedin.com/feed/update/urn:li:activity:7482823133020794880
      X:  x.com/tatyanti/status/2077057793144610885
- [x] 14.07 interim (Claude): methodology paper outline DONE
      (docs/methodology_paper_outline.md, was STRETCH); Briefing #1
      drafted (business/content_briefing1_S036.md, [FILL 17.07] marks);
      arch doc stale rows fixed (BOCD live, auth.py live — verified vs
      code); social/posts_dashboard_live.md marked DEPRECATED (pre-canon
      phrasing).
- [ ] 17.07: Model Weather Briefing #1; live-run post READY too
      (screenshot live_run_S034.png exists; slot 22.07, may go early).
- [ ] HN repost ~21-22.07 if mod silent (pack ready).
- [ ] If PyPI resolves: recovery chain -> republish 1.0.1 -> OIDC.
- [ ] Batch 2 (Zendesk AI, Parloa) after 17.07 cleanup.
- [x] Second GitHub verified email — DONE 2026-07-14 (S035b).
- [ ] GoatCounter week-1 review (17.07, week completes).
- [ ] STRETCH: methodology paper outline.

## ARCHIVE — S035 items (2026-07-13, early content sprint)
- [x] CUSUM explainer drafted + chart generated from fresh SEED=42
      backtest run (alert 2025-08-10 re-confirmed). 2 defects caught
      (chart scale hid alert; "error rate" -> "JSON success rate").
- [x] Auto-memory zenodo ref FIXED (concept = ...21045517; ...518
      marked stale version DOI). Closes the S034 addendum follow-up.

## ARCHIVE — S034 items (all closed)
- [x] SEC-1b (alert #6) CLOSED S034: PR #13 squash-merged (b6388b8).
      gateway/auth.py InvalidSignature branch logs
      sha256(pub_bytes).hexdigest()[:12] (key_sha256=..., digest over
      PARSED key bytes = canonical identity). _sanitize_for_log kept for
      exc branch (SL3). SL2 rewritten. Host gate: ruff x2 + 127 passed.
      Post-merge CodeQL scan #17 (5218f50) VISUALLY CONFIRMED:
      0 Open / 6 Closed -- SAST fully clean. (codeql #16 on the merge
      commit was cancelled by concurrency when the memory push landed;
      #17 scanned the tree incl. the fix -- expected behavior.)
- [ ] KEYSTONE_REPORT_SEC-1.md fully amended (sections 2/4/7, dated
      07-12). REMAINS ONLY: Tatiana signature (section 5).
- [ ] (DONE 07-10) memory/* S033 + Keystone committed to main (0433f44);
      this correction commit pending.
- [~] PyPI #11202: re-reply to verification email SENT 07-12 09:01
      (Tatiana chose to send ahead of the ~07-17 plan). HARD RULE now:
      NO further touches (no emails, no issue pings) until they respond.
      If total silence persists, next escalation ~end of July via
      admin@pypi.org (different channel), not another follow-up.
      On resolution: new pass + 2FA + recovery codes -> delete temp
      branch lPpHBOqwfdAqYN6j -> republish 1.0.1 -> Trusted Publishing.
- [ ] Sebastian (Legora): single follow-up SENT 07-10. Do NOT message
      again unless a trigger event (provider incident / Legora news / his
      post) makes it relevant.
- [ ] Sigge/Martin/Lars invites: if still Pending ~07-17, withdraw. On ANY
      acceptance, first message uses locked phrasing (their notes carry
      old "caught" wording).
- [ ] HN 48773957: waiting on mod reply to the 07-06 email. Else proper
      "Show HN:" repost in 2-3 weeks.
- [x] Stale hn@ Gmail draft DELETED (verified S034: drafts search for
      to:hn@ycombinator.com returns zero).
- [x] DOI discrepancy RESOLVED S034 addendum: verified live --
      ...21045517 = concept DOI (resolves to latest v1.0.1/21139614);
      ...21045518 = v1.0.0 VERSION DOI (stale record, old wording).
      Fixed to concept DOI in README (badge + docs line + bibtex ->
      v1.0.1), SECURITY.md, ROADMAP.md, CITATION.cff (doi: added,
      version 1.0.1). NOTE: auto-memory reference_zenodo_doi.md says
      concept = ...518 -- WRONG, fix next session. Session-log line
      S026 "concept DOI ...518 minted" was the original error
      (append-only, stands corrected here).
- [ ] TATIANA: dev.to article -- 2 edits in the editor (122 tests ->
      127; footer DOI ...21045518 -> ...21045517 x2). Instructions
      given S034.
- [x] drift-defense landing "122 tests" -> 127 FIXED S034 addendum
      (folder mounted mid-session; single occurrence in index.html;
      no DOI references on the landing).
- [x] (S034 addendum) LICENSE added (052918d): GitHub now detects
      Apache-2.0 (was Other/NOASSERTION -- no LICENSE file existed).
      README refreshed: 127 tests, CodeQL line, roadmap rows 2/3.

## DONE S033 (detail in log)
- [~] SEC-1: PR #12 squash-merged; 127 passed host & CI, ruff/format
      green. Post-merge CodeQL: 4 audit.py alerts CLOSED (int() barrier),
      but auth.py path re-opened as alert #6 (custom sanitizer not
      recognized). Functionally fixed (SL2 proves it) but not CodeQL-clean
      -- see DO NEXT follow-up. Keystone written (needs #6 amendment +
      signature).
- [x] dependabot.yml security-only pip policy merged (PR #10, squash).
- [x] Dependabot codeql-action 3->4 bump merged (PR #11); no pip version
      PRs opened under the new policy (correct behavior).
- [x] PyPI #11202 gentle ping posted in issue (07-10).
- [x] Sebastian single light-touch follow-up sent (LinkedIn, 07-10 15:11).

## DONE S031 -> S032 (history)
- [x] drift-defense Pages build FIXED S032: transient GitHub Pages infra
      error on 9c1e9fb deploy (build was green), NOT a repo defect. Fixed
      via empty commit 3aceaf0 -> run #7 green. Live landing verified.
- [x] hn@ycombinator.com mod email SENT by Tatiana 07-06 15:03.
- [x] GitHub infra hardening S032: ruleset protect-main ACTIVE (no
      force-push/delete); PR #1 (workflow permissions contents:read +
      dependabot.yml); PR #9 (CodeQL SAST py+js, security-extended,
      weekly); Dependabot actions bumps #2/#3 merged, floor bumps #4-#8
      closed by library policy.

## OPEN — Admin / Security (deadline)
- [x] GitHub 2FA TOTP — DONE 2026-07-02.
- [~] PyPI recovery #11202 IN PROGRESS: proof sent 2026-07-02 10:46; issue
      moved to "Verification in Process"; gentle ping posted 07-10. If
      silent ~1 week, re-reply to the verification email. Then: new pass +
      2FA + recovery codes -> delete temp branch lPpHBOqwfdAqYN6j ->
      republish 1.0.1 -> Trusted Publishing (OIDC).
- [x] Add a second verified email on GitHub — DONE 2026-07-14 (S035b;
      closed the account-loss scenario that hit PyPI).

## OPEN — Hygiene
- [x] Bulk CRLF renormalize — DONE S030 (sandbox-mount read artifact, not
      a repo defect; ignore permanently, CI is ground truth).

## OPEN — Growth (PRIVATE detail in business/, gitignored)
- [~] Outreach batch 1 (2026-07-03): 6 invites still Pending as of S034
      (07-12, verified in Invitation Manager)
      (Jose/Joel/Delphine; Sigge/Martin/Lars). Sebastian ACCEPTED 07-03,
      single follow-up sent 07-10 (no reply yet). PAUSED per playbook;
      batch 2 (Ultimate/Zendesk AI, Parloa; then Tier B) waits for replies.
      LESSON LOCKED: notes say "a seeded backtest flags it 38 days before
      the postmortem" — never "caught ... early".
- [x] Void Stitch triage (S031): likely bot — disengage.
- [x] Zenodo v1.0.1 published S030 (DOI 10.5281/zenodo.21139614).

## NICE-TO-HAVE
- [x] Track 1b DONE S034 (afternoon sprint): 3 live emissions
      mistral/mistral-small-latest -> local gateway, all accepted
      (Ed25519 key d0d81dfe86d9..., batches 420d6f59/bd1e2a3a/f3ebca96).
      Rolling json_rate converged 0.203 -> 0.252 -> 0.291 (DP noise
      averaging as designed). New Mistral key seismograph-probe-local in
      business/mistral_key.txt (gitignored); OLD key untouched (Render).

## DONE S034 afternoon sprint (marketing/infra)
- [x] Landing v2 LIVE on https://driftdefense.dev (8f2a07c + 9b6b055):
      topbar CTA, client-path section, mid-CTA, mailto mini-form,
      JSON-LD, canonical on new domain. Enforce HTTPS ON.
- [x] Domain driftdefense.dev bought (Porkbun, ~$8.75/yr, WHOIS privacy,
      auto-renew, exp 2027-07-12). DNS: 4xA GitHub Pages IPs + CNAME www.
      Strategy: SEISMOGRAPH = engine brand, Drift Defense = service brand.
- [x] GoatCounter analytics LIVE (driftdefense.goatcounter.com, email
      verified, site domain set): pageviews + 5 CTA click events
      (cta-topbar/hero/baseline/mid/final). Tatiana's ABP blocks own
      visits -- stats are a lower bound.
- [x] README -> landing funnel link (df235d6, utm_source=github).
- [x] Marketing pack: business/marketing_pack_S034.md (HN repost draft,
      batch 2 notes, 2-week content plan w/ weekly "Model Weather
      Briefing", UTM registry, paid-spend rules: NO ads until analytics
      2wk + HN repost + 1 organic scan request).
- [ ] TATIANA: dashboard screenshot -> business/live_run_S034.png, then
      post business/portfolio_post_live_run_S034.md (LinkedIn+X drafts
      ready; may post early, else slot Wed 22.07).

## DEFERRED — Phase 3 future
- [ ] SSO/RBAC, SOC 2, in-VPC probe, SLAs / canary-gated rollback, hires.
- [ ] Branch protection: add required status checks + PR-flow when a
      second contributor appears (ruleset exists, deliberately light now).

---

## COMPLETED — index (full detail in log + archive)
Phase 0-2 + Phase 3 (multi-tenant, audit): see archive.
S025: README badges, dep-graph generator, P3-002 webhooks.
S026: re-verification; grant/market pack; Zenodo DOI; ROADMAP.md;
  SECURITY.md; README nav + citation; live-probe code.
S027: live-probe arc merged; first live Mistral run; probe hardening;
  Track 1b/2/3; LinkedIn + X published. 122 passed, main green.
S028-S033: see log (E1 canon fix, dev.to publish, Show HN, Zenodo v1.0.1,
  outreach batch 1, drift-defense Pages fix, GitHub infra hardening
  (ruleset + workflow perms + Dependabot + CodeQL), SEC-1 log-injection
  fix -> 127 passed).
