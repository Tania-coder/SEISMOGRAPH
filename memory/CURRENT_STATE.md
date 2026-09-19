# SEISMOGRAPH — CURRENT STATE
# Lean session-start read. Full history: memory/project_session_log.md
# (append-only, never edit) + memory/archive/. Backlog: project_open_tasks.md.
# Last updated: 2026-09-19 (Session 055) — CLAMP measurement taken,
# G-31 deferred, and a PROVIDER-SIDE KEY MIGRATION found that can kill
# the google leg. Prior full refresh: Session 054, same day.
#   main @3d1d079 (BENCH-1 merge), host gate GREEN 398 on 2026-09-19.
#   Landed S054: BENCH-1 (corpus digests pinned; corpus loadable as data).
#   Baseline 378 -> 398. Keystone BENCH-1 signed BEFORE the merge —
#   third in a row, after FLOOR-1 and BUF-1.
#   S054 was an ENGINE-ONLY session: no probe ran, no published number
#   moved, nothing was published. The second observer is not advanced.
# Prior: 2026-09-16 (S051-S053: FLOOR-1, SKILL-1, BUF-1, FLOOR-1b,
#   README-1; 325 -> 378; mistral leg recovered).
# Prior: 2026-09-04 (S049: first public artefact in 42 days; CAN-3
#   refuted; signature gate added to protocol 01).

## Identity
- Director: Tatiana Radchenko (Aarhus). Claude = Executor.
- SEISMOGRAPH: federated, privacy-preserving early-warning network for silent
  LLM/agent API drift. OSS, Apache-2.0.
- Repo: github.com/Tania-coder/SEISMOGRAPH | pip install seismograph-probe.
- Branch convention: seismograph/task-{id}. Never commit on main.

## Three-role protocol (S048; amended S049; see business/guide_pack/01)
- DIRECTOR (Tatiana): decides, signs Keystones, runs git, publishes, spends.
- EXECUTOR (this Cowork project): has the machine. Builds, measures,
  verifies, lands. Never signs, never publishes, never runs the
  Director's git.
- GUIDE (separate Claude web project): no machine, no repo. Holds strategy
  and the open-decision register. Consulted BETWEEN sessions.
- Evidence standard: tag every claim [measured] / [derived] / [assumed];
  a scoped test run is never a gate; arithmetic is a prediction, not a
  measurement, until observed. business/guide_pack/05.
- **SIGNATURE GATE (S049).** The signature precedes the merge. Enforced
  by tests/test_keystone_signed.py, so an unsigned report is a red gate.
  Both dates always recorded, never backdated. Held three times running:
  FLOOR-1, BUF-1, BENCH-1.

## Baseline (re-verify at session start — do not trust this file)
- Tests: **398 on MAIN** [measured 2026-09-19, host gate, ruff clean,
  71 files formatted]. Prior lines: 378 (2026-09-16), 345, 325.
- Gate is always all three: `ruff check .`, `ruff format --check .`,
  `py -3.10 -m pytest -q` from the repo root. Ruff pinned 0.15.20.
- **Corpus digests are now pinned in the gate** (S054, BENCH-1).
  CANARY_SUITE_V2 + FROZEN_TOOL_SCHEMA_V1 hashes to
  d4fbb0a0ee7f704accc2b91c2832a4905cdf7b5cb175785490eabe878b9aba14.
  A prompt edit now fails tests/test_suite_corpus_pinned.py. Editing a
  pinned digest to turn a red gate green inverts the control into a
  rubber stamp: a legitimate new corpus is a NEW suite version with a
  NEW pin, added deliberately.
- **OPEN FINDING (S049): the gate runs on Python 3.10.11, but BOTH
  pyproject.toml and pyproject_probe.toml declare
  requires-python = ">=3.11".** The whole baseline is proven only on a
  version the package disclaims. Needs its own task.

## Clamp measurement [measured 2026-09-19, S055]

`MAX_OUTPUT_LENGTH = 320` on the FLOOR-1 corpus (max_tokens=128):

- Clamp removes **32.3%** of the reference leg's mean (166.19 -> 112.52).
- Saturation: 9/42 paired records (21.4%), 17/50 full (34.0%), max 710.
- **The generation signal SURVIVES the clamp**: raw -39.67 chars
  (-23.87%), clamped -31.29 (-27.80%), Laplace scale b = 320/(50*2) =
  3.20, so |d|/b = 9.78. The Executor's prediction that the clamp would
  flatten the signal is REFUTED. Sixth Executor conclusion killed by
  measurement.
- The real driver is not mean length but the FRACTION above the clamp,
  which depends on spread. Our corpus is heavy-tailed (median 52.5 at
  mean 166.2, CV 1.35) so mass stays below the cap. [derived] on a
  low-spread corpus (CV 0.10, mean 600) the clamped difference is
  EXACTLY 0.00 while the raw difference would be -141.6 chars (44x the
  noise).
- **Silent-failure mode:** a fully saturated clamp reports 320 +- noise,
  i.e. a perfectly stable model. Indistinguishable from real stability
  in the published fields. Same family as DASH-2's 10/10 while losing
  45% of runs.
- Production is NOT affected today: live_emit uses max_tokens=64, which
  is exactly what the 320 bound was derived from. Upper bound from the
  published means: saturation <= 40.7% (google), <= 27.9% (mistral).
  The exact live fraction is NOT measured — see Open now.

Evidence: docs/evidence/driftfloor/*.csv (pinned), verified twice by
two independent implementations.

## PROVIDER RISK — the google leg cannot be restored if its key is lost
[measured 2026-09-19] Google is migrating API keys from `AIza` to `AQ.`
("moving away from Traffic keys towards a more secure Authentication
Key"). AI Studio now issues ONLY `AQ.` keys, and those FAIL against the
Gemini API: `?key=` gives 401 ACCESS_TOKEN_TYPE_UNSUPPORTED, and the
OpenAI-compatible endpoint gives 400 on every prompt (50/50 measured).
No `AIza` key remains in the Director's AI Studio account.

The live google leg runs on the `GEMINI_API_KEY` GitHub secret, which
cannot be read back. It worked on 2026-09-16. **If that secret is ever
rotated, expires or is revoked, the leg dies and cannot be restored**
with any key AI Studio issues today. An observer lost to a provider-side
change that touches neither the model nor our code — the exact class
this project exists to detect.

## HARD RULES — the bridge and the mount
- (S029) After ANY write through the mount, verify via a read-back —
  sandbox mount reads pad NULs and serve stale cache.
- (S035) NEVER rewrite an existing memory/log file wholesale through the
  bridge. Build the new content, write, re-verify — or append natively
  from PowerShell.
- (S037) The bridge can drop mid-session; after a reconnect re-verify
  that writes landed BEFORE committing.
- (S046) NEVER end a session with uncommitted work. Broken twice since
  written (PRIV-011 at S045; DASH-2 at S047).
- (S048) A scoped or subset test run is NEVER a gate result.
- (S049) Verify the PUBLIC SURFACE, not that the publish action
  succeeded. Change the filename on every revision.
- **(S054, new — accepted in Keystone BENCH-1 sec 7) Never reuse an
  output filename between revisions within a session. After every write
  through the bridge, read the file back and compare its SHA-256
  against the source before running the gate. Size is NOT sufficient:
  two revisions of equal length are indistinguishable by size. A
  successful tool response is not evidence of a write.**
- **(S054, new) Never rewrite a file through the bridge while the
  Director may have it open in an editor. Say so before the write and
  confirm the editor was closed and reopened: a stale buffer saves the
  old revision over the new one and leaves a fresh mtime behind.**
- The general form, rediscovered at S029, S049 and twice at S054: the
  confirmation an action returns describes the REQUEST, not the RESULT.
- device_bash has failed to start since S047 ("Workspace unavailable").
  Standing fallback: device_stage_files to read, edit in the container,
  device_commit_files to write back, git from PowerShell, and Chrome +
  the GitHub REST API read from the page context.

## HARD RULE — git ONLY from PowerShell (Tatiana)
- NEVER run git from the sandbox (mount leaves index.lock; if locked:
  Remove-Item .git\index.lock -Force). A fresh GitHub clone in /tmp IS safe.
- Web-UI PR merge via Tatiana's Chrome is OK with her explicit approval.
- Каждое новое окно PowerShell: FIRST cd D:\Dev\Projects\SEISMOGRAPH.
- (S046) Put ONLY runnable commands in code fences. Broken at S052 and
  again at S054 — a signature line in a fence was pasted into PowerShell.

## Live assets
- Board: https://seismograph-weather.onrender.com/dashboard — /v1/weather
  on Neon free Postgres. Cron scheduled 05:17 and 17:17 UTC, but runs
  fire **2.5-4.5 h late** [measured S049], so multiple-of-12 h arithmetic
  on gaps is unsound.
- Last raw read [measured 2026-09-16]: google and mistral both STABLE,
  window_end 2026-09-16. The mistral leg is NOT dark any more. NOT
  re-read since; treat as stale at session start.
- PUBLIC ARTEFACT — Weather Report #1, published 2026-09-04:
    dev.to   https://dev.to/taniacoder/i-gave-my-drift-monitor-a-denominator-the-first-thing-it-exposed-was-a-hole-in-my-own-data-5508
    LinkedIn https://www.linkedin.com/feed/update/urn:li:activity:7501709720328753152/
    Archival copy of record: docs/reports/2026-09-04-weather-report-01.md
- Talk delivered at Claude Code Meetup #3, Aarhus, 2026-09-17. Next
  meetup November, another show-and-tell slot available.
- Landing: https://driftdefense.dev (repo D:\Dev\Projects\drift-defense).
  Brand rule: SEISMOGRAPH = engine, Drift Defense = service.
- Guide pack: business/guide_pack/ (gitignored, private, and therefore
  NOT backed up anywhere — open item).
- PyPI: seismograph-probe 1.1.0 (18 Jul, stale).
- DOI: https://doi.org/10.5281/zenodo.21045517 (concept; ...518 is the
  stale v1.0.0 version DOI — do not cite).

## Facts canon (E1, fixed S029; wording upgraded S043 — use ONLY these)
- Incident: Anthropic postmortem 2025-09-17, THREE infra bugs, NOT a model
  update. Backtest models bug #1: context-window routing error, Claude
  Sonnet 4 (NOT 3.5 Sonnet), 0.8% from 2025-08-05, ~16% from 2025-08-29.
- Model tuple: anthropic/claude-sonnet-4@global.
- Detection (SEED=42): first alert 2025-08-10; lead 38 d over postmortem.
- LOCKED PHRASING: "a seeded backtest flags it 38 days before the
  postmortem"; prefer "synthetic replay / would-have flagged".
  NEVER "caught ... early" (implies live catch).
- FLOOR-1 (S051/S053), the project's own measurement: gemini-3.1-flash-lite
  42/42 = 100% identical (positive control); gemini-3.5-flash-lite
  59.5-63.4% across four runs on two dates; the `-latest` alias is NOT
  distinguishable from pinned 3.5 (cross pairs 57.1-64.3%, inside the
  within-model range — a negative result, reported as one); a generation
  change separates on mean output length (-24%) where hash agreement
  cannot. Instability is a property of the MODEL, not the prompt category.
- M = 1 observer. Quorum requires 3. **No public alert can fire, by
  construction.** Central strategic fact, unchanged.

## Open now (ranked; full backlog: project_open_tasks.md)

**Provider risk, new and highest**
0. **The google leg's key is irreplaceable** (see above). Options, none
   taken: obtain an `AIza` key another way; migrate the leg to a
   provider whose keys still work; accept and document the risk. A
   Director decision, not an Executor one.

**Decisions owed before more engine work**
1. **BENCH-0 — the two-tier decision.** Fleet-only (any private corpus,
   never promoted to a public alert) versus fleet PLUS a registry of
   pinned public suites that different observers can actually be
   compared on. Naive pluggability makes M = 1 PER SUITE and destroys
   quorum, so this gates BENCH-2. Director/Guide, not Executor.
2. **5.5 in Keystone BENCH-1 — PARTLY ANSWERED, still open.** The
   clamp was measured (above): it does not flatten the signal on our
   corpus, and the failure mode is low spread, not long answers.
   G-31 remains open: the saturation fraction on the LIVE legs is NOT
   measured, only bounded (<= 40.7% google). Blocked by the key
   migration above; one run of measure_drift_floor.py at
   --max-tokens 64 closes it as soon as a working key exists.

**Engine**
3. BENCH-2 — deterministic sampler (benchmark id + revision + seed + n
   -> fixed item ids) and the first real adapter. Blocked on 1 and 2.
   No public benchmark is usable until this exists: corpora over 200
   prompts are rejected, not reduced.
4. BENCH-3 — a correctness feature. CanaryResult has no "the answer was
   right" field. Hash agreement answers "did the output change";
   pass-rate on a known-answer corpus answers "did it get worse", which
   is the question that makes drift a business event.
5. Nonce fix in probe/canary.py — tool-call JSON carries a per-call
   random id inside the hashed string, so 8 of 50 canaries emit a
   changing fingerprint every run, forever. Now cheaper than before:
   with the corpus versioned as data it rides as a NEW suite version
   instead of a silent baseline discontinuity.
6. pytest coverage for scripts/measure_drift_floor.py, then
   `seismograph compare` as a real command.
7. BUF-2 — store the signed window_end clamped to arrival, so a late
   spooled batch does not read as fresh (weakens DASH-3 up to ~59 h).
   UNIQUE constraint on batch_id. Runner spool via actions/cache.
8. Check the live_emit spool default — CHANGELOG and ProbeConfig
   disagree.
9. Reconcile the two content-addressing schemes: probe/canary.py::
   suite_content_hash (production, now pinned) vs probe/canary_suite.py::
   CanarySuiteVersion.from_prompts (Phase-0 stub, different prompt
   shape, no tool schemas). Limitation accepted in BENCH-1 sec 5.2;
   the rebase is NOT scheduled.
10. requires-python >= 3.11 vs a gate run on 3.10.11 (see Baseline).
11. PRIV-012 (avg_output_tokens, ~128x). Naive last_alert_timestamp.
    Dependabot PRs. VALID_PAYLOAD impossible in tests.

**Operations, unverified since the date shown**
12. probe-weather-multi failed runs #121-#148 (28 in a row), #149-#151
    green; cause never investigated [2026-09-16]. keep-demo-warm
    #542/#543 failed at ~15 min.
13. The gateway 409 duplicate-batch change has NOT been confirmed live
    on Render. The deployed commit is not visible from /v1/weather.
14. probe/suites/*.json is not declared as package data in
    pyproject_probe.toml, so the wheel ships the loader without the
    default corpus. Fix with the probe 1.2.0 release (backlog D-10).
15. observer_count: 1 field on /v1/weather (G-04) — presentational.

**Structural**
16. **Published metrics are not quorum-gated** — accepted as OPEN and
    UNDEFENDED in the DASH-2 signature, with the recorded consequence
    that it is a PREREQUISITE for a second observer, not a follow-up.
17. **The second observer is the binding constraint, and only
    publishing produces one.** Strongest leads: Augustin Gottlieb
    (Merkle, QA & Automation — gave the feedback BENCH-1 answers, and
    plausibly already runs an eval suite in CI) and Anders Hansen
    (AgentX, unattended scheduled agents). Both from the 2026-09-17
    meetup; neither followed up yet.
18. business/ and social/ exist on one disk only. Private is not backed
    up. A private GitHub repo would close it.
19. Carried Director clicks: SSH signing key for verified commits;
    Zenodo release to archive docs/reports/; formsubmit activation;
    OpenSSF questionnaire; NLnet recheck ~25.09; optional Neon password
    reset.

## Scheduler reconciliation [measured 2026-09-04, not re-run since]
Window 2026-08-24T05:58Z -> 2026-09-01T10:11Z, workflow probe_weather.yml:
  A = 16 scheduled runs fired (#105-#120)
  B = 9 success / 7 failure / 0 cancelled, at RUN level
  C = 10 google rows on the board  =>  6 runs produced no google row
H3 (scheduler gap) and H4 (job timeout) are both REFUTED: the runs fired
and nothing was cancelled. Run-level status is a poor proxy for per-leg
collection — a run is marked failed if ANY leg fails, and a failed run
can still carry a successful leg.
