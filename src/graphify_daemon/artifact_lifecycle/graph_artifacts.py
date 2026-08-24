"""Slow-cadence disk artifacts: graph.json and KNOWLEDGE.md, generated
from the resident snapshot.

See specs/artifact-lifecycle/spec.md "Atomic graph.json writes" and
"KNOWLEDGE.md generated from the resident snapshot".

`generate_knowledge_md` is a lightweight, self-contained generator, not
`graphify.report.generate` — that function needs cohesion_scores,
surprising_connections, detection_result, and token_cost as inputs, none
of which this daemon's pipeline currently computes; faking them to call it
would be a bigger task than what task 10.5/10.6 asks for.
"""

from __future__ import annotations

from pathlib import Path

from graphify.analyze import god_nodes as _god_nodes
from graphify.export import to_json

from graphify_daemon.vault_compiler.snapshot import GraphSnapshot


def write_graph_json(snapshot: GraphSnapshot, path: Path) -> None:
    """Write `snapshot.graph` to `path` atomically via `graphify.export.to_json`.

    `to_json` serializes every graph-level attribute (`networkx.json_graph.
    node_link_data`), which would include the pre-warmed trigram index
    cached on `graph.graph["_trigram_index"]` by `get_trigram_index` (task
    group 5's `SnapshotHolder.publish`) — a non-JSON-serializable `array`.
    Strips it from an independent copy first, never mutating the shared
    snapshot's graph (which stays immutable for concurrent readers).
    """
    graph = snapshot.graph
    if "_trigram_index" in graph.graph:
        graph = graph.copy()
        del graph.graph["_trigram_index"]
    to_json(graph, snapshot.community_map, str(path), force=True)


def generate_knowledge_md(snapshot: GraphSnapshot) -> str:
    """Render a lightweight Markdown summary of `snapshot`: stats, god
    nodes, and communities. Reads only the in-RAM snapshot, never disk.
    """
    graph = snapshot.graph
    lines = [
        "# Knowledge Graph Summary",
        "",
        f"- Snapshot version: {snapshot.version}",
        f"- Nodes: {graph.number_of_nodes()}",
        f"- Edges: {graph.number_of_edges()}",
        f"- Communities: {len(snapshot.community_map)}",
        "",
        "## God nodes",
        "",
    ]
    for i, node in enumerate(_god_nodes(graph, top_n=10), 1):
        lines.append(f"{i}. {node['label']} ({node['degree']} edges)")

    lines += ["", "## Communities", ""]
    for cid, nodes in sorted(snapshot.community_map.items()):
        lines.append(f"- Community {cid}: {len(nodes)} nodes")

    return "\n".join(lines) + "\n"
