"""Daemon.__init__ creates its output directory owner-only on POSIX.

See specs/artifact-lifecycle/spec.md "Owner-only permissions on
derived-artifact files and directories".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission bits")
def test_output_dir_is_created_owner_only(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")

    Daemon(vault_root, paths)

    assert paths.output_dir.stat().st_mode & 0o777 == 0o700
