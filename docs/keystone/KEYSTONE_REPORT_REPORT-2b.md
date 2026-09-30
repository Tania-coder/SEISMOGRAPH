# KEYSTONE REPORT (SIGNED 2026-09-30) -- REQ-REPORT2B-001..002
# REPORT-2b: Weather Report #2 re-read before publication (G-37)
# Authored Session 058, 2026-09-30.
# Base: main @eea3a1c (host baseline 431, measured 2026-09-30).
# Branch: seismograph/task-report-2b.

## 0. Provenance

Update block and four tests written by Claude (Executor) in a cloud
sandbox and written into the Director's tree through the device
bridge; every file read back and compared by SHA-256 before any gate.
The board read and every git command are the Director's, from her own
PowerShell. The snapshot `docs/evidence/weather-2026-09-30T193201Z.json`
(751 bytes, SHA-256 14bce7ed..6971a973) is the Director's read.
Publication is the Director's act. Nothing in this task was posted.

## 1. What

- `docs/reports/2026-09-22-weather-report-02.md`: an "Update,
  2026-09-30" block above the body, a third snapshot named in the
  provenance paragraph, and the "Data as of" row states both reads.
  The 2026-09-22 body is unchanged, byte for byte below the block.
- `tests/test_weather_window_stats.py`: four tests. Snapshot committed;
  update figures recomputed; the mistral row is the SAME row on both
  reads; the update block's text is pinned to its snapshot.

## 2. Why

Report #2 was committed 2026-09-22 and not published; G-36 was missed
by eight days [measured 2026-09-30: absent from dev.to API and from the
Director's LinkedIn activity]. G-37 forbids quoting the board without
reading it immediately before. The Director chose (2026-09-30) to keep
the archival body and add a dated update rather than rewrite it.

## 3. Evidence

### 3.1 Figures [measured fields / derived rates], 2026-09-30T19:32:01Z

    mistral  window_end 2026-09-19T09:31:44Z (same row as 09-22)
             age 274.01 h  STALE, agrees
    google   rate 0.8926  NOMINAL  age 8.26 h  STABLE, agrees
             saturation bound <= 0.4163 (41.6%)

### 3.2 Bindings, verified by breaking them (container, then reverted)

| change in the report text | result |
|---|---|
| `274.01 h` -> `274.02 h` | 1 failed, 25 passed |
| `0.8926` -> `0.8927` | 1 failed, 25 passed |
| `41.6%` -> `41.9%` | 1 failed, 25 passed |
| snapshot name, last digit | 1 failed, 25 passed |

Restored: 26 passed, file identical to source.

### 3.3 Gates

Container, py3.12, ruff 0.15.20, gateway.main stubbed to its live
constant (STALE_AFTER_HOURS = 30.0, read from the Director's tree):
26 passed in this file, ruff clean. NOT a gate result. The host gate
is run by the Director before the merge; expected 435.

## 4. Defects caught and fixed

- D10: the new test block ended with an extra blank line; ruff format
  flagged it; fixed before handover.
- D11 (bridge): a re-write of two memory files through the device
  bridge reported success and left the old bytes on disk with a new
  mtime. Caught by SHA-256 read-back; fixed by writing from a fresh
  staging path. Same failure shape as S056 defect 3.

## 5. Known limitations

5.1 The update-block test matches substrings (as REPORT-2 sec 5.1).
5.2 Why mistral stopped on 2026-09-19 is still not diagnosed, now for
    eleven days. The report says so.
5.3 G-31 still bounded, not measured.
5.4 One observer. Unchanged.

## 6. Provider ToS compliance

No probe designed or changed. No provider endpoint called. The only
network read was the Director's GET of her own public board.

## 7. Methodology note

A report that is committed but not published goes stale silently: the
gate stays green because the text still matches its own snapshot.
Proposed: the closing packet lists every artefact committed but not
yet published, with its snapshot date, so the gap is visible at the
next session start rather than found eight days later.

## 8. Accountability

- [x] sec 5.1 -- substring match accepted as for REPORT-2.
- [x] sec 5.2 -- mistral stoppage published as not diagnosed.
- [x] sec 7 -- rule proposed for guide_pack/06.
- [x] Publication decision: the 2026-09-22 body goes out unchanged
      under a dated 2026-09-30 update.
- [ ] sec 5.3, G-31 -- LEFT EMPTY ON PURPOSE, as in CLAMP-1 and
      REPORT-2.

**SIGNED -- Tatiana Radchenko, 2026-09-30.**
