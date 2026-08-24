"""Reads keep serving the previous community assignment while clustering runs.

See specs/vault-compiler/spec.md "Reads continue serving previous
communities during clustering".
"""

from __future__ import annotations

import threading
import time

import networkx as nx

from graphify_daemon.vault_compiler.clustering import run_clustering_cycle
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def _random_graph(n: int) -> nx.Graph:
    graph = nx.erdos_renyi_graph(n, 0.01, seed=42)
    return nx.relabel_nodes(graph, {i: str(i) for i in graph.nodes()})


def test_get_community_during_active_clustering_returns_previous_assignment() -> None:
    graph = _random_graph(600)
    holder = SnapshotHolder()
    sentinel_map = {0: ["sentinel"]}
    holder.publish(graph, sentinel_map)

    result_holder: dict[str, object] = {}

    def do_cycle() -> None:
        result_holder["result"] = run_clustering_cycle(holder, timeout=30.0)

    clustering_thread = threading.Thread(target=do_cycle)
    clustering_thread.start()
    time.sleep(0.05)  # let the subprocess actually start

    assert clustering_thread.is_alive(), "test assumes clustering is still running here"
    assert holder.current().community_map == sentinel_map

    clustering_thread.join(timeout=30)

    assert result_holder["result"] is not None
    assert holder.current().community_map != sentinel_map
