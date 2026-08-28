"""DASH-1: scorable-base normalisation of the published JSON rate.

The wire metric ``json_success_rate`` is a mean over the FULL canary
batch, but ``json_valid`` is scored only for ``structured_output``
prompts.  Its ceiling is therefore scorable/total (9/50 = 0.18 for
suite v2.0.0), not 1.0.  These tests pin the read-side rescaling that
turns it into a true [0, 1] rate, and pin that the detector input is
NOT rescaled.

#SG-TRACE: REQ-DASH-003
"""

from datetime import datetime

from engine.repository import SignalRow
from gateway.main import _compute_model_weather, _scorable_json_rate

_MT = "google/gemini-3.5-flash-lite"


def _row(
    rate: float | None,
    n: float = 50.0,
    suite: str = "v2.0.0",
    length: float | None = 150.0,
) -> SignalRow:
    """Build a SignalRow with only the fields DASH-1 reads."""
    return SignalRow(
        batch_id="b",
        model_tuple=_MT,
        timestamp=datetime(2026, 8, 11, 12, 0, 0),
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
# T1/T2 -- the ceiling maps to 1.0 and the scale is linear
# ---------------------------------------------------------------------------


def test_scorable_json_rate_normalises_v2_ceiling_to_one() -> None:
    """9/50 is 100% validity on every prompt that can score."""
    assert _scorable_json_rate(9 / 50, 50.0, "v2.0.0") == 1.0


def test_scorable_json_rate_is_linear_below_the_ceiling() -> None:
    """Half the scorable prompts valid -> 0.5, not 0.09."""
    assert _scorable_json_rate(0.09, 50.0, "v2.0.0") == 0.5


def test_scorable_json_rate_handles_legacy_suite_sizes() -> None:
    """v1.0.0 is 1 scorable prompt of 3; v1.1.0 is 1 of 4."""
    assert _scorable_json_rate(1 / 3, 3.0, "v1.0.0") == 1.0
    assert _scorable_json_rate(0.25, 4.0, "v1.1.0") == 1.0


# ---------------------------------------------------------------------------
# T3 -- DP noise can overshoot the ceiling; the result must stay in [0, 1]
# ---------------------------------------------------------------------------


def test_scorable_json_rate_clamps_dp_overshoot() -> None:
    """A noised batch rate above its ceiling clamps to 1.0."""
    assert _scorable_json_rate(0.20, 50.0, "v2.0.0") == 1.0


def test_scorable_json_rate_clamps_negative_noise_to_zero() -> None:
    """Laplace noise is two-sided; a negative rate clamps to 0.0."""
    assert _scorable_json_rate(-0.01, 50.0, "v2.0.0") == 0.0


# ---------------------------------------------------------------------------
# T4/T5 -- uninterpretable rows are excluded, never published on a guess
# ---------------------------------------------------------------------------


def test_unknown_suite_version_is_excluded() -> None:
    """A suite the gateway has not been taught yields None."""
    assert _scorable_json_rate(0.5, 50.0, "v9.9.9") is None


def test_legacy_empty_suite_version_is_excluded() -> None:
    """Pre-ENG-1 rows carry "" and have no known scorable count."""
    assert _scorable_json_rate(0.5, 50.0, "") is None


def test_missing_rate_or_empty_batch_is_excluded() -> None:
    """None rate, or a non-positive n, cannot be rescaled."""
    assert _scorable_json_rate(None, 50.0, "v2.0.0") is None
    assert _scorable_json_rate(0.18, 0.0, "v2.0.0") is None
    assert _scorable_json_rate(0.18, None, "v2.0.0") is None


def test_weather_returns_none_when_no_row_is_interpretable() -> None:
    """All-unknown history publishes nothing, not a wrong number."""
    repo = _FakeRepo([_row(0.18, suite="v9.9.9"), _row(0.18, suite="")])
    out = _compute_model_weather(repo, _MT)
    assert out.recent_json_success_rate is None


# ---------------------------------------------------------------------------
# T6 -- normalise per row, then average (never average first)
# ---------------------------------------------------------------------------


def test_mixed_suite_versions_normalise_per_row_before_averaging() -> None:
    """A v1.1.0 row and a v2.0.0 row are averaged on a common scale.

    Raw means (0.25 and 0.09) would average to 0.17, which is
    meaningless.  Normalised they are 1.0 and 0.5 -> 0.75.
    """
    repo = _FakeRepo(
        [
            _row(0.25, n=4.0, suite="v1.1.0"),
            _row(0.09, n=50.0, suite="v2.0.0"),
        ]
    )
    out = _compute_model_weather(repo, _MT)
    assert out.recent_json_success_rate == 0.75


def test_uninterpretable_rows_do_not_drag_the_average() -> None:
    """An excluded row must not be counted as a zero."""
    repo = _FakeRepo([_row(0.18), _row(0.18, suite="v9.9.9")])
    out = _compute_model_weather(repo, _MT)
    assert out.recent_json_success_rate == 1.0


# ---------------------------------------------------------------------------
# T7 -- READ-SIDE ONLY: the stored/detector value must stay raw
# ---------------------------------------------------------------------------


def test_normalisation_does_not_mutate_the_stored_row() -> None:
    """DASH-1 is a read-side projection, not a rewrite.

    Rescaling the value the detector consumes would contaminate the
    live CUSUM baseline -- the PRIV-011 cutover failure mode.  This
    guards that the row leaves the read path byte-identical.
    """
    row = _row(0.18)
    repo = _FakeRepo([row])

    out = _compute_model_weather(repo, _MT)

    assert row.json_success_rate == 0.18
    assert out.recent_json_success_rate == 1.0
    assert out.recent_json_success_rate != row.json_success_rate


# ---------------------------------------------------------------------------
# ADVERSARIAL (a) -- a forged batch cannot manufacture an out-of-range rate
# ---------------------------------------------------------------------------


def test_adv_forged_batch_cannot_exceed_the_clamp() -> None:
    """A forged batch cannot manufacture a flattering public number.

    A Sybil probe claiming suite v2.0.0 at n=1 with rate 1.0 is
    rejected outright by the completeness guard, so it never reaches
    the published average.  A forged COMPLETE batch is still accepted
    -- signature and reputation weighting are the defence there, not
    this function -- but it remains bounded in [0, 1].

    Noted honestly: the published metric has never been quorum-gated;
    only DRIFTING status is.  Pre-existing, recorded as a known
    limitation, not introduced by DASH-1.
    """
    assert _scorable_json_rate(1.0, 1.0, "v2.0.0") is None

    forged_complete = _scorable_json_rate(1.0, 50.0, "v2.0.0")
    assert forged_complete is not None
    assert 0.0 <= forged_complete <= 1.0


def test_adv_real_validity_collapse_still_moves_the_number() -> None:
    """Normalisation is monotone, so a real collapse still shows."""
    healthy = _scorable_json_rate(0.18, 50.0, "v2.0.0")
    collapsed = _scorable_json_rate(0.0, 50.0, "v2.0.0")
    assert healthy == 1.0
    assert collapsed == 0.0


# ---------------------------------------------------------------------------
# ADVERSARIAL (b) -- a PARTIAL suite run has an unknown scorable count
# ---------------------------------------------------------------------------


def test_partial_batch_is_excluded() -> None:
    """A partial v2.0.0 batch must not be published on the full base.

    Defect caught in Stage 3: a 3-record partial whose single scorable
    prompt was valid (true rate 100%) rescaled to 1/9 = 11%.  Only a
    complete suite run contains exactly `scorable` scorable records, so
    anything else is excluded.  execute_canary_strict guarantees
    completeness for compliant probes; this guard does not trust the
    public ingest path to be strict.
    """
    assert _scorable_json_rate(1 / 3, 3.0, "v2.0.0") is None
    assert _scorable_json_rate(0.18, 49.0, "v2.0.0") is None
    assert _scorable_json_rate(0.18, 50.0, "v2.0.0") == 1.0


def test_partial_batch_does_not_reach_the_published_average() -> None:
    """One complete row plus one partial row publishes the complete one."""
    repo = _FakeRepo([_row(0.18), _row(1 / 3, n=3.0)])
    out = _compute_model_weather(repo, _MT)
    assert out.recent_json_success_rate == 1.0
