"""The next snapshot has no node/edge whose only provenance is a deleted file.

See specs/vault-compiler/spec.md "Idempotent deletion".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch
from graphify_daemon.vault_compiler.snapshot import build_graph


def test_deleted_files_node_is_gone_from_the_next_build(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("# Deletable\n\nSome content.\n")
    cache = ExtractionCache()

    create_batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, tmp_path, cache)
    graph_before = build_graph(cache)
    assert any(d.get("source_file") == "note.md" for _, d in graph_before.nodes(data=True))

    note.unlink()
    delete_batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.DELETED),))
    extract_batch(delete_batch, tmp_path, cache)
    graph_after = build_graph(cache)

    assert not any(d.get("source_file") == "note.md" for _, d in graph_after.nodes(data=True))
    assert not any(d.get("source_file") == "note.md" for _, _, d in graph_after.edges(data=True))
