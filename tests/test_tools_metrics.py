"""build_handlers records query latency to an optional Metrics registry."""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp import types

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.graph_query_api import tools as tools_module
from graphify_daemon.graph_query_api.tools import build_handlers


class _FakeSnapshot:
    version = 1


def test_query_latency_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_execute_tool(name: str, arguments: dict, snapshot: object) -> str:
        time.sleep(0.02)
        return "result"

    monkeypatch.setattr(tools_module, "execute_tool", _fake_execute_tool)

    metrics = Metrics()
    _on_list_tools, on_call_tool = build_handlers(lambda: _FakeSnapshot(), metrics=metrics)

    asyncio.run(on_call_tool(None, types.CallToolRequestParams(name="graph_stats", arguments={})))

    percentiles = metrics.latency_percentiles("query")
    assert percentiles["p50"] >= 0.015


def test_metrics_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_module, "execute_tool", lambda *a, **k: "result")
    _on_list_tools, on_call_tool = build_handlers(lambda: _FakeSnapshot())  # no metrics kwarg
    asyncio.run(on_call_tool(None, types.CallToolRequestParams(name="graph_stats", arguments={})))
