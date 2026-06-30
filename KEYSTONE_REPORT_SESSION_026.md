# KEYSTONE REPORT — Session 026 (2026-06-29)

**Task:** Track 1 of the product-hardening pass — make the canary probe
*real*. Wire `execute_canary(mock=False)` to a live OpenAI-compatible
provider so the pipeline can run against an actual model, not synthetic
mock data. Provider-agnostic by configuration (local Ollama → hosted
OpenAI/Groq/Mistral).
**Branch:** suggested `seismograph/task-live-probe` (Tatiana commits).
**Director:** Tatiana | **Co-pilot:** Claude (Lead Technical Co-Pilot)

---

## 1. Provenance

| Artifact | Origin |
|---|---|
| `probe/providers.py` (new — OpenAICompatibleProvider, ProviderError, model_name_from_tuple) | AI |
| `probe/canary.py` (execute_canary now accepts a live `provider`; raw output still hashed + discarded) | AI |
| `tests/test_providers.py` (new — 11 tests, fully offline) | AI |
| `scripts/live_probe.py` (new — live run CLI; prints only privacy-safe features) | AI |
| `.env.example` (probe endpoint config block) | AI |
| `docs/PROVIDER_TOS_CHECKS.md` (self-hosted + Groq rows) | AI |
| All commits, pushes, the live run against a real endpoint | Human (Tatiana) |

## 2. Verification summary

- **New tests: 11/11 passed** (`tests/test_providers.py`), fully offline via
  an injected fake HTTP transport — no network.
- **Probe-side regression: 69 passed** on fresh bytecode
  (`PYTHONPYCACHEPREFIX` off the NTFS mount): test_providers + test_sdk +
  test_privacy + test_crypto + test_adapters + test_storage. These exercise
  the modified `canary.py` end-to-end through a clean recompile.
- **ruff check + format: clean** on `probe/providers.py`, `probe/canary.py`,
  `tests/test_providers.py`, `scripts/live_probe.py` (`--no-cache`).
- **Privacy invariant re-asserted by test** (`test_execute_canary_live_no_raw_output`):
  the raw model string never appears on the serialised result; only the
  64-char SHA-256 hash, length, json_valid and latency survive.
- **Adversarial (b) covered** (`test_adversarial_silent_drift_changes_hash_and_length`):
  a provider-side semantic shift with an identical latency profile and no
  error changes the response hash AND output length — exactly the signal the
  CUSUM detector consumes. **Adversarial (a)** (Sybil/fabricated probe) is
  unchanged and remains gated at the AgreementScorer quorum layer.

## 3. Defects caught and fixed

- **Transport exceptions could escape as raw errors (real, fixed):** a custom
  transport raising `TimeoutError` bypassed `ProviderError`. `complete()` now
  wraps any non-`ProviderError` transport exception into `ProviderError` with
  a payload-free message. Test: `test_provider_timeout_raises_clean`.
- **Sandbox mount truncation of `canary.py` (environment, mitigated):** after
  tool-based edits, the sandbox's read of `canary.py` was truncated mid-`for`
  loop (the same NTFS-overlay artifact that affects `engine/correlation.py`).
  Mitigation: `canary.py` was rewritten in full via a single sandbox-side
  write so the in-sandbox file is complete and parses; AST-verified.

## 4. Known limitations

- **The live run itself is pending Tatiana's execution.** Tests prove the
  wire format, privacy and drift-signal behaviour offline; the actual call to
  a real endpoint (Ollama/OpenAI) must be run on a machine with that endpoint.
  Command: `python scripts/live_probe.py`.
- **Full 118-test suite not run in-sandbox.** `engine/correlation.py` and
  `gateway/main.py` are truncated by the NTFS-overlay read, so a fresh-compile
  full run errors on collection for the 5 engine/gateway test modules. Those
  modules are untouched this session; Tatiana re-runs `py -3.10 -m pytest -q`
  on the real disk to confirm 107 baseline + 11 new = **118 expected**.
- **Gateway/dashboard emission not yet wired.** `live_probe.py` proves the real
  call and prints results; feeding the live `SignalBatch` through the privacy
  aggregator + crypto signing into `POST /v1/signals` (so the public dashboard
  shows a real model) is the immediate next step.
- **Groq ToS row marked ⚠ VERIFY** — complete it before any production probe
  against the free tier. Self-hosted Ollama needs no third-party ToS.

## 5. Accountability statement

The above is an accurate account of Session 026. New and probe-side tests pass
(11 new, 69 probe-side, fresh bytecode); ruff is clean; the privacy and
silent-drift invariants are asserted by named tests. The live run and the full
118-test confirmation are Tatiana's to execute on the real disk. Nothing is
overclaimed; pending items are stated as pending.

Signed: _________________________  Tatiana — 2026-06-29

## 6. Methodology note (one improvement)

The recurring NTFS-overlay truncation (now hit on `correlation.py`, `main.py`,
`canary.py`) keeps forcing full-file rewrites and blocking in-sandbox full
runs. Recommendation: add a one-line CI job that runs `python -m compileall
probe engine gateway scripts` on push — it deterministically catches any
truncation/syntax breakage on a clean checkout, independent of the sandbox
artifact, and gives a trustworthy green signal the sandbox currently cannot.
