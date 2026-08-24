"""build_handlers accepts a pre-constructed QueryCache so the caller can
read its hit_rate() elsewhere (the metrics endpoint), without changing
build_handlers' (on_list_tools, on_call_tool) return shape.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp import types

from graphify_daemon.graph_query_api import tools as tools_module
from graphify_daemon.graph_query_api.query_cache import QueryCache
from graphify_daemon.graph_query_api.tools import build_handlers


class _FakeSnapshot:
    version = 1


def test_injected_query_cache_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_execute_tool(name: str, arguments: dict, snapshot: object) -> str:
        raise AssertionError("must be served from the pre-populated injected cache")

    monkeypatch.setattr(tools_module, "execute_tool", _fake_execute_tool)

    query_cache = QueryCache()
    query_cache.set(
        version=1,
        question="q",
        mode="bfs",
        depth=3,
        token_budget=2000,
        context_filters=None,
        result="cached answer",
    )

    _on_list_tools, on_call_tool = build_handlers(lambda: _FakeSnapshot(), query_cache=query_cache)

    result = asyncio.run(
        on_call_tool(None, types.CallToolRequestParams(name="query_graph", arguments={"question": "q"}))
    )

    assert result.content[0].text == "cached answer"
    assert query_cache.hit_rate() == 1.0


def test_query_cache_is_optional() -> None:
    on_list_tools, on_call_tool = build_handlers(lambda: _FakeSnapshot())
    assert callable(on_list_tools)
    assert callable(on_call_tool)
