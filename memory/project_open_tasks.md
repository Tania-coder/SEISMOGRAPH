# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-12 (Session 034 in progress)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## DO NEXT (S033 close -> S034)
- [~] SEC-1b (alert #6) IMPLEMENTED S034, awaiting host gate + PR:
      gateway/auth.py InvalidSignature branch now logs
      sha256(pub_bytes).hexdigest()[:12] (key_sha256=...) -- digest over
      PARSED key bytes (canonical identity), not the raw hex string.
      _sanitize_for_log kept for exc branch (SL3). SL2 rewritten (digest
      asserted, attacker hex absent). Sandbox gate green on clean /tmp
      copy: ruff check + format --check + 127 passed (mount again served
      a corrupted read -- NUL padding; host/CI = ground truth).
      REMAINS: Tatiana host gate -> branch seismograph/task-sec-1b ->
      PR -> merge -> confirm alert #6 auto-closes on next main scan.
- [~] KEYSTONE_REPORT_SEC-1.md amended S034: section 2 SAST outcome
      corrected, section 4 records #6 unsoftened, new section 7 addendum
      (SEC-1b). REMAINS: Tatiana signature (section 5, dated 07-12).
- [ ] (DONE 07-10) memory/* S033 + Keystone committed to main (0433f44);
      this correction commit pending.
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
