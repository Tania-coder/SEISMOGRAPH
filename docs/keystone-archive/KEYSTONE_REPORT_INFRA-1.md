# KEYSTONE REPORT (SIGNED) — REQ-STORE-007
# INFRA-1: dialect-aware storage — managed Postgres for the weather board
# Session 044, 2026-08-04. Base: main @ebff22e (baseline 286).
# Contract: business/CONTRACT_INFRA-1_S044.md

## 1. What
DatabaseSession (engine/repository.py) is now dialect-aware. A new pure
helper _engine_kwargs(db_url) routes create_engine arguments: SQLite
URLs keep the historical behaviour exactly (":memory:" StaticPool for
tests; check_same_thread=False; parent-dir auto-create for file URLs);
any other SQLAlchemy URL — concretely postgresql+psycopg2:// for Neon —
gets pool_pre_ping=True and no SQLite-only arguments. Dockerfile adds
psycopg2-binary>=2.9 (runtime image only, not a host test dep).
render.yaml declares SEISMOGRAPH_DB_URL with sync:false so the Render
dashboard owns the secret DSN. Plus one hygiene commit: ruff format on
scripts/anthropic_backtest.py (main was not format-clean since 08-01).

## 2. Why
Render free tier wipes the container FS on restart; the board's SQLite
lived there. S042 found /v1/weather empty; on 2026-08-04 it is empty
AGAIN despite 6 days of 5x/day warm-up — every restart destroys the
30-sample CUSUM warm-up that any live alert depends on. Managed Postgres
(Neon free, 0.5 GB, autosuspend 5 min) moves state off the ephemeral
box for EUR 0/mo. pool_pre_ping is load-bearing: Neon suspends idle
computes and drops pooled connections; without pre-ping the first
request after each resume 500s.

## 3. Evidence
- Gate (sandbox, this session): ruff check clean, ruff format --check
  clean (60 files), pytest **291 passed** (286 base + 5 new
  tests/test_repository_backend.py). Host gate pending (Tatiana).
- A1-A5 of the contract each map to a named test; A4 is the break case
  (DSN mangled into os.makedirs by the old code — reproduced against
  pre-patch logic, impossible after).
- ORM audit: models use DateTime/Float/String/int PKs only —
  dialect-neutral; _apply_additive_columns uses generic ALTER TABLE.

### Adversarial case 1 — poisoned / Sybil probe
Storage-only change; AgreementScorer quorum + TTL untouched (zero diff
in engine/correlation.py / detector.py). Existing Sybil/metric-flood
tests pass unchanged inside the 291.

### Adversarial case 2 — provider change with no latency/uptime signal
Detection path (CUSUM over DP-noised aggregates) unchanged. This task
raises detection RELIABILITY for case (b): persistent state means the
30-sample warm-up finally survives restarts, so the board can actually
hold a v2.0.0 baseline long enough to alert.

## 4. Recommended setting
SEISMOGRAPH_DB_URL = postgresql+psycopg2://...neon.tech/<db>?sslmode=require
(set once in Render dashboard; never in git). STORAGE_BACKEND stays
"sqlite" — it selects the generic SQLAlchemy repository (historical
name). Keep keep-demo-warm cron (masks Render free-tier wake latency).

## 5. Compatibility caveats
- First deploy after cutover starts with an EMPTY board until the next
  probe_weather run (5x/day cadence -> < ~5 h gap). Baseline restart
  date must be noted on the landing (existing S040 rule).
- STORAGE_BACKEND naming + "SQLite backend" gateway log line are now
  misleading with a Postgres DSN — cosmetic, deferred.
- Neon free tier: 0.5 GB storage / 100 CU-h per month — orders of
  magnitude above board load (DP aggregates, 5x/day). Cold start
  0.5-2 s after 5 min idle; pre-ping + keep-demo-warm absorb it.
- If psycopg2 is ever installed host-side, test_postgres_url_skips_
  sqlite_setup still never dials out (create_engine is stubbed).

## 6. Contract defects found during implementation
None. C1 held without edits to any existing test (291 = 286 + 5 new).

## 7. Sign-off
- [x] Tatiana — reviewed and accepted (2026-08-04)
— signed by the Director, 2026-08-04 —
