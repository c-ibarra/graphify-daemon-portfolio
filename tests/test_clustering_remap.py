"""Community ID stability via remap_communities_to_previous.

See specs/vault-compiler/spec.md "Community ID stability via remap".
"""

from __future__ import annotations

import random

import networkx as nx

from graphify_daemon.vault_compiler.clustering import (
    build_previous_node_community,
    run_clustering_cycle,
)
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_build_previous_node_community_inverts_the_map() -> None:
    community_map = {0: ["a", "b"], 1: ["c"]}
    assert build_previous_node_community(community_map) == {"a": 0, "b": 0, "c": 1}


def _blocked_graph() -> nx.Graph:
    sizes = [60, 60, 60, 60, 60]
    probs = [
        [0.3, 0.01, 0.01, 0.01, 0.01],
        [0.01, 0.3, 0.01, 0.01, 0.01],
        [0.01, 0.01, 0.3, 0.01, 0.01],
        [0.01, 0.01, 0.01, 0.3, 0.01],
        [0.01, 0.01, 0.01, 0.01, 0.3],
    ]
    graph = nx.stochastic_block_model(sizes, probs, seed=3)
    return nx.relabel_nodes(graph, {n: str(n) for n in graph.nodes()})


def _invert(community_map: dict[int, list[str]]) -> dict[str, int]:
    return {node: cid for cid, nodes in community_map.items() for node in nodes}


def test_community_churn_stays_below_5_percent_after_adding_a_synthetic_note() -> None:
    base_graph = _blocked_graph()
    holder = SnapshotHolder()
    holder.publish(base_graph, {})

    first = run_clustering_cycle(holder)
    assert first is not None
    previous_communities = first.community_map

    updated_graph = base_graph.copy()
    existing_nodes = list(base_graph.nodes())
    new_nodes = [f"synthetic-{i}" for i in range(10)]
    updated_graph.add_nodes_from(new_nodes)
    rng = random.Random(7)
    for i in range(12):
        updated_graph.add_edge(new_nodes[i % 10], rng.choice(existing_nodes))

    # A batch publish carries forward whatever community_map is already
    # current -- only run_clustering_cycle updates it.
    holder.publish(updated_graph, previous_communities)

    second = run_clustering_cycle(holder)
    assert second is not None

    old_node_to_cid = _invert(previous_communities)
    new_node_to_cid = _invert(second.community_map)

    changed = sum(1 for node, old_cid in old_node_to_cid.items() if new_node_to_cid.get(node) != old_cid)
    churn = changed / len(old_node_to_cid)
    assert churn < 0.05, f"community churn {churn:.1%} exceeds the 5% budget"
