"""
tests/test_dp_sensitivity.py
=============================
FIX-1 (REQ-PRIV-010): batch-aware DP sensitivity tests.

DS1 -- exact inverse-n scaling (property over n, both metrics)
DS2 -- n=1 degrades exactly to the former global worst-case bounds
DS3 -- invalid n rejected (0, negative)
DS4 -- unknown metric rejected
DS5a -- property: _laplace_noise scale is calibrated (MAD == b*ln2,
        checked at the n=1 worst-case scale b=4096, no clamping)
DS5b -- property: flush() noise deviation matches delta_f/EPSILON at
        n=100 (clamping negligible at that scale)
DS6 -- adversarial: larger batch => strictly quieter flush metrics;
       at n=100 the rate noise floor is below a 0.8%-scale drift signal

Test-design note (defect caught in first version): flush() clamps
metrics (max(0,.) and [0,1]), which truncates Laplace tails.  Noise-
scale assertions must either avoid the clamp region (rate=0.5, large n)
or test _laplace_noise directly.  Deviations measured against raw
values near a clamp boundary understate the true scale.
"""

from __future__ import annotations

import math
import random
from statistics import median

import pytest
from probe.canary import CanaryResult
from probe.privacy import (
    _METRIC_SENSITIVITY,
    EPSILON,
    MAX_OUTPUT_LENGTH,
    Aggregator,
    _laplace_noise,
    _metric_sensitivity,
)

MODEL = "anthropic/claude-sonnet-4@global"
SUITE = "v1.0.0"
LN2 = math.log(2.0)


def _result(
    i: int, output_length: int = 512, json_valid: bool = True
) -> CanaryResult:
    """One synthetic CanaryResult (no raw output, per privacy contract)."""
    return CanaryResult(
        timestamp=f"2026-07-15T12:{i // 60:02d}:{i % 60:02d}+00:00",
        model_tuple=MODEL,
        suite_version=SUITE,
        prompt_id=f"p{i:04d}",
        response_hash="c" * 64,
        output_length=output_length,
        json_valid=json_valid,
        latency_ms=-1,
    )


def _flush_metrics(n: int, seed: int) -> dict[str, float]:
    """Flush n results (half json_valid) with a seeded RNG.

    raw json_success_rate is ~0.5 (exactly 0.5 for even n), keeping the
    noised rate away from the [0,1] clamp boundaries so the observed
    deviation reflects the injected noise, not truncation.
    """
    agg = Aggregator(_rng=random.Random(seed))
    for i in range(n):
        agg.add_result(_result(i, json_valid=(i % 2 == 0)))
    return agg.flush(MODEL).metrics


# ---------------------------------------------------------------------------
# DS1 -- inverse-n scaling property
# ---------------------------------------------------------------------------


def test_metric_sensitivity_scales_inverse_n() -> None:
    """DS1: delta_f(metric, n) == base_delta_f / n exactly, for all n.

    #SG-TRACE: REQ-PRIV-010 | test: test_metric_sensitivity_scales_inverse_n
    """
    for metric, base in _METRIC_SENSITIVITY.items():
        for n in [1, 2, 3, 10, 50, 100, 200, 1000]:
            assert _metric_sensitivity(metric, n) == pytest.approx(base / n)


# ---------------------------------------------------------------------------
# DS2 -- n=1 degradation to former worst-case bounds
# ---------------------------------------------------------------------------


def test_metric_sensitivity_n1_equals_legacy_bounds() -> None:
    """DS2: n=1 reproduces the pre-FIX-1 global bounds exactly.

    #SG-TRACE: REQ-PRIV-010
    #   | assumption: single-record batches keep the conservative
    #     Phase-0 guarantee; the fix can only tighten noise, never
    #     weaken privacy
    #   | test: test_metric_sensitivity_n1_equals_legacy_bounds
    """
    assert _metric_sensitivity("avg_output_length", 1) == float(
        MAX_OUTPUT_LENGTH
    )
    assert _metric_sensitivity("json_success_rate", 1) == 1.0


# ---------------------------------------------------------------------------
# DS3 / DS4 -- invalid input rejection
# ---------------------------------------------------------------------------


def test_metric_sensitivity_rejects_invalid_n() -> None:
    """DS3: n < 1 raises ValueError (no silent zero/negative scale).

    #SG-TRACE: REQ-PRIV-010 | test: test_metric_sensitivity_rejects_invalid_n
    """
    for bad in [0, -1, -100]:
        with pytest.raises(ValueError):
            _metric_sensitivity("avg_output_length", bad)


def test_metric_sensitivity_rejects_unknown_metric() -> None:
    """DS4: unknown metric raises KeyError (no default sensitivity).

    #SG-TRACE: REQ-PRIV-010
    #   | test: test_metric_sensitivity_rejects_unknown_metric
    """
    with pytest.raises(KeyError):
        _metric_sensitivity("latency_ms", 10)


# ---------------------------------------------------------------------------
# DS5a -- _laplace_noise scale calibration (no clamping involved)
# ---------------------------------------------------------------------------


def test_laplace_noise_scale_calibrated_at_worst_case() -> None:
    """DS5a: MAD of _laplace_noise(b) == b*ln2 at b=4096 (n=1 scale).

    Tests the mechanism directly, without flush()'s clamps, because
    clamping truncates the tails and understates the observed scale.

    #SG-TRACE: REQ-PRIV-010
    #   | assumption: 8000 seeded draws give MAD within +-10% of truth
    #   | test: test_laplace_noise_scale_calibrated_at_worst_case
    """
    b = _metric_sensitivity("avg_output_length", 1) / EPSILON  # 4096.0
    assert b == pytest.approx(4096.0)
    rng = random.Random(1337)
    mad = median(abs(_laplace_noise(b, rng)) for _ in range(8000))
    assert mad == pytest.approx(b * LN2, rel=0.10)


# ---------------------------------------------------------------------------
# DS5b -- flush() noise calibration at n=100 (clamp-free regime)
# ---------------------------------------------------------------------------


def test_flush_noise_scale_matches_batch_sensitivity() -> None:
    """DS5b: empirical flush() noise MAD matches b*ln2 at n=100.

    With n=100 identical-length records, raw_avg=512 and b=20.48, so
    the max(0,.) clamp at 0 is ~25 MADs away -- truncation negligible.

    #SG-TRACE: REQ-PRIV-010
    #   | assumption: seeded RNG; 4000 flushes give MAD within +-25%
    #   | test: test_flush_noise_scale_matches_batch_sensitivity
    """
    n = 100
    raw_avg = 512.0
    b = _metric_sensitivity("avg_output_length", n) / EPSILON
    devs = [
        _flush_metrics(n, seed=seed)["avg_output_length"] - raw_avg
        for seed in range(4000)
    ]
    mad = median(abs(d) for d in devs)
    assert mad == pytest.approx(b * LN2, rel=0.25)


# ---------------------------------------------------------------------------
# DS6 -- adversarial: bigger batch strictly quieter, rate metric usable
# ---------------------------------------------------------------------------


def test_flush_noise_shrinks_with_batch_size() -> None:
    """DS6: n=100 rate noise is ~100x below n=1 and below drift scale.

    Adversarial framing: EXP-1A showed the n=1 worst-case bounds drown
    the drift signal (b_rate=0.5 saturates a [0,1] metric).  Two pins:
    (1) mechanism level, clamp-free: the injected noise scale shrinks
    exactly 100x from n=1 to n=100; (2) system level: the flushed rate
    metric at n=100 (raw_rate=0.5, away from clamp boundaries) has a
    median |noise| < 0.01, so a 0.8%-scale drift signal is no longer
    beneath the noise floor by construction.

    A flush-level n=1 comparison is deliberately NOT made on the rate
    metric: at raw_rate=1.0 the [0,1] clamp zeroes every positive draw
    (median |dev| is exactly 0.0), which understates the true n=1
    noise -- caught as a defect in the first version of this test.

    #SG-TRACE: REQ-PRIV-010
    #   | assumption: median |Laplace(0,b)| = b*ln2; b_rate(n=1)=0.5,
    #     b_rate(n=100)=0.005
    #   | test: test_flush_noise_shrinks_with_batch_size
    """
    # (1) Mechanism level: exact 100x scale ratio, no clamps involved.
    b1 = _metric_sensitivity("json_success_rate", 1) / EPSILON
    b100 = _metric_sensitivity("json_success_rate", 100) / EPSILON
    assert b1 == pytest.approx(0.5)
    assert b100 == pytest.approx(0.005)
    assert b1 / b100 == pytest.approx(100.0)
    rng = random.Random(2026)
    mad_1 = median(abs(_laplace_noise(b1, rng)) for _ in range(4000))
    rng = random.Random(2026)
    mad_100 = median(abs(_laplace_noise(b100, rng)) for _ in range(4000))
    assert mad_1 == pytest.approx(b1 * LN2, rel=0.10)
    assert mad_100 == pytest.approx(b100 * LN2, rel=0.10)
    assert mad_100 < mad_1 / 20.0

    # (2) System level: flushed rate noise floor at n=100.
    devs_100 = [
        _flush_metrics(100, seed=seed)["json_success_rate"] - 0.5
        for seed in range(1500)
    ]
    flush_mad_100 = median(abs(d) for d in devs_100)
    assert flush_mad_100 < 0.01
