"""daemon._on_batch serializes batch compilation: two near-simultaneous
batches never interleave.

See specs/vault-compiler/spec.md "Single-writer batch execution".
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


def _daemon(tmp_path: Path, **kwargs) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths, **kwargs)


def test_two_near_simultaneous_batches_never_interleave(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = _daemon(tmp_path)
    a = daemon.vault_root / "a.md"
    a.write_text("# A\n")
    b = daemon.vault_root / "b.md"
    b.write_text("# B\n")

    events: list[str] = []

    def _fake_extract_batch(batch, vault_root, cache, *, metrics=None):
        name = batch.changes[0].path.name
        events.append(f"{name}-start")
        time.sleep(0.2)
        events.append(f"{name}-end")
        return {}

    monkeypatch.setattr(daemon_module, "extract_batch", _fake_extract_batch)

    batch_a = Batch(changes=(FileChange(path=a, kind=ChangeKind.MODIFIED),))
    batch_b = Batch(changes=(FileChange(path=b, kind=ChangeKind.MODIFIED),))

    thread_a = threading.Thread(target=lambda: daemon._on_batch(batch_a))
    thread_b = threading.Thread(target=lambda: daemon._on_batch(batch_b))

    thread_a.start()
    time.sleep(0.05)  # let a.md's batch actually start and take the coordinator lock
    thread_b.start()

    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert events == ["a.md-start", "a.md-end", "b.md-start", "b.md-end"]
