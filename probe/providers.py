"""
seismograph.probe.providers
============================
Live provider adapter for canary execution.

This module is the ONLY place the probe makes an outbound call to a model
endpoint. It speaks the OpenAI-compatible Chat Completions wire format,
which is supported by OpenAI, Groq, Together, Mistral, vLLM, and a locally
hosted Ollama (``/v1/chat/completions``). One adapter therefore covers
local-and-free through to hosted-and-paid by configuration alone.

Privacy boundary:
  - This module receives the raw model output, but returns it to the
    caller (probe.canary.execute_canary) which immediately hashes and
    discards it. No raw text is persisted or transmitted from here.
  - No prompt or output is logged.

Cost cap:
  - temperature is forced to 0 and max_tokens defaults low (20) so a full
    suite stays far under the <$0.10/probe/day target.

Dependency policy:
  - Uses only the Python standard library (urllib) so the seismograph-probe
    package stays dependency-light. The HTTP transport is injectable so
    tests run fully offline.

#SG-TRACE: REQ-CANARY-020
#   | assumption: OpenAI-compatible /v1/chat/completions is a sufficient
#     common denominator across target providers
#   | test: test_provider_builds_openai_payload
#SG-TRACE: REQ-CANARY-021
#   | assumption: temperature=0 + small max_tokens keeps probes within the
#     deterministic, low-cost canary contract
#   | test: test_provider_forces_temperature_zero
#SG-TRACE: REQ-PRIV-020
#   | assumption: provider returns raw text to caller only; caller hashes
#     and discards; nothing is logged or stored here
#   | test: test_provider_does_not_retain_raw_output
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

# A transport takes (url, headers, body_bytes, timeout) and returns the
# decoded JSON response dict. Injectable so tests never touch the network.
Transport = Callable[[str, dict, bytes, float], dict]


class ProviderError(RuntimeError):
    """Raised when a live provider call fails or returns an unusable body.

    Carries no prompt or output text — only a short, safe diagnostic.

    Attributes
    ----------
    status_code:
        HTTP status of the failed call when the failure WAS an HTTP
        response (populated by the transport's ``HTTPError`` branch), and
        ``None`` for every other failure mode -- transport/DNS/timeout
        errors, non-JSON bodies, schema errors, and the constructor's own
        validation errors -- which have no status at all.

        The attribute exists so callers can classify a failure
        structurally.  The status is ALSO in the message string for human
        readers, but that string is not a contract: no caller may parse
        it (contract CAN-2a C3).

    #SG-TRACE: REQ-CAN2A-001
    #   | assumption: an optional keyword with a None default keeps every
    #     pre-existing single-argument ProviderError(...) construction
    #     site valid and unchanged in behaviour
    #   | test: test_provider_error_status_code_optional_and_defaults_none
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


def model_name_from_tuple(model_tuple: str) -> str:
    """Extract the API model name from a SEISMOGRAPH model tuple.

    A model tuple is ``"<provider>/<model>@<version>"`` (version optional),
    e.g. ``"openai/gpt-4o@2025-08"`` -> ``"gpt-4o"`` and
    ``"ollama/llama3.1"`` -> ``"llama3.1"``.

    #SG-TRACE: REQ-CANARY-022
    #   | assumption: the API model name is the segment after the first
    #     slash and before an optional '@version' tag
    #   | test: test_model_name_from_tuple
    """
    if "/" in model_tuple:
        model_tuple = model_tuple.split("/", 1)[1]
    return model_tuple.split("@", 1)[0]


def _urllib_transport(
    url: str, headers: dict, body: bytes, timeout: float
) -> dict:
    """Default stdlib HTTP POST transport returning a decoded JSON dict.

    #SG-TRACE: REQ-CANARY-023
    #   | assumption: a 2xx JSON body is returned; network/HTTP errors
    #     surface as ProviderError with no payload leakage
    #   | test: test_provider_timeout_raises_clean
    #SG-TRACE: REQ-CAN2A-002
    #   | assumption: HTTPError.code is the only place a real HTTP status
    #     is known; it is attached structurally here so no caller ever
    #     has to parse the message string (contract CAN-2a C3).  The
    #     message text itself is left byte-identical to the pre-CAN-2a
    #     wording so existing log/assert expectations still hold.
    #   | test: test_transport_http_error_carries_structured_status
    """
    req = urllib.request.Request(
        url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            f"provider HTTP {exc.code}", status_code=exc.code
        ) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(
            f"provider unreachable: {type(exc).__name__}"
        ) from None
    except json.JSONDecodeError:
        raise ProviderError("provider returned non-JSON body") from None


@dataclass(frozen=True)
class CompletionResult:
    """Structured result of one chat completion call.

    Carries the raw text / raw tool-call JSON back to the caller
    (probe.canary.execute_canary), which immediately derives
    booleans/hashes and discards the raw strings.  Nothing here is
    logged or persisted by this module.

    Fields
    ------
    text:
        Raw assistant message content.  Empty string when the model
        answered with a tool call only (content null).
    tool_calls_json:
        Canonical JSON string (sorted keys, ASCII) of the
        ``message.tool_calls`` list, or None when the response
        contained no tool calls.
    output_tokens:
        ``usage.completion_tokens`` if present and integral, else None.
    reasoning_tokens:
        ``usage.completion_tokens_details.reasoning_tokens`` if present
        and integral, else None.
    latency_ms:
        Wall-clock milliseconds for the API call.

    #SG-TRACE: REQ-TOKMET-001
    #   | assumption: usage fields are optional in OpenAI-compatible
    #     responses; None-safe capture, never an exception
    #   | test: test_usage_fields_none_safe
    """

    text: str
    tool_calls_json: str | None
    output_tokens: int | None
    reasoning_tokens: int | None
    latency_ms: int


def _int_or_none(value: object) -> int | None:
    """Coerce a usage counter to int, or None if absent/non-integral.

    #SG-TRACE: REQ-TOKMET-001
    #   | assumption: providers may send usage counters as int or
    #     float; bool and strings are treated as absent (None)
    #   | test: test_usage_fields_none_safe
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _parse_usage(data: dict) -> tuple[int | None, int | None]:
    """Extract (output_tokens, reasoning_tokens) from a response dict.

    None-safe: any missing or malformed level yields None for that
    field, never an exception.

    #SG-TRACE: REQ-TOKMET-001
    #   | assumption: usage.completion_tokens and
    #     usage.completion_tokens_details.reasoning_tokens are the
    #     OpenAI-compatible field names; other providers omit them
    #   | test: test_usage_fields_none_safe
    """
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None, None
    output_tokens = _int_or_none(usage.get("completion_tokens"))
    details = usage.get("completion_tokens_details")
    reasoning_tokens = (
        _int_or_none(details.get("reasoning_tokens"))
        if isinstance(details, dict)
        else None
    )
    return output_tokens, reasoning_tokens


class OpenAICompatibleProvider:
    """Minimal OpenAI-compatible Chat Completions client for canaries.

    Parameters
    ----------
    base_url:
        Endpoint root, e.g. ``"https://api.openai.com/v1"`` or
        ``"http://localhost:11434/v1"`` for Ollama.
    api_key:
        Bearer token. Optional (a local Ollama needs none). Never logged.
    max_tokens:
        Hard upper bound on generated tokens (cost cap). Default 20.
    timeout:
        Per-call wall-clock timeout in seconds.
    transport:
        Injectable HTTP transport (defaults to stdlib). Tests pass a fake.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        max_tokens: int = 20,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if api_key is not None and not api_key.isascii():
            # HTTP headers are latin-1/ASCII only; a non-ASCII key
            # (e.g. a pasted placeholder) would otherwise crash deep
            # in urllib with an opaque UnicodeEncodeError. Fail early
            # with a clear, payload-free message.
            # #SG-TRACE: REQ-CANARY-025
            #   | assumption: a valid bearer token is ASCII; non-ASCII
            #     means a wrong/placeholder value, not a real key
            #   | test: test_provider_rejects_non_ascii_api_key
            raise ProviderError(
                "API key contains non-ASCII characters; this looks "
                "like a placeholder or the wrong value, not a real "
                "API key"
            )
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._transport = transport or _urllib_transport

    def complete(self, model: str, system: str, user: str) -> tuple[str, int]:
        """Run one chat completion; return (raw_text, latency_ms).

        temperature is forced to 0 for determinism and cost control.
        Signature and error behavior are frozen (backward-compatible
        wrapper over complete_ex).

        #SG-TRACE: REQ-CANARY-021
        #   | assumption: temperature=0 + max_tokens cap keep the call
        #     deterministic and within the canary cost contract
        #   | test: test_provider_forces_temperature_zero
        """
        res = self.complete_ex(model, system, user)
        return res.text, res.latency_ms

    def complete_ex(
        self,
        model: str,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Run one chat completion; return a structured CompletionResult.

        temperature is forced to 0.  When ``tools`` is given, the
        OpenAI-compatible ``tools`` parameter is included verbatim and
        a content of null is tolerated (tool-call-only answers).
        Without ``tools``, behavior matches the historical complete()
        contract exactly: non-string content raises ProviderError.

        Parameters
        ----------
        tools:
            Optional OpenAI-format tool definitions list.  Omitted
            from the payload when None (wire-format unchanged for all
            pre-existing callers).
        max_tokens:
            Optional per-call override of the constructor cap.  Used
            by the tool canary (needs ~64 tokens for arguments) while
            keeping the plain-text canaries at the tight default.

        #SG-TRACE: REQ-TOOLCAN-020
        #   | assumption: adding "tools" only when not None keeps the
        #     request byte-identical for non-tool canaries (backward
        #     compatible with providers rejecting unknown params)
        #   | test: test_complete_ex_payload_omits_tools_when_none
        #SG-TRACE: REQ-TOOLCAN-021
        #   | assumption: tool_calls serialised with sorted keys /
        #     ASCII so the caller's hash is canonical; raw string is
        #     returned to caller only, never logged here
        #   | test: test_complete_ex_returns_tool_calls_json
        """
        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload: dict = {
            "model": model,
            "temperature": 0,
            "max_tokens": (
                self._max_tokens if max_tokens is None else max_tokens
            ),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if tools is not None:
            payload["tools"] = tools
        body = json.dumps(payload).encode("utf-8")

        start = time.perf_counter()
        try:
            data = self._transport(url, headers, body, self._timeout)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"transport failed: {type(exc).__name__}"
            ) from None
        latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected completion schema") from None
        if not isinstance(message, dict):
            raise ProviderError("unexpected completion schema") from None

        raw = message.get("content")
        tool_calls = message.get("tool_calls")
        tool_calls_json: str | None = None
        if isinstance(tool_calls, list) and tool_calls:
            tool_calls_json = json.dumps(
                tool_calls, sort_keys=True, ensure_ascii=True
            )

        if not isinstance(raw, str):
            if tools is None:
                # Frozen historical contract: text canaries require a
                # string content.
                raise ProviderError(
                    "completion content not a string"
                ) from None
            # Tool mode: content may legitimately be null.
            raw = ""

        output_tokens, reasoning_tokens = _parse_usage(data)

        return CompletionResult(
            text=raw,
            tool_calls_json=tool_calls_json,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            latency_ms=latency_ms,
        )
