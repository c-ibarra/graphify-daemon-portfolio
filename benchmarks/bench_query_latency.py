"""Reproducible query-latency benchmark: run each of the 7 read tools
repeatedly against a deterministic synthetic graph, measured with the
project's own `Metrics` class (`record_latency`/`latency_percentiles`).

Run: uv run python benchmarks/bench_query_latency.py [--size N] [--seed N] [--iterations N]

See specs/performance-benchmarking/spec.md "Reproducible query-latency
benchmark".
"""

from __future__ import annotations

import argparse
import time

from graphify.build import build_from_json
from graphify.cluster import cluster
from synthetic_graph import DEFAULT_NODE_COUNT, DEFAULT_SEED, generate_synthetic_extraction

from graphify_daemon.adapters.graphify_query import get_trigram_index
from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.graph_query_api.tools import execute_tool
from graphify_daemon.vault_compiler.snapshot import GraphSnapshot

DEFAULT_ITERATIONS = 500

_TOOL_ARGUMENTS = {
    "query_graph": {"question": "Node 1"},
    "get_node": {"label": "Node 1"},
    "get_neighbors": {"label": "Node 1"},
    "get_community": {"community_id": 0},
    "god_nodes": {},
    "graph_stats": {},
    "shortest_path": {"source": "Node 1", "target": "Node 2"},
}


def build_snapshot(node_count: int, seed: int) -> GraphSnapshot:
    extraction = generate_synthetic_extraction(node_count=node_count, seed=seed)
    graph = build_from_json(extraction, directed=True)
    community_map = cluster(graph)
    trigram_index = get_trigram_index(graph)
    return GraphSnapshot(graph=graph, trigram_index=trigram_index, community_map=community_map, version=1)


def run_benchmark(snapshot: GraphSnapshot, iterations: int) -> Metrics:
    metrics = Metrics(latency_window=iterations)
    for tool_name, arguments in _TOOL_ARGUMENTS.items():
        for _ in range(iterations):
            start = time.monotonic()
            execute_tool(tool_name, arguments, snapshot)
            metrics.record_latency(tool_name, time.monotonic() - start)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=DEFAULT_NODE_COUNT, help="Synthetic graph node count")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    args = parser.parse_args()

    print(f"Building synthetic graph: {args.size} nodes, seed={args.seed}...")
    snapshot = build_snapshot(args.size, args.seed)
    print(
        f"Graph ready: {snapshot.graph.number_of_nodes()} nodes, "
        f"{snapshot.graph.number_of_edges()} edges, {len(snapshot.community_map)} communities."
    )

    print(f"Running {args.iterations} iterations per tool...")
    metrics = run_benchmark(snapshot, args.iterations)

    print(f"\n{'Tool':<15} {'p50 (ms)':>10} {'p95 (ms)':>10} {'p99 (ms)':>10}")
    for tool_name in _TOOL_ARGUMENTS:
        pct = metrics.latency_percentiles(tool_name)
        print(f"{tool_name:<15} {pct['p50'] * 1000:>10.2f} {pct['p95'] * 1000:>10.2f} {pct['p99'] * 1000:>10.2f}")


if __name__ == "__main__":
    main()
