"""Shutdown compiles whatever's still pending in the debounce window,
instead of silently dropping it the way watcher.stop() alone used to.

See specs/artifact-lifecycle/spec.md "Shutdown drains the pending
debounce batch before persisting".
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths


def test_shutdown_compiles_a_batch_still_sitting_in_the_debounce_window(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    # A long debounce so the real watchdog event is still pending, not yet
    # auto-flushed, when shutdown() is called.
    daemon = Daemon(vault_root, paths, debounce_ms=10_000)
    daemon.cold_start()
    daemon.start()

    note = vault_root / "note.md"
    note.write_text("# Note\n\nSome content.\n")
    time.sleep(0.3)  # let the real watchdog event reach the pending queue

    daemon.shutdown()

    snapshot = daemon.holder.current()
    assert snapshot is not None
    assert any(d.get("source_file") == "note.md" for _, d in snapshot.graph.nodes(data=True))

    cache_data = json.loads(daemon.paths.graph_cache_json.read_text())
    assert "note.md" in cache_data["entries"]
