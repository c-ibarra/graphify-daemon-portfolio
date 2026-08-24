"""Immutable, versioned graph snapshots and their atomic publish.

See specs/vault-compiler/spec.md "Immutable snapshot structure",
"Trigram index pre-warmed before publish", "Atomic snapshot publish",
and "Stable reader reference per request".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx
from graphify.build import build_from_json

from graphify_daemon.adapters.graphify_query import get_trigram_index
from graphify_daemon.vault_compiler.extraction import ExtractionCache


@dataclass(frozen=True)
class GraphSnapshot:
    """A NetworkX graph, pre-warmed trigram index, and community map, published
    together as one atomic reference swap. See CONTEXT.md: Snapshot."""

    graph: nx.Graph
    trigram_index: dict[str, Any]
    community_map: dict[int, list[str]]
    version: int


def build_graph(cache: ExtractionCache) -> nx.Graph:
    """Merge every cached extraction result into one directed graph via `build_from_json`.

    Rebuilds from the full corpus in `cache`, not just the files changed in
    the triggering batch — the cache is what makes that affordable without
    re-reading the vault. Directed, matching the adapter's shortest-path
    semantics (caller->callee direction).
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for result in cache.entries().values():
        nodes.extend(result.get("nodes", []))
        edges.extend(result.get("edges", []))
    return build_from_json({"nodes": nodes, "edges": edges}, directed=True)


class SnapshotHolder:
    """Owns the single published `GraphSnapshot` reference and its version counter.

    `publish` pre-warms the trigram index before the swap (never lazily on
    first read) — see specs/vault-compiler/spec.md. The swap itself is a
    single reference reassignment; `current()` never takes a lock.
    """

    def __init__(self) -> None:
        self._current: GraphSnapshot | None = None
        self._next_version = 1

    def publish(self, graph: nx.Graph, community_map: dict[int, list[str]]) -> GraphSnapshot:
        trigram_index = get_trigram_index(graph)
        snapshot = GraphSnapshot(
            graph=graph,
            trigram_index=trigram_index,
            community_map=community_map,
            version=self._next_version,
        )
        self._next_version += 1
        self._current = snapshot
        return snapshot

    def current(self) -> GraphSnapshot | None:
        return self._current
