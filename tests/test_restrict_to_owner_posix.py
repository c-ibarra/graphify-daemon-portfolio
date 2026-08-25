"""restrict_to_owner: owner-only permissions on POSIX, no-op elsewhere.

See specs/artifact-lifecycle/spec.md "Owner-only permissions on
derived-artifact files and directories".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify_daemon.artifact_lifecycle.security import restrict_to_owner


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission bits")
def test_restrict_to_owner_file_grants_no_group_or_other_access(tmp_path: Path) -> None:
    f = tmp_path / "secret.txt"
    f.write_text("data")
    f.chmod(0o644)

    restrict_to_owner(f)

    assert f.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission bits")
def test_restrict_to_owner_directory_grants_no_group_or_other_access(tmp_path: Path) -> None:
    d = tmp_path / "outdir"
    d.mkdir()
    d.chmod(0o755)

    restrict_to_owner(d)

    assert d.stat().st_mode & 0o777 == 0o700
