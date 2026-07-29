"""
seismograph.engine.detector
============================
Single-metric CUSUM change-point detector with per-(model_tuple,
suite_version, metric_name) state management.

Algorithm
---------
Page-CUSUM over standardised observations z = (x - mu0) / sigma0:

    S+(n) = max(0, S+(n-1) + z(n) - k)   -- detects positive shifts
    S-(n) = max(0, S-(n-1) - z(n) - k)   -- detects negative shifts

Alert fires when S+(n) > h or S-(n) > h.

Default parameters (h=5.0, k=0.5) are conservative starting points
calibrated for standardised unit-variance observations.  Formal
threshold decisions must be recorded in data/drift_labels/ before any
production deployment.

Baseline phase
--------------
Each (model_tuple, suite_version, metric_name) stream accumulates
_MetricState.MIN_BASELINE_SAMPLES observations to estimate mu0 and
sigma0 before CUSUM becomes active.  Observations during the baseline
phase never generate alerts.

Suite scoping (ENG-1)
---------------------
``suite_version`` is part of the stream identity.  Observations produced
under different canary corpora are never mixed into one baseline, so a
corpus cutover (e.g. v1.1.0 -> v2.0.0) starts a fresh, cold baseline
instead of writing a step change into the incumbent stream.  The
parameter is defaulted to ``""`` everywhere (the legacy catch-all
bucket) so every pre-ENG-1 call site remains valid, exactly as
``metric_name`` was introduced in FIX-2.

Architectural notes
-------------------
This module implements single-metric time-series detection.  Cross-
observer agreement gating (ensuring a single org never promotes a
public alert) is handled in engine/correlation.py (AgreementScorer).
The two layers are intentionally separate: detector.py fires per-org
candidate alerts; correlation.py decides whether to surface them.

#SG-TRACE: REQ-ENGINE-006
#   | assumption: CUSUM h and k calibrated offline on labelled
#     drift_labels/ data; defaults are starting points only
#   | test: test_cusum_threshold_calibration
#SG-TRACE: REQ-ENGINE-009
#   | assumption: baseline of MIN_BASELINE_SAMPLES=10 is sufficient
#     for stable mu0/sigma0 estimates for Phase 0 mock data;
#     Phase 1 will tune this on real probe traffic
#   | test: test_cusum_baseline_stability
#SG-TRACE: REQ-ENGSCOPE-001
#   | assumption: the caller-asserted suite_version string is a
#     sufficient corpus label for stream identity; content-hash scoping
#     is stronger but needs a wire change (contract ENG-1 D1, deferred)
#   | test: test_suite_scoped_streams_are_independent
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Alert dataclass
# ---------------------------------------------------------------------------


@dataclass
class DriftAlert:
    """Emitted by CUSUMDetector when a change point is detected.

    Fields
    ------
    timestamp_ns:
        Monotonic nanosecond timestamp of the observation that tripped
        the threshold.
    model_tuple:
        The model identifier being monitored,
        e.g. "openai/gpt-4o@2025-08".
    metric_name:
        Which metric crossed the threshold,
        e.g. "json_success_rate".
    direction:
        "positive" if S+ > h (upward shift detected),
        "negative" if S- > h (downward shift detected).
    cusum_score:
        The CUSUM accumulator value at the time of alert.
    threshold:
        The h value that was exceeded.
    window_count:
        Total observations fed to this (model_tuple, suite_version,
        metric_name) stream since last reset, including baseline
        samples.
    suite_version:
        Canary suite version the drifting observations were produced
        under, e.g. "v1.1.0".  Empty string is the legacy catch-all
        bucket (callers that predate ENG-1).

    #SG-TRACE: REQ-ENGINE-010
    #   | assumption: direction field is sufficient to distinguish
    #     degradation (negative) from unexpected improvement (positive)
    #   | test: test_drift_alert_direction
    #SG-TRACE: REQ-ENGSCOPE-002
    #   | assumption: suite_version is appended LAST with a "" default so
    #     every existing positional and keyword construction of DriftAlert
    #     stays valid (contract C2)
    #   | test: test_drift_alert_legacy_construction_defaults_suite
    """

    timestamp_ns: int
    model_tuple: str
    metric_name: str
    direction: str  # "positive" | "negative"
    cusum_score: float
    threshold: float
    window_count: int
    suite_version: str = ""


# ---------------------------------------------------------------------------
# Per-stream CUSUM state (private)
# ---------------------------------------------------------------------------


class _MetricState:
    """CUSUM state for one (model_tuple, suite_version, metric_name) key.

    Baseline accumulation phase: first MIN_BASELINE_SAMPLES observations
    are used to compute mu0 and sigma0.  No alert can fire during this
    phase.  After baseline is finalised, each subsequent observation
    updates the CUSUM accumulators.

    #SG-TRACE: REQ-ENGINE-009
    #   | assumption: sigma0 clamped to 1.0 when near-zero to prevent
    #     division by zero on constant series (e.g. mock data with
    #     identical values)
    #   | test: test_cusum_constant_series_no_error
    """

    MIN_BASELINE_SAMPLES: int = 10

    def __init__(self, h: float, k: float) -> None:
        self.h = h
        self.k = k
        self._buf: list[float] = []  # baseline accumulation buffer
        self._mu0: float | None = None
        self._sigma0: float | None = None
        self._s_pos: float = 0.0
        self._s_neg: float = 0.0
        self._n: int = 0  # total observations (incl. baseline)

    @property
    def baseline_ready(self) -> bool:
        """True once mu0 and sigma0 have been estimated."""
        return self._mu0 is not None

    def _finalize_baseline(self) -> None:
        """Estimate mu0 and sigma0 from the buffered baseline window."""
        n = len(self._buf)
        mu = sum(self._buf) / n
        variance = (
            sum((x - mu) ** 2 for x in self._buf) / (n - 1) if n > 1 else 0.0
        )
        sigma = math.sqrt(variance)
        # Clamp sigma to prevent division-by-zero on constant series
        if sigma < 1e-9:
            sigma = 1.0
        self._mu0 = mu
        self._sigma0 = sigma

    def update(
        self,
        value: float,
        model_tuple: str,
        metric_name: str,
        timestamp_ns: int,
        suite_version: str = "",
    ) -> DriftAlert | None:
        """Process one observation.

        Returns a DriftAlert if a threshold is exceeded, else None.
        During the baseline phase always returns None.

        ``suite_version`` is carried through onto the emitted alert only;
        the CUSUM arithmetic (h, k, baseline window) is untouched by it,
        so detection power on a single stream is identical to pre-ENG-1.

        #SG-TRACE: REQ-ENGSCOPE-002
        #   | assumption: relabelling a stream must not change its
        #     detection threshold or delay -- suite_version is metadata
        #     on the alert, never an input to the accumulators
        #   | test: test_adv2_silent_provider_change_alerts_unchanged
        """
        self._n += 1

        # ---- Baseline accumulation phase ---------------------------------
        if not self.baseline_ready:
            self._buf.append(value)
            if len(self._buf) >= self.MIN_BASELINE_SAMPLES:
                self._finalize_baseline()
            return None

        # ---- CUSUM update ------------------------------------------------
        assert self._mu0 is not None and self._sigma0 is not None
        z = (value - self._mu0) / self._sigma0

        # Page-CUSUM accumulators
        self._s_pos = max(0.0, self._s_pos + z - self.k)
        self._s_neg = max(0.0, self._s_neg - z - self.k)

        # Check for positive shift
        if self._s_pos > self.h:
            return DriftAlert(
                timestamp_ns=timestamp_ns,
                model_tuple=model_tuple,
                metric_name=metric_name,
                direction="positive",
                cusum_score=self._s_pos,
                threshold=self.h,
                window_count=self._n,
                suite_version=suite_version,
            )

        # Check for negative shift
        if self._s_neg > self.h:
            return DriftAlert(
                timestamp_ns=timestamp_ns,
                model_tuple=model_tuple,
                metric_name=metric_name,
                direction="negative",
                cusum_score=self._s_neg,
                threshold=self.h,
                window_count=self._n,
                suite_version=suite_version,
            )

        return None


# ---------------------------------------------------------------------------
# CUSUMDetector -- public API
# ---------------------------------------------------------------------------


class CUSUMDetector:
    """Multi-stream CUSUM detector.

    Maintains independent _MetricState instances keyed by
    (model_tuple, suite_version, metric_name).  Each stream has its own
    baseline, mu0/sigma0 estimates, and S+/S- accumulators.

    Usage
    -----
    detector = CUSUMDetector(h=5.0, k=0.5)
    alert = detector.update("openai/gpt-4o@2025-08",
                            "json_success_rate",
                            0.65,
                            suite_version="v1.1.0")
    if alert:
        # hand alert to AgreementScorer in correlation.py

    Omitting ``suite_version`` puts the observation in the legacy ``""``
    bucket, which is what every pre-ENG-1 call site does.

    #SG-TRACE: REQ-ENGINE-006
    #   | assumption: h=5.0 and k=0.5 are reasonable defaults for
    #     standardised observations; must be tuned for production
    #   | test: test_cusum_stable_window_no_false_positive
    #SG-TRACE: REQ-ENGINE-011
    #   | assumption: reset() is called by the caller after a confirmed
    #     public alert to restart accumulation post-changepoint
    #   | test: test_cusum_reset_clears_state
    #SG-TRACE: REQ-ENGSCOPE-001
    #   | assumption: two batches identical except for suite_version warm
    #     two independent baselines and never contribute to one another's
    #     CUSUM score
    #   | test: test_suite_scoped_streams_are_independent
    """

    def __init__(
        self,
        h: float = 5.0,
        k: float = 0.5,
        baseline_samples: int | None = None,
    ) -> None:
        """Initialise the detector.

        Parameters
        ----------
        h:
            Detection threshold.  Alert fires when S+ > h or S- > h.
        k:
            Slack parameter (allowable drift before accumulation
            starts).  Typically 0.5 standard deviations.
        baseline_samples:
            Override the per-stream baseline window size.  Defaults to
            _MetricState.MIN_BASELINE_SAMPLES (10).  Use a larger value
            when the expected inter-observation noise is high relative
            to the drift signal (e.g., daily probes over 30 days).
        """
        self.h = h
        self.k = k
        self._baseline_samples: int = (
            baseline_samples
            if baseline_samples is not None
            else _MetricState.MIN_BASELINE_SAMPLES
        )
        self._states: dict[tuple[str, str, str], _MetricState] = {}

    def update(
        self,
        model_tuple: str,
        metric_name: str,
        value: float,
        timestamp_ns: int | None = None,
        suite_version: str = "",
    ) -> DriftAlert | None:
        """Feed one scalar observation to the appropriate stream.

        Creates a new stream on first call for this
        (model_tuple, suite_version, metric_name) triple.

        Parameters
        ----------
        model_tuple:
            Model identifier, e.g. "openai/gpt-4o@2025-08".
        metric_name:
            Metric being tracked, e.g. "json_success_rate".
        value:
            The observed metric value.
        timestamp_ns:
            Monotonic nanosecond timestamp.  Defaults to
            time.monotonic_ns() if not supplied.
        suite_version:
            Canary suite version the observation was produced under.
            Part of the stream identity: two otherwise identical
            observations under different suite versions warm two
            independent baselines.  Defaults to "" (legacy catch-all
            bucket) so pre-ENG-1 call sites keep working unchanged.

        Returns
        -------
        DriftAlert or None
            Alert if the CUSUM threshold was exceeded; None otherwise.
            None is always returned during the baseline phase.

        #SG-TRACE: REQ-ENGSCOPE-001
        #   | assumption: suite_version is appended after timestamp_ns so
        #     every existing positional call (mt, metric, value[, ts])
        #     is unchanged (contract C2)
        #   | test: test_legacy_update_call_lands_in_empty_suite_bucket
        """
        key = (model_tuple, suite_version, metric_name)
        if key not in self._states:
            state = _MetricState(h=self.h, k=self.k)
            state.MIN_BASELINE_SAMPLES = self._baseline_samples
            self._states[key] = state
        ts = timestamp_ns if timestamp_ns is not None else time.monotonic_ns()
        return self._states[key].update(
            value, model_tuple, metric_name, ts, suite_version
        )

    def reset(
        self,
        model_tuple: str,
        metric_name: str | None = None,
        suite_version: str | None = None,
    ) -> None:
        """Reset CUSUM state for a model_tuple.

        Parameters
        ----------
        model_tuple:
            Which model tuple to reset.
        metric_name:
            If provided, reset only this metric stream.
            If None, reset every metric for the selected suites.
        suite_version:
            If provided, reset only streams under this suite version.
            If None (the pre-ENG-1 behaviour), reset the selected
            metric(s) across ALL suite versions of this model_tuple.

        #SG-TRACE: REQ-ENGSCOPE-003
        #   | assumption: a legacy reset(mt, metric) call means "drop this
        #     metric everywhere", so it must span suites; narrowing to one
        #     suite is opt-in via the new parameter
        #   | test: test_reset_scopes_by_suite_version
        """
        keys = [
            k
            for k in self._states
            if k[0] == model_tuple
            and (suite_version is None or k[1] == suite_version)
            and (metric_name is None or k[2] == metric_name)
        ]
        for k in keys:
            del self._states[k]

    @property
    def tracked_streams(self) -> list[tuple[str, str, str]]:
        """Return all tracked (model_tuple, suite_version, metric_name)."""
        return list(self._states.keys())
