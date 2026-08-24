"""An in-flight slow-cadence clustering run delays the next batch's
compilation -- it isn't raced.

See specs/vault-compiler/spec.md "Clustering serializes the next batch".
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from graphify_daemon.artifact_lifecycle import cadence as cadence_module
from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange


def _daemon(tmp_path: Path, **kwargs) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths, **kwargs)


def test_batch_triggered_during_active_clustering_waits_for_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = _daemon(tmp_path, slow_cadence_change_threshold=1)
    daemon.cold_start()

    a = daemon.vault_root / "a.md"
    a.write_text("# A\n")
    b = daemon.vault_root / "b.md"
    b.write_text("# B\n")

    events: list[str] = []

    def _fake_run_clustering_cycle(holder, *, timeout=None, metrics=None):
        events.append("clustering-start")
        time.sleep(0.3)
        events.append("clustering-end")
        return None

    monkeypatch.setattr(cadence_module, "run_clustering_cycle", _fake_run_clustering_cycle)

    batch_a = Batch(changes=(FileChange(path=a, kind=ChangeKind.MODIFIED),))
    batch_b = Batch(changes=(FileChange(path=b, kind=ChangeKind.MODIFIED),))

    thread_a = threading.Thread(target=lambda: daemon._on_batch(batch_a))
    thread_a.start()
    time.sleep(0.05)  # let batch A actually enter the fake clustering's sleep

    daemon._on_batch(batch_b)
    events.append("batch-b-done")

    thread_a.join(timeout=5)

    assert events.index("clustering-end") < events.index("batch-b-done")
