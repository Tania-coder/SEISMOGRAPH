"""
tests.test_detector_suite_scope
================================
Behavioural + adversarial tests for suite-scoped CUSUM streams (ENG-1).

engine/detector.py keys every stream on
``(model_tuple, suite_version, metric_name)``.  This file carries the
stream-identity coverage for that change; the cross-observer agreement
side lives in tests/test_agreement_scorer.py.

Test inventory (contract ENG-1 §5)
----------------------------------
  T1     40 observations split across two suites warm two independent
         baselines            -- test_suite_scoped_streams_are_independent
  T2     warmed+drifting suite alerts, fresh suite stays silent
                              -- test_drift_alerts_only_on_the_drifting_suite
  T3     legacy (no-suite) call sites still work
                 -- test_legacy_update_call_lands_in_empty_suite_bucket,
                    test_drift_alert_legacy_construction_defaults_suite
  ADV-2  silent provider change (only avg_output_length moves) is detected
         with the SAME score, window_count and delay as pre-ENG-1
                 -- test_adv2_silent_provider_change_alerts_unchanged

#SG-TRACE: REQ-ENGSCOPE-001
#SG-TRACE: REQ-ENGSCOPE-002
#SG-TRACE: REQ-ENGSCOPE-003
"""

from __future__ import annotations

from engine.detector import CUSUMDetector, DriftAlert

MODEL = "anthropic/claude-sonnet-4@global"
METRIC = "json_success_rate"
LEN_METRIC = "avg_output_length"
V1 = "v1.1.0"
V2 = "v2.0.0"

# A stable baseline window followed by a SMALL upward shift.  The shift is
# deliberately sub-obvious so the alert takes several observations to
# accumulate -- that delay is what ADV-2 pins down.
_BASELINE: list[float] = [
    500.0,
    505.0,
    495.0,
    510.0,
    490.0,
    502.0,
    498.0,
    507.0,
    493.0,
    500.0,
]
_SHIFTED: list[float] = [505.0] * 40


# ---------------------------------------------------------------------------
# T1 -- two suites, two independent baselines
# ---------------------------------------------------------------------------


def test_suite_scoped_streams_are_independent() -> None:
    """T1: 40 observations, half per suite -> two streams of 20 each.

    Neither stream reaches ``baseline_samples=30`` from the other's data.
    A pre-ENG-1 detector would have seen ONE stream of 40 and finalised
    its baseline across the corpus cutover.

    #SG-TRACE: REQ-ENGSCOPE-001
    #   | test: test_suite_scoped_streams_are_independent
    """
    det = CUSUMDetector(h=5.0, k=0.5, baseline_samples=30)
    for i in range(40):
        suite = V1 if i % 2 == 0 else V2
        det.update(
            model_tuple=MODEL,
            metric_name=METRIC,
            value=500.0 + i,
            timestamp_ns=i,
            suite_version=suite,
        )

    assert sorted(det.tracked_streams) == [
        (MODEL, V1, METRIC),
        (MODEL, V2, METRIC),
    ]
    state_v1 = det._states[(MODEL, V1, METRIC)]
    state_v2 = det._states[(MODEL, V2, METRIC)]
    assert state_v1._n == 20
    assert state_v2._n == 20
    # 20 < 30: neither borrowed the other's samples to finish its baseline.
    assert not state_v1.baseline_ready
    assert not state_v2.baseline_ready

    # Control: the same 40 observations under ONE suite DO finish a
    # baseline -- so the split is what kept them apart, not the count.
    control = CUSUMDetector(h=5.0, k=0.5, baseline_samples=30)
    for i in range(40):
        control.update(
            model_tuple=MODEL,
            metric_name=METRIC,
            value=500.0 + i,
            timestamp_ns=i,
            suite_version=V1,
        )
    assert control._states[(MODEL, V1, METRIC)].baseline_ready


def test_suite_scoped_streams_do_not_share_cusum_score() -> None:
    """One suite drifting hard leaves the other suite's accumulators at 0.

    #SG-TRACE: REQ-ENGSCOPE-001
    #   | test: test_suite_scoped_streams_do_not_share_cusum_score
    """
    det = CUSUMDetector(h=5.0, k=0.5, baseline_samples=10)
    for suite in (V1, V2):
        for i, value in enumerate(_BASELINE):
            det.update(
                model_tuple=MODEL,
                metric_name=LEN_METRIC,
                value=value,
                timestamp_ns=i,
                suite_version=suite,
            )
    # Only V1 receives the drifted values.
    for i, value in enumerate(_SHIFTED[:20]):
        det.update(
            model_tuple=MODEL,
            metric_name=LEN_METRIC,
            value=value,
            timestamp_ns=100 + i,
            suite_version=V1,
        )

    assert det._states[(MODEL, V1, LEN_METRIC)]._s_pos > 0.0
    assert det._states[(MODEL, V2, LEN_METRIC)]._s_pos == 0.0
    assert det._states[(MODEL, V2, LEN_METRIC)]._s_neg == 0.0


# ---------------------------------------------------------------------------
# T2 -- alert fires on the drifting suite only
# ---------------------------------------------------------------------------


def test_drift_alerts_only_on_the_drifting_suite() -> None:
    """T2: warmed+drifting v1.1.0 alerts; fresh v2.0.0 stays silent.

    This is the CAN-2 cutover case (contract §2 B1): the corpus changes
    and the detector must NOT read the step as a provider change.

    #SG-TRACE: REQ-ENGSCOPE-001
    #   | test: test_drift_alerts_only_on_the_drifting_suite
    """
    det = CUSUMDetector(h=5.0, k=0.5, baseline_samples=10)
    for i, value in enumerate(_BASELINE):
        det.update(
            model_tuple=MODEL,
            metric_name=LEN_METRIC,
            value=value,
            timestamp_ns=i,
            suite_version=V1,
        )

    v1_alert: DriftAlert | None = None
    v2_alerts: list[DriftAlert] = []
    for i, value in enumerate(_SHIFTED):
        got_v1 = det.update(
            model_tuple=MODEL,
            metric_name=LEN_METRIC,
            value=value,
            timestamp_ns=100 + i,
            suite_version=V1,
        )
        if got_v1 is not None and v1_alert is None:
            v1_alert = got_v1
        # The freshly cut-over corpus reports a WILDLY different absolute
        # level; it is still in its baseline phase and must not alert.
        got_v2 = det.update(
            model_tuple=MODEL,
            metric_name=LEN_METRIC,
            value=value * 3.0,
            timestamp_ns=100 + i,
            suite_version=V2,
        )
        if got_v2 is not None:
            v2_alerts.append(got_v2)

    assert v1_alert is not None, "the warmed, drifting suite must alert"
    assert v1_alert.suite_version == V1
    assert v1_alert.metric_name == LEN_METRIC
    assert v2_alerts == [], "a fresh suite must not alert on its own baseline"


# ---------------------------------------------------------------------------
# T3 -- backward compatibility (contract C2)
# ---------------------------------------------------------------------------


def test_legacy_update_call_lands_in_empty_suite_bucket() -> None:
    """T3: a pre-ENG-1 positional update() call still works.

    ``update(mt, metric, value, ts)`` -- no suite_version -- constructs the
    stream in the legacy "" bucket, distinct from any named suite.

    #SG-TRACE: REQ-ENGSCOPE-001
    #   | test: test_legacy_update_call_lands_in_empty_suite_bucket
    """
    det = CUSUMDetector(h=5.0, k=0.5, baseline_samples=3)
    det.update(MODEL, METRIC, 0.95, 1)
    det.update(MODEL, METRIC, 0.94, 2)
    assert det.tracked_streams == [(MODEL, "", METRIC)]

    det.update(MODEL, METRIC, 0.95, 3, V1)
    assert sorted(det.tracked_streams) == [
        (MODEL, "", METRIC),
        (MODEL, V1, METRIC),
    ]
    assert det._states[(MODEL, "", METRIC)]._n == 2
    assert det._states[(MODEL, V1, METRIC)]._n == 1


def test_drift_alert_legacy_construction_defaults_suite() -> None:
    """T3: DriftAlert built without suite_version defaults to "".

    #SG-TRACE: REQ-ENGSCOPE-002
    #   | test: test_drift_alert_legacy_construction_defaults_suite
    """
    alert = DriftAlert(
        timestamp_ns=1,
        model_tuple=MODEL,
        metric_name=METRIC,
        direction="negative",
        cusum_score=6.0,
        threshold=5.0,
        window_count=31,
    )
    assert alert.suite_version == ""


def test_reset_scopes_by_suite_version() -> None:
    """reset() spans all suites by default and narrows when asked.

    #SG-TRACE: REQ-ENGSCOPE-003
    #   | test: test_reset_scopes_by_suite_version
    """
    det = CUSUMDetector(h=5.0, k=0.5, baseline_samples=3)
    for suite in (V1, V2):
        det.update(MODEL, METRIC, 0.9, 1, suite)
        det.update(MODEL, LEN_METRIC, 500.0, 1, suite)

    # Narrow: one suite, one metric.
    det.reset(MODEL, METRIC, suite_version=V1)
    assert (MODEL, V1, METRIC) not in det.tracked_streams
    assert (MODEL, V2, METRIC) in det.tracked_streams
    assert (MODEL, V1, LEN_METRIC) in det.tracked_streams

    # Legacy two-arg call: that metric, across every suite.
    det.reset(MODEL, METRIC)
    assert (MODEL, V2, METRIC) not in det.tracked_streams

    # Model-wide: everything.
    det.reset(MODEL)
    assert det.tracked_streams == []


# ---------------------------------------------------------------------------
# ADV-2 -- silent provider change, no infra signal
# ---------------------------------------------------------------------------


def _run_length_stream(
    detector: CUSUMDetector,
    values: list[float],
    suite_version: str,
) -> tuple[int | None, DriftAlert | None]:
    """Feed avg_output_length while holding the infra metrics constant.

    Returns (index of the first alert, that alert).  json_success_rate and
    result_count are fed at a FIXED value on every step, so any alert must
    come from the semantic metric alone.
    """
    first_index: int | None = None
    first_alert: DriftAlert | None = None
    for i, value in enumerate(values):
        alert = detector.update(
            model_tuple=MODEL,
            metric_name=LEN_METRIC,
            value=value,
            timestamp_ns=i,
            suite_version=suite_version,
        )
        # Infra-style signals: perfectly flat, no error, no latency change.
        assert (
            detector.update(
                model_tuple=MODEL,
                metric_name=METRIC,
                value=0.99,
                timestamp_ns=i,
                suite_version=suite_version,
            )
            is None
        )
        assert (
            detector.update(
                model_tuple=MODEL,
                metric_name="result_count",
                value=10.0,
                timestamp_ns=i,
                suite_version=suite_version,
            )
            is None
        )
        if alert is not None and first_index is None:
            first_index, first_alert = i, alert
    return first_index, first_alert


def test_adv2_silent_provider_change_alerts_unchanged() -> None:
    """ADV-2: relabelling a stream must not cost detection power.

    Latency (result_count) and correctness (json_success_rate) are held
    perfectly constant; only avg_output_length shifts, under a SINGLE
    suite_version.  The CUSUM must alert exactly as it does on main:
    identical first-alert index, identical cusum_score, identical
    window_count.  The legacy run (no suite_version -> "" bucket) is the
    on-main reference; the suite-scoped run is the ENG-1 behaviour.

    This is a power-regression guard: a wider key space must not raise the
    detection threshold or delay the alert.

    #SG-TRACE: REQ-ENGSCOPE-002
    #   | test: test_adv2_silent_provider_change_alerts_unchanged
    """
    values = _BASELINE + _SHIFTED

    legacy = CUSUMDetector(h=5.0, k=0.5, baseline_samples=10)
    legacy_index, legacy_alert = _run_length_stream(legacy, values, "")

    scoped = CUSUMDetector(h=5.0, k=0.5, baseline_samples=10)
    scoped_index, scoped_alert = _run_length_stream(scoped, values, V1)

    assert legacy_alert is not None, (
        "reference run must detect the silent shift"
    )
    assert scoped_alert is not None, (
        "suite-scoped run must detect the same silent shift"
    )
    # No delay, no threshold change, no score change.
    assert scoped_index == legacy_index
    assert scoped_alert.cusum_score == legacy_alert.cusum_score
    assert scoped_alert.window_count == legacy_alert.window_count
    assert scoped_alert.threshold == legacy_alert.threshold == 5.0
    assert scoped_alert.direction == legacy_alert.direction == "positive"
    # Only the label differs.
    assert legacy_alert.suite_version == ""
    assert scoped_alert.suite_version == V1
    # And the infra streams genuinely never fired (no cross-metric leakage).
    assert scoped._states[(MODEL, V1, METRIC)]._s_pos == 0.0
    assert scoped._states[(MODEL, V1, "result_count")]._s_pos == 0.0
