"""Off-event-loop query execution: a slow query never delays a concurrent fast one.

See specs/graph-query-api/spec.md "Off-event-loop query execution".
"""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp import types

from graphify_daemon.graph_query_api import tools as tools_module
from graphify_daemon.graph_query_api.tools import build_handlers


class _FakeSnapshot:
    version = 1


# Real, registered tool names with no required arguments -- since
# _dispatch (task group 3) now validates the tool name and its
# arguments before ever reaching execute_tool, a fake name like "slow"
# would be rejected as unknown before the fake below ever ran.
_SLOW_TOOL = "graph_stats"
_FAST_TOOL = "god_nodes"


def test_fast_query_completes_before_a_concurrent_slow_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_order: list[str] = []

    def _fake_execute_tool(name: str, arguments: dict, snapshot: object) -> str:
        if name == _SLOW_TOOL:
            time.sleep(0.3)
        completion_order.append(name)
        return f"{name}-result"

    monkeypatch.setattr(tools_module, "execute_tool", _fake_execute_tool)

    _on_list_tools, on_call_tool = build_handlers(lambda: _FakeSnapshot())

    async def scenario() -> float:
        slow_task = asyncio.create_task(on_call_tool(None, types.CallToolRequestParams(name=_SLOW_TOOL, arguments={})))
        await asyncio.sleep(0.02)  # let the slow task actually start its thread

        start = time.monotonic()
        await on_call_tool(None, types.CallToolRequestParams(name=_FAST_TOOL, arguments={}))
        fast_duration = time.monotonic() - start

        await slow_task
        return fast_duration

    fast_duration = asyncio.run(scenario())

    assert fast_duration < 0.15, "fast query was delayed by the concurrently-running slow one"
    assert completion_order[0] == _FAST_TOOL


_ALL_TOOL_ARGUMENTS = {
    "query_graph": {"question": "q"},
    "get_node": {"label": "x"},
    "get_neighbors": {"label": "x"},
    "get_community": {"community_id": 0},
    "god_nodes": {},
    "graph_stats": {},
    "shortest_path": {"source": "a", "target": "b"},
}


def test_burst_across_all_seven_tools_slow_one_does_not_delay_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slow_name = "query_graph"
    completion_order: list[str] = []

    def _fake_execute_tool(name: str, arguments: dict, snapshot: object) -> str:
        if name == slow_name:
            time.sleep(0.3)
        completion_order.append(name)
        return f"{name}-result"

    monkeypatch.setattr(tools_module, "execute_tool", _fake_execute_tool)

    _on_list_tools, on_call_tool = build_handlers(lambda: _FakeSnapshot())

    async def scenario() -> None:
        await asyncio.gather(
            *(
                on_call_tool(None, types.CallToolRequestParams(name=name, arguments=args))
                for name, args in _ALL_TOOL_ARGUMENTS.items()
            )
        )

    asyncio.run(scenario())

    assert completion_order[-1] == slow_name
    assert set(completion_order[:-1]) == set(_ALL_TOOL_ARGUMENTS) - {slow_name}
