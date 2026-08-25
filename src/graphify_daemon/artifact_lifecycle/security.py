"""Owner-only filesystem permissions for derived artifacts.

See specs/artifact-lifecycle/spec.md "Owner-only permissions on
derived-artifact files and directories". Derived artifacts are
reconstructible from the vault, but that doesn't make them non-confidential
— they can carry vault-derived names, relationships, and relative paths.
"""

from __future__ import annotations

import os
from pathlib import Path

_OWNER_ONLY_DIR_MODE = 0o700
_OWNER_ONLY_FILE_MODE = 0o600


def restrict_to_owner(path: Path) -> None:
    """Restrict `path` to owner-only access on POSIX platforms.

    Applies `0o700` to a directory, `0o600` to a file — the caller
    doesn't need to know which; this checks `path.is_dir()` itself. A
    no-op (never an error) on platforms where POSIX permission bits
    aren't meaningful (`os.name != "posix"`).
    """
    if os.name != "posix":
        return
    mode = _OWNER_ONLY_DIR_MODE if path.is_dir() else _OWNER_ONLY_FILE_MODE
    os.chmod(path, mode)
