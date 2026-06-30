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

# A transport takes (url, headers, body_bytes, timeout) and returns the
# decoded JSON response dict. Injectable so tests never touch the network.
Transport = Callable[[str, dict, bytes, float], dict]


class ProviderError(RuntimeError):
    """Raised when a live provider call fails or returns an unusable body.

    Carries no prompt or output text — only a short, safe diagnostic.
    """


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
    """
    req = urllib.request.Request(
        url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"provider HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(
            f"provider unreachable: {type(exc).__name__}"
        ) from None
    except json.JSONDecodeError:
        raise ProviderError("provider returned non-JSON body") from None


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

        #SG-TRACE: REQ-CANARY-021
        #   | assumption: temperature=0 + max_tokens cap keep the call
        #     deterministic and within the canary cost contract
        #   | test: test_provider_forces_temperature_zero
        """
        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": model,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
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
            raw = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected completion schema") from None
        if not isinstance(raw, str):
            raise ProviderError("completion content not a string") from None
        return raw, latency_ms
