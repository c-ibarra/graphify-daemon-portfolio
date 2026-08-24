"""Clustering timeout leaves the previous community assignment intact.

See specs/vault-compiler/spec.md "Clustering failure or timeout fallback".
"""

from __future__ import annotations

import logging

import networkx as nx
import pytest

from graphify_daemon.vault_compiler.clustering import run_clustering_cycle
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_timeout_preserves_previous_communities_and_logs_the_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = nx.erdos_renyi_graph(200, 0.02, seed=1)
    graph = nx.relabel_nodes(graph, {i: str(i) for i in graph.nodes()})

    holder = SnapshotHolder()
    sentinel_map = {0: ["sentinel"]}
    holder.publish(graph, sentinel_map)

    with caplog.at_level(logging.WARNING):
        result = run_clustering_cycle(holder, timeout=0.001)

    assert result is None
    assert holder.current().community_map == sentinel_map
    assert any("timeout" in record.message.lower() for record in caplog.records), (
        "expected a log record naming the timeout"
    )
