"""vault_index.db: per-batch writes with SQLite concurrency safety.

See specs/artifact-lifecycle/spec.md "Artifact cadence table" and
"SQLite concurrency safety".
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from graphify_daemon.artifact_lifecycle import vault_index
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache


def test_busy_timeout_is_at_least_5000ms(tmp_path: Path) -> None:
    conn = vault_index.connect(tmp_path / "vault_index.db")
    (value,) = conn.execute("PRAGMA busy_timeout").fetchone()
    assert value >= vault_index.MIN_BUSY_TIMEOUT_MS


def test_synchronous_is_explicitly_set(tmp_path: Path) -> None:
    conn = vault_index.connect(tmp_path / "vault_index.db")
    (value,) = conn.execute("PRAGMA synchronous").fetchone()
    assert value in (0, 1, 2, 3)


def test_init_schema_creates_files_table(tmp_path: Path) -> None:
    conn = vault_index.connect(tmp_path / "vault_index.db")
    vault_index.init_schema(conn)
    conn.execute(
        "INSERT INTO files (path, mtime, size, node_count, edge_count) VALUES (?, ?, ?, ?, ?)",
        ("a.md", 1.0, 10, 2, 1),
    )
    conn.commit()
    row = conn.execute("SELECT path, node_count FROM files WHERE path = 'a.md'").fetchone()
    assert row == ("a.md", 2)


def test_concurrent_writer_waits_instead_of_failing_immediately(tmp_path: Path) -> None:
    db_path = tmp_path / "vault_index.db"
    conn1 = vault_index.connect(db_path)
    vault_index.init_schema(conn1)
    conn1.execute("BEGIN IMMEDIATE")
    conn1.execute(
        "INSERT INTO files (path, mtime, size, node_count, edge_count) VALUES (?, ?, ?, ?, ?)",
        ("a.md", 1.0, 10, 1, 0),
    )
    # lock held, not yet committed

    outcome: dict[str, float] = {}

    def try_write() -> None:
        # A separate connection, created in this thread -- sqlite3
        # connections are thread-affine by default.
        conn2 = vault_index.connect(db_path)
        start = time.monotonic()
        conn2.execute(
            "INSERT INTO files (path, mtime, size, node_count, edge_count) VALUES (?, ?, ?, ?, ?)",
            ("b.md", 2.0, 20, 1, 0),
        )
        conn2.commit()
        outcome["waited"] = time.monotonic() - start

    thread = threading.Thread(target=try_write)
    thread.start()
    time.sleep(0.1)
    conn1.commit()
    thread.join(timeout=6)

    assert not thread.is_alive(), "the concurrent writer never got past busy_timeout"
    assert outcome["waited"] >= 0.08, "expected the writer to wait for the lock, not fail instantly"


def test_connection_survives_use_from_a_different_thread(tmp_path: Path) -> None:
    # Reproduces the daemon's real shape: `connect()` happens in one thread
    # (the constructor's), and `sync_batch` runs later on a fresh
    # `threading.Timer` thread per debounce flush (batching.py). Without
    # `check_same_thread=False` this raises sqlite3.ProgrammingError on
    # every single real batch -- caught live, not by the existing tests,
    # since they all call `sync_batch` synchronously in the test's own thread.
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    changed = vault_root / "a.md"
    changed.write_text("# A\n")

    conn = vault_index.connect(tmp_path / "vault_index.db")
    vault_index.init_schema(conn)

    batch = Batch(changes=(FileChange(path=changed, kind=ChangeKind.MODIFIED),))
    error: list[BaseException] = []

    def run_in_other_thread() -> None:
        try:
            vault_index.sync_batch(conn, batch, vault_root, ExtractionCache())
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    thread = threading.Thread(target=run_in_other_thread)
    thread.start()
    thread.join(timeout=5)

    assert not error, f"sync_batch raised from a different thread: {error}"
    row = conn.execute("SELECT path FROM files WHERE path = 'a.md'").fetchone()
    assert row is not None


def test_sync_batch_upserts_changed_files_and_deletes_removed_ones(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    kept = vault_root / "kept.md"
    kept.write_text("# Kept\n")
    deleted_path = vault_root / "deleted.md"

    conn = vault_index.connect(tmp_path / "vault_index.db")
    vault_index.init_schema(conn)

    # Seed a row for the file that this batch will delete.
    conn.execute(
        "INSERT INTO files (path, mtime, size, node_count, edge_count) VALUES (?, ?, ?, ?, ?)",
        ("deleted.md", 0.0, 5, 1, 0),
    )
    conn.commit()

    cache = ExtractionCache()
    cache.set(Path("kept.md"), {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [{"source": "n1", "target": "n2"}]})

    batch = Batch(
        changes=(
            FileChange(path=kept, kind=ChangeKind.MODIFIED),
            FileChange(path=deleted_path, kind=ChangeKind.DELETED),
        )
    )

    vault_index.sync_batch(conn, batch, vault_root, cache)

    rows = {row[0]: row for row in conn.execute("SELECT path, node_count, edge_count FROM files")}
    assert "deleted.md" not in rows
    assert rows["kept.md"][1:] == (2, 1)
