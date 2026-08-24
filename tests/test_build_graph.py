"""Merging the full ExtractionCache corpus into one graph.

See specs/vault-compiler/spec.md "Immutable snapshot structure".
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_file
from graphify_daemon.vault_compiler.snapshot import build_graph


def test_build_graph_merges_every_cached_file(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    a.write_text("# A\n\nLinks to [B](./b.md).\n")
    b = tmp_path / "b.md"
    b.write_text("# B\n")

    cache = ExtractionCache()
    cache.set(Path("a.md"), extract_file(a, tmp_path))
    cache.set(Path("b.md"), extract_file(b, tmp_path))

    graph = build_graph(cache)

    assert isinstance(graph, nx.DiGraph)
    source_files = {data["source_file"] for _, data in graph.nodes(data=True)}
    assert source_files == {"a.md", "b.md"}
