"""collect_metrics: the full metrics endpoint payload.

See specs/artifact-lifecycle/spec.md "Operational metrics".
"""

from __future__ import annotations

import networkx as nx

from graphify_daemon.artifact_lifecycle.metrics import Metrics, collect_metrics
from graphify_daemon.graph_query_api.query_cache import QueryCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_collect_metrics_reports_all_required_fields() -> None:
    holder = SnapshotHolder()
    graph = nx.DiGraph()
    graph.add_node("n1")
    holder.publish(graph, {})

    metrics = Metrics()
    metrics.set_gauge("queue_depth", 3)
    metrics.increment("extraction_errors", 2)
    metrics.record_event_time("clustering_success")
    metrics.record_latency("query", 0.01)
    metrics.record_latency("query", 0.02)

    query_cache = QueryCache()
    query_cache.set(
        version=1,
        question="q",
        mode="bfs",
        depth=3,
        token_budget=2000,
        context_filters=None,
        result="r",
    )
    query_cache.get(version=1, question="q", mode="bfs", depth=3, token_budget=2000, context_filters=None)

    payload = collect_metrics(metrics, holder, query_cache)

    assert payload["queue_depth"] == 3
    assert payload["snapshot_version"] == 1
    assert payload["lru_cache_hit_rate"] == query_cache.hit_rate()
    assert set(payload["query_latency_seconds"]) == {"p50", "p95", "p99"}
    assert payload["seconds_since_last_clustering"] is not None
    assert payload["rss_bytes"] > 0
    assert payload["extraction_error_count"] == 2
    assert "git_sha" in payload
    assert "git_dirty" in payload


def test_collect_metrics_handles_no_snapshot_yet() -> None:
    holder = SnapshotHolder()
    metrics = Metrics()
    query_cache = QueryCache()

    payload = collect_metrics(metrics, holder, query_cache)

    assert payload["snapshot_version"] is None
    assert payload["seconds_since_last_clustering"] is None
