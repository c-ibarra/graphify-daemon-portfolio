"""VaultWatcher.schedule_idle fires its callback after the quiet period,
with no batch involved.

See specs/vault-compiler/spec.md "Slow-cadence idle trigger fires without
a subsequent batch".
"""

from __future__ import annotations

import threading
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, VaultWatcher


def test_idle_timer_fires_without_further_batch(tmp_path: Path) -> None:
    batches: list[Batch] = []
    watcher = VaultWatcher(tmp_path, batches.append, debounce_ms=100)

    fired = threading.Event()
    watcher.schedule_idle(fired.set, 0.1)

    assert fired.wait(timeout=1.0)
    assert batches == []
