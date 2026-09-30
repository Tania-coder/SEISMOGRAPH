# KEYSTONE REPORT (SIGNED 2026-09-30) -- REQ-REPORT2C-001..002
# REPORT-2c: the mistral stoppage diagnosed and fixed before publication
# Authored Session 058, 2026-09-30.
# Base: main @54c9321 (host baseline 435, measured 2026-09-30).
# Branch: seismograph/task-report-2c.

## 0. Provenance

Report text and two tests written by Claude (Executor) in a cloud
sandbox, written into the Director's tree through the device bridge,
read back and compared by SHA-256 before any gate. The snapshot
`docs/evidence/weather-2026-09-30T205449Z.json` (739 bytes, SHA-256
c31cc56259d24744..) is the Director's own read. Creating the new API
key, updating the GitHub secret and dispatching the workflow were the
Director's acts. Nothing in this task was posted.

## 1. What

A second paragraph in the report's 2026-09-30 update block, and two
tests pinning it to the new snapshot. The 2026-09-22 body and the
first update paragraph are unchanged.

## 2. Why

Keystone REPORT-2b, signed an hour earlier, accepted publishing the
mistral stoppage as "not diagnosed". Within the hour it was diagnosed
and fixed. Publishing a sentence the author knows to be out of date is
the failure this project exists to refuse.

## 3. Evidence

### 3.1 Diagnosis [measured, Executor read-only in the Director's browser]

- GitHub Actions run #179 (2026-09-30 11:10 UTC): mistral job,
  "0/50 prompts completed", emission step 11 s. No error text logged.
- GitHub secret MISTRAL_API_KEY: last updated 2026-09-15.
- Mistral admin, expired keys: key ...ANa3 created ~2026-09-15, expired
  ~2026-09-18, last used 2026-09-19.
- Mistral usage: completions 2026-09-15..18, zero after 2026-09-19.
- Plan: pay-as-you-go, EUR 0.01 of EUR 8.5 allowance used. Quota is NOT
  the cause.
- [assumed until the fix, then measured] that the secret held ...ANa3:
  inferred from matching dates; confirmed when a new no-expiry key in
  the secret produced a row within minutes (manual dispatch, all four
  jobs green, mistral window_end 2026-09-30T20:48:38Z).

### 3.2 Figures [measured fields / derived rates], 20:54:49 UTC

    mistral  window 2026-09-15T17:36:49Z -> 2026-09-30T20:48:38Z
             age 0.10 h  STABLE, agrees
             span 363.20 h  rate 0.2974 -> DARK

### 3.3 Bindings, verified by breaking them (container, reverted)

`0.10 h`, `363.20 h`, `0.2974`, snapshot name: each change 1 failed,
27 passed. Restored: 28 passed.

### 3.4 Gates

Container only, NOT a gate result. Host gate expected 437.

## 4. Defects caught and fixed

- D12: the probe records "0/50 prompts completed" and discards the
  per-request error, so an expired credential, a quota refusal and a
  provider outage are indistinguishable in the logs. NOT fixed here;
  opened as a task. The diagnosis needed the provider console.
- D13 (process): a credential with an expiry date was put into CI with
  nothing to warn before it expired. Replaced by a no-expiry key.

## 5. Known limitations

5.1 Substring match (as REPORT-2 sec 5.1).
5.2 STABLE on a leg collecting at 0.2974 is limitation 2 of the report,
    now observed live rather than described. Not fixed.
5.3 G-31 still bounded, not measured.
5.4 One observer.

## 6. Provider ToS compliance

No probe designed or changed. The Executor called no provider endpoint;
it read the Director's own Mistral console and GitHub settings pages.

## 7. Methodology note

A diagnosis that needs the provider's console is a missing log line.
Proposed: every discarded run records the first error per failed
prompt (status code and message), inside the probe, so the next
stoppage is diagnosed from the repository.

## 8. Accountability

- [x] sec 3.1 -- diagnosis accepted: expired API key.
- [x] sec 5.2 -- STABLE on a DARK-collecting leg published as a known
      limitation, not fixed here.
- [x] sec 7 -- D12 opened as a task.
- [ ] sec 5.3, G-31 -- LEFT EMPTY ON PURPOSE, as in CLAMP-1, REPORT-2
      and REPORT-2b.

**SIGNED -- Tatiana Radchenko, 2026-09-30.**
