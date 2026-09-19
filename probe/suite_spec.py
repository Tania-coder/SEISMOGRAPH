"""
seismograph.probe.suite_spec
============================
Load a canary corpus from a data file instead of a Python literal.

A SEISMOGRAPH observer measures drift by re-running a fixed corpus and
watching its feature distribution move.  Nothing in that mechanism
requires the corpus to be OUR corpus: any deterministic prompt set
works, including a pinned subset of a public benchmark.  What the
mechanism does require is that two observers claiming to run the same
corpus really are running the same bytes, which is what the content
address guarantees.

This module is the loader half of that.  It does not change how a
corpus is addressed -- ``probe.canary.suite_content_hash`` remains the
single digest function -- it only lets a corpus arrive as data.

Privacy: a spec file is read inside the probe perimeter and its prompt
texts never leave this process.  Only the digest and derived features
are ever transmitted.

Licensing: ``license`` is mandatory.  A benchmark-derived corpus
carries the upstream terms with it, and a suite whose terms are
unrecorded cannot be audited later.  The field is enforced at load
time so the omission fails fast rather than at publication.

#SG-TRACE: REQ-BENCH1-010
#   | assumption: a spec file that reproduces the pinned digest is
#     behaviourally identical to the literal corpus it replaces
#   | test: test_canary_v2_spec_reproduces_pinned_digest
#SG-TRACE: REQ-BENCH1-011
#   | assumption: a self-declared suite_id inside the file makes a
#     tampered corpus self-refuting at load time
#   | test: test_declared_suite_id_mismatch_is_rejected
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from probe.canary import suite_content_hash

SCHEMA_ID: str = "seismograph.suite/1"

# Mirrors CanarySuiteRegistry.MAX_PROMPTS_PER_SUITE.  Restated here
# because the loader must refuse an oversized corpus before anything
# is constructed, not after.
MAX_PROMPTS: int = 200

REQUIRED_PROMPT_KEYS: frozenset[str] = frozenset(
    {"prompt_id", "category", "system", "user"}
)


class SuiteSpecError(ValueError):
    """A spec file is malformed, oversized, or self-inconsistent."""


@dataclass(frozen=True)
class SuiteSpec:
    """An immutable, content-addressed corpus loaded from data.

    Attributes
    ----------
    name:
        Short identifier, e.g. "canary-v2".
    suite_version:
        Version string stamped on every CanaryResult.
    license:
        Upstream terms of the prompt corpus. Mandatory.
    source:
        Where the prompts came from, in enough detail to re-derive
        them (module path, dataset revision, sampler seed).
    prompts:
        Ordered corpus. Order is part of corpus identity.
    tools:
        Frozen tool schemas folded into the digest.
    """

    name: str
    suite_version: str
    license: str
    source: str
    prompts: list[dict[str, str]]
    tools: list[dict] = field(default_factory=list)

    @property
    def suite_id(self) -> str:
        """Content address of this corpus (prompts + tool schemas)."""
        return suite_content_hash(self.prompts, self.tools)

    def as_suite(self) -> list[dict[str, str]]:
        """Return the corpus in the shape ``execute_canary`` takes."""
        return self.prompts


def _require_str(value: object, label: str) -> str:
    """Return a non-empty string or raise SuiteSpecError."""
    if not isinstance(value, str) or not value.strip():
        raise SuiteSpecError(f"{label} must be a non-empty string")
    return value


def _validate_prompts(raw: object) -> list[dict[str, str]]:
    """Validate the corpus and return it unchanged.

    Checks, in the order a malformed file is most likely to fail:
    the container, the size cap, each entry's exact key set and value
    types, non-empty system/user text, and prompt_id uniqueness.

    #SG-TRACE: REQ-BENCH1-012
    #   | assumption: an exact key set keeps the canonical JSON of the
    #     corpus free of fields unrelated to the prompts themselves
    #   | test: test_extra_prompt_key_is_rejected
    """
    if not isinstance(raw, list) or not raw:
        raise SuiteSpecError("prompts must be a non-empty list")
    if len(raw) > MAX_PROMPTS:
        raise SuiteSpecError(
            f"suite has {len(raw)} prompts; cap is {MAX_PROMPTS}"
        )
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SuiteSpecError(f"prompt {index} is not an object")
        if set(entry) != REQUIRED_PROMPT_KEYS:
            raise SuiteSpecError(
                f"prompt {index} keys {sorted(entry)} != "
                f"{sorted(REQUIRED_PROMPT_KEYS)}"
            )
        for key in sorted(REQUIRED_PROMPT_KEYS):
            _require_str(entry[key], f"prompt {index} field {key!r}")
        prompt_id = entry["prompt_id"]
        if prompt_id in seen:
            raise SuiteSpecError(f"duplicate prompt_id {prompt_id!r}")
        seen.add(prompt_id)
    return raw


def _validate_tools(raw: object) -> list[dict]:
    """Validate the tool schema list and return it unchanged."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SuiteSpecError("tools must be a list")
    for index, schema in enumerate(raw):
        if not isinstance(schema, dict):
            raise SuiteSpecError(f"tool {index} is not an object")
    return raw


def load_suite_spec(path: str | Path) -> SuiteSpec:
    """Load, validate and content-address a suite spec file.

    A ``suite_id`` recorded in the file is treated as a claim, not as
    data: it is recomputed from the corpus and a mismatch raises.  A
    file that has been edited in place therefore refutes itself at
    load time rather than silently starting a new baseline under the
    old version string.

    Raises
    ------
    SuiteSpecError
        On any schema, size, shape, licensing or digest violation.

    #SG-TRACE: REQ-BENCH1-011 | test: (see module docstring)
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SuiteSpecError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SuiteSpecError(f"{path}: top level must be an object")

    schema = raw.get("schema")
    if schema != SCHEMA_ID:
        raise SuiteSpecError(f"{path}: schema {schema!r} != {SCHEMA_ID!r}")

    spec = SuiteSpec(
        name=_require_str(raw.get("name"), "name"),
        suite_version=_require_str(raw.get("suite_version"), "suite_version"),
        license=_require_str(raw.get("license"), "license"),
        source=_require_str(raw.get("source"), "source"),
        prompts=_validate_prompts(raw.get("prompts")),
        tools=_validate_tools(raw.get("tools")),
    )

    declared = raw.get("suite_id")
    if declared is not None and declared != spec.suite_id:
        raise SuiteSpecError(
            f"{path}: declared suite_id {declared!r} does not match "
            f"the corpus, which hashes to {spec.suite_id!r}"
        )
    return spec
