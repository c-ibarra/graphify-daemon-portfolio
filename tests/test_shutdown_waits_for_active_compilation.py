"""Shutdown waits for an in-flight batch compilation before persisting.

Reuses the interception pattern from the archived
harden-graphify-daemon-audit's test_daemon_single_writer.py.

See specs/artifact-lifecycle/spec.md "Shutdown drains the pending
debounce batch before persisting".
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from graphify_daemon import daemon as daemon_module
from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange


def _daemon(tmp_path: Path) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths)


def test_shutdown_waits_for_an_in_flight_batch_before_persisting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()
    daemon.start()

    events: list[str] = []

    def fake_extract_batch(batch, vault_root, cache, *, metrics=None, nested_repo_names=frozenset()):
        events.append("batch-start")
        time.sleep(0.2)
        events.append("batch-end")
        return {}

    monkeypatch.setattr(daemon_module, "extract_batch", fake_extract_batch)

    original_persist = daemon.persist_on_shutdown

    def spy_persist() -> None:
        events.append("persisted")
        original_persist()

    monkeypatch.setattr(daemon, "persist_on_shutdown", spy_persist)

    # Deliberately not written to disk: extract_batch is faked and never
    # touches the real filesystem, and the daemon's own live watcher (it's
    # started, so shutdown() can stop/join it without error) must not
    # observe a real file write here -- that would queue a second, genuine
    # batch that shutdown()'s own drain would separately compile, racing
    # this synthetic one and doubling the fake's "batch-start" count.
    a = daemon.vault_root / "a.md"
    batch = Batch(changes=(FileChange(path=a, kind=ChangeKind.MODIFIED),))

    batch_thread = threading.Thread(target=lambda: daemon._on_batch(batch))
    batch_thread.start()
    time.sleep(0.05)  # let the batch actually start and take the coordinator lock

    daemon.shutdown()
    batch_thread.join(timeout=5)

    assert events == ["batch-start", "batch-end", "persisted"]
