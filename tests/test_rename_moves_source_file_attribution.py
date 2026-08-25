"""A normal rename leaves no trace of the previous path in the next snapshot.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch
from graphify_daemon.vault_compiler.snapshot import build_graph


def test_rename_moves_source_file_attribution(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    destination = tmp_path / "b.md"
    source.write_text("# A\n\nSome content about A.\n")
    cache = ExtractionCache()

    create_batch = Batch(changes=(FileChange(path=source, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, tmp_path, cache)
    assert cache.get(Path("a.md")) is not None

    source.rename(destination)  # the real filesystem move, as if a watcher already observed it
    rename_batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))
    extract_batch(rename_batch, tmp_path, cache)

    assert cache.get(Path("a.md")) is None
    assert cache.get(Path("b.md")) is not None

    graph = build_graph(cache)
    assert not any(d.get("source_file") == "a.md" for _, d in graph.nodes(data=True))
    assert any(d.get("source_file") == "b.md" for _, d in graph.nodes(data=True))
