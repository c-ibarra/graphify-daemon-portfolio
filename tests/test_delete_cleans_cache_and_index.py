"""Idempotent deletion: cache, mtime, and SQLite index end up clean.

See specs/vault-compiler/spec.md "Idempotent deletion".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.artifact_lifecycle.vault_index import connect, init_schema, sync_batch
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_deleting_an_existing_file_cleans_cache_mtime_and_index(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("# Note\n")
    cache = ExtractionCache()
    conn = connect(tmp_path / "vault_index.db")
    init_schema(conn)

    create_batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, tmp_path, cache)
    sync_batch(conn, create_batch, tmp_path, cache)

    assert cache.get(Path("note.md")) is not None
    assert cache.mtime(Path("note.md")) is not None
    assert conn.execute("SELECT 1 FROM files WHERE path = ?", ("note.md",)).fetchone() is not None

    note.unlink()
    delete_batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.DELETED),))
    extract_batch(delete_batch, tmp_path, cache)
    sync_batch(conn, delete_batch, tmp_path, cache)

    assert cache.get(Path("note.md")) is None
    assert cache.mtime(Path("note.md")) is None
    assert conn.execute("SELECT 1 FROM files WHERE path = ?", ("note.md",)).fetchone() is None
