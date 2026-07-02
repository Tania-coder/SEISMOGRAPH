# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-02 (Session 028 close)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## DO NEXT (S029) — fix facts FIRST, then content
- [x] E1 CRITICAL — DONE S029 (commit 0d9c81d, merged to main). Sonnet 4 +
      3 infra bugs fixed in: backtest script, notebook (regenerated),
      README, Architecture §12, ROADMAP, landing.html, .zenodo.json,
      mcp.py docstrings. Detection unchanged: 2025-08-10, lead 38/19 d.
      122 passed, ruff clean. NOTE: business/, social/, job_search/ still
      say "3.5 Sonnet" (+ cover_letter says 103 tests) — fix before sending.
      Zenodo: existing DOI archive immutable; fixed text applies to next
      version upload. Private session notes added to .gitignore.
- [ ] dev.to article (Track 3 cont.): connect dev.to (sign in via GitHub =
      "dev.to OAuth"); Claude drafts a long-form technical article from the
      README "Technical overview" + CUSUM backtest + architecture; Tatiana
      publishes. Structure in NEXT_SESSION_PROMPT.md part 2.1.
- [ ] Track 2 LANDING (drift-defense — SEPARATE GitHub Pages repo): add repo to
      session; hero = pitch block A + "View live dashboard" CTA; FIX stale
      "107 tests" -> 122 on the landing graphic.
- [ ] X thread: Pin to profile; optional first-comment with repo + dashboard links.

## OPEN — Admin / Security (deadline)
- [x] GitHub 2FA TOTP — DONE 2026-07-02. Full 6-step security checklist closed
      (recovery codes regenerated, passwords rotated, sessions/tokens/OAuth
      pruned, 0 collaborators, org clean, Windows pass + remote-access check).
- [~] PyPI recovery #11202 IN PROGRESS (2026-07-02): branch lPpHBOqwfdAqYN6j
      pushed, reply sent. Await 2FA/password reset -> new pass + 2FA + recovery
      codes -> delete temp branch -> republish 1.0.1 sole author.

## OPEN — Hygiene
- [ ] Bulk CRLF renormalize of 4 phantom files (correlation.py, gateway/main.py,
      first_party_fleet.py, test_privacy.py): on a CLEAN tree
      `git rm --cached -r . ; git reset --hard`. .gitattributes (eol=lf) in place.

## OPEN — Growth (PRIVATE detail in business/, gitignored)
- [ ] Outreach pack ready (business/outreach_pack_S026.md). Tatiana sends from LinkedIn.

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
