# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-06 (Session 032 close)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## DO NEXT (S032 close -> S033)
- [ ] TATIANA: delete the stale hn@ Gmail draft ("A few hours ago...",
      created 07-06 14:32). The mod email itself was SENT 07-06 15:03.
- [ ] PyPI #11202: if no support reply by 2026-07-09/10, post a polite
      ping in the issue.
- [ ] Sebastian (Legora): ACCEPTED invite 07-03 20:52, but no reply to
      the 07-03 message. If still silent by Thu 2026-07-09, ONE
      follow-up message, then stop.
- [ ] On ANY invite acceptance: first message immediately uses locked
      phrasing (esp. the 4 targets whose notes carry old "caught"
      wording: Sigge, Martin, Lars, Delphine). If Sigge/Martin/Lars
      silent by ~07-17: withdraw those invites.
- [ ] HN 48773957: waiting on mod reply to Tatiana's 07-06 email. If
      nothing changes: proper "Show HN:" repost in 2-3 weeks.

## DONE S031 -> S032 (history)
- [x] drift-defense Pages build FIXED S032: transient GitHub Pages infra
      error on 9c1e9fb deploy (build was green), NOT a repo defect.
      UI re-run stuck in queue; fixed via empty commit 3aceaf0 (Tatiana,
      PowerShell), run #7 green in 48s. Live landing verified: Evidence
      row shows the dev.to writeup link (correct href). Leftover: run #6
      attempt #2 stuck Queued, harmless (identical tree).
- [x] hn@ycombinator.com mod email SENT by Tatiana 07-06 15:03.
- [x] Status sweep S032: PyPI silent; Sebastian accepted invite (no
      reply yet); all 6 invites Pending, no acceptances from the six;
      HN comment still [flagged].

## OPEN — Admin / Security (deadline)
- [x] GitHub 2FA TOTP — DONE 2026-07-02.
- [~] PyPI recovery #11202 IN PROGRESS: branch pushed, reply sent 2026-07-02
      10:46 with proof. Awaiting support (S032: re-checked, still silent).
      Ping 2026-07-09/10. Then: new pass + 2FA + recovery codes -> delete
      temp branch lPpHBOqwfdAqYN6j -> republish 1.0.1 sole author.

## OPEN — Hygiene
- [x] Bulk CRLF renormalize — DONE S030: clean-tree reset produced zero
      diff (no real CRLF issue existed). The persistent ruff-check failures
      on those same 4 files are a CONFIRMED sandbox-mount read artifact
      (extra NUL bytes on read only, host file + git blob both clean) —
      not a repo defect, no further action, ignore permanently.

## OPEN — Growth (PRIVATE detail in business/, gitignored)
- [~] Outreach batch 1 (S030, 2026-07-03): 6 invites still Pending as of
      S032 (Jose/Joel/Delphine sent 07-03; Sigge/Martin/Lars ~1.5 w).
      Sebastian ACCEPTED 07-03 20:52; awaiting reply to first message.
      PAUSED per playbook — wait for replies, track in
      business/outreach_pack_S026.md, before sending batch 2 (remaining
      Tier-A: Ultimate/Zendesk AI, Parloa; then Tier B).
      LESSON LOCKED: connection notes must say "a seeded backtest flags it
      38 days before the postmortem" — never "caught ... early" (4 of 6
      pending notes went out with the wrong version; unfixable post-send,
      mitigation = locked phrasing in first message upon acceptance).
- [x] Void Stitch triage (S031): likely AI/engagement bot -- disengage,
      no further replies in that dev.to thread.
- [x] Zenodo v1.0.1 published S030 (DOI 10.5281/zenodo.21139614) — done,
      no further action.

## NICE-TO-HAVE
- [ ] Track 1b: real Mistral emission to LOCAL dashboard (API key = long
      no-dash string from console.mistral.ai -> API Keys, NOT org UUID).

## DEFERRED — Phase 3 future
- [ ] SSO/RBAC, SOC 2, in-VPC probe, SLAs / canary-gated rollback, hires.

---

## COMPLETED — index (full detail in log + archive)
Phase 0-2 + Phase 3 (multi-tenant, audit): see archive.
S025: README badges, dep-graph generator, P3-002 webhooks.
S026: re-verification; grant/market pack (whitepaper, pitch deck, one-pager);
  Zenodo DOI; ROADMAP.md; SECURITY.md; README nav + citation; live-probe code.
S027: live-probe arc COMMITTED + MERGED to main; first live Mistral run; probe
  hardening (sys.path bootstrap, non-ASCII key guard, .gitattributes); Track 1b
  live signed signal -> gateway -> dashboard (live_emit.py + tests); untrack
  runtime db; CI red->green hotfix (ruff format); Track 2 dashboard explainer
  panel; Track 3 README hero + Technical overview (test count -> 122); LinkedIn
  post + X thread published. 122 passed, main green.
S028-S032: see log (E1 canon fix, dev.to publish, Show HN, Zenodo v1.0.1,
  outreach batch 1, drift-defense Pages fix).
