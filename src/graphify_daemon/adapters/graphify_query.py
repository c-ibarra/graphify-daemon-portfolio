"""Sole module authorized to import `graphify.serve` private symbols.

`graphify.serve` is not part of graphify's public API (see
`graphify/__init__.py`'s lazy-export `__getattr__`), but this daemon's read
plane depends on 5 of its private symbols. Every other module in this
codebase must go through this adapter instead of importing `graphify.serve`
directly.
"""

from __future__ import annotations

from typing import Any, cast

import networkx as nx
from graphify.serve import (
    _communities_from_graph,
    _find_node,
    _get_trigram_index,
    _query_graph_text,
    _shortest_path_text,
)


def query_graph_text(
    G: nx.Graph,
    question: str,
    *,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
    context_filters: list[str] | None = None,
) -> str:
    return cast(
        str,
        _query_graph_text(
            G,
            question,
            mode=mode,
            depth=depth,
            token_budget=token_budget,
            context_filters=context_filters,
        ),
    )


def get_trigram_index(G: nx.Graph) -> dict[str, Any]:
    return cast(dict[str, Any], _get_trigram_index(G))


def communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    return cast(dict[int, list[str]], _communities_from_graph(G))


def shortest_path_text(G: nx.Graph, arguments: dict[str, Any]) -> str:
    return cast(str, _shortest_path_text(G, arguments))


def find_node(G: nx.Graph, label: str) -> list[str]:
    return cast(list[str], _find_node(G, label))
