# Keystone Report — SEC-1

**Task:** Remediate the 5 CodeQL `py/log-injection` Medium alerts surfaced by
the first CodeQL scan of `main` (introduced with the CodeQL workflow in PR #9).
**Session:** S033 · 2026-07-10 · Director: Tatiana Radchenko · Agent: Claude
(Cowork), Aegis profile (Security & Privacy Auditor).
**Merged:** PR #12 (squash) into `main`. Branch `seismograph/task-sec-1`
(commits f1002db → 04de724 → 299e029), deleted after merge.

---

## 1. Provenance (AI-generated vs. human-edited)

- **AI-generated:** the `_sanitize_for_log()` helper and the two call-site
  changes in `gateway/auth.py`; the `alert_id = int(alert_id)` taint break in
  `engine/audit.py`; the full `tests/test_security_logging.py` suite (5 tests);
  the PR description; this report.
- **Human-executed (Tatiana, from PowerShell — per the git-only-from-PowerShell
  rule):** every `git` operation (branch, commit, push, checkout); the two
  deterministic tooling passes `ruff check --fix` (04de724) and
  `ruff format` (299e029); the final local gate run
  (`ruff check` + `ruff format --check` + `pytest`).
- **AI-directed, human-clicked:** PR creation and squash-merge via the browser,
  under explicit "берём SEC-1" authorization and the standing merge approval.

## 2. Verification summary

- **Unit + adversarial suite:** `tests/test_security_logging.py`, 5 tests
  (SL1–SL5), incl. 2 adversarial cases (forged log line via a whitespace-
  injected key; non-int `alert_id`).
- **Full suite:** `py -3.10 -m pytest -q` → **127 passed** (was 122; +5),
  run locally on the host (ground truth) and confirmed green on CI across the
  3.10 and 3.11 matrix legs.
- **Lint/format:** `ruff check .` → All checks passed; `ruff format --check .`
  → clean. Both gates green on CI.
- **SAST:** CodeQL (python + javascript-typescript, security-extended) green on
  the PR diff. **Post-merge outcome (S033 correction / S034):** 4 of 5 alerts
  closed (`int()` in `engine/audit.py` is a CodeQL-recognized taint barrier);
  the `auth.py` path re-opened as **alert #6** (Medium, `gateway/auth.py:120`)
  because CodeQL does not model the custom `_sanitize_for_log` as a sanitizer.
  Resolved by the SEC-1b follow-up (see addendum, §7).
- **Tooling note:** the in-sandbox pytest/ruff could not be trusted here (known
  mount read-truncation artifact — the sandbox served a 139-line view of a
  154-line file). Verification was therefore done (a) in isolation against exact
  copies of the functions under test (5/5 pass) and (b) authoritatively on the
  host + CI. CI is ground truth, per standing rule.

## 3. Defects caught and fixed (specific)

- **Primary vulnerability — `gateway/auth.py:95` (and the exc branch, :100):**
  `bytes.fromhex()` silently ignores ASCII whitespace, so a `public_key_hex`
  such as `"00" + "\n" + "00"*31` parses to a valid 32-byte key and reaches the
  `InvalidSignature` log branch, where `public_key_hex[:16]` was logged raw —
  letting an attacker inject CR/LF and forge audit-log lines. Fixed by escaping
  control chars via `_sanitize_for_log()` (truncate-after-escape) at both
  `logger.warning` call sites. Crypto verdict unchanged.
- **4 taint alerts — `engine/audit.py:163,183,207,225`:** `alert_id` flows into
  debug/info log calls. Semi-false-positive in practice (FastAPI coerces the
  path param to `int`), closed defensively with `alert_id = int(alert_id)` at
  the top of `generate()`, which also hard-rejects a non-int id before any
  lookup or log call.
- **Self-caught during VERIFY (documented honestly):** the first draft of the
  SL2 adversarial value used `"00"*32 + "\nERROR forged-admin-line"`. The
  letters `R`/`O` are non-hex, so `bytes.fromhex` would have raised `ValueError`
  and routed to the *exception* branch — meaning SL2 would NOT have exercised
  the `InvalidSignature` branch it claimed to test. Corrected to a
  whitespace-only injection inside otherwise-valid hex, positioned early enough
  to land in the logged slice. Caught before commit.
- **Two CI failures caught and fixed (not softened):** (1) `ruff` I001 import
  ordering in the new test file — resolved with `ruff check --fix` (the auto-fix
  removed a blank line; a blind manual guess would have *added* one, i.e. the
  wrong direction — a concrete argument for using the tool over guessing);
  (2) `ruff format` wanted a one-line reformat of `engine/audit.py` — resolved
  with `ruff format`.

## 4. Known limitations (unsoftened)

- **SL3 is defense-in-depth, not a proven exploit.** CPython's `fromhex`
  `ValueError` does not echo the offending input, so there is no *known* natural
  path to smuggle a control char through the exception branch today. Sanitizing
  `exc` guards against a future change that logs a raw exception carrying user
  data; the test is a regression guard, and the docstring says so plainly.
- **Scope is the logging boundary only.** No change to crypto verdicts,
  statistical logic, or report contents (Aegis bound honored). Other modules
  were not swept for the same pattern beyond the 5 flagged sites.
- **Post-merge scan did NOT fully clear (S033 correction).** 4 of 5 alerts
  closed; the `auth.py` key path re-opened as alert #6 because CodeQL treats
  the custom `_sanitize_for_log` as taint-preserving. The original fix was
  functionally correct (SL2 proved the escaping) but the first S033 report
  overclaimed "expected to auto-close" for all 5 — recorded here unsoftened.
  Remediated in SEC-1b (§7): the `InvalidSignature` branch now logs
  `sha256(pub_bytes)[:12]` instead of any form of the attacker-controlled hex,
  severing the taint path at the source and — better practice regardless of
  CodeQL — no longer logging key material at all. `_sanitize_for_log` remains
  on the exception branch (defense in depth, SL3).
- **Alert #6 auto-close is expected, not yet confirmed** — verify on the first
  `main` CodeQL scan after the SEC-1b merge before treating SAST as clean.

## 5. Accountability statement

The change is a security fix at the logging boundary, verified by a full green
test suite (127 passed) and clean lint/format/SAST on CI. No architectural
invariant (privacy-by-construction, OTel-native, content-addressed baselines,
correlation-first alerts, canary cost cap, PEP8) was altered.

Signed: ______________________  (Tatiana Radchenko)   Date: 2026-07-12

## 6. Methodology note (one process improvement)

The session lost time to the sandbox mount serving truncated reads of
freshly-written files, which produced a misleading local `SyntaxError` and made
in-sandbox `ruff`/`pytest` untrustworthy. **Improvement:** for any task that
touches code, run the authoritative gate once on the host —
`ruff format . ; ruff check . ; py -3.10 -m pytest -q` — *before* opening the
PR, rather than relying on the sandbox and discovering `ruff`/format issues via
CI round-trips. Adopted mid-task here (it caught the format issue and confirmed
127 passed in a single pass); recommend making it the default pre-push step for
all future code tasks.

## 7. Addendum — SEC-1b (S034, 2026-07-12): alert #6 remediation

- **Change (AI-generated, minimal diff):** in `gateway/auth.py`, the
  `InvalidSignature` branch now logs `hashlib.sha256(pub_bytes).hexdigest()[:12]`
  (`key_sha256=…`) instead of a sanitized slice of `public_key_hex`. Rationale:
  a hex digest is pure `[0-9a-f]` (physically cannot carry control characters,
  so the CodeQL taint path is severed at the source, no sanitizer modeling
  needed) and it stops logging key material — correct practice independent of
  SAST. Design choice: the digest is computed over the **parsed key bytes**,
  not the raw hex string, so whitespace tricks in the hex representation
  cannot change the logged identity and repeat offenders correlate across
  log lines. `_sanitize_for_log` is unchanged and still guards the exception
  branch (SL3).
- **Tests:** SL2 rewritten for the new contract — asserts exactly one log
  record, no raw newline, the expected digest present, digest alphabet
  `[0-9a-f]`, and that the whitespace-stripped attacker hex prefix does not
  appear anywhere in the message. SL1/SL3/SL4/SL5 unchanged and green.
- **Verification:** `ruff check` + `ruff format --check` + `pytest` →
  **127 passed** on a clean sandbox copy (the repo mount again served a
  corrupted read — stale length, NUL padding — mid-session, consistent with
  the S033 methodology note; the gate was therefore run against an exact
  heredoc-reconstructed copy). **Host gate + CI remain ground truth and must
  be green before merge.** Alert #6 closure to be confirmed on the post-merge
  `main` scan.

---
*Constitution adversarial cases (Sybil probe; silent semantic drift with no
latency signal) are N/A for a logging-boundary fix that does not touch the
probe, correlation engine, or detector — noted per Stage 3 requirements.*
*Provider ToS check: N/A (no new canary probe design).*
