"""The seven tools produce correct output against a real snapshot.

See specs/graph-query-api/spec.md "Minimum read tool surface".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify_daemon.graph_query_api.tools import execute_tool
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_file
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


@pytest.fixture
def snapshot(tmp_path: Path):
    a = tmp_path / "alpha.md"
    a.write_text("# Alpha\n\nLinks to [Beta](./beta.md) and mentions `Gamma`.\n")
    b = tmp_path / "beta.md"
    b.write_text("# Beta\n\nSome content about Gamma.\n")

    cache = ExtractionCache()
    cache.set(Path("alpha.md"), extract_file(a, tmp_path))
    cache.set(Path("beta.md"), extract_file(b, tmp_path))

    from graphify_daemon.vault_compiler.snapshot import build_graph

    holder = SnapshotHolder()
    graph = build_graph(cache)
    community_map = {0: list(graph.nodes())}
    return holder.publish(graph, community_map)


def test_query_graph(snapshot) -> None:
    result = execute_tool("query_graph", {"question": "Alpha"}, snapshot)
    assert "Alpha" in result


def test_get_node(snapshot) -> None:
    result = execute_tool("get_node", {"label": "alpha.md"}, snapshot)
    assert "Node:" in result


def test_get_node_no_match(snapshot) -> None:
    result = execute_tool("get_node", {"label": "does-not-exist"}, snapshot)
    assert "No node matching" in result


def test_get_neighbors(snapshot) -> None:
    result = execute_tool("get_neighbors", {"label": "alpha.md"}, snapshot)
    assert "Neighbors of" in result


def test_get_community(snapshot) -> None:
    result = execute_tool("get_community", {"community_id": 0}, snapshot)
    assert "Community 0" in result


def test_get_community_not_found(snapshot) -> None:
    result = execute_tool("get_community", {"community_id": 999}, snapshot)
    assert "not found" in result


def test_god_nodes(snapshot) -> None:
    result = execute_tool("god_nodes", {}, snapshot)
    assert "God nodes" in result


def test_graph_stats(snapshot) -> None:
    result = execute_tool("graph_stats", {}, snapshot)
    assert "Nodes:" in result
    assert "Edges:" in result
    assert "Communities: 1" in result


def test_shortest_path(snapshot) -> None:
    result = execute_tool("shortest_path", {"source": "alpha.md", "target": "beta.md"}, snapshot)
    assert isinstance(result, str)
    assert result
