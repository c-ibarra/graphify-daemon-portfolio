"""Structural diff between the legacy watcher's graph.json and this
daemon's own, for the migration parallel-run window (task group 12).

See design.md's Migration Plan: "Run both pipelines in parallel for 3
days; diff node/edge sets daily; the only expected difference is
community IDs."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graphify.build import build_from_json


def compare_graph_jsons(legacy_path: Path, new_path: Path) -> dict[str, Any]:
    """Diff node and edge sets between two graph.json files.

    Reports which node IDs and (source, target) edge pairs exist in one
    file but not the other. Does not compare node/edge attributes (e.g.
    community assignment) — the migration plan expects those to differ;
    interpreting whether an observed diff is "just community IDs" is task
    12.5's job, done against real data over the 3-day run, not this
    comparator's.
    """
    legacy_graph = build_from_json(json.loads(legacy_path.read_text()))
    new_graph = build_from_json(json.loads(new_path.read_text()))

    legacy_nodes = set(legacy_graph.nodes())
    new_nodes = set(new_graph.nodes())
    legacy_edges = set(legacy_graph.edges())
    new_edges = set(new_graph.edges())

    return {
        "nodes_only_in_legacy": legacy_nodes - new_nodes,
        "nodes_only_in_new": new_nodes - legacy_nodes,
        "edges_only_in_legacy": legacy_edges - new_edges,
        "edges_only_in_new": new_edges - legacy_edges,
    }
