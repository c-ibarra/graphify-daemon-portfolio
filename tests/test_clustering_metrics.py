"""run_clustering_cycle records a "clustering_success" event on success."""

from __future__ import annotations

import networkx as nx

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.clustering import run_clustering_cycle
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def _small_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("n1", label="N1")
    return graph


def test_successful_clustering_records_the_event(monkeypatch) -> None:
    holder = SnapshotHolder()
    holder.publish(_small_graph(), {})
    metrics = Metrics()

    assert metrics.seconds_since_event("clustering_success") is None
    run_clustering_cycle(holder, metrics=metrics)
    assert metrics.seconds_since_event("clustering_success") is not None


def test_metrics_is_optional() -> None:
    holder = SnapshotHolder()
    holder.publish(_small_graph(), {})
    run_clustering_cycle(holder)  # no metrics kwarg -- must not raise
