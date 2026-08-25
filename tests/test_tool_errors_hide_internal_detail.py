"""An unexpected tool failure returns a generic, tool-named message to
the MCP client -- never the raw exception text.

See specs/graph-query-api/spec.md "MCP tool errors never leak internal
exception text".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp import types

from graphify_daemon.graph_query_api import tools as tools_module
from graphify_daemon.graph_query_api.tools import build_handlers
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_file
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder, build_graph

_SENSITIVE_DETAIL = "/home/example-user/vault/private-note.md"


@pytest.fixture
def snapshot(tmp_path: Path):
    a = tmp_path / "alpha.md"
    a.write_text("# Alpha\n")
    cache = ExtractionCache()
    cache.set(Path("alpha.md"), extract_file(a, tmp_path))
    holder = SnapshotHolder()
    graph = build_graph(cache)
    return holder.publish(graph, {0: list(graph.nodes())})


def test_unexpected_tool_failure_hides_internal_detail(snapshot, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(name, arguments, snap):
        raise RuntimeError(f"internal failure reading {_SENSITIVE_DETAIL}")

    monkeypatch.setattr(tools_module, "execute_tool", _boom)

    on_call_tool = build_handlers(lambda: snapshot)[1]
    result = asyncio.run(on_call_tool(None, types.CallToolRequestParams(name="graph_stats", arguments={})))

    assert result.is_error
    text = result.content[0].text
    assert _SENSITIVE_DETAIL not in text
    assert "graph_stats" in text
