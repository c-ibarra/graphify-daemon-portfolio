"""The real exception detail behind a generic tool-failure result is
still logged, so operators retain full diagnosability.

See specs/graph-query-api/spec.md "MCP tool errors never leak internal
exception text".
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from mcp import types

from graphify_daemon.graph_query_api import tools as tools_module
from graphify_daemon.graph_query_api.tools import build_handlers
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_file
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder, build_graph

_SENSITIVE_DETAIL = "internal failure reading /secret/path.md"


@pytest.fixture
def snapshot(tmp_path: Path):
    a = tmp_path / "alpha.md"
    a.write_text("# Alpha\n")
    cache = ExtractionCache()
    cache.set(Path("alpha.md"), extract_file(a, tmp_path))
    holder = SnapshotHolder()
    graph = build_graph(cache)
    return holder.publish(graph, {0: list(graph.nodes())})


def test_real_exception_detail_is_logged(snapshot, monkeypatch: pytest.MonkeyPatch, caplog: object) -> None:
    def _boom(name, arguments, snap):
        raise RuntimeError(_SENSITIVE_DETAIL)

    monkeypatch.setattr(tools_module, "execute_tool", _boom)

    on_call_tool = build_handlers(lambda: snapshot)[1]
    with caplog.at_level(logging.ERROR):  # type: ignore[attr-defined]
        asyncio.run(on_call_tool(None, types.CallToolRequestParams(name="graph_stats", arguments={})))

    assert any(_SENSITIVE_DETAIL in record.message for record in caplog.records)  # type: ignore[attr-defined]
