"""VaultWatcher surfaces observable backpressure: a warning (log +
metric) once per pending-file accumulation episode past a configurable
threshold -- never once per file, and never a second time within the
same still-accumulating episode.

See specs/vault-compiler/spec.md "Observable pending-file backpressure".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.batching import VaultWatcher


def test_one_accumulation_episode_warns_exactly_once(tmp_path: Path) -> None:
    metrics = Metrics()
    watcher = VaultWatcher(
        tmp_path,
        lambda batch: None,
        debounce_ms=1000,  # long enough that all 3 writes land in one episode
        metrics=metrics,
        pending_warn_threshold=2,
    )
    watcher.start()
    try:
        (tmp_path / "a.md").write_text("a")
        time.sleep(0.02)
        (tmp_path / "b.md").write_text("b")
        time.sleep(0.02)
        (tmp_path / "c.md").write_text("c")
        time.sleep(0.1)  # give the threshold check time to run, well before the 1s flush

        assert metrics.counter("queue_depth_warnings") == 1
    finally:
        watcher.stop()


def test_two_separate_episodes_warn_twice(tmp_path: Path) -> None:
    metrics = Metrics()
    watcher = VaultWatcher(
        tmp_path,
        lambda batch: None,
        debounce_ms=100,
        metrics=metrics,
        pending_warn_threshold=1,
    )
    watcher.start()
    try:
        (tmp_path / "a.md").write_text("a")
        time.sleep(0.3)  # let the first episode flush
        assert metrics.counter("queue_depth_warnings") == 1

        (tmp_path / "b.md").write_text("b")
        time.sleep(0.3)  # let the second episode flush
        assert metrics.counter("queue_depth_warnings") == 2
    finally:
        watcher.stop()
