"""
tests.test_tool_canary
======================
Feature A (SG-FEAT-TOOLCALL-001): tool-calling canary category.

All tests run fully OFFLINE via injected fake transports. No network.

Covers (see /tmp/agents/engine/CONTRACT.md, section 3, Feature A):
  A1  suite v1.1 registers in the content-addressed registry, <= 200
  A2  suite_content_hash is deterministic and covers the tool schema
  A3  live tool request carries tools / temperature=0 / max_tokens<=64
  A4  schema-valid tool call -> tool_call_valid=True
  A5  validity matrix: wrong name, missing required, bad enum, extra
      property, non-JSON arguments, no tool call -> False, no raise
  A6  mock path scores the tool canary offline
  A7  no raw tool-call/argument text leaves the probe
  A8  Aggregator emits DP-noised tool_call_validity_rate
  A9  legacy batches (no tool canaries) keep the legacy key set
  ADV(b) schema-shifted provider response with identical latency and
      no json/latency signal is caught by tool_call_validity_rate

#SG-TRACE: REQ-TOOLCAN-001..012 | tests below
"""

from __future__ import annotations

import json
import random

import pytest
from probe.canary import (
    CANARY_SUITE_V1,
    CANARY_SUITE_V1_1,
    FROZEN_TOOL_SCHEMA_V1,
    SUITE_VERSION_V1_1,
    TOOL_CANARY_MAX_TOKENS,
    CanaryResult,
    _is_tool_call_valid,
    execute_canary,
    suite_content_hash,
)
from probe.canary_suite import CanaryPrompt, CanarySuiteRegistry
from probe.canary_suite import CanarySuiteVersion as SuiteVersion
from probe.privacy import Aggregator
from probe.providers import OpenAICompatibleProvider

MODEL = "openai/gpt-4o@2025-08"


def _tool_calls(name: str = "get_weather", arguments: str | None = None):
    """One OpenAI-shaped tool_calls list."""
    if arguments is None:
        arguments = '{"location": "Paris, France", "unit": "celsius"}'
    return [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }
    ]


def _make_tool_transport(tool_calls_for):
    """Fake transport: tool_calls_for(payload) -> tool_calls list | None.

    Requests WITHOUT a "tools" parameter (text canaries) get a plain
    deterministic text answer; requests WITH tools get the tool_calls
    produced by tool_calls_for (or a plain answer when it returns
    None -- a provider ignoring the tools parameter).
    Captures every request on transport.captured.
    """
    captured: list[dict] = []

    def transport(url, headers, body, timeout):
        payload = json.loads(body.decode("utf-8"))
        captured.append({"url": url, "headers": headers, "payload": payload})
        calls = tool_calls_for(payload) if "tools" in payload else None
        if calls is None:
            message = {"content": '{"persons": ["Marie Curie"]}'}
        else:
            message = {"content": None, "tool_calls": calls}
        return {
            "choices": [{"message": message}],
            "usage": {"completion_tokens": 12},
        }

    transport.captured = captured
    return transport


def _result(i: int, tool_call_valid: bool | None) -> CanaryResult:
    """Synthetic CanaryResult for aggregator tests (no raw output)."""
    return CanaryResult(
        timestamp=f"2026-07-24T12:{i // 60:02d}:{i % 60:02d}+00:00",
        model_tuple=MODEL,
        suite_version=SUITE_VERSION_V1_1,
        prompt_id=f"p{i:04d}",
        response_hash="d" * 64,
        output_length=100,
        json_valid=False,
        latency_ms=-1,
        tool_call_valid=tool_call_valid,
    )


# ---------------------------------------------------------------------------
# A1 -- suite is content-addressed and within the cost cap
# ---------------------------------------------------------------------------


def test_suite_v1_1_registers_content_addressed() -> None:
    """A1: v1.1 suite registers, stays append-only, <= 200 prompts.

    #SG-TRACE: REQ-TOOLCAN-002 | test: (this)
    """
    assert len(CANARY_SUITE_V1_1) <= 200
    assert len(CANARY_SUITE_V1_1) == len(CANARY_SUITE_V1) + 1
    # v1.0.0 corpus is untouched (append-only policy).
    assert CANARY_SUITE_V1_1[: len(CANARY_SUITE_V1)] == CANARY_SUITE_V1

    prompts = [
        CanaryPrompt(prompt_id=p["prompt_id"], text=p["user"])
        for p in CANARY_SUITE_V1_1
    ]
    v_a = SuiteVersion.from_prompts(prompts)
    v_b = SuiteVersion.from_prompts(prompts)
    assert v_a.version_hash == v_b.version_hash  # content-addressed

    registry = CanarySuiteRegistry()
    registry.register(v_a)
    # Re-registering the identical content is a mutation attempt.
    with pytest.raises(ValueError):
        registry.register(v_b)


def test_suite_content_hash_covers_tool_schema() -> None:
    """A2: hash is deterministic AND sensitive to the tool schema.

    #SG-TRACE: REQ-TOOLCAN-002 | test: (this)
    """
    h1 = suite_content_hash(CANARY_SUITE_V1_1, tools=[FROZEN_TOOL_SCHEMA_V1])
    h2 = suite_content_hash(CANARY_SUITE_V1_1, tools=[FROZEN_TOOL_SCHEMA_V1])
    assert h1 == h2
    assert len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)

    mutated = json.loads(json.dumps(FROZEN_TOOL_SCHEMA_V1))
    mutated["function"]["parameters"]["required"] = ["location"]
    h3 = suite_content_hash(CANARY_SUITE_V1_1, tools=[mutated])
    assert h3 != h1, "tool-schema change must produce a new version hash"

    # Prompt-only hash differs from prompt+tools hash.
    assert suite_content_hash(CANARY_SUITE_V1_1) != h1


def test_frozen_tool_schema_shape() -> None:
    """The frozen schema keeps the constructs the validator supports.

    #SG-TRACE: REQ-TOOLCAN-001 | test: (this)
    """
    fn = FROZEN_TOOL_SCHEMA_V1["function"]
    assert FROZEN_TOOL_SCHEMA_V1["type"] == "function"
    assert fn["name"] == "get_weather"
    params = fn["parameters"]
    assert params["required"] == ["location", "unit"]
    assert params["additionalProperties"] is False
    assert params["properties"]["unit"]["enum"] == [
        "celsius",
        "fahrenheit",
    ]


# ---------------------------------------------------------------------------
# A3 -- live request wire format
# ---------------------------------------------------------------------------


def test_tool_canary_request_wire_format() -> None:
    """A3: tools param present, temperature 0, small max_tokens.

    #SG-TRACE: REQ-TOOLCAN-020 | test: (this)
    """
    tr = _make_tool_transport(lambda p: _tool_calls())
    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=tr)
    results = execute_canary(
        MODEL,
        suite=CANARY_SUITE_V1_1,
        mock=False,
        provider=prov,
        suite_version=SUITE_VERSION_V1_1,
    )
    assert len(results) == len(CANARY_SUITE_V1_1)

    tool_reqs = [r["payload"] for r in tr.captured if "tools" in r["payload"]]
    assert len(tool_reqs) == 1, "exactly one tool-calling request"
    payload = tool_reqs[0]
    assert payload["tools"] == [FROZEN_TOOL_SCHEMA_V1]
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == TOOL_CANARY_MAX_TOKENS <= 64

    # Non-tool canaries keep the legacy wire format (no tools key).
    text_reqs = [
        r["payload"] for r in tr.captured if "tools" not in r["payload"]
    ]
    assert len(text_reqs) == len(CANARY_SUITE_V1)


def test_complete_ex_payload_omits_tools_when_none() -> None:
    """Backward compat: no tools key on the wire for text canaries.

    #SG-TRACE: REQ-TOOLCAN-020 | test: (this)
    """
    tr = _make_tool_transport(lambda p: None)
    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=tr)
    res = prov.complete_ex("m", "s", "u")
    assert "tools" not in tr.captured[0]["payload"]
    assert res.text == '{"persons": ["Marie Curie"]}'
    assert res.tool_calls_json is None
    assert res.output_tokens == 12  # usage still captured (Feature B)


def test_complete_ex_returns_tool_calls_json() -> None:
    """A4 wire level: null content tolerated; canonical tool_calls JSON.

    #SG-TRACE: REQ-TOOLCAN-021 | test: (this)
    """
    calls = _tool_calls()
    tr = _make_tool_transport(lambda p: calls)
    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=tr)
    res = prov.complete_ex("m", "s", "u", tools=[FROZEN_TOOL_SCHEMA_V1])
    assert res.text == ""  # content was null in tool mode
    assert res.tool_calls_json == json.dumps(
        calls, sort_keys=True, ensure_ascii=True
    )
    assert _is_tool_call_valid(res.tool_calls_json) is True


# ---------------------------------------------------------------------------
# A4/A5 -- validity matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool_calls_json", "expected"),
    [
        # A4: schema-valid call.
        (json.dumps(_tool_calls()), True),
        # fahrenheit is inside the enum -> still valid.
        (
            json.dumps(
                _tool_calls(
                    arguments='{"location": "Oslo", "unit": "fahrenheit"}'
                )
            ),
            True,
        ),
        # A5: wrong function name.
        (json.dumps(_tool_calls(name="get_wether")), False),
        # A5: missing required argument.
        (json.dumps(_tool_calls(arguments='{"location": "Paris"}')), False),
        # A5: enum violation.
        (
            json.dumps(
                _tool_calls(
                    arguments='{"location": "Paris", "unit": "kelvin"}'
                )
            ),
            False,
        ),
        # A5: additionalProperties violation (silently renamed field).
        (
            json.dumps(
                _tool_calls(
                    arguments=(
                        '{"location": "Paris", "unit": "celsius", '
                        '"units": "celsius"}'
                    )
                )
            ),
            False,
        ),
        # A5: wrong argument type.
        (
            json.dumps(
                _tool_calls(arguments='{"location": 42, "unit": "celsius"}')
            ),
            False,
        ),
        # A5: arguments are not JSON.
        (json.dumps(_tool_calls(arguments="location=Paris")), False),
        # A5: empty / absent tool calls.
        ("[]", False),
        (None, False),
        ("", False),
        ("not json at all", False),
    ],
)
def test_tool_call_validity_matrix(
    tool_calls_json: str | None, expected: bool
) -> None:
    """A4/A5: parse-and-validate against the frozen schema, no raises.

    #SG-TRACE: REQ-TOOLCAN-003, REQ-TOOLCAN-004 | test: (this)
    """
    assert _is_tool_call_valid(tool_calls_json) is expected


# ---------------------------------------------------------------------------
# A6 -- mock path
# ---------------------------------------------------------------------------


def test_execute_canary_mock_tool_suite() -> None:
    """A6: offline mock run scores the tool canary, no provider needed.

    #SG-TRACE: REQ-TOOLCAN-005 | test: (this)
    """
    results = execute_canary(
        MODEL,
        suite=CANARY_SUITE_V1_1,
        mock=True,
        suite_version=SUITE_VERSION_V1_1,
    )
    assert len(results) == len(CANARY_SUITE_V1_1)
    assert all(r.suite_version == SUITE_VERSION_V1_1 for r in results)

    tool = next(r for r in results if r.prompt_id == "v1.1.0-toolcall")
    assert tool.tool_call_valid is True
    assert tool.latency_ms == -1
    # Non-tool canaries are "not applicable", never False-by-accident.
    for r in results:
        if r.prompt_id != "v1.1.0-toolcall":
            assert r.tool_call_valid is None


def test_execute_canary_default_suite_unchanged() -> None:
    """Backward compat: default run is byte-for-byte the v1.0.0 flow.

    #SG-TRACE: REQ-TOOLCAN-010 | test: (this)
    """
    results = execute_canary(MODEL, mock=True)
    assert len(results) == len(CANARY_SUITE_V1)
    assert all(r.suite_version == "v1.0.0" for r in results)
    assert all(r.tool_call_valid is None for r in results)
    assert all(r.output_tokens is None for r in results)


def test_execute_canary_tool_requires_complete_ex() -> None:
    """Live tool canary with a legacy provider object fails loudly.

    #SG-TRACE: REQ-TOOLCAN-006 | test: (this)
    """

    class LegacyProvider:
        def complete(self, model, system, user):
            return "ok", 1

    with pytest.raises(ValueError, match="complete_ex"):
        execute_canary(
            MODEL,
            suite=CANARY_SUITE_V1_1,
            mock=False,
            provider=LegacyProvider(),
            suite_version=SUITE_VERSION_V1_1,
        )


# ---------------------------------------------------------------------------
# A7 -- privacy: raw tool call text never leaves the probe
# ---------------------------------------------------------------------------


def test_no_raw_tool_output_leaves_probe() -> None:
    """A7: serialised results contain no fragment of the raw tool call.

    #SG-TRACE: REQ-TOOLCAN-021 | test: (this)
    """
    secret_location = "SECRET-LOCATION-FRAGMENT"
    tr = _make_tool_transport(
        lambda p: _tool_calls(
            arguments=(
                f'{{"location": "{secret_location}", "unit": "celsius"}}'
            )
        )
    )
    prov = OpenAICompatibleProvider(base_url="http://x/v1", transport=tr)
    results = execute_canary(
        MODEL,
        suite=CANARY_SUITE_V1_1,
        mock=False,
        provider=prov,
        suite_version=SUITE_VERSION_V1_1,
    )
    blob = json.dumps([r.to_dict() for r in results])
    assert secret_location not in blob
    assert "arguments" not in blob
    assert all(len(r.response_hash) == 64 for r in results)


# ---------------------------------------------------------------------------
# A8/A9 -- aggregation
# ---------------------------------------------------------------------------


def test_tool_validity_rate_dp_noised() -> None:
    """A8: rate emitted, DP-noised, clamped to [0, 1].

    #SG-TRACE: REQ-TOOLCAN-011 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(42))
    # 4 results: 2 tool canaries (1 valid, 1 invalid), 2 text canaries.
    for i, valid in enumerate([True, False, None, None]):
        agg.add_result(_result(i, tool_call_valid=valid))
    batch = agg.flush(MODEL)

    assert "tool_call_validity_rate" in batch.metrics
    rate = batch.metrics["tool_call_validity_rate"]
    assert 0.0 <= rate <= 1.0
    # Raw component over the full batch is 1/4; seeded Laplace noise
    # makes the emitted value differ from the raw mean.
    assert rate != pytest.approx(0.25), "DP noise must perturb the rate"


def test_legacy_batch_omits_tool_rate() -> None:
    """A9: batches without tool canaries keep the legacy key set.

    #SG-TRACE: REQ-GW-030 | test: (this)
    """
    agg = Aggregator(_rng=random.Random(7))
    for i in range(3):
        agg.add_result(_result(i, tool_call_valid=None))
    batch = agg.flush(MODEL)
    assert set(batch.metrics) == {
        "avg_output_length",
        "json_success_rate",
        "result_count",
    }


# ---------------------------------------------------------------------------
# ADVERSARIAL (b) -- schema-shifted response with no latency/json signal
# ---------------------------------------------------------------------------


def test_adversarial_schema_shift_caught_by_tool_validity() -> None:
    """CONTRACT adversarial (b): provider silently renames an argument.

    Window 1: schema-conforming tool calls.
    Window 2: same latency profile, same text-canary outputs (json
    signal unchanged), but the tool call now sends "units" instead of
    the frozen required "unit".  Arguments still parse as JSON; no
    error, no uptime/latency signal.

    tool_call_validity_rate is the ONLY scalar that moves -- exactly
    the per-metric stream the CUSUM detector consumes.

    #SG-TRACE: REQ-TOOLCAN-004, REQ-TOOLCAN-011 | test: (this)
    """
    stable_tr = _make_tool_transport(lambda p: _tool_calls())
    shifted_tr = _make_tool_transport(
        lambda p: _tool_calls(
            arguments='{"location": "Paris, France", "units": "celsius"}'
        )
    )
    prov_stable = OpenAICompatibleProvider("http://x/v1", transport=stable_tr)
    prov_shifted = OpenAICompatibleProvider(
        "http://x/v1", transport=shifted_tr
    )

    r_stable = execute_canary(
        MODEL,
        suite=CANARY_SUITE_V1_1,
        mock=False,
        provider=prov_stable,
        suite_version=SUITE_VERSION_V1_1,
    )
    r_shifted = execute_canary(
        MODEL,
        suite=CANARY_SUITE_V1_1,
        mock=False,
        provider=prov_shifted,
        suite_version=SUITE_VERSION_V1_1,
    )

    t_stable = next(r for r in r_stable if r.prompt_id == "v1.1.0-toolcall")
    t_shifted = next(r for r in r_shifted if r.prompt_id == "v1.1.0-toolcall")

    # The per-canary boolean flips ...
    assert t_stable.tool_call_valid is True
    assert t_shifted.tool_call_valid is False
    # ... while no other signal moves: json canary unchanged in both
    # windows, and the response still "succeeded" (no exception).
    j_stable = next(r for r in r_stable if r.prompt_id == "v1.0.0-format")
    j_shifted = next(r for r in r_shifted if r.prompt_id == "v1.0.0-format")
    assert j_stable.json_valid and j_shifted.json_valid
    assert j_stable.response_hash == j_shifted.response_hash

    # Aggregated raw rates: 1/4 vs 0/4 over the full batch -- a
    # material drop for CUSUM even before DP noise.
    def raw_rate(results):
        return sum(1 for r in results if r.tool_call_valid is True) / len(
            results
        )

    assert raw_rate(r_stable) == pytest.approx(0.25)
    assert raw_rate(r_shifted) == pytest.approx(0.0)
