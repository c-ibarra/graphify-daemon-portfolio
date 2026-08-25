"""Daemon lifecycle: RUNNING -> STOPPING -> STOPPED, never backward.

See specs/artifact-lifecycle/spec.md "Explicit lifecycle states gate
event acceptance" and "Shutdown is idempotent".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.daemon import Daemon, DaemonState
from graphify_daemon.paths import DaemonPaths


def _daemon(tmp_path: Path) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths)


def test_daemon_starts_running_and_ends_stopped_after_shutdown(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()
    daemon.start()
    assert daemon._state is DaemonState.RUNNING

    daemon.shutdown()

    assert daemon._state is DaemonState.STOPPED


def test_repeated_shutdown_does_not_revert_to_an_earlier_state(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()
    daemon.start()

    daemon.shutdown()
    assert daemon._state is DaemonState.STOPPED

    daemon.shutdown()
    assert daemon._state is DaemonState.STOPPED
