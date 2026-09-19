"""
tests.test_suite_spec
=====================
Contract for the data-file corpus loader (BENCH-1).

The acceptance criterion that matters is not "the loader parses JSON".
It is that the corpus arriving as data is the SAME corpus as the
Python literal it replaces -- same content address, same prompts in
the same order, and the same results out of a mock run.  Anything less
starts a new baseline under an old version string, which is the one
outcome content addressing exists to prevent.

#SG-TRACE: REQ-BENCH1-010, REQ-BENCH1-011, REQ-BENCH1-012
#   | assumption: digest equality plus mock-run equality together
#     establish behavioural identity for an offline corpus swap
#   | test: (this module)
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from probe.canary import (
    CANARY_SUITE_V2,
    FROZEN_TOOL_SCHEMA_V1,
    execute_canary,
    execute_canary_strict,
)
from probe.suite_spec import (
    MAX_PROMPTS,
    SCHEMA_ID,
    SuiteSpecError,
    load_suite_spec,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANARY_V2_SPEC = REPO_ROOT / "probe" / "suites" / "canary_v2.json"

PINNED_V2_WITH_TOOLS = (
    "d4fbb0a0ee7f704accc2b91c2832a4905cdf7b5cb175785490eabe878b9aba14"
)


def _load_raw() -> dict:
    """Return the shipped spec as a mutable dict."""
    return json.loads(CANARY_V2_SPEC.read_text(encoding="utf-8"))


def _write(tmp_path: Path, raw: dict) -> Path:
    """Write a spec dict to a temp file and return its path."""
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_canary_v2_spec_reproduces_pinned_digest() -> None:
    """The shipped spec is the v2.0.0 corpus, byte for byte.

    #SG-TRACE: REQ-BENCH1-010 | test: (this)
    """
    spec = load_suite_spec(CANARY_V2_SPEC)
    assert spec.suite_id == PINNED_V2_WITH_TOOLS
    assert spec.suite_version == "v2.0.0"
    assert len(spec.prompts) == 50
    assert spec.tools == [FROZEN_TOOL_SCHEMA_V1]
    assert spec.license.strip()


def test_spec_prompts_equal_the_literal_corpus() -> None:
    """Same prompts, same order, field for field.

    #SG-TRACE: REQ-BENCH1-010 | test: (this)
    """
    spec = load_suite_spec(CANARY_V2_SPEC)
    assert spec.as_suite() == CANARY_SUITE_V2


def test_mock_run_from_spec_matches_mock_run_from_literal() -> None:
    """Behavioural identity: the swap changes no emitted feature.

    Timestamp and latency are excluded -- they are properties of the
    run, not of the corpus.

    #SG-TRACE: REQ-BENCH1-010 | test: (this)
    """
    spec = load_suite_spec(CANARY_V2_SPEC)
    common = {"model_tuple": "mock/mock@test", "mock": True}
    from_spec = execute_canary(
        suite=spec.as_suite(), suite_version=spec.suite_version, **common
    )
    from_literal = execute_canary(
        suite=CANARY_SUITE_V2, suite_version="v2.0.0", **common
    )
    assert len(from_spec) == len(from_literal) == 50
    for left, right in zip(from_spec, from_literal, strict=True):
        assert replace(left, timestamp="", latency_ms=0) == replace(
            right, timestamp="", latency_ms=0
        )


def test_declared_suite_id_mismatch_is_rejected(tmp_path: Path) -> None:
    """ADVERSARIAL: a file edited in place must refute itself.

    One character changed in one prompt while suite_id and
    suite_version keep their old values -- the exact shape of a silent
    baseline break.

    #SG-TRACE: REQ-BENCH1-011 | test: (this)
    """
    raw = _load_raw()
    raw["prompts"][7]["user"] += "."
    with pytest.raises(SuiteSpecError, match="declared suite_id"):
        load_suite_spec(_write(tmp_path, raw))


def test_reordered_corpus_is_rejected(tmp_path: Path) -> None:
    """ADVERSARIAL: same prompts, different order, old suite_id.

    #SG-TRACE: REQ-BENCH1-011 | test: (this)
    """
    raw = _load_raw()
    prompts = raw["prompts"]
    prompts[10], prompts[11] = prompts[11], prompts[10]
    with pytest.raises(SuiteSpecError, match="declared suite_id"):
        load_suite_spec(_write(tmp_path, raw))


def test_tool_schema_edit_is_rejected(tmp_path: Path) -> None:
    """ADVERSARIAL: provider-visible change with prompts untouched.

    #SG-TRACE: REQ-BENCH1-011 | test: (this)
    """
    raw = _load_raw()
    raw["tools"][0]["function"]["name"] += "_v2"
    with pytest.raises(SuiteSpecError, match="declared suite_id"):
        load_suite_spec(_write(tmp_path, raw))


def test_oversized_suite_is_rejected(tmp_path: Path) -> None:
    """The 200-prompt cost cap is enforced before construction.

    #SG-TRACE: REQ-BENCH1-012 | test: (this)
    """
    raw = _load_raw()
    template = raw["prompts"][0]
    raw["prompts"] = [
        {**copy.deepcopy(template), "prompt_id": f"p-{i}"}
        for i in range(MAX_PROMPTS + 1)
    ]
    raw.pop("suite_id")
    with pytest.raises(SuiteSpecError, match="cap is 200"):
        load_suite_spec(_write(tmp_path, raw))


def test_duplicate_prompt_id_is_rejected(tmp_path: Path) -> None:
    """Two rows under one id make per-prompt features ambiguous.

    #SG-TRACE: REQ-BENCH1-012 | test: (this)
    """
    raw = _load_raw()
    raw["prompts"][1]["prompt_id"] = raw["prompts"][0]["prompt_id"]
    raw.pop("suite_id")
    with pytest.raises(SuiteSpecError, match="duplicate prompt_id"):
        load_suite_spec(_write(tmp_path, raw))


def test_extra_prompt_key_is_rejected(tmp_path: Path) -> None:
    """An extra field would move the digest for a non-prompt reason.

    #SG-TRACE: REQ-BENCH1-012 | test: (this)
    """
    raw = _load_raw()
    raw["prompts"][0]["note"] = "harmless"
    raw.pop("suite_id")
    with pytest.raises(SuiteSpecError, match="keys"):
        load_suite_spec(_write(tmp_path, raw))


def test_missing_license_is_rejected(tmp_path: Path) -> None:
    """A corpus whose terms are unrecorded cannot be audited later.

    #SG-TRACE: REQ-BENCH1-013
    #   | assumption: licensing must fail at load, not at publication
    #   | test: (this)
    """
    raw = _load_raw()
    raw["license"] = "   "
    with pytest.raises(SuiteSpecError, match="license"):
        load_suite_spec(_write(tmp_path, raw))


def test_wrong_schema_is_rejected(tmp_path: Path) -> None:
    """A future schema must not be read under today's rules.

    #SG-TRACE: REQ-BENCH1-012 | test: (this)
    """
    raw = _load_raw()
    raw["schema"] = "seismograph.suite/2"
    with pytest.raises(SuiteSpecError, match="schema"):
        load_suite_spec(_write(tmp_path, raw))
    assert SCHEMA_ID == "seismograph.suite/1"


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    """A truncated file fails loudly, not as an empty corpus.

    #SG-TRACE: REQ-BENCH1-012 | test: (this)
    """
    path = tmp_path / "suite.json"
    path.write_text('{"schema": "seismograph.suite/1",', encoding="utf-8")
    with pytest.raises(SuiteSpecError, match="invalid JSON"):
        load_suite_spec(path)


def test_strict_run_from_spec_matches_strict_run_from_literal() -> None:
    """The production runner, not just the plain one.

    ``execute_canary_strict`` is what a real leg calls: it tolerates a
    per-prompt failure, then discards the whole run unless every
    prompt produced a result. A corpus swap has to be invisible
    through that path too, otherwise the equality proved above holds
    only for a code path no observer uses.

    #SG-TRACE: REQ-BENCH1-014
    #   | assumption: identical results through the strict runner
    #     establish the swap is safe on the production path
    #   | test: (this)
    """
    spec = load_suite_spec(CANARY_V2_SPEC)
    common = {"model_tuple": "mock/mock@test", "mock": True}
    from_spec = execute_canary_strict(
        suite=spec.as_suite(), suite_version=spec.suite_version, **common
    )
    from_literal = execute_canary_strict(
        suite=CANARY_SUITE_V2, suite_version="v2.0.0", **common
    )
    assert len(from_spec) == len(from_literal) == 50
    for left, right in zip(from_spec, from_literal, strict=True):
        assert replace(left, timestamp="", latency_ms=0) == replace(
            right, timestamp="", latency_ms=0
        )
