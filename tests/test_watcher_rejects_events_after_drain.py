"""VaultWatcher.reject_new_events() stops new events from being queued;
drain_pending_batch() returns exactly what was queued before that point.

See specs/artifact-lifecycle/spec.md "Explicit lifecycle states gate
event acceptance" and "Shutdown drains the pending debounce batch before
persisting".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, VaultWatcher


def test_events_after_reject_new_events_are_dropped(tmp_path: Path) -> None:
    batches: list[Batch] = []
    # A long debounce so nothing auto-flushes mid-test -- drain_pending_batch
    # is what's under test, not the debounce timer itself.
    watcher = VaultWatcher(tmp_path, batches.append, debounce_ms=10_000)
    watcher.start()
    try:
        (tmp_path / "a.md").write_text("a")
        time.sleep(0.3)  # let the real watchdog event reach _queue_change

        watcher.reject_new_events()

        (tmp_path / "b.md").write_text("b")
        time.sleep(0.3)

        pending = watcher.drain_pending_batch()
    finally:
        watcher.stop()

    assert batches == []  # debounce (10s) never fired
    assert pending is not None
    assert {change.path.name for change in pending.changes} == {"a.md"}
