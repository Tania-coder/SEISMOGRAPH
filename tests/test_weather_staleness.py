"""DASH-3: a leg that stopped reporting must not publish STABLE.

Defect D-11.  Before this change ``status`` read ONLY the alert table:

    status = "DRIFTING" if recent_alerts else "STABLE"

so a leg whose probe had been dead for a week still published
``STABLE`` with ``sample_count: 10``.  At a single observer it could
publish nothing else, because ``required_quorum(1) == 3`` makes a public
alert unreachable by construction -- the green light was produced by the
system's own inability to raise an alarm.  Measured on the live board
2026-09-09T17:38Z: the mistral leg had ``window_end``
2026-09-02T09:38:39Z (176.0 h old) and read ``STABLE``.

These tests pin the third state, its precedence, the threshold that a
MEASURED healthy leg must survive, and the timezone handling that would
otherwise move the threshold by the host's UTC offset.

They also pin what DASH-3 deliberately does NOT do: it does not hide or
alter the published metrics of a stale leg, and it does not attempt to
diagnose WHY the leg stopped.

#SG-TRACE: REQ-DASH-005
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from engine.repository import SignalRow
from gateway.main import (
    STALE_AFTER_HOURS,
    _compute_model_weather,
    _window_age_hours,
)
from gateway.schema import ModelWeatherResponse

_MT = "mistral/mistral-small-latest"

# The live board's own numbers on 2026-09-09T17:38:24Z, archived at
# docs/evidence/weather-2026-09-09T173824Z.json.  Both are regression
# pins: the healthy leg was LATE (the probe fires 2.5-4.5 h behind its
# 12 h slot), so a threshold tight enough to fail it would have shipped
# a false STALE the same day it landed.
_MEASURED_HEALTHY_AGE_H = 21.65
_MEASURED_DEAD_AGE_H = 176.0


def _naive_utc_now() -> datetime:
    """Now, in the naive-UTC shape SignalRow.timestamp is stored in."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row(
    age_hours: float,
    rate: float | None = 9 / 50,
    n: float = 50.0,
    suite: str = "v2.0.0",
    length: float | None = 150.0,
) -> SignalRow:
    """A SignalRow whose timestamp is *age_hours* old."""
    return SignalRow(
        batch_id="b",
        model_tuple=_MT,
        timestamp=_naive_utc_now() - timedelta(hours=age_hours),
        avg_output_length=length,
        json_success_rate=rate,
        result_count=n,
        suite_version=suite,
    )


class _FakeRepo:
    """Minimal BaseRepository stand-in for the weather read path."""

    def __init__(
        self,
        rows: list[SignalRow],
        alerts: list[object] | None = None,
    ) -> None:
        self._rows = rows
        self._alerts = alerts or []

    def get_recent_signals(
        self, model_tuple: str, limit: int = 10
    ) -> list[SignalRow]:
        return self._rows[:limit]

    def get_recent_alerts(
        self, model_tuple: str, hours_back: int = 24
    ) -> list[object]:
        return self._alerts


# ---------------------------------------------------------------------------
# T1 -- the defect itself
# ---------------------------------------------------------------------------


def test_stale_window_is_not_published_as_stable() -> None:
    """A leg whose newest sample is a day and a half old is STALE."""
    rows = [_row(31.0), _row(43.0), _row(55.0)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.status == "STALE"


def test_fresh_window_is_stable() -> None:
    """A leg reporting on cadence keeps its green light."""
    rows = [_row(1.0), _row(13.0), _row(25.0)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.status == "STABLE"


def test_empty_window_is_stale_not_stable() -> None:
    """No samples at all is the strongest form of no evidence.

    The pre-DASH-3 code published STABLE here too, with
    ``sample_count: 0`` -- a model tuple that had never emitted a single
    batch read as green.
    """
    w = _compute_model_weather(_FakeRepo([]), _MT)
    assert w.status == "STALE"
    assert w.sample_count == 0
    assert w.window_age_hours is None


# ---------------------------------------------------------------------------
# T2 -- the threshold, pinned to measured reality
# ---------------------------------------------------------------------------


def test_healthy_leg_at_measured_age_is_not_stale() -> None:
    """21.65 h was a LIVE leg on 2026-09-09; it must stay STABLE.

    This is the test that forbids tightening the threshold to 24 h.
    """
    rows = [_row(_MEASURED_HEALTHY_AGE_H), _row(36.1)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.status == "STABLE"


def test_dead_leg_at_measured_age_is_stale() -> None:
    """176.0 h was the dead mistral leg publishing STABLE."""
    rows = [_row(_MEASURED_DEAD_AGE_H), _row(188.5)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.status == "STALE"


def test_threshold_leaves_room_above_a_late_scheduled_run() -> None:
    """The constant itself must clear the measured jitter.

    12 h slot + 4.5 h worst measured lateness = 16.5 h, and a real read
    saw 21.65 h.  A threshold at or below that is a false-alarm
    generator, so the guard is on the constant, not only on behaviour.
    """
    assert STALE_AFTER_HOURS > _MEASURED_HEALTHY_AGE_H
    assert STALE_AFTER_HOURS < _MEASURED_DEAD_AGE_H


def test_boundary_is_not_inclusive() -> None:
    """Exactly at the threshold is still STABLE, so it cannot flap.

    Uses the pure helper with an injected clock: deriving the boundary
    from wall-clock time inside _compute_model_weather would make the
    comparison race the test's own execution.
    """
    now = datetime(2026, 9, 9, 17, 38, 24, tzinfo=timezone.utc)
    end = now - timedelta(hours=STALE_AFTER_HOURS)
    assert _window_age_hours(end, now=now) == pytest.approx(STALE_AFTER_HOURS)
    assert not _window_age_hours(end, now=now) > STALE_AFTER_HOURS


def test_just_past_the_boundary_is_stale() -> None:
    """One minute past the threshold flips the verdict."""
    rows = [_row(STALE_AFTER_HOURS + (1 / 60))]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.status == "STALE"


# ---------------------------------------------------------------------------
# T3 -- precedence
# ---------------------------------------------------------------------------


def test_alert_outranks_staleness() -> None:
    """A quorum-verified alert is a positive finding; it wins.

    DRIFTING > STALE > STABLE.  An alert says something was observed;
    stale data only says nothing has been observed lately.
    """
    alert = SimpleNamespace(timestamp=_naive_utc_now())
    repo = _FakeRepo([_row(200.0)], alerts=[alert])
    w = _compute_model_weather(repo, _MT)
    assert w.status == "DRIFTING"
    assert w.last_alert_timestamp is not None


# ---------------------------------------------------------------------------
# T4 -- timezone handling (the silent way to move the threshold)
# ---------------------------------------------------------------------------


def test_naive_window_end_is_not_shifted_by_host_zone() -> None:
    """A naive timestamp is STAMPED UTC, never interpreted locally.

    SignalRow.timestamp is naive UTC by invariant.  Reading it in the
    host's zone would add that host's offset to every age and move the
    effective threshold by hours -- on a host whose clock zone we do not
    control.
    """
    now = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
    naive_end = datetime(2026, 9, 9, 6, 0, 0)
    assert _window_age_hours(naive_end, now=now) == pytest.approx(6.0)


def test_aware_window_end_is_converted_not_rejected() -> None:
    """An already-aware timestamp in another zone still ages correctly."""
    now = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
    aware_end = datetime(
        2026, 9, 9, 8, 0, 0, tzinfo=timezone(timedelta(hours=2))
    )
    assert _window_age_hours(aware_end, now=now) == pytest.approx(6.0)


def test_naive_now_is_treated_as_utc() -> None:
    """A naive injected clock does not raise on the subtraction."""
    naive_now = datetime(2026, 9, 9, 12, 0, 0)
    end = datetime(2026, 9, 9, 11, 0, 0)
    assert _window_age_hours(end, now=naive_now) == pytest.approx(1.0)


def test_empty_window_end_has_no_age() -> None:
    assert _window_age_hours(None) is None


# ---------------------------------------------------------------------------
# T5 -- what DASH-3 does NOT do
# ---------------------------------------------------------------------------


def test_stale_leg_still_publishes_its_numbers() -> None:
    """The verdict changes; the evidence is not withheld.

    Hiding the metrics of a stale leg would destroy the reader's ability
    to see WHAT the leg last reported, which is exactly the provenance
    DASH-2 was built to expose.
    """
    rows = [_row(176.0), _row(188.0)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.status == "STALE"
    assert w.recent_json_success_rate is not None
    assert w.recent_avg_output_length is not None
    assert w.sample_count == 2
    assert w.window_start is not None
    assert w.window_end is not None


def test_age_is_published_alongside_the_status() -> None:
    """A reader gets the number the verdict was made from."""
    rows = [_row(40.0)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.window_age_hours == pytest.approx(40.0, abs=0.05)


# ---------------------------------------------------------------------------
# T6 -- the schema contract
# ---------------------------------------------------------------------------


def test_schema_accepts_stale() -> None:
    row = ModelWeatherResponse(model_tuple=_MT, status="STALE")
    assert row.status == "STALE"
    assert row.window_age_hours is None


def test_schema_still_rejects_an_invented_status() -> None:
    """Widening to three values must not open the field up entirely."""
    with pytest.raises(ValueError):
        ModelWeatherResponse(model_tuple=_MT, status="SUNNY")
