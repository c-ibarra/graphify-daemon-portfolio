"""A new schedule_idle call replaces the previous idle timer.

See specs/vault-compiler/spec.md "Slow-cadence idle trigger fires without
a subsequent batch".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.vault_compiler.batching import VaultWatcher


def test_second_schedule_idle_replaces_the_first(tmp_path: Path) -> None:
    watcher = VaultWatcher(tmp_path, lambda _batch: None, debounce_ms=100)

    calls: list[str] = []
    watcher.schedule_idle(lambda: calls.append("first"), 0.15)
    time.sleep(0.05)  # well before the first timer would fire
    watcher.schedule_idle(lambda: calls.append("second"), 0.15)

    time.sleep(0.4)  # comfortably past both timers' quiet periods

    assert calls == ["second"]
