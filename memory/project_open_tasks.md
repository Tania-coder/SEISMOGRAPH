# SEISMOGRAPH — Project Open Tasks (LEAN)
# Quick-read backlog. Session-start summary: memory/CURRENT_STATE.md
# Full append-only log: memory/project_session_log.md (never edit)
# Last updated: 2026-07-02 (Session 030 close)

## Legend
[ ] open  [~] in progress  [x] complete  [D] deferred

---

## DO NEXT (S030 close -> S031)
- [x] E1 CRITICAL — DONE S029 (commit 0d9c81d, merged to main).
- [x] dev.to article — PUBLISHED S029; S030 added link to README + landing,
      drafted reply to the 1 comment (Void Stitch) — Tatiana still needs to
      POST the reply (social/S030_dev_to_reply_and_show_hn.md).
- [x] Track 2 LANDING — DONE S029 (hero, 122 tests); S030 added Evidence
      link to dev.to (commit 9c1e9fb).
- [x] X thread pinned (S029).
- [ ] Show HN — draft ready (social/S030_dev_to_reply_and_show_hn.md);
      Tatiana posts AM US time.

## OPEN — Admin / Security (deadline)
- [x] GitHub 2FA TOTP — DONE 2026-07-02.
- [~] PyPI recovery #11202 IN PROGRESS: branch pushed, reply sent 2026-07-02
      10:46 with proof. Awaiting support (S030: re-checked, no reply yet).
      Then: new pass + 2FA + recovery codes -> delete temp branch
      lPpHBOqwfdAqYN6j -> republish 1.0.1 sole author.

## OPEN — Hygiene
- [x] Bulk CRLF renormalize — DONE S030: clean-tree reset produced zero
      diff (no real CRLF issue existed). The persistent ruff-check failures
      on those same 4 files are a CONFIRMED sandbox-mount read artifact
      (extra NUL bytes on read only, host file + git blob both clean) —
      not a repo defect, no further action, ignore permanently.

## OPEN — Growth (PRIVATE detail in business/, gitignored)
- [ ] Outreach pack ready (business/outreach_pack_S026.md). Tatiana sends from LinkedIn.
- [x] Zenodo v1.0.1 published S030 (DOI 10.5281/zenodo.21139614) — done,
      no further action.

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
