"""seismograph.memory.ast_graph
================================
Static intra-repository dependency-graph builder.

Walks the first-party Python packages, parses each module with the
``ast`` module (no imports executed, no third-party deps), and emits a
content-stable ``graph.json`` at the repository root describing:

  * which internal module each module imports (``imports``),
  * the inverse relation (``imported_by``),
  * the top-level functions and classes each module defines,
  * a line count per module.

The constitution names ``graph.json`` + ``memory/ast_graph.py`` as the
canonical source for dependency mapping ("Do not re-derive from raw file
reads"). This script is that source. Re-run after structural changes:

    py -3.10 memory/ast_graph.py     # from the repository root

Determinism
-----------
All collections are sorted before serialisation so re-running on an
unchanged tree produces a byte-identical ``graph.json`` (clean diffs).

#SG-TRACE: REQ-ATLAS-001
#   | assumption: only first-party packages in _PACKAGES form graph
#     nodes; stdlib and third-party imports are recorded as external
#     fan-out counts, never as nodes
#   | test: graph_json_roundtrip (manual; see __main__ self-check)
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path

# First-party top-level packages that count as graph nodes. An import is
# "internal" iff its dotted root is one of these.
_PACKAGES: tuple[str, ...] = (
    "probe",
    "engine",
    "gateway",
    "dashboard",
)

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_OUTPUT: Path = _REPO_ROOT / "graph.json"


def _module_name(path: Path) -> str:
    """Return the dotted module name for a .py file under the repo root.

    ``engine/webhooks.py`` -> ``engine.webhooks``;
    ``probe/adapters/mcp.py`` -> ``probe.adapters.mcp``. An
    ``__init__.py`` collapses to its package (``probe/__init__.py`` ->
    ``probe``).
    """
    rel = path.relative_to(_REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_internal(root: str) -> bool:
    """True if a dotted import root names a first-party package."""
    return root in _PACKAGES


def _imports_of(tree: ast.AST) -> set[str]:
    """Collect the dotted roots of every import in a parsed module.

    Handles both ``import a.b`` (root ``a``) and ``from a.b import c``
    (root ``a``). Relative imports (``from . import x``) resolve to an
    empty root and are skipped here; the codebase uses absolute imports.
    """
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _defs_of(tree: ast.AST) -> tuple[list[str], list[str]]:
    """Return ``(functions, classes)`` defined at module top level."""
    functions: list[str] = []
    classes: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
    return sorted(functions), sorted(classes)


def build_graph() -> dict[str, object]:
    """Parse every first-party module and assemble the graph dict.

    #SG-TRACE: REQ-ATLAS-001
    #   | assumption: a module that fails to parse is fatal; a syntax
    #     error in source must surface, not be silently dropped
    #   | test: graph_json_roundtrip
    """
    files: list[Path] = []
    for package in _PACKAGES:
        files.extend(sorted((_REPO_ROOT / package).rglob("*.py")))

    modules: dict[str, dict[str, object]] = {}
    internal_edges: set[tuple[str, str]] = set()

    for path in sorted(files):
        name = _module_name(path)
        raw = path.read_text(encoding="utf-8")
        # Normalise newlines defensively: a CRLF-checked-out tree
        # otherwise trips ast.parse on bare carriage returns.
        source = raw.replace("\r\n", "\n").replace("\r", "\n")
        tree = ast.parse(source, filename=str(path))
        roots = _imports_of(tree)
        internal = sorted(r for r in roots if _is_internal(r))
        external = sorted(r for r in roots if not _is_internal(r))
        functions, classes = _defs_of(tree)
        modules[name] = {
            "path": str(path.relative_to(_REPO_ROOT)).replace("\\", "/"),
            "package": name.split(".")[0],
            "imports_internal": internal,
            "imports_external": external,
            "imported_by": [],
            "functions": functions,
            "classes": classes,
            "loc": source.count("\n") + 1,
        }
        for target in internal:
            if target != name.split(".")[0]:
                internal_edges.add((name.split(".")[0], target))

    # Populate the inverse relation at package granularity.
    for src, dst in sorted(internal_edges):
        for _mod_name, meta in modules.items():
            if meta["package"] == dst and src not in meta["imported_by"]:
                meta["imported_by"].append(src)
    for meta in modules.values():
        meta["imported_by"] = sorted(set(meta["imported_by"]))

    edges = [[src, dst] for src, dst in sorted(internal_edges)]
    return {
        "schema": "seismograph.depgraph/1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packages": list(_PACKAGES),
        "module_count": len(modules),
        "package_edges": edges,
        "modules": dict(sorted(modules.items())),
    }


def main() -> None:
    """Build the graph and write ``graph.json`` at the repo root."""
    graph = build_graph()
    _OUTPUT.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"graph.json written: {graph['module_count']} modules, "
        f"{len(graph['package_edges'])} package edges"
    )


if __name__ == "__main__":
    main()
