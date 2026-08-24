"""query_graph results are cached, version-scoped.

See specs/graph-query-api/spec.md "Version-scoped LRU result cache".
"""

from __future__ import annotations

import asyncio

import pytest
from mcp import types

from graphify_daemon.graph_query_api import tools as tools_module
from graphify_daemon.graph_query_api.tools import build_handlers


def _snapshot(version: int) -> object:
    class _FakeSnapshot:
        pass

    snap = _FakeSnapshot()
    snap.version = version  # type: ignore[attr-defined]
    return snap


def _params(question: str = "Alpha") -> types.CallToolRequestParams:
    return types.CallToolRequestParams(name="query_graph", arguments={"question": question})


def test_identical_repeated_query_is_served_from_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def _fake_execute_tool(name: str, arguments: dict, snapshot: object) -> str:
        nonlocal call_count
        call_count += 1
        return "the answer"

    monkeypatch.setattr(tools_module, "execute_tool", _fake_execute_tool)

    snapshot = _snapshot(version=1)
    _on_list_tools, on_call_tool = build_handlers(lambda: snapshot)

    result1 = asyncio.run(on_call_tool(None, _params()))
    result2 = asyncio.run(on_call_tool(None, _params()))

    assert call_count == 1, "the second identical query should be served from cache"
    assert result1.content[0].text == result2.content[0].text == "the answer"


def test_query_after_a_new_snapshot_publishes_is_recomputed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def _fake_execute_tool(name: str, arguments: dict, snapshot: object) -> str:
        nonlocal call_count
        call_count += 1
        return f"answer-for-v{snapshot.version}"

    monkeypatch.setattr(tools_module, "execute_tool", _fake_execute_tool)

    current_snapshot = _snapshot(version=1)
    _on_list_tools, on_call_tool = build_handlers(lambda: current_snapshot)

    asyncio.run(on_call_tool(None, _params()))
    current_snapshot = _snapshot(version=2)  # a new snapshot published
    result = asyncio.run(on_call_tool(None, _params()))

    assert call_count == 2, "a new snapshot version must not be served from the stale entry"
    assert result.content[0].text == "answer-for-v2"
