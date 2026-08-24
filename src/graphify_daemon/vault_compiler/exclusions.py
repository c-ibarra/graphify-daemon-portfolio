"""Vault exclusion rules — what never enters a Batch.

See specs/vault-compiler/spec.md "Vault exclusion list" and
"Vault observation scope".
"""

from __future__ import annotations

from pathlib import Path

EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({".obsidian", ".trash", "node_modules", ".git", "__pycache__"})
# .md/.py is the full observed scope, so it already excludes *.ajson (and
# every other suffix) without a separate check.
OBSERVED_SUFFIXES: frozenset[str] = frozenset({".md", ".py"})


def is_excluded(
    path: Path,
    vault_root: Path,
    *,
    nested_repo_names: frozenset[str] = frozenset(),
) -> bool:
    """Return True if `path` (absolute, under `vault_root`) must never enter a Batch.

    `nested_repo_names` covers the 9 nested git repositories the vault
    contains — vault-specific data (see design.md), passed in rather than
    hardcoded here.

    Also excludes anything outside the observed scope (`.md`/`.py`) — see
    "Vault observation scope".
    """
    relative = path.relative_to(vault_root)
    if relative.suffix not in OBSERVED_SUFFIXES:
        return True
    excluded_names = EXCLUDED_DIR_NAMES | nested_repo_names
    return any(part in excluded_names for part in relative.parts)
