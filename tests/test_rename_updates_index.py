"""vault_index.db reflects a rename on both its previous and destination path.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.artifact_lifecycle.vault_index import connect, init_schema, sync_batch
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_rename_moves_the_index_row(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    source = vault_root / "a.md"
    destination = vault_root / "b.md"
    source.write_text("# A\n")

    cache = ExtractionCache()
    conn = connect(tmp_path / "vault_index.db")
    init_schema(conn)

    create_batch = Batch(changes=(FileChange(path=source, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, vault_root, cache)
    sync_batch(conn, create_batch, vault_root, cache)
    assert conn.execute("SELECT 1 FROM files WHERE path = ?", ("a.md",)).fetchone() is not None

    source.rename(destination)
    rename_batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))
    extract_batch(rename_batch, vault_root, cache)
    sync_batch(conn, rename_batch, vault_root, cache)

    assert conn.execute("SELECT 1 FROM files WHERE path = ?", ("a.md",)).fetchone() is None
    assert conn.execute("SELECT 1 FROM files WHERE path = ?", ("b.md",)).fetchone() is not None


def test_rename_into_exclusion_removes_row_without_creating_a_destination_row(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    source = vault_root / "a.md"
    source.write_text("# A\n")
    excluded_dir = vault_root / ".trash"
    excluded_dir.mkdir()
    destination = excluded_dir / "a.md"

    cache = ExtractionCache()
    conn = connect(tmp_path / "vault_index.db")
    init_schema(conn)

    create_batch = Batch(changes=(FileChange(path=source, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, vault_root, cache)
    sync_batch(conn, create_batch, vault_root, cache)

    source.rename(destination)
    rename_batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))
    extract_batch(rename_batch, vault_root, cache)
    sync_batch(conn, rename_batch, vault_root, cache)

    assert conn.execute("SELECT path FROM files").fetchall() == []
