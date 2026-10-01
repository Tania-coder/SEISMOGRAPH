"""SBOM-1: the probe's dependency licences, checked in the gate.

Companies run ``seismograph-probe`` inside their own infrastructure, so
the first question their security review asks is what is inside it and
under which terms.  The answer is a CycloneDX SBOM committed under
``docs/compliance/sbom/``.  These tests make that answer a checked
artefact rather than a document that can drift:

- the root component is ``seismograph-probe`` under Apache-2.0;
- every component carries a licence, and every licence in it is on an
  explicit allow-list compatible with distributing under Apache-2.0
  (no GPL/AGPL/LGPL, no unknown terms);
- every runtime dependency declared in ``pyproject_probe.toml`` appears
  in the SBOM, so adding a dependency without regenerating the SBOM
  turns the gate red.

What these tests do NOT prove: that the SBOM matches what a user's
resolver installs today.  An SBOM describes one resolution, on the date
in docs/compliance/LICENSES.md; it is regenerated at every release.

#SG-TRACE: REQ-SBOM1-001
#   | assumption: CycloneDX licence fields (id / expression / name) are
#     the licence of record for each component
#   | test: test_every_component_licence_is_allowed
#SG-TRACE: REQ-SBOM1-002
#   | assumption: a declared dependency missing from the SBOM means the
#     SBOM is stale, not that the dependency is unused
#   | test: test_declared_dependencies_are_in_the_sbom
"""

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SBOM_DIR = _ROOT / "docs" / "compliance" / "sbom"
_SBOM_CORE = _SBOM_DIR / "seismograph-probe-1.1.0-core.cdx.json"
_SBOM_ALL = _SBOM_DIR / "seismograph-probe-1.1.0-all.cdx.json"
_PYPROJECT = _ROOT / "pyproject_probe.toml"

# Licences compatible with distributing the probe under Apache-2.0 as
# an unmodified dependency.  MPL-2.0 is file-level copyleft: it binds
# only changes to MPL files, and the probe vendors none (certifi is a
# runtime dependency).  Adding to this list is a deliberate act that
# belongs in a Keystone, never a way to turn a red gate green.
ALLOWED_LICENCES: frozenset[str] = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "PSF-2.0",
    }
)

_SPDX_OPERATORS = {"AND", "OR", "WITH"}


def _normalise(name: str) -> str:
    """PEP 503 normalised distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _licence_ids(component: dict) -> set[str]:
    """Return the SPDX ids a CycloneDX component declares.

    Trove-classifier strings ("License :: OSI Approved :: ...") that
    cyclonedx-py adds alongside an SPDX id are informational and are
    ignored when an SPDX id or expression is present.
    """
    ids: set[str] = set()
    names: set[str] = set()
    for entry in component.get("licenses", []):
        if "expression" in entry:
            tokens = re.split(r"[\s()]+", entry["expression"])
            ids.update(t for t in tokens if t and t not in _SPDX_OPERATORS)
            continue
        lic = entry.get("license", {})
        if "id" in lic:
            ids.add(lic["id"])
        elif "name" in lic:
            names.add(lic["name"])
    if ids:
        return ids
    return names


def licence_violations(sbom: dict) -> dict[str, set[str]]:
    """Map component name -> licences outside the allow-list.

    A component with no licence at all is reported with the marker
    ``{"<none>"}``: unknown terms are not permission.
    """
    bad: dict[str, set[str]] = {}
    for component in sbom.get("components", []):
        ids = _licence_ids(component)
        if not ids:
            bad[component["name"]] = {"<none>"}
            continue
        outside = {i for i in ids if i not in ALLOWED_LICENCES}
        if outside:
            bad[component["name"]] = outside
    return bad


def _declared_dependencies(pyproject: str) -> dict[str, set[str]]:
    """Parse runtime and optional dependency names from the probe TOML.

    A deliberately small parser: the gate runs on Python 3.10, which
    has no ``tomllib``, and the file's layout is under our control.
    """
    out: dict[str, set[str]] = {"core": set(), "all": set()}
    section = None
    for raw in pyproject.splitlines():
        line = raw.strip()
        if line.startswith("dependencies = ["):
            section = "core"
            continue
        if line.startswith("all = ["):
            section = "all"
            continue
        if section and line.startswith("]"):
            section = None
            continue
        if section:
            match = re.match(r'"([A-Za-z0-9_.\-]+)', line)
            if match:
                out[section].add(_normalise(match.group(1)))
    out["all"] |= out["core"]
    return out


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", [_SBOM_CORE, _SBOM_ALL])
def test_sbom_is_cyclonedx_for_the_probe(path):
    sbom = _load(path)
    assert sbom["bomFormat"] == "CycloneDX"
    root = sbom["metadata"]["component"]
    assert root["name"] == "seismograph-probe"
    assert "Apache-2.0" in _licence_ids(root)


@pytest.mark.parametrize("path", [_SBOM_CORE, _SBOM_ALL])
def test_every_component_licence_is_allowed(path):
    bad = licence_violations(_load(path))
    assert not bad, (
        f"{path.name}: components outside the licence allow-list: {bad}. "
        "Replace the dependency or record a deliberate exception in a "
        "Keystone; never widen the list to make this pass."
    )


@pytest.mark.parametrize(
    ("path", "extra"), [(_SBOM_CORE, "core"), (_SBOM_ALL, "all")]
)
def test_declared_dependencies_are_in_the_sbom(path, extra):
    declared = _declared_dependencies(_PYPROJECT.read_text(encoding="utf-8"))[
        extra
    ]
    assert declared, "parser found no dependencies; layout changed?"
    present = {_normalise(c["name"]) for c in _load(path)["components"]}
    missing = declared - present
    assert not missing, (
        f"{path.name} is stale: declared but absent {sorted(missing)}. "
        "Regenerate per docs/compliance/LICENSES.md."
    )


def test_a_copyleft_component_is_rejected():
    """Adversarial: a GPL dependency must turn the check red."""
    sbom = {
        "components": [
            {"name": "ok", "licenses": [{"license": {"id": "MIT"}}]},
            {
                "name": "viral",
                "licenses": [{"expression": "GPL-3.0-only OR MIT"}],
            },
            {"name": "agpl", "licenses": [{"license": {"id": "AGPL-3.0"}}]},
        ]
    }
    bad = licence_violations(sbom)
    assert bad == {"viral": {"GPL-3.0-only"}, "agpl": {"AGPL-3.0"}}


def test_a_component_without_licence_is_rejected():
    """Unknown terms are not permission."""
    bad = licence_violations({"components": [{"name": "mystery"}]})
    assert bad == {"mystery": {"<none>"}}


def test_parser_reads_the_real_layout():
    declared = _declared_dependencies(_PYPROJECT.read_text(encoding="utf-8"))
    assert declared["core"] == {"httpx", "cryptography"}
    assert declared["all"] == {"httpx", "cryptography", "opentelemetry-sdk"}
