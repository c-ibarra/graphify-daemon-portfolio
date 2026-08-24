"""File-change batching for the vault watcher.

See specs/vault-compiler/spec.md "Debounce batching" and
"Single reconstruction per batch".
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from graphify_daemon.vault_compiler.exclusions import is_excluded

logger = logging.getLogger(__name__)

DEFAULT_PENDING_WARN_THRESHOLD = 200

if TYPE_CHECKING:
    # Deferred to avoid a runtime cycle: artifact_lifecycle.metrics ->
    # vault_compiler.snapshot -> vault_compiler.extraction -> this module.
    from graphify_daemon.artifact_lifecycle.metrics import Metrics


class ChangeKind(Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


_WATCHDOG_EVENT_KIND: dict[str, ChangeKind] = {
    "created": ChangeKind.CREATED,
    "modified": ChangeKind.MODIFIED,
    "deleted": ChangeKind.DELETED,
    "moved": ChangeKind.RENAMED,
}


@dataclass(frozen=True)
class FileChange:
    path: Path
    kind: ChangeKind


@dataclass(frozen=True)
class Batch:
    """The set of vault files changed within one debounce window. See CONTEXT.md: Batch."""

    changes: tuple[FileChange, ...]


class _DebouncedEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        vault_root: Path,
        nested_repo_names: frozenset[str],
        on_change: Callable[[FileChange], None],
    ) -> None:
        self._vault_root = vault_root
        self._nested_repo_names = nested_repo_names
        self._on_change = on_change

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        kind = _WATCHDOG_EVENT_KIND.get(event.event_type)
        if kind is None:
            return
        raw_path = event.dest_path if kind is ChangeKind.RENAMED else event.src_path
        path = Path(raw_path.decode() if isinstance(raw_path, bytes) else raw_path)
        if is_excluded(path, self._vault_root, nested_repo_names=self._nested_repo_names):
            return
        self._on_change(FileChange(path=path, kind=kind))


class VaultWatcher:
    """Watches `vault_root` recursively; emits one `Batch` per debounce window.

    Applies `exclusions.is_excluded` before an event is included in a batch.
    """

    def __init__(
        self,
        vault_root: Path,
        on_batch: Callable[[Batch], None],
        *,
        debounce_ms: int = 300,
        nested_repo_names: frozenset[str] = frozenset(),
        metrics: Metrics | None = None,
        pending_warn_threshold: int = DEFAULT_PENDING_WARN_THRESHOLD,
    ) -> None:
        self._vault_root = vault_root
        self._on_batch = on_batch
        self._debounce_seconds = debounce_ms / 1000
        self._metrics = metrics
        self._pending_warn_threshold = pending_warn_threshold
        self._warned_this_episode = False
        self._lock = threading.Lock()
        self._pending: list[FileChange] = []
        self._timer: threading.Timer | None = None
        self._handler = _DebouncedEventHandler(vault_root, nested_repo_names, self._queue_change)
        self._observer = Observer()
        self._observer.schedule(self._handler, str(vault_root), recursive=True)

    def start(self) -> None:
        self._observer.start()

    def stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._observer.stop()
        self._observer.join()

    def _queue_change(self, change: FileChange) -> None:
        with self._lock:
            self._pending.append(change)
            if self._metrics is not None:
                self._metrics.set_gauge("queue_depth", len(self._pending))
            if len(self._pending) >= self._pending_warn_threshold and not self._warned_this_episode:
                logger.warning(
                    "Pending change queue depth (%d) crossed threshold (%d)",
                    len(self._pending),
                    self._pending_warn_threshold,
                )
                if self._metrics is not None:
                    self._metrics.increment("queue_depth_warnings")
                self._warned_this_episode = True
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_seconds, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            if not self._pending:
                return
            batch = Batch(changes=tuple(self._pending))
            self._pending.clear()
            self._warned_this_episode = False
            if self._metrics is not None:
                self._metrics.set_gauge("queue_depth", 0)
            self._timer = None
        self._on_batch(batch)


class BatchConsumer:
    """Single-writer: calls `compile_batch` exactly once per `Batch`, never per file.

    Decoupled from `VaultWatcher` so cold-start reconciliation (task 11.2)
    can hand it a `Batch` directly, without going through the filesystem watcher.
    """

    def __init__(self, compile_batch: Callable[[Batch], None]) -> None:
        self._compile_batch = compile_batch

    def consume(self, batch: Batch) -> None:
        self._compile_batch(batch)
