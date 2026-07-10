# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-10 (Session 033 close)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## DO NEXT (S033 close -> S034)
- [ ] Confirm the 5 CodeQL py/log-injection alerts show 0 open after the
      post-merge main scan (were queued at S033 close). If any remain,
      re-open SEC-1.
- [ ] Sign KEYSTONE_REPORT_SEC-1.md (Tatiana signature line, section 5).
- [ ] Commit pending memory/* edits (S032 close + S033 entry) + the
      Keystone file to main. Verify commit file list before push.
- [ ] PyPI #11202: ping posted 07-10. If still silent ~1 week, re-reply to
      the verification email in Gmail. On resolution: new pass + 2FA +
      recovery codes -> delete temp branch lPpHBOqwfdAqYN6j -> republish
      1.0.1 -> set up Trusted Publishing (OIDC).
- [ ] Sebastian (Legora): single follow-up SENT 07-10. Do NOT message
      again unless a trigger event (provider incident / Legora news / his
      post) makes it relevant.
- [ ] Sigge/Martin/Lars invites: if still Pending ~07-17, withdraw. On ANY
      acceptance, first message uses locked phrasing (their notes carry
      old "caught" wording).
- [ ] HN 48773957: waiting on mod reply to the 07-06 email. Else proper
      "Show HN:" repost in 2-3 weeks.
- [ ] TATIANA (carryover): delete the stale hn@ Gmail draft (07-06 14:32);
      the mod email itself was SENT 07-06 15:03.

## DONE S033 (detail in log)
- [x] SEC-1: fixed 5 CodeQL py/log-injection alerts (PR #12, squash).
      _sanitize_for_log in gateway/auth.py + int() taint break in
      engine/audit.py + 5 tests (SL1-SL5). 127 passed on host & CI
      (3.10+3.11); ruff check/format + CodeQL green. Keystone written
      (KEYSTONE_REPORT_SEC-1.md, needs signature).
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
- [~] Outreach batch 1 (2026-07-03): 6 invites still Pending as of S033
      (Jose/Joel/Delphine; Sigge/Martin/Lars). Sebastian ACCEPTED 07-03,
      single follow-up sent 07-10 (no reply yet). PAUSED per playbook;
      batch 2 (Ultimate/Zendesk AI, Parloa; then Tier B) waits for replies.
      LESSON LOCKED: notes say "a seeded backtest flags it 38 days before
      the postmortem" — never "caught ... early".
- [x] Void Stitch triage (S031): likely bot — disengage.
- [x] Zenodo v1.0.1 published S030 (DOI 10.5281/zenodo.21139614).

## NICE-TO-HAVE
- [ ] Track 1b: real Mistral emission to LOCAL dashboard (API key = long
      no-dash string from console.mistral.ai -> API Keys, NOT org UUID).

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
