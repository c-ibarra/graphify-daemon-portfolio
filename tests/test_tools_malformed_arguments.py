"""Malformed or out-of-range MCP requests fail cleanly (isError=True),
never raise. See specs/graph-query-api/spec.md "Malformed and
out-of-range MCP requests fail cleanly".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp import types

from graphify_daemon.graph_query_api.tools import build_handlers
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_file
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder, build_graph


@pytest.fixture
def snapshot(tmp_path: Path):
    a = tmp_path / "alpha.md"
    a.write_text("# Alpha\n\nLinks to [Beta](./beta.md) and mentions `Gamma`.\n")
    cache = ExtractionCache()
    cache.set(Path("alpha.md"), extract_file(a, tmp_path))
    holder = SnapshotHolder()
    graph = build_graph(cache)
    return holder.publish(graph, {0: list(graph.nodes())})


def _call(get_snapshot, name: str, arguments: dict) -> types.CallToolResult:
    _on_list_tools, on_call_tool = build_handlers(get_snapshot)
    return asyncio.run(on_call_tool(None, types.CallToolRequestParams(name=name, arguments=arguments)))


def test_unknown_tool_name(snapshot) -> None:
    result = _call(lambda: snapshot, "not_a_real_tool", {})
    assert result.is_error


def test_non_numeric_community_id(snapshot) -> None:
    result = _call(lambda: snapshot, "get_community", {"community_id": "not-a-number"})
    assert result.is_error


def test_negative_depth(snapshot) -> None:
    result = _call(lambda: snapshot, "query_graph", {"question": "q", "depth": -1})
    assert result.is_error


def test_negative_token_budget(snapshot) -> None:
    result = _call(lambda: snapshot, "query_graph", {"question": "q", "token_budget": -1})
    assert result.is_error


def test_context_filter_too_large(snapshot) -> None:
    result = _call(
        lambda: snapshot, "query_graph", {"question": "q", "context_filter": [str(i) for i in range(10_000)]}
    )
    assert result.is_error


def test_missing_required_argument(snapshot) -> None:
    result = _call(lambda: snapshot, "query_graph", {})  # "question" is required
    assert result.is_error


def test_snapshot_not_ready(snapshot) -> None:
    result = _call(lambda: None, "get_community", {"community_id": 0})
    assert result.is_error


def test_control_valid_get_community_still_works(snapshot) -> None:
    result = _call(lambda: snapshot, "get_community", {"community_id": 0})
    assert not result.is_error
    assert "Community 0" in result.content[0].text
