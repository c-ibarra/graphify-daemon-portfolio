"""Ordered SIGTERM drain: let an in-flight batch finish, then persist artifacts.

See specs/artifact-lifecycle/spec.md "Ordered shutdown drain".

Actual `signal.signal(SIGTERM, ...)` registration belongs to whatever
process-level entrypoint eventually runs this daemon — out of scope here,
same deferral as task group 7's `run()`. This module provides the
drain-then-persist primitive that a signal handler would call.
"""

from __future__ import annotations

import threading
from collections.abc import Callable


class ShutdownCoordinator:
    """A lock-based drain: `run_batch` and `shutdown` never overlap.

    `run_batch` is what `BatchConsumer.consume` (task group 3) gets wrapped
    in. `shutdown` blocks until any in-flight `run_batch` call finishes —
    the same lock both use — then runs `persist`, guaranteeing that batch's
    artifacts are the ones persisted, per "SIGTERM during an active batch
    completes cleanly".
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def run_batch(self, fn: Callable[[], None]) -> None:
        with self._lock:
            fn()

    def shutdown(self, persist: Callable[[], None]) -> None:
        with self._lock:
            persist()
