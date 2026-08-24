"""The 7 read tools behave correctly against an empty graph -- pins the
already-correct non-crashing behavior against a future regression.

See specs/graph-query-api/spec.md "Read tools handle an empty graph".
"""

from __future__ import annotations

import pytest

from graphify_daemon.graph_query_api.tools import execute_tool
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder, build_graph


@pytest.fixture
def empty_snapshot():
    holder = SnapshotHolder()
    graph = build_graph(ExtractionCache())
    return holder.publish(graph, {})


def test_god_nodes_against_empty_graph(empty_snapshot) -> None:
    result = execute_tool("god_nodes", {}, empty_snapshot)
    assert isinstance(result, str)


def test_shortest_path_against_empty_graph(empty_snapshot) -> None:
    result = execute_tool("shortest_path", {"source": "a", "target": "b"}, empty_snapshot)
    assert isinstance(result, str)


def test_get_community_against_empty_graph(empty_snapshot) -> None:
    result = execute_tool("get_community", {"community_id": 0}, empty_snapshot)
    assert "not found" in result


def test_graph_stats_against_empty_graph(empty_snapshot) -> None:
    result = execute_tool("graph_stats", {}, empty_snapshot)
    assert "Nodes: 0" in result
    assert "Edges: 0" in result
