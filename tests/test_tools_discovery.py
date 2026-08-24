"""All seven tools are discoverable with schemas matching graphify's own.

See specs/graph-query-api/spec.md "Minimum read tool surface".
"""

from __future__ import annotations

import asyncio

import networkx as nx

from graphify_daemon.graph_query_api.tools import build_handlers
from graphify_daemon.vault_compiler.snapshot import GraphSnapshot

EXPECTED_TOOLS = {
    "query_graph": {"question"},
    "get_node": {"label"},
    "get_neighbors": {"label"},
    "get_community": {"community_id"},
    "god_nodes": set(),
    "graph_stats": set(),
    "shortest_path": {"source", "target"},
}


def _empty_snapshot() -> GraphSnapshot:
    return GraphSnapshot(graph=nx.DiGraph(), trigram_index={}, community_map={}, version=1)


def test_all_seven_tools_are_discoverable_with_expected_required_fields() -> None:
    on_list_tools, _on_call_tool = build_handlers(_empty_snapshot)

    result = asyncio.run(on_list_tools(None, None))

    tools_by_name = {tool.name: tool for tool in result.tools}
    assert set(tools_by_name) == set(EXPECTED_TOOLS)
    for name, required in EXPECTED_TOOLS.items():
        assert set(tools_by_name[name].input_schema.get("required", [])) == required
