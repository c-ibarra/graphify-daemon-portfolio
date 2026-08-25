"""After shutdown() completes, no new non-daemon thread remains alive.

See specs/artifact-lifecycle/spec.md "Uniform cleanup across SIGTERM,
SIGINT, and normal exit".
"""

from __future__ import annotations

import threading
from pathlib import Path

from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths


def test_shutdown_leaves_no_new_alive_nondaemon_threads(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    daemon = Daemon(vault_root, paths)
    daemon.cold_start()

    before = {t.ident for t in threading.enumerate()}

    daemon.start()
    daemon.shutdown()

    surviving_new_threads = [
        t for t in threading.enumerate() if t.ident not in before and t.is_alive() and not t.daemon
    ]
    assert surviving_new_threads == []
