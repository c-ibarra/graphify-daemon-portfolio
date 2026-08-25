"""Calling shutdown() twice is safe: the second call is a no-op.

See specs/artifact-lifecycle/spec.md "Shutdown is idempotent".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths


def _daemon(tmp_path: Path) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths)


def test_second_shutdown_call_does_not_persist_or_close_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()
    daemon.start()

    calls: list[bool] = []
    original_persist = daemon.persist_on_shutdown

    def spy_persist() -> None:
        calls.append(True)
        original_persist()

    monkeypatch.setattr(daemon, "persist_on_shutdown", spy_persist)

    daemon.shutdown()
    daemon.shutdown()  # must not raise, must not persist a second time

    assert calls == [True]
