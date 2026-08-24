"""No tool implementation reads from disk on the query path.

See specs/graph-query-api/spec.md "No disk reads on the query path": every
query is resolved against the in-RAM snapshot, never graph.json. Verified
here more strictly than the literal "rename graph.json away" scenario --
this daemon's query path never opens ANY file at all, so we assert that
directly rather than depending on a specific file being absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify_daemon.graph_query_api.tools import execute_tool
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_file
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder, build_graph

QUERIES = [
    ("query_graph", {"question": "Alpha"}),
    ("get_node", {"label": "alpha.md"}),
    ("get_neighbors", {"label": "alpha.md"}),
    ("get_community", {"community_id": 0}),
    ("god_nodes", {}),
    ("graph_stats", {}),
    ("shortest_path", {"source": "alpha.md", "target": "beta.md"}),
]


def test_no_tool_touches_disk_during_query_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = tmp_path / "alpha.md"
    a.write_text("# Alpha\n\nLinks to [Beta](./beta.md).\n")
    b = tmp_path / "beta.md"
    b.write_text("# Beta\n")

    cache = ExtractionCache()
    cache.set(Path("alpha.md"), extract_file(a, tmp_path))
    cache.set(Path("beta.md"), extract_file(b, tmp_path))

    holder = SnapshotHolder()
    graph = build_graph(cache)
    snapshot = holder.publish(graph, {0: list(graph.nodes())})

    def _forbidden_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the query path must never open a file")

    monkeypatch.setattr(Path, "open", _forbidden_open)

    for name, arguments in QUERIES:
        execute_tool(name, arguments, snapshot)
