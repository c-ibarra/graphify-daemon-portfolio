"""Per-batch vault_index.db writes, with SQLite concurrency safety.

See specs/artifact-lifecycle/spec.md "Artifact cadence table" and
"SQLite concurrency safety".

Schema note: this is a fresh, minimal schema for this daemon's own
per-batch index (path, mtime, size, node/edge counts) — not a replica of
the legacy watcher's vault_db.py schema (files/links/contradictions with
bespoke title/author/blockquote metadata parsing). Schema compatibility
for the 5 legacy consumers is task group 12's decision, made when those
scripts are actually inspected for migration.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from graphify_daemon.artifact_lifecycle.security import restrict_to_owner
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind
from graphify_daemon.vault_compiler.exclusions import is_excluded
from graphify_daemon.vault_compiler.extraction import ExtractionCache

MIN_BUSY_TIMEOUT_MS = 5000


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with `busy_timeout` >= 5000ms and an explicit `synchronous` pragma.

    `check_same_thread=False`: the daemon opens one connection in its
    constructor's thread and reuses it from `VaultWatcher`'s debounce
    `threading.Timer` thread, which is a new thread every time it fires
    (see `batching.py`'s `_queue_change`). Safe because `sync_batch` is
    never called concurrently from two threads at once -- the single-writer
    batch consumer (task 3.6) serializes access, sqlite3's default
    same-thread check just doesn't know that.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    restrict_to_owner(db_path.parent)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={MIN_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    restrict_to_owner(db_path)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the `files` table if it doesn't exist."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL
            )
            """
        )


def sync_batch(
    conn: sqlite3.Connection,
    batch: Batch,
    vault_root: Path,
    cache: ExtractionCache,
    *,
    nested_repo_names: frozenset[str] = frozenset(),
) -> None:
    """Upsert or delete one `files` row per `FileChange` in `batch`.

    `node_count`/`edge_count` come from `cache`'s extraction result for
    that file when present, else 0.

    `RENAMED` changes delete `previous_path`'s row before the destination
    is processed, mirroring `extraction.extract_batch`'s own ordering —
    see specs/vault-compiler/spec.md "Rename carries source and
    destination as one logical unit". If the destination is excluded
    (`nested_repo_names` mirrors the watcher's own exclusion config), no
    row is created for it, matching that same rename-into-exclusion is
    equivalent to deletion.
    """
    with conn:
        for change in batch.changes:
            relative = change.path.relative_to(vault_root)
            if change.kind is ChangeKind.DELETED:
                conn.execute("DELETE FROM files WHERE path = ?", (str(relative),))
                continue
            if change.kind is ChangeKind.RENAMED:
                assert change.previous_path is not None  # enforced by FileChange.__post_init__
                previous_relative = change.previous_path.relative_to(vault_root)
                conn.execute("DELETE FROM files WHERE path = ?", (str(previous_relative),))
                if is_excluded(change.path, vault_root, nested_repo_names=nested_repo_names):
                    continue
            result = cache.get(relative)
            node_count = len(result["nodes"]) if result else 0
            edge_count = len(result["edges"]) if result else 0
            try:
                stat = change.path.stat()
                mtime, size = stat.st_mtime, stat.st_size
            except FileNotFoundError:
                mtime, size = 0.0, 0
            conn.execute(
                """
                INSERT INTO files (path, mtime, size, node_count, edge_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    mtime=excluded.mtime,
                    size=excluded.size,
                    node_count=excluded.node_count,
                    edge_count=excluded.edge_count
                """,
                (str(relative), mtime, size, node_count, edge_count),
            )
