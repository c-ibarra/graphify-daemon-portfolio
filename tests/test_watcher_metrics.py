"""VaultWatcher reports its pending-change queue depth to an optional Metrics registry."""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.batching import Batch, VaultWatcher


def test_queue_depth_gauge_reflects_pending_changes(tmp_path: Path) -> None:
    metrics = Metrics()
    batches: list[Batch] = []
    watcher = VaultWatcher(tmp_path, batches.append, debounce_ms=200, metrics=metrics)
    watcher.start()
    try:
        (tmp_path / "a.md").write_text("a")
        time.sleep(0.05)
        (tmp_path / "b.md").write_text("b")
        time.sleep(0.05)
        # Not asserting an exact count: a single write can surface as more
        # than one filesystem event depending on the platform/watchdog
        # backend (e.g. created + modified). What matters is that pending
        # changes are visible before the debounce window flushes.
        assert metrics.gauge("queue_depth") > 0

        time.sleep(0.3)  # let the debounce window flush
        assert metrics.gauge("queue_depth") == 0
    finally:
        watcher.stop()


def test_metrics_is_optional(tmp_path: Path) -> None:
    watcher = VaultWatcher(tmp_path, lambda batch: None, debounce_ms=100)
    watcher.start()
    watcher.stop()  # no metrics kwarg -- must not raise
