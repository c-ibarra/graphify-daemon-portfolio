"""Reproducible clustering benchmark: run community clustering against a
deterministic synthetic graph 5 times, report min/mean/max duration.

Run: uv run python benchmarks/bench_clustering.py [--size N] [--seed N]

See specs/performance-benchmarking/spec.md "Reproducible clustering
benchmark".
"""

from __future__ import annotations

import argparse
import statistics
import time

from graphify.build import build_from_json
from synthetic_graph import DEFAULT_NODE_COUNT, DEFAULT_SEED, generate_synthetic_extraction

from graphify_daemon.vault_compiler.clustering import run_clustering_subprocess

RUNS = 5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=DEFAULT_NODE_COUNT, help="Synthetic graph node count")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    print(f"Building synthetic graph: {args.size} nodes, seed={args.seed}...")
    extraction = generate_synthetic_extraction(node_count=args.size, seed=args.seed)
    graph = build_from_json(extraction, directed=True)
    print(f"Graph ready: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges.")

    durations: list[float] = []
    for run in range(1, RUNS + 1):
        start = time.monotonic()
        result = run_clustering_subprocess(graph)
        duration = time.monotonic() - start
        durations.append(duration)
        community_count = len(result) if result is not None else 0
        print(f"  run {run}/{RUNS}: {duration * 1000:.1f} ms ({community_count} communities)")

    print(
        f"\nmin={min(durations) * 1000:.1f} ms  "
        f"mean={statistics.mean(durations) * 1000:.1f} ms  "
        f"max={max(durations) * 1000:.1f} ms"
    )


if __name__ == "__main__":
    main()
