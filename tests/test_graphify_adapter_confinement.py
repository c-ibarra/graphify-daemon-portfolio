"""Enforces that `graphify.serve` is imported from exactly one module.

Scoped to `src/` (production code): the confinement requirement is about
what ships in the daemon, not about the contract test in
`test_graphify_adapter_contract.py`, which must import `graphify.serve`
directly to verify its live signatures.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
ADAPTER_MODULE = "graphify_daemon.adapters.graphify_query"


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(SRC_ROOT).with_suffix("").parts)


def _imports_graphify_serve(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "graphify.serve" or alias.name.startswith("graphify.serve.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "graphify.serve" or module.startswith("graphify.serve."):
                return True
    return False


def test_only_adapter_module_imports_graphify_serve() -> None:
    offenders = [
        str(path.relative_to(SRC_ROOT.parent))
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if _module_name(path) != ADAPTER_MODULE and _imports_graphify_serve(path)
    ]
    assert not offenders, f"Only {ADAPTER_MODULE} may import graphify.serve; found unauthorized imports in: {offenders}"


def test_adapter_module_itself_imports_graphify_serve() -> None:
    adapter_path = SRC_ROOT / "graphify_daemon" / "adapters" / "graphify_query.py"
    assert adapter_path.exists()
    assert _imports_graphify_serve(adapter_path), (
        "Sanity check: the adapter module should import graphify.serve — "
        "if this fails, the scan logic itself is broken."
    )
