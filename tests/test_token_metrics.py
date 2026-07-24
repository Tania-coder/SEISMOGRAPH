"""
tests.test_token_metrics
========================
Feature B (SG-FEAT-TOKENS-001): per-canary output_tokens /
reasoning_tokens capture and DP-noised aggregation, plus the additive
gateway metric-allowlist extension (REQ-GW-030) shared with Feature A.

All tests run fully OFFLINE (fake transports / TestClient). No network.

Covers (see /tmp/agents/engine/CONTRACT.md, section 3, Feature B):
  B1  usage fields captured from an OpenAI-compatible response
  B2  None-safe parsing (absent / partial / malformed usage)
  B3  avg_output_tokens emitted, clamped, DP-noised
  B4  all-None token fields -> metric key absent
  B5  batch-aware sensitivity for the three new metric names
  B6  SignalBatch + gateway accept the new metric keys
  B7  gateway still rejects unknown metric keys (allowlist additive,
      not open)
  B8  legacy payloads still return 202
  B9  ProbeSDK span attributes flow into CanaryResult token fields
  ADV(a) poisoned/Sybil single-org probe injecting drifted new-metric
      values cannot produce a public alert (quorum gate unchanged)

#SG-TRACE: REQ-TOKMET-001..011, REQ-GW-030 | tests below
"""

from __future__ import annotations

import hashlib
import random
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from gateway.main import app
from probe.canary import (
    SUITE_VERSION_V1_1,
    CanaryResult,
    execute_canary,
)
from probe.privacy import (
    MAX_TOKEN_COUNT,
    Aggregator,
    SignalBatch,
    _metric_sensitivity,
)
from probe.providers import OpenAICompatibleProvider, _parse_usage

MODEL = "openai/gpt-4o@2025-08"
SUITE = "v1.0.0"


def _result(
    i: int,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> CanaryResult:
    """Synthetic CanaryResult (no raw output, per privacy contract)."""
    return CanaryResult(
        timestamp=f"2026-07-24T13:{i // 60:02d}:{i % 60:02d}+00:00",
        model_tuple=MODEL,
        suite_version=SUITE,
        prompt_id=f"p{i:04d}",
        response_hash="e" * 64,
        output_length=256,
        json_valid=True,
        latency_ms=-1,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


# ---------------------------------------------------------------------------
# B1/B2 -- provider-level usage parsing
# ---------------------------------------------------------------------------


def test_usage_fields_none_safe() -> None:
    """B1/B2: usage parsing captures ints and never raises.

    #SG-TRACE: REQ-TOKMET-001 | test: (this)
    """
    # Full OpenAI-compatible usage block.
    assert _parse_usage(
        {
            "usage": {
                "completion_tokens": 17,
                "completion_tokens_details": {"reasoning_tokens": 5},
            }
        }
    ) == (17, 5)
    # No usage at all.
    assert _parse_usage({}) == (None, None)
    # Usage without details.
    assert _parse_usage({"usage": {"completion_tokens": 9}}) == (9, None)
    # Malformed levels: never raise, degrade to None.
    assert _parse_usage({"usage": "n/a"}) == (None, None)
    assert _parse_usage({"usage": {"completion_tokens": "9"}}) == (None, None)
    assert _parse_usage({"usage": {"completion_tokens": True}}) == (None, None)
    assert _parse_usage(
        {
            "usage": {
                "completion_tokens": 3.0,
                "completion_tokens_details": "none",
            }
        }
    ) == (3, None)


def test_execute_canary_captures_usage_tokens() -> None:
    """B1: live canaries carry per-canary token counters.

    #SG-TRACE: REQ-TOKMET-002 | test: (this)
    """

    def transport(url, headers, body, timeout):
        return {
            "choices": [{"message": {"content": '{"persons": []}'}}],
            "usage": {
                "completion_tokens": 21,
                "completion_tokens_details": {"reasoning_tokens": 8},
            },
        }

    prov = OpenAICompatibleProvider(
        base_url="http://x/v1", transport=transport
    )
    results = execute_canary(MODEL, mock=False, provider=prov)
    assert all(r.output_tokens == 21 for r in results)
    assert all(r.reasoning_tokens == 8 for r in results)


def test_execute_canary_usage_absent_is_none() -> None:
    """B2: providers that report no usage yield None (never 0-faked).

    #SG-TRACE: REQ-TOKMET-001 | test: (this)
    """

    def transport(url, headers, body, timeout):
        return {"choices": [{"message": {"content": "ok"}}]}

    prov = OpenAICompatibleProvider(
        base_url="http://x/v1", transport=transport
    )
    results = execute_canary(MODEL, mock=False, provider=prov)
    assert all(r.output_tokens is None for r in results)
    assert all(r.reasoning_tokens is None for r in results)


def test_canary_result_backward_compatible_defaults() -> None:
    """Old-style keyword construction still valid; to_dict None-safe.

    #SG-TRACE: REQ-TOOLCAN-010 | test: (this)
    """
    r = CanaryResult(
        timestamp="2026-07-24T00:00:00+00:00",
        model_tuple=MODEL,
        suite_version=SUITE,
        prompt_id="p1",
        response_hash="a" * 64,
        output_length=1,
        json_valid=False,
        latency_ms=-1,
    )
    assert r.tool_call_valid is None
    assert r.output_tokens is None
    assert r.reasoning_tokens is None
    d = r.to_dict()
    assert d["output_tokens"] is None and d["reasoning_tokens"] is None


# ---------------------------------------------------------------------------
# B3/B4/B5 -- aggregation with DP treatment
# ---------------------------------------------------------------------------


def test_token_metrics_clamped_and_noised() -> None:
    """B3: emitted, None->0, clamped to MAX_TOKEN_COUNT, DP-noised.

    #SG-TRACE: REQ-TOKMET-010, REQ-TOKMET-011 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(99))
    # One absurd counter (adversarial probe-side value) plus a None.
    agg.add_result(_result(0, output_tokens=10**9, reasoning_tokens=100))
    agg.add_result(_result(1, output_tokens=100, reasoning_tokens=None))
    batch = agg.flush(MODEL)

    assert "avg_output_tokens" in batch.metrics
    assert "avg_reasoning_tokens" in batch.metrics
    # Clamp bounds the mean: (8192 + 100) / 2 = 4146 raw, + Laplace
    # noise with scale (8192/2)/2.0 -- but never near 10**9 / 2.
    raw_clamped = (MAX_TOKEN_COUNT + 100) / 2
    assert (
        batch.metrics["avg_output_tokens"] < raw_clamped + 8 * MAX_TOKEN_COUNT
    )
    assert batch.metrics["avg_output_tokens"] >= 0.0
    # Noise perturbs: emitted != raw clamped means.
    assert batch.metrics["avg_output_tokens"] != pytest.approx(raw_clamped)
    assert batch.metrics["avg_reasoning_tokens"] != pytest.approx(50.0)
    assert batch.metrics["avg_reasoning_tokens"] >= 0.0


def test_token_metrics_absent_when_all_none() -> None:
    """B4: no token data anywhere -> keys absent (legacy key set).

    #SG-TRACE: REQ-TOKMET-011 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(3))
    for i in range(4):
        agg.add_result(_result(i))
    batch = agg.flush(MODEL)
    assert "avg_output_tokens" not in batch.metrics
    assert "avg_reasoning_tokens" not in batch.metrics
    assert set(batch.metrics) == {
        "avg_output_length",
        "json_success_rate",
        "result_count",
    }


def test_token_metrics_partial_none_still_emitted() -> None:
    """B3 edge: one reporting record is enough; None contributes 0.

    #SG-TRACE: REQ-TOKMET-011 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(11))
    agg.add_result(_result(0, output_tokens=40))
    agg.add_result(_result(1, output_tokens=None))
    batch = agg.flush(MODEL)
    assert "avg_output_tokens" in batch.metrics
    assert "avg_reasoning_tokens" not in batch.metrics


def test_metric_sensitivity_new_keys_scale() -> None:
    """B5: batch-aware sensitivity for the three new metric names.

    #SG-TRACE: REQ-PRIV-010, REQ-TOKMET-010 | test: (this)
    """
    for n in (1, 4, 50):
        assert _metric_sensitivity(
            "tool_call_validity_rate", n
        ) == pytest.approx(1.0 / n)
        assert _metric_sensitivity("avg_output_tokens", n) == pytest.approx(
            MAX_TOKEN_COUNT / n
        )
        assert _metric_sensitivity("avg_reasoning_tokens", n) == pytest.approx(
            MAX_TOKEN_COUNT / n
        )
    with pytest.raises(ValueError):
        _metric_sensitivity("avg_output_tokens", 0)


# ---------------------------------------------------------------------------
# B6/B7/B8 -- wire-format allowlists (probe SignalBatch + gateway)
# ---------------------------------------------------------------------------


def _signal_batch(metrics: dict[str, float]) -> SignalBatch:
    return SignalBatch(
        batch_id="12345678-1234-5678-1234-567812345678",
        client_id="87654321-4321-8765-4321-876543218765",
        window_start="2026-07-24T00:00:00+00:00",
        window_end="2026-07-24T01:00:00+00:00",
        model_tuple=MODEL,
        suite_version=SUITE_VERSION_V1_1,
        metrics=metrics,
        canary_hashes={"v1.1.0-toolcall": "f" * 64},
        result_count=4,
    )


def test_signal_batch_accepts_new_metric_keys() -> None:
    """B6 probe-side: new keys pass the SignalBatch allowlist.

    #SG-TRACE: REQ-GW-030 | test: (this)
    """
    batch = _signal_batch(
        {
            "avg_output_length": 100.0,
            "json_success_rate": 0.9,
            "result_count": 4.0,
            "tool_call_validity_rate": 0.75,
            "avg_output_tokens": 33.2,
            "avg_reasoning_tokens": 5.1,
        }
    )
    assert batch.metrics["tool_call_validity_rate"] == 0.75

    # Unknown keys are still a leakage path -> rejected.
    with pytest.raises(ValueError, match="unknown keys"):
        _signal_batch({"raw_prompt_text": 1.0})


def _gateway_payload(metrics: dict[str, float]) -> dict:
    return {
        "batch_id": "12345678-1234-5678-1234-567812345678",
        "client_id": "87654321-4321-8765-4321-876543218765",
        "window_start": "2026-07-24T00:00:00Z",
        "window_end": "2026-07-24T01:00:00Z",
        "model_tuple": MODEL,
        "suite_version": SUITE_VERSION_V1_1,
        "metrics": metrics,
        "canary_hashes": {"v1.1.0-toolcall": hashlib.sha256(b"x").hexdigest()},
        "result_count": 4,
    }


def test_gateway_accepts_new_metric_keys() -> None:
    """B6 gateway-side: additive allowlist -> 202 for new metrics.

    #SG-TRACE: REQ-GW-030 | test: (this)
    """
    payload = _gateway_payload(
        {
            "json_success_rate": 0.95,
            "avg_output_length": 512.0,
            "tool_call_validity_rate": 0.9,
            "avg_output_tokens": 30.0,
            "avg_reasoning_tokens": 4.0,
        }
    )
    with patch("gateway.main.verify_signature", return_value=True):
        with TestClient(app) as c:
            resp = c.post("/v1/signals", json=payload)
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "accepted"


def test_gateway_still_rejects_unknown_metric_key() -> None:
    """B7: the allowlist is additive, not open -- unknown keys 422.

    #SG-TRACE: REQ-GW-030, REQ-PRIV-001 | test: (this)
    """
    payload = _gateway_payload(
        {
            "json_success_rate": 0.95,
            "tool_call_validity_rate_raw_text": 0.1,
        }
    )
    with patch("gateway.main.verify_signature", return_value=True):
        with TestClient(app) as c:
            resp = c.post("/v1/signals", json=payload)
    assert resp.status_code == 422, resp.text


def test_gateway_accepts_legacy_payload() -> None:
    """B8: pre-feature payloads are untouched by the extension.

    #SG-TRACE: REQ-GW-030 | test: (this)
    """
    payload = _gateway_payload(
        {"json_success_rate": 0.95, "avg_output_length": 512.0}
    )
    payload["suite_version"] = "v1.0.0"
    with patch("gateway.main.verify_signature", return_value=True):
        with TestClient(app) as c:
            resp = c.post("/v1/signals", json=payload)
    assert resp.status_code == 202, resp.text


# ---------------------------------------------------------------------------
# B9 -- ProbeSDK span-attribute path
# ---------------------------------------------------------------------------


def _make_sdk(tmp_path):
    from probe.crypto import KeyManager
    from probe.sdk import ProbeConfig, ProbeSDK

    config = ProbeConfig(
        model_tuple=MODEL,
        suite_version_hash="a" * 64,
        gateway_endpoint="http://localhost:8000/v1/signals",
    )
    return ProbeSDK(
        config,
        _key_manager=KeyManager(key_path=tmp_path / ".seismograph_id"),
    )


def test_finish_span_captures_token_attributes(tmp_path) -> None:
    """B9: gen_ai.usage.* attributes flow into the staged result.

    #SG-TRACE: REQ-TOKMET-003 | test: (this)
    """
    sdk = _make_sdk(tmp_path)
    span = sdk.start_canary_span(prompt_count=1)
    span.attributes["gen_ai.usage.output_tokens"] = 128
    span.attributes["gen_ai.usage.reasoning_tokens"] = 32
    sdk.finish_canary_span(status_code="OK")

    result = sdk._aggregator._pending[MODEL][0]
    assert result.output_tokens == 128
    assert result.reasoning_tokens == 32
    assert result.tool_call_valid is None


def test_finish_span_absent_attributes_are_none(tmp_path) -> None:
    """B9 edge: no usage attributes -> None fields (no 0-faking).

    #SG-TRACE: REQ-TOKMET-003 | test: (this)
    """
    sdk = _make_sdk(tmp_path)
    sdk.start_canary_span(prompt_count=1)
    sdk.finish_canary_span(status_code="OK")

    result = sdk._aggregator._pending[MODEL][0]
    assert result.output_tokens is None
    assert result.reasoning_tokens is None
    assert result.tool_call_valid is None


def test_finish_span_captures_tool_call_valid(tmp_path) -> None:
    """SDK path for Feature A: explicit boolean attribute flows through.

    #SG-TRACE: REQ-TOOLCAN-012 | test: (this)
    """
    sdk = _make_sdk(tmp_path)
    span = sdk.start_canary_span(prompt_count=1)
    span.attributes["gen_ai.response.tool_call_valid"] = False
    sdk.finish_canary_span(status_code="OK")
    result = sdk._aggregator._pending[MODEL][0]
    assert result.tool_call_valid is False


# ---------------------------------------------------------------------------
# ADVERSARIAL (a) -- poisoned/Sybil probe on the NEW metrics
# ---------------------------------------------------------------------------


def test_sybil_single_client_new_metrics_no_public_alert() -> None:
    """CONTRACT adversarial (a): one poisoned probe floods drifted
    tool_call_validity_rate / avg_reasoning_tokens values.

    The new metrics ride the exact same pipeline as the old ones:
    Ed25519-signed batch -> allowlist -> per-(model,metric) CUSUM ->
    AgreementScorer population-scaled quorum.  A single client_id can
    fire LOCAL alerts but must NEVER promote to a PublicDriftAlert,
    so GET /v1/weather stays STABLE.

    #SG-TRACE: REQ-GW-030, REQ-ENGINE-012 | test: (this)
    """
    from engine.correlation import AgreementScorer
    from engine.detector import CUSUMDetector

    sybil = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    def payload(i: int, prefix: str, rate: float, reasoning: float) -> dict:
        p = _gateway_payload(
            {
                "tool_call_validity_rate": rate,
                "avg_reasoning_tokens": reasoning,
            }
        )
        p["batch_id"] = f"{prefix}{i:06d}-0000-0000-0000-000000000000"
        p["client_id"] = sybil
        return p

    with patch("gateway.main.verify_signature", return_value=True):
        with TestClient(app) as c:
            app.state.detector = CUSUMDetector(
                h=5.0, k=0.5, baseline_samples=3
            )
            app.state.scorer = AgreementScorer()

            # Baseline window: healthy values.
            for i in range(3):
                resp = c.post("/v1/signals", json=payload(i, "30", 0.95, 20.0))
                assert resp.status_code == 202, resp.text

            # Poisoned flood: collapsed validity, absurd reasoning.
            cusum_fired = False
            for i in range(15):
                resp = c.post(
                    "/v1/signals", json=payload(i, "31", 0.0, 8000.0)
                )
                assert resp.status_code == 202, resp.text
                if resp.json().get("alerts"):
                    cusum_fired = True

            assert cusum_fired, (
                "local CUSUM must fire on the injected drift (the "
                "poison IS detected locally)"
            )

            # But: no quorum -> no public alert -> STABLE weather.
            weather = c.get("/v1/weather")

    assert weather.status_code == 200
    entry = next(
        (e for e in weather.json() if e["model_tuple"] == MODEL), None
    )
    assert entry is not None
    assert entry["status"] == "STABLE", (
        "single-org poison on NEW metrics must not reach the public "
        f"dashboard; got {entry['status']!r}"
    )
    assert entry["last_alert_timestamp"] is None


def test_sybil_cannot_smuggle_raw_text_via_new_metrics() -> None:
    """CONTRACT adversarial (a), schema level: the new metric names do
    not open a raw-text channel -- values must be JSON numbers and any
    non-allowlisted key still 422s.

    #SG-TRACE: REQ-GW-030, REQ-PRIV-001 | test: (this)
    """
    # Non-numeric value in a new metric key -> 422 (pydantic float).
    bad_value = _gateway_payload({"tool_call_validity_rate": 0.5})
    bad_value["metrics"] = {"tool_call_validity_rate": "raw model output"}
    # Unknown key crafted to look like a new metric -> 422.
    bad_key = _gateway_payload(
        {"json_success_rate": 0.5, "avg_output_tokens_text": 1.0}
    )
    with patch("gateway.main.verify_signature", return_value=True):
        with TestClient(app) as c:
            assert c.post("/v1/signals", json=bad_value).status_code == 422
            assert c.post("/v1/signals", json=bad_key).status_code == 422
