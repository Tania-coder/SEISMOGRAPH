"""
Tests for the live provider adapter (probe/providers.py) and the
live wiring of probe.canary.execute_canary(mock=False).

All tests run fully OFFLINE via an injected fake transport. No network.

Adversarial coverage:
  - provider-side semantic change with identical latency profile must
    change the response hash AND output length (so the detector can fire)
    while producing no error -- i.e. a silent drift the canary still sees.
  - malformed / error responses must raise cleanly with no partial result
    and no payload leakage.

#SG-TRACE: REQ-CANARY-020 | test: test_provider_builds_openai_payload
#SG-TRACE: REQ-CANARY-021 | test: test_provider_forces_temperature_zero
#SG-TRACE: REQ-PRIV-020   | test: test_execute_canary_live_no_raw_output
"""

from __future__ import annotations

import json

import pytest
from probe.canary import CANARY_SUITE_V1, execute_canary
from probe.providers import (
    OpenAICompatibleProvider,
    ProviderError,
    model_name_from_tuple,
)


def _make_transport(content_for):
    """Build a fake transport returning an OpenAI-shaped completion.

    content_for: callable(payload_dict) -> str (the model 'output').
    Records every captured request on transport.captured.
    """
    captured: list[dict] = []

    def transport(url, headers, body, timeout):
        payload = json.loads(body.decode("utf-8"))
        captured.append({"url": url, "headers": headers, "payload": payload})
        text = content_for(payload)
        return {"choices": [{"message": {"content": text}}]}

    transport.captured = captured
    return transport


def test_model_name_from_tuple() -> None:
    assert model_name_from_tuple("openai/gpt-4o@2025-08") == "gpt-4o"
    assert model_name_from_tuple("ollama/llama3.1") == "llama3.1"
    assert model_name_from_tuple("gpt-4o") == "gpt-4o"


def test_provider_builds_openai_payload() -> None:
    tr = _make_transport(lambda p: "ok")
    prov = OpenAICompatibleProvider(
        base_url="http://x/v1", api_key="secret", transport=tr
    )
    raw, latency = prov.complete("m", "sys", "usr")
    assert raw == "ok"
    assert latency >= 0
    req = tr.captured[0]
    assert req["url"] == "http://x/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer secret"
    assert req["payload"]["messages"][0]["role"] == "system"
    assert req["payload"]["messages"][1]["content"] == "usr"


def test_provider_forces_temperature_zero() -> None:
    tr = _make_transport(lambda p: "ok")
    prov = OpenAICompatibleProvider(
        base_url="http://x/v1", max_tokens=20, transport=tr
    )
    prov.complete("m", "s", "u")
    payload = tr.captured[0]["payload"]
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 20


def test_provider_no_api_key_omits_auth_header() -> None:
    tr = _make_transport(lambda p: "ok")
    prov = OpenAICompatibleProvider(base_url="http://local/v1", transport=tr)
    prov.complete("m", "s", "u")
    assert "Authorization" not in tr.captured[0]["headers"]


def test_provider_timeout_raises_clean() -> None:
    def boom(url, headers, body, timeout):
        raise TimeoutError("slow")

    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=boom)
    with pytest.raises(ProviderError):
        prov.complete("m", "s", "u")


def test_provider_bad_schema_raises() -> None:
    def bad(url, headers, body, timeout):
        return {"unexpected": True}

    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=bad)
    with pytest.raises(ProviderError):
        prov.complete("m", "s", "u")


def test_execute_canary_live_returns_three_results() -> None:
    tr = _make_transport(lambda p: '{"persons": []}')
    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=tr)
    results = execute_canary("ollama/llama3.1", mock=False, provider=prov)
    assert len(results) == len(CANARY_SUITE_V1)
    assert all(r.latency_ms >= 0 for r in results)
    assert all(r.model_tuple == "ollama/llama3.1" for r in results)


def test_execute_canary_live_requires_provider() -> None:
    with pytest.raises(ValueError):
        execute_canary("ollama/llama3.1", mock=False, provider=None)


def test_execute_canary_live_no_raw_output() -> None:
    """The privacy invariant: no raw text on the result object."""
    tr = _make_transport(lambda p: "some secret model output")
    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=tr)
    results = execute_canary("ollama/llama3.1", mock=False, provider=prov)
    blob = json.dumps([r.to_dict() for r in results])
    assert "some secret model output" not in blob
    # only the hash and length survive
    assert all(len(r.response_hash) == 64 for r in results)


def test_adversarial_silent_drift_changes_hash_and_length() -> None:
    """Provider-side semantic shift, same latency profile, no error.

    Stable window vs drifted window must yield different hashes and
    different output lengths for the JSON canary -- the exact signal the
    CUSUM detector consumes. This is adversarial case (b): a change that
    emits no latency/uptime signal but shifts semantic output.
    """
    stable = _make_transport(lambda p: '{"persons": ["Marie Curie"]}')
    drift = _make_transport(
        lambda p: '{"persons": ["Marie Curie"], "extra": "DRIFTED"}'
    )
    prov_stable = OpenAICompatibleProvider("http://x/v1", transport=stable)
    prov_drift = OpenAICompatibleProvider("http://x/v1", transport=drift)

    r0 = execute_canary("ollama/m", mock=False, provider=prov_stable)
    r1 = execute_canary("ollama/m", mock=False, provider=prov_drift)

    fmt0 = next(x for x in r0 if x.prompt_id == "v1.0.0-format")
    fmt1 = next(x for x in r1 if x.prompt_id == "v1.0.0-format")
    assert fmt0.response_hash != fmt1.response_hash
    assert fmt0.output_length != fmt1.output_length
    # both remain valid JSON -> structural success, semantic drift caught
    assert fmt0.json_valid and fmt1.json_valid


def test_execute_canary_mock_still_works() -> None:
    """Offline mock path is unchanged and needs no provider."""
    results = execute_canary("openai/gpt-4o@2025-08", mock=True)
    assert len(results) == len(CANARY_SUITE_V1)
    assert all(r.latency_ms == -1 for r in results)


def test_provider_rejects_non_ascii_api_key() -> None:
    """Adversarial: a non-ASCII key (e.g. a Cyrillic placeholder)
    is rejected up front with a clean ProviderError and never
    reaches urllib (no opaque UnicodeEncodeError).
    """
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider(
            base_url="http://x/v1", api_key="ключ-placeholder"
        )
