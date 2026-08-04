"""INFRA-1 -- dialect-aware engine construction (REQ-STORE-007).

The public Model Weather board lost its SQLite state on every free-tier
restart (S042 finding).  The fix points SEISMOGRAPH_DB_URL at a managed
Postgres, which requires DatabaseSession to stop passing SQLite-only
arguments to non-SQLite dialects while keeping the historical SQLite
behaviour byte-for-byte.

Only DP-noised aggregates are ever persisted, so moving storage off-box
does not change the privacy perimeter (privacy-by-construction invariant).
"""

from unittest.mock import MagicMock

import engine.repository as repo_mod
from engine.repository import DatabaseSession, _engine_kwargs
from sqlalchemy.pool import StaticPool

NEON_URL = "postgresql+psycopg2://user:pw@ep-x.eu-central-1.aws.neon.tech/main?sslmode=require"


# #SG-TRACE: REQ-STORE-007 | assumption: :memory: URLs are only used by
#   tests and must keep StaticPool sharing | test: this one
def test_engine_kwargs_sqlite_memory_keeps_staticpool():
    kw = _engine_kwargs("sqlite:///:memory:")
    assert kw["poolclass"] is StaticPool
    assert kw["connect_args"] == {"check_same_thread": False}


def test_engine_kwargs_sqlite_file_keeps_check_same_thread():
    kw = _engine_kwargs("sqlite:///data/seismograph.db")
    assert kw == {"connect_args": {"check_same_thread": False}}


def test_engine_kwargs_postgres_has_no_sqlite_args():
    kw = _engine_kwargs(NEON_URL)
    assert "connect_args" not in kw
    assert "poolclass" not in kw
    assert kw["pool_pre_ping"] is True


# #SG-TRACE: REQ-STORE-007 | assumption: a stubbed create_engine is enough
#   to prove __init__ routing without a live Postgres driver
#   | test: this one (adversarial: DSN must not be mangled into makedirs)
def test_postgres_url_skips_sqlite_setup(monkeypatch):
    makedirs_calls = []
    monkeypatch.setattr(
        repo_mod.os, "makedirs", lambda *a, **k: makedirs_calls.append(a)
    )
    created = {}

    def fake_create_engine(url, **kwargs):
        created["url"] = url
        created["kwargs"] = kwargs
        return MagicMock()

    monkeypatch.setattr(repo_mod, "create_engine", fake_create_engine)
    DatabaseSession(NEON_URL)
    assert created["url"] == NEON_URL
    assert created["kwargs"] == {"pool_pre_ping": True}
    assert makedirs_calls == []


def test_sqlite_file_url_still_creates_parent_dir(tmp_path):
    db_path = tmp_path / "sub" / "dir" / "x.db"
    session = DatabaseSession(f"sqlite:///{db_path}")
    assert db_path.exists()
    # And the engine is usable end-to-end (schema created).
    with session.session() as s:
        assert s is not None
