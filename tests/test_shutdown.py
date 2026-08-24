"""Ordered SIGTERM drain: an in-flight batch finishes before artifacts persist.

See specs/artifact-lifecycle/spec.md "Ordered shutdown drain".
"""

from __future__ import annotations

import threading
import time

from graphify_daemon.artifact_lifecycle.shutdown import ShutdownCoordinator


def test_shutdown_waits_for_an_in_flight_batch_before_persisting() -> None:
    coordinator = ShutdownCoordinator()
    events: list[str] = []

    def slow_batch() -> None:
        events.append("batch-start")
        time.sleep(0.2)
        events.append("batch-end")

    def persist() -> None:
        events.append("persisted")

    batch_thread = threading.Thread(target=lambda: coordinator.run_batch(slow_batch))
    batch_thread.start()
    time.sleep(0.05)  # let the batch actually start

    coordinator.shutdown(persist)
    batch_thread.join(timeout=5)

    assert events == ["batch-start", "batch-end", "persisted"]


def test_shutdown_persists_immediately_when_no_batch_is_in_flight() -> None:
    coordinator = ShutdownCoordinator()
    called = []
    coordinator.shutdown(lambda: called.append(True))
    assert called == [True]


def test_run_batch_after_shutdown_still_runs() -> None:
    """shutdown() doesn't prevent a subsequent run_batch call from acquiring
    the lock -- the coordinator only sequences them, it isn't a one-shot
    kill switch. (The daemon's own entrypoint decides whether to accept new
    batches after a shutdown request; that's outside this primitive.)"""
    coordinator = ShutdownCoordinator()
    coordinator.shutdown(lambda: None)

    ran = []
    coordinator.run_batch(lambda: ran.append(True))
    assert ran == [True]
