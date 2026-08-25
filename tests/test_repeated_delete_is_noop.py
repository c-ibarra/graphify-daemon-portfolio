"""A second DELETED event for the same path is a no-op, not an error.

See specs/vault-compiler/spec.md "Idempotent deletion".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.artifact_lifecycle.vault_index import connect, init_schema, sync_batch
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_second_delete_for_the_same_path_does_not_raise_or_change_state(tmp_path: Path) -> None:
    note = tmp_path / "gone.md"
    note.write_text("# Gone\n")
    cache = ExtractionCache()
    conn = connect(tmp_path / "vault_index.db")
    init_schema(conn)

    create = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    extract_batch(create, tmp_path, cache)
    sync_batch(conn, create, tmp_path, cache)

    note.unlink()
    first = Batch(changes=(FileChange(path=note, kind=ChangeKind.DELETED),))
    extract_batch(first, tmp_path, cache)
    sync_batch(conn, first, tmp_path, cache)

    second = Batch(changes=(FileChange(path=note, kind=ChangeKind.DELETED),))
    extract_batch(second, tmp_path, cache)  # must not raise
    sync_batch(conn, second, tmp_path, cache)  # must not raise

    assert cache.get(Path("gone.md")) is None
    assert conn.execute("SELECT 1 FROM files WHERE path = ?", ("gone.md",)).fetchone() is None
