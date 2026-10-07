"""
COMPARE-1 transport additions in probe/providers.py.

Fully offline: fake transports and a monkeypatched urlopen. No network.

Covers:
  - backward compatibility: default payload and old CompletionResult
    construction are unchanged (canary contract REQ-CANARY-021 holds);
  - finish_reason / returned model / null content captured as data;
  - send_temperature=False omits the parameter (COMPARE-1 section 6);
  - provider error codes extracted from the HTTP error body, sanitised
    so free text that may echo the request or the key is never kept.

Adversarial: an error body whose message echoes the prompt and the API
key must leave neither in the exception string nor in error_code.

#SG-TRACE: REQ-COMPARE-020 | test: test_transport_http_error_extracts_code
#SG-TRACE: REQ-COMPARE-021 | test: test_completion_result_old_construction_still_valid
#SG-TRACE: REQ-COMPARE-022 | test: test_default_payload_keys_unchanged
"""  # noqa: E501

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from probe import providers
from probe.providers import (
    CompletionResult,
    OpenAICompatibleProvider,
    ProviderError,
)


def _transport(response: dict):
    """Fake transport returning a fixed response, recording payloads."""
    captured: list[dict] = []

    def transport(url, headers, body, timeout):
        captured.append(json.loads(body.decode("utf-8")))
        return response

    transport.captured = captured
    return transport


def _http_error(status: int, body: bytes):
    """Patchable urlopen that raises HTTPError with the given body."""

    def urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, status, "err", {}, io.BytesIO(body)
        )

    return urlopen


def test_default_payload_keys_unchanged() -> None:
    tr = _transport({"choices": [{"message": {"content": "ok"}}]})
    OpenAICompatibleProvider("http://x/v1", transport=tr).complete_ex(
        "m", "s", "u"
    )
    assert list(tr.captured[0]) == [
        "model",
        "temperature",
        "max_tokens",
        "messages",
    ]
    assert tr.captured[0]["temperature"] == 0


def test_send_temperature_false_omits_parameter() -> None:
    tr = _transport({"choices": [{"message": {"content": "ok"}}]})
    OpenAICompatibleProvider("http://x/v1", transport=tr).complete_ex(
        "m", "s", "u", send_temperature=False
    )
    assert "temperature" not in tr.captured[0]


def test_finish_reason_and_returned_model_captured() -> None:
    tr = _transport(
        {
            "model": "mistral-small-latest",
            "choices": [
                {"message": {"content": "x"}, "finish_reason": "length"}
            ],
        }
    )
    res = OpenAICompatibleProvider("http://x/v1", transport=tr).complete_ex(
        "m", "s", "u"
    )
    assert res.finish_reason == "length"
    assert res.returned_model == "mistral-small-latest"
    assert res.content_null is False


def test_missing_or_malformed_metadata_is_none() -> None:
    tr = _transport({"model": 7, "choices": [{"message": {"content": "x"}}]})
    res = OpenAICompatibleProvider("http://x/v1", transport=tr).complete_ex(
        "m", "s", "u"
    )
    assert res.finish_reason is None
    assert res.returned_model is None


def test_null_content_allowed_is_data() -> None:
    tr = _transport({"choices": [{"message": {"content": None}}]})
    res = OpenAICompatibleProvider("http://x/v1", transport=tr).complete_ex(
        "m", "s", "u", allow_null_content=True
    )
    assert res.text == ""
    assert res.content_null is True


def test_null_content_default_still_raises() -> None:
    """Frozen historical contract for text canaries."""
    tr = _transport({"choices": [{"message": {"content": None}}]})
    prov = OpenAICompatibleProvider("http://x/v1", transport=tr)
    with pytest.raises(ProviderError):
        prov.complete_ex("m", "s", "u")


def test_non_string_content_still_raises_even_if_null_allowed() -> None:
    tr = _transport({"choices": [{"message": {"content": ["chunk"]}}]})
    prov = OpenAICompatibleProvider("http://x/v1", transport=tr)
    with pytest.raises(ProviderError):
        prov.complete_ex("m", "s", "u", allow_null_content=True)


def test_completion_result_old_construction_still_valid() -> None:
    res = CompletionResult("t", None, 1, None, 5)
    assert res.finish_reason is None
    assert res.returned_model is None
    assert res.content_null is False


def test_transport_http_error_extracts_code(monkeypatch) -> None:
    body = json.dumps(
        {"error": {"message": "You exceeded", "code": "insufficient_quota"}}
    ).encode()
    monkeypatch.setattr(
        providers.urllib.request, "urlopen", _http_error(429, body)
    )
    with pytest.raises(ProviderError) as info:
        providers._urllib_transport("http://x/v1/c", {}, b"{}", 1.0)
    assert info.value.status_code == 429
    assert info.value.error_code == "insufficient_quota"
    assert str(info.value) == "provider HTTP 429"


def test_transport_top_level_code_mistral_shape(monkeypatch) -> None:
    body = json.dumps(
        {"object": "error", "message": "m", "type": "invalid_request"}
    ).encode()
    monkeypatch.setattr(
        providers.urllib.request, "urlopen", _http_error(400, body)
    )
    with pytest.raises(ProviderError) as info:
        providers._urllib_transport("http://x/v1/c", {}, b"{}", 1.0)
    assert info.value.error_code == "invalid_request"


def test_transport_non_json_error_body_has_no_code(monkeypatch) -> None:
    monkeypatch.setattr(
        providers.urllib.request,
        "urlopen",
        _http_error(502, b"<html>bad gateway</html>"),
    )
    with pytest.raises(ProviderError) as info:
        providers._urllib_transport("http://x/v1/c", {}, b"{}", 1.0)
    assert info.value.status_code == 502
    assert info.value.error_code is None


def test_error_code_rejects_free_text(monkeypatch) -> None:
    """Adversarial: the body echoes prompt and key in every field."""
    key = "sk-SECRETKEY123456"
    prompt = "my private prompt text"
    echo = f"{prompt} {key}"
    body = json.dumps(
        {"error": {"code": echo, "type": echo, "message": echo}}
    ).encode()
    monkeypatch.setattr(
        providers.urllib.request, "urlopen", _http_error(400, body)
    )
    with pytest.raises(ProviderError) as info:
        providers._urllib_transport("http://x/v1/c", {}, b"{}", 1.0)
    assert info.value.error_code is None
    text = f"{info.value} {info.value.error_code!r}"
    assert key not in text
    assert prompt not in text


def test_error_code_length_cap() -> None:
    assert providers._safe_code("a" * 64) == "a" * 64
    assert providers._safe_code("a" * 65) is None
    assert providers._safe_code(3505) == "3505"
    assert providers._safe_code(True) is None


def test_transport_failure_kinds(monkeypatch) -> None:
    """Each failure branch records a structural kind (no parsing)."""
    cases = [
        (TimeoutError("slow"), "timeout"),
        (urllib.error.URLError(TimeoutError("connect")), "timeout"),
        (urllib.error.URLError(OSError("dns")), "network"),
    ]
    for exc, kind in cases:

        def urlopen(req, timeout, _exc=exc):
            raise _exc

        monkeypatch.setattr(providers.urllib.request, "urlopen", urlopen)
        with pytest.raises(ProviderError) as info:
            providers._urllib_transport("http://x/v1/c", {}, b"{}", 1.0)
        assert info.value.failure_kind == kind
        assert info.value.status_code is None

    monkeypatch.setattr(
        providers.urllib.request, "urlopen", _http_error(503, b"")
    )
    with pytest.raises(ProviderError) as info:
        providers._urllib_transport("http://x/v1/c", {}, b"{}", 1.0)
    assert info.value.failure_kind == "http"

    bad = OpenAICompatibleProvider(
        "http://x/v1", transport=_transport({"nope": 1})
    )
    with pytest.raises(ProviderError) as info:
        bad.complete_ex("m", "s", "u")
    assert info.value.failure_kind == "bad_schema"


def test_system_none_omits_system_message() -> None:
    tr = _transport({"choices": [{"message": {"content": "ok"}}]})
    OpenAICompatibleProvider("http://x/v1", transport=tr).complete_ex(
        "m", None, "u"
    )
    assert tr.captured[0]["messages"] == [{"role": "user", "content": "u"}]
