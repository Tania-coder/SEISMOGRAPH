"""DASH-2: sample provenance on the published weather numbers.

DASH-1 made ``recent_json_success_rate`` a true [0, 1] rate.  It did
not say what that rate rests on.  A reader could not tell whether 98.2%
came from ten batches or two, nor how old they were -- publishing a
percentage without its base is the same defect DASH-1 fixed, one level
up.  These tests pin the denominator, pin that the two per-metric
counts are allowed to diverge, and pin that the window bounds are
published as timezone-aware UTC.

They also pin what DASH-2 deliberately does NOT do: it does not touch
the metric values, and it does not defend against a Sybil inflating the
count.

#SG-TRACE: REQ-DASH-004
"""

from datetime import datetime, timedelta, timezone

from engine.repository import SignalRow
from gateway.main import _as_published_utc, _compute_model_weather
from gateway.schema import ModelWeatherResponse

_MT = "google/gemini-3.5-flash-lite"
_T0 = datetime(2026, 8, 28, 5, 17, 0)


def _row(
    rate: float | None = 9 / 50,
    n: float = 50.0,
    suite: str = "v2.0.0",
    length: float | None = 150.0,
    ts: datetime | None = None,
) -> SignalRow:
    """Build a SignalRow with only the fields the weather path reads."""
    return SignalRow(
        batch_id="b",
        model_tuple=_MT,
        timestamp=_T0 if ts is None else ts,
        avg_output_length=length,
        json_success_rate=rate,
        result_count=n,
        suite_version=suite,
    )


class _FakeRepo:
    """Minimal BaseRepository stand-in for the weather read path."""

    def __init__(self, rows: list[SignalRow]) -> None:
        self._rows = rows

    def get_recent_signals(
        self, model_tuple: str, limit: int = 10
    ) -> list[SignalRow]:
        return self._rows[:limit]

    def get_recent_alerts(
        self, model_tuple: str, hours_back: int = 24
    ) -> list[object]:
        return []


# ---------------------------------------------------------------------------
# T1 -- the denominator is published at all
# ---------------------------------------------------------------------------


def test_full_window_publishes_its_size() -> None:
    """Ten complete batches report ten samples on every count."""
    rows = [_row(ts=_T0 - timedelta(hours=12 * i)) for i in range(10)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.sample_count == 10
    assert w.json_sample_count == 10
    assert w.length_sample_count == 10


def test_short_window_is_reported_honestly() -> None:
    """Two batches must not be published as if they were ten."""
    w = _compute_model_weather(_FakeRepo([_row(), _row()]), _MT)
    assert w.sample_count == 2
    assert w.json_sample_count == 2


# ---------------------------------------------------------------------------
# T2 -- the two per-metric counts are allowed to diverge
# ---------------------------------------------------------------------------


def test_counts_diverge_when_a_row_is_uninterpretable() -> None:
    """A partial run is excluded from the rate but still a sample.

    This is the case a single sample_count would misreport: the window
    holds three batches, the rate rests on two of them.
    """
    rows = [_row(), _row(), _row(n=3.0)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.sample_count == 3
    assert w.json_sample_count == 2
    assert w.length_sample_count == 3


def test_length_count_tracks_its_own_nulls() -> None:
    """A row with no length still counts toward the JSON rate."""
    rows = [_row(), _row(length=None)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.sample_count == 2
    assert w.json_sample_count == 2
    assert w.length_sample_count == 1


def test_zero_interpretable_rows_report_zero_not_none() -> None:
    """No usable rate: the value is None but the count is a hard 0."""
    rows = [_row(suite="v9.9.9"), _row(suite="")]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.recent_json_success_rate is None
    assert w.sample_count == 2
    assert w.json_sample_count == 0


# ---------------------------------------------------------------------------
# T3 -- window bounds
# ---------------------------------------------------------------------------


def test_window_bounds_are_timezone_aware_utc() -> None:
    """Stored naive UTC must be published with an explicit offset.

    An offset-less ISO 8601 string is LOCAL time by spec, so a browser
    would render the wrong instant.  The offset is attached, and the
    instant is not shifted.
    """
    w = _compute_model_weather(_FakeRepo([_row(ts=_T0)]), _MT)
    assert w.window_start is not None
    assert w.window_start.tzinfo is not None
    assert w.window_start.utcoffset() == timedelta(0)
    assert w.window_start.replace(tzinfo=None) == _T0


def test_window_bounds_do_not_assume_row_order() -> None:
    """Bounds come from min/max, not from row position.

    get_recent_signals orders by id, which is only a proxy for time.
    Rows arriving out of order must not invert the window.
    """
    early = _T0 - timedelta(days=4)
    late = _T0
    rows = [_row(ts=late), _row(ts=early), _row(ts=_T0 - timedelta(days=2))]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.window_start.replace(tzinfo=None) == early
    assert w.window_end.replace(tzinfo=None) == late


def test_empty_window_has_no_bounds_and_no_samples() -> None:
    """An unseen model publishes zeroes and Nones, never a guess."""
    w = _compute_model_weather(_FakeRepo([]), _MT)
    assert w.sample_count == 0
    assert w.json_sample_count == 0
    assert w.length_sample_count == 0
    assert w.window_start is None
    assert w.window_end is None


def test_stale_window_is_visible_rather_than_hidden() -> None:
    """A leg that stopped emitting shows an old window_end.

    This is the reader-facing half of the open google-leg sample loss:
    the board currently cannot show that a leg has gone quiet.
    """
    old = _T0 - timedelta(days=30)
    w = _compute_model_weather(_FakeRepo([_row(ts=old)]), _MT)
    assert w.window_end.replace(tzinfo=None) == old


def test_as_published_utc_normalises_an_already_aware_value() -> None:
    """An aware non-UTC value is converted, not relabelled."""
    aware = datetime(2026, 8, 28, 7, 17, tzinfo=timezone(timedelta(hours=2)))
    out = _as_published_utc(aware)
    assert out.utcoffset() == timedelta(0)
    assert out.replace(tzinfo=None) == datetime(2026, 8, 28, 5, 17)


def test_as_published_utc_passes_none_through() -> None:
    """No timestamp stays no timestamp."""
    assert _as_published_utc(None) is None


# ---------------------------------------------------------------------------
# Adversarial (a) -- poisoned / Sybil probe
# ---------------------------------------------------------------------------


def test_adv_sybil_volume_inflates_the_count_and_is_not_defended() -> None:
    """Publishing a count makes forged VOLUME worth something.

    Before DASH-2 a forged complete batch could only move the average.
    Now it also raises the apparent support for that average.  Nothing
    here mitigates that -- signature verification and the un-gated
    published metric (DASH-1 Keystone sec 7.1) are the place for it.
    This test exists so the exposure is pinned, not so it looks solved.
    """
    honest = [_row(rate=9 / 50)]
    flooded = honest + [_row(rate=9 / 50) for _ in range(9)]
    w_honest = _compute_model_weather(_FakeRepo(honest), _MT)
    w_flooded = _compute_model_weather(_FakeRepo(flooded), _MT)
    assert w_honest.json_sample_count == 1
    assert w_flooded.json_sample_count == 10
    assert w_honest.recent_json_success_rate == (
        w_flooded.recent_json_success_rate
    )


def test_adv_forged_partial_cannot_pad_the_json_denominator() -> None:
    """Incomplete forged batches raise sample_count, never json count.

    The DASH-1 completeness guard is what holds here; DASH-2 must not
    quietly widen the denominator it protects.
    """
    rows = [_row()] + [_row(n=1.0) for _ in range(9)]
    w = _compute_model_weather(_FakeRepo(rows), _MT)
    assert w.sample_count == 10
    assert w.json_sample_count == 1


# ---------------------------------------------------------------------------
# Adversarial (b) -- provider change with no latency/uptime signal
# ---------------------------------------------------------------------------


def test_adv_provenance_does_not_alter_the_published_metrics() -> None:
    """Adding a denominator must not move the numerator.

    A real semantic collapse has to read the same after DASH-2 as
    before it; the detector consumes the raw wire value regardless.
    """
    collapsed = [_row(rate=0.0, length=12.0) for _ in range(4)]
    w = _compute_model_weather(_FakeRepo(collapsed), _MT)
    assert w.recent_json_success_rate == 0.0
    assert w.recent_avg_output_length == 12.0
    assert w.json_sample_count == 4


def test_adv_stored_rows_are_not_mutated_by_the_read() -> None:
    """The weather read stays a projection, never a write."""
    rows = [_row(ts=_T0)]
    _compute_model_weather(_FakeRepo(rows), _MT)
    assert rows[0].timestamp == _T0
    assert rows[0].timestamp.tzinfo is None


# ---------------------------------------------------------------------------
# Backward compatibility -- the response is additive
# ---------------------------------------------------------------------------


def test_response_still_constructs_without_provenance() -> None:
    """Existing callers that omit the new fields keep working."""
    w = ModelWeatherResponse(model_tuple=_MT, status="STABLE")
    assert w.sample_count == 0
    assert w.window_start is None
