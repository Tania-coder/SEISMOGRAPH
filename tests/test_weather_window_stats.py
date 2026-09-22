"""REPORT-2: every collection figure the report quotes, recomputed.

Keystone CLAMP-1 sec 7, accepted by signature: a number that appears
in a published artefact has an instrument that recomputes it in the
gate.  Weather Report #1 did its window arithmetic by hand, in prose.
These tests pin the derivations that Weather Report #2 quotes, against
the two archived /v1/weather snapshots the report cites.

The pair of snapshots is the point.  On 2026-09-09 the mistral leg
published STABLE with a window 176.0 h old; on 2026-09-22 the same leg
published STALE at 73.2 h.  Nothing about the leg improved -- DASH-3
landed in between.  Both rows publish sample_count 10.  The tests
below pin that contrast so that a regression in DASH-3, in the clamp,
or in the probe schedule turns the gate red rather than turning a
published report quietly wrong.

#SG-TRACE: REQ-REPORT2-001
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from gateway.main import STALE_AFTER_HOURS
from probe.privacy import MAX_OUTPUT_LENGTH

# scripts/ is not a package (no __init__.py), so the instrument is
# loaded by path, exactly as tests/test_clamp_saturation.py loads its
# own.  Importing it as `scripts.x` happens to work under implicit
# namespace packages on some interpreters and not others; the gate
# must not depend on which one is running.
_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "weather_window_stats.py"


def _load():
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    spec = importlib.util.spec_from_file_location("wwstats", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: @dataclass resolves the module out of
    # sys.modules while the class body is executing, and a module
    # loaded by path is not there unless it is put there.  Omitting
    # this raised AttributeError at collection time, not at use.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_M = _load()

DARK_BELOW = _M.DARK_BELOW
DEGRADED_BELOW = _M.DEGRADED_BELOW
WorkflowScheduleError = _M.WorkflowScheduleError
leg_window = _M.leg_window
nominal_interval_hours = _M.nominal_interval_hours
render = _M.render
snapshot_windows = _M.snapshot_windows

_EVIDENCE = _ROOT / "docs" / "evidence"
_SNAP_0922 = _EVIDENCE / "weather-2026-09-22T104310Z.json"
_SNAP_0909 = _EVIDENCE / "weather-2026-09-09T173824Z.json"
_READ_0909 = datetime(2026, 9, 9, 17, 38, 24, tzinfo=timezone.utc)

_GOOGLE = "google/gemini-3.5-flash-lite"
_MISTRAL = "mistral/mistral-small-latest"


def _by_tuple(windows):
    return {w.model_tuple: w for w in windows}


# --------------------------------------------------------------------
# The snapshots the report cites
# --------------------------------------------------------------------


def test_both_snapshots_are_committed():
    """A report may cite only evidence that ships with the repo."""
    assert _SNAP_0922.is_file()
    assert _SNAP_0909.is_file()


def test_report2_google_figures():
    """google, 2026-09-22: 119.97 h over 10 samples, 13.33 h mean."""
    w = _by_tuple(snapshot_windows(_SNAP_0922))[_GOOGLE]
    assert w.sample_count == 10
    assert w.span_hours == pytest.approx(119.97, abs=0.01)
    assert w.mean_interval_hours == pytest.approx(13.33, abs=0.01)
    assert w.collection_rate == pytest.approx(0.9003, abs=0.0001)
    assert w.collection_class == "NOMINAL"
    assert w.age_hours == pytest.approx(0.68, abs=0.01)
    assert w.age_source == "published"
    assert w.published_status == "STABLE"
    assert w.status_agrees_with_age is True


def test_report2_mistral_figures():
    """mistral, 2026-09-22: dark since 09-19, and the board says so."""
    w = _by_tuple(snapshot_windows(_SNAP_0922))[_MISTRAL]
    assert w.sample_count == 10
    assert w.span_hours == pytest.approx(407.88, abs=0.01)
    assert w.mean_interval_hours == pytest.approx(45.32, abs=0.01)
    assert w.collection_rate == pytest.approx(0.2648, abs=0.0001)
    assert w.collection_class == "DARK"
    assert w.age_hours == pytest.approx(73.19, abs=0.01)
    assert w.published_status == "STALE"
    assert w.status_agrees_with_age is True


def test_report2_mistral_window_start_is_the_september_freeze():
    """The window still opens at the outage timestamp from Report #1.

    Ten rows in seventeen days is why: the last-10 window has not
    accumulated enough new rows to evict 2026-09-02.
    """
    w = _by_tuple(snapshot_windows(_SNAP_0922))[_MISTRAL]
    assert w.window_start.startswith("2026-09-02T09:38:39")


def test_the_dash3_defect_is_pinned_as_history():
    """2026-09-09: a 176 h old window published STABLE.

    This is the measurement DASH-3 was built from.  It is pinned here
    so that the contrast Report #2 draws is recomputed, not recalled.
    """
    legs = _by_tuple(snapshot_windows(_SNAP_0909, _READ_0909))
    mistral = legs[_MISTRAL]
    assert mistral.published_status == "STABLE"
    assert mistral.age_hours == pytest.approx(176.00, abs=0.01)
    assert mistral.age_hours > STALE_AFTER_HOURS
    assert mistral.status_agrees_with_age is False
    # ... while its collection rate inside that window looked healthy.
    assert mistral.collection_class == "NOMINAL"


def test_the_same_leg_now_agrees_with_its_own_age():
    """The pair, stated as one assertion: the board learned to say it."""
    then = _by_tuple(snapshot_windows(_SNAP_0909, _READ_0909))[_MISTRAL]
    now = _by_tuple(snapshot_windows(_SNAP_0922))[_MISTRAL]
    assert then.sample_count == now.sample_count == 10
    assert then.status_agrees_with_age is False
    assert now.status_agrees_with_age is True


# --------------------------------------------------------------------
# Binding to live constants, not to numbers typed into a report
# --------------------------------------------------------------------


def test_nominal_interval_comes_from_the_workflow():
    """Twice a day, parsed from the cron, not restated here."""
    assert nominal_interval_hours() == pytest.approx(12.0)


def test_a_changed_schedule_is_refused_not_guessed(tmp_path):
    """A cadence this instrument cannot parse must raise."""
    bad = tmp_path / "probe_weather.yml"
    bad.write_text('    - cron: "*/30 * * * *"\n', encoding="utf-8")
    with pytest.raises(WorkflowScheduleError):
        nominal_interval_hours(bad)

    none = tmp_path / "no_cron.yml"
    none.write_text("on: workflow_dispatch\n", encoding="utf-8")
    with pytest.raises(WorkflowScheduleError):
        nominal_interval_hours(none)


def test_saturation_bound_uses_live_clamp():
    """The bound moves with probe.privacy, not with a report."""
    w = _by_tuple(snapshot_windows(_SNAP_0922))[_GOOGLE]
    assert w.max_output_length == MAX_OUTPUT_LENGTH
    assert w.saturation_upper_bound == pytest.approx(
        w.avg_output_length / MAX_OUTPUT_LENGTH
    )
    # The published G-31 bound, to the digit the report may quote.
    assert w.saturation_upper_bound == pytest.approx(0.4193, abs=0.0001)


def test_stale_agreement_uses_live_threshold():
    """The agreement check moves with DASH-3's threshold."""
    w = _by_tuple(snapshot_windows(_SNAP_0922))[_MISTRAL]
    assert w.stale_after_hours == STALE_AFTER_HOURS
    assert w.age_hours > STALE_AFTER_HOURS


# --------------------------------------------------------------------
# Adversarial and edge cases
# --------------------------------------------------------------------


def _row(**kw):
    base = {
        "model_tuple": "x/y",
        "status": "STABLE",
        "sample_count": 10,
        "recent_avg_output_length": 100.0,
        "window_start": "2026-09-01T00:00:00Z",
        "window_end": "2026-09-05T12:00:00Z",
    }
    base.update(kw)
    return base


def test_counts_cannot_witness_collection_loss():
    """Identical counts, opposite collection classes.

    The Report #1 finding, as a property: a run discarded for retry
    exhaustion writes no row, so sample_count is blind to it by
    construction.  Only the bounds separate these two legs.
    """
    healthy = leg_window(_row(), nominal=12.0)
    dark = leg_window(_row(window_end="2026-09-19T00:00:00Z"), nominal=12.0)
    assert healthy.sample_count == dark.sample_count == 10
    assert healthy.collection_class == "NOMINAL"
    assert dark.collection_class == "DARK"


def test_a_dark_leg_is_never_classified_nominal():
    """The adversarial row: healthy counts, a window a month wide."""
    w = leg_window(_row(window_end="2026-10-01T00:00:00Z"), nominal=12.0)
    assert w.collection_rate < DARK_BELOW
    assert w.collection_class == "DARK"


def test_classification_vocabulary_is_disjoint_from_status():
    """The instrument never re-labels a leg 'STABLE'.

    A leg that stopped collecting is not stable; it is unmeasured.
    The published status is quoted back verbatim and never recycled as
    a verdict of this instrument's own.
    """
    classes = set()
    for snap, read_at in ((_SNAP_0922, None), (_SNAP_0909, _READ_0909)):
        for w in snapshot_windows(snap, read_at):
            classes.add(w.collection_class)
    assert classes <= {"NOMINAL", "DEGRADED", "DARK", "UNDETERMINED"}
    assert not classes & {"STABLE", "DRIFTING", "STALE"}


def test_degraded_band_sits_between_nominal_and_dark():
    assert 0.0 < DARK_BELOW < DEGRADED_BELOW < 1.0


def test_one_sample_bounds_no_interval():
    """n-1 intervals, so a single sample must not divide by zero."""
    w = leg_window(_row(sample_count=1), nominal=12.0)
    assert w.mean_interval_hours is None
    assert w.collection_rate is None
    assert w.collection_class == "UNDETERMINED"


def test_zero_samples_are_undetermined_not_zero():
    w = leg_window(_row(sample_count=0), nominal=12.0)
    assert w.collection_class == "UNDETERMINED"


def test_published_age_wins_over_read_at():
    """A snapshot that carries its own age is not second-guessed."""
    w = leg_window(
        _row(window_age_hours=5.0),
        read_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        nominal=12.0,
    )
    assert w.age_hours == pytest.approx(5.0)
    assert w.age_source == "published"


def test_age_is_unavailable_rather_than_invented():
    """Pre-DASH-3 snapshot, no --read-at: refuse to guess."""
    w = leg_window(_row(), nominal=12.0)
    assert w.age_hours is None
    assert w.age_source == "unavailable"
    assert w.status_agrees_with_age is None


def test_render_states_the_provenance_of_every_constant():
    windows = snapshot_windows(_SNAP_0922)
    text = render(_SNAP_0922, windows)
    assert "probe.privacy, live" in text
    assert "gateway.main, live" in text
    assert "probe_weather.yml cron, live" in text
    assert "NOT measured" in text


def test_snapshot_files_are_valid_published_rows():
    """Guard the evidence itself: the fields the report quotes exist."""
    required = {
        "model_tuple",
        "status",
        "sample_count",
        "recent_avg_output_length",
        "window_start",
        "window_end",
    }
    for snap in (_SNAP_0922, _SNAP_0909):
        rows = json.loads(snap.read_text(encoding="utf-8"))
        assert rows, f"{snap.name} is empty"
        for row in rows:
            assert required <= set(row), snap.name


# --------------------------------------------------------------------
# The published artefact itself
# --------------------------------------------------------------------

_REPORT_2 = _ROOT / "docs" / "reports" / "2026-09-22-weather-report-02.md"


def test_report2_quotes_only_figures_the_instrument_reproduces():
    """Close the loop the CLAMP-1 rule opens.

    The rule accepted by signature is that a number in a published
    artefact has an instrument that recomputes it in the gate.  The
    tests above pin the instrument.  This one pins the ARTEFACT to the
    instrument: if the clamp, the staleness threshold or the probe
    schedule moves, the report stops matching its own evidence and the
    gate names the file, rather than leaving a published number
    quietly wrong on a platform that will not re-run anything.
    """
    if not _REPORT_2.is_file():
        pytest.skip("Weather Report #2 not yet in the repository")
    text = _REPORT_2.read_text(encoding="utf-8")

    now = _by_tuple(snapshot_windows(_SNAP_0922))
    then = _by_tuple(snapshot_windows(_SNAP_0909, _READ_0909))

    expected = {
        "mistral age, 2026-09-09": f"{then[_MISTRAL].age_hours:.2f} h",
        "mistral age, 2026-09-22": f"{now[_MISTRAL].age_hours:.2f} h",
        "mistral span, 2026-09-09": f"{then[_MISTRAL].span_hours:.2f} h",
        "mistral span, 2026-09-22": f"{now[_MISTRAL].span_hours:.2f} h",
        "mistral interval, then": (
            f"{then[_MISTRAL].mean_interval_hours:.2f} h"
        ),
        "mistral interval, now": (
            f"{now[_MISTRAL].mean_interval_hours:.2f} h"
        ),
        "nominal interval": (f"{now[_MISTRAL].nominal_interval_hours:.2f} h"),
        "mistral rate, then": f"{then[_MISTRAL].collection_rate:.4f}",
        "mistral rate, now": f"{now[_MISTRAL].collection_rate:.4f}",
        "staleness threshold": f"{int(STALE_AFTER_HOURS)} hours",
        "google saturation bound": (
            f"{now[_GOOGLE].saturation_upper_bound * 100:.1f}%"
        ),
        "mistral saturation bound": (
            f"{now[_MISTRAL].saturation_upper_bound * 100:.1f}%"
        ),
    }
    missing = {
        name: value for name, value in expected.items() if value not in text
    }
    assert not missing, (
        "Weather Report #2 quotes figures this instrument no longer "
        f"reproduces: {missing}. Either the report is stale or a live "
        "constant moved; fix the report, never the pin."
    )


def test_report2_states_both_snapshots_it_rests_on():
    """A reader must be able to recompute it without asking me."""
    if not _REPORT_2.is_file():
        pytest.skip("Weather Report #2 not yet in the repository")
    text = _REPORT_2.read_text(encoding="utf-8")
    assert _SNAP_0922.name in text
    assert _SNAP_0909.name in text
    assert "weather_window_stats.py" in text
