# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-12 (Session 034 in progress)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## DO NEXT (S033 close -> S034)
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
- [ ] Add a second verified email on GitHub (single-email warning banner;
      closes the account-loss scenario that hit PyPI).

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
