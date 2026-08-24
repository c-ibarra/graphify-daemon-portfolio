"""compare_graph_jsons: structural diff between two graph.json files.

See design.md's Migration Plan (task group 12).
"""

from __future__ import annotations

import json
from pathlib import Path

from graphify_daemon.migration.comparator import compare_graph_jsons


def _write_graph_json(path: Path, *, nodes: list[str], edges: list[tuple[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "directed": True,
                "multigraph": False,
                "graph": {},
                "nodes": [{"id": n} for n in nodes],
                "links": [{"source": s, "target": t} for s, t in edges],
            }
        )
    )


def test_reports_exactly_the_known_node_and_edge_difference(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy_graph.json"
    new_path = tmp_path / "new_graph.json"

    _write_graph_json(legacy_path, nodes=["a", "b", "c"], edges=[("a", "b")])
    _write_graph_json(new_path, nodes=["a", "b", "d"], edges=[("a", "b"), ("b", "d")])

    diff = compare_graph_jsons(legacy_path, new_path)

    assert diff["nodes_only_in_legacy"] == {"c"}
    assert diff["nodes_only_in_new"] == {"d"}
    assert diff["edges_only_in_legacy"] == set()
    assert diff["edges_only_in_new"] == {("b", "d")}


def test_identical_graphs_report_no_differences(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy_graph.json"
    new_path = tmp_path / "new_graph.json"

    _write_graph_json(legacy_path, nodes=["a", "b"], edges=[("a", "b")])
    _write_graph_json(new_path, nodes=["a", "b"], edges=[("a", "b")])

    diff = compare_graph_jsons(legacy_path, new_path)

    assert diff == {
        "nodes_only_in_legacy": set(),
        "nodes_only_in_new": set(),
        "edges_only_in_legacy": set(),
        "edges_only_in_new": set(),
    }
