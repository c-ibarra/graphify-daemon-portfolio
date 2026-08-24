"""Deterministic synthetic graph generator for reproducible benchmarks.

Not derived from any real vault -- fixed-seed, parametrizable in size.
The default size (~21,000 nodes) matches the previously-measured
real-vault baseline cited in the main README, so new benchmark figures
measured against this generator are comparable to it, not just internally
reproducible. See specs/performance-benchmarking/spec.md "Deterministic
synthetic graph generator".
"""

from __future__ import annotations

import random
from typing import Any

DEFAULT_NODE_COUNT = 21_000
DEFAULT_SEED = 42
DEFAULT_EDGES_PER_NODE = 3
# ~15 nodes/community matches the real-vault baseline's measured density
# (21,122 nodes -> 1,429 communities, see design.md/README.md).
DEFAULT_CLUSTER_SIZE = 15
DEFAULT_CROSS_CLUSTER_PROBABILITY = 0.15

_FILE_TYPES = ("code", "document", "concept")
_RELATIONS = ("calls", "contains", "references", "imports", "defines")
_CONFIDENCES = ("EXTRACTED", "INFERRED", "AMBIGUOUS")
_NODES_PER_FILE = 10


def generate_synthetic_extraction(
    *,
    node_count: int = DEFAULT_NODE_COUNT,
    seed: int = DEFAULT_SEED,
    edges_per_node: int = DEFAULT_EDGES_PER_NODE,
    cluster_size: int = DEFAULT_CLUSTER_SIZE,
    cross_cluster_probability: float = DEFAULT_CROSS_CLUSTER_PROBABILITY,
) -> dict[str, list[dict[str, Any]]]:
    """Deterministically generate a `graphify.build.build_from_json`-compatible
    extraction dict (`{"nodes": [...], "edges": [...]}`), shaped to
    resemble real vault-extracted nodes/edges closely enough for
    representative query-latency and clustering benchmarks.

    Nodes are grouped into fixed-size clusters of `cluster_size`; each
    edge stays within its source node's cluster with probability
    `1 - cross_cluster_probability`, and otherwise jumps to a uniformly
    random cluster. This gives the graph genuine community structure --
    a purely uniform-random graph (every edge target chosen from the
    full node set) has none, which makes community-detection algorithms
    pathologically slow (observed: `run_clustering_subprocess` never
    finished, even after a 300s timeout, against an earlier
    uniform-random version of this generator at 21k nodes).

    The same `(node_count, seed, edges_per_node, cluster_size,
    cross_cluster_probability)` always produces an identical graph -- no
    wall-clock or OS randomness involved.
    """
    rng = random.Random(seed)
    cluster_count = max(1, -(-node_count // cluster_size))  # ceil division

    nodes: list[dict[str, Any]] = []
    for i in range(node_count):
        file_index = i // _NODES_PER_FILE
        nodes.append(
            {
                "id": f"node_{i}",
                "label": f"Node {i}",
                "file_type": rng.choice(_FILE_TYPES),
                "source_file": f"synthetic/file_{file_index}.md",
                "source_location": f"L{i % _NODES_PER_FILE + 1}",
            }
        )

    edges: list[dict[str, Any]] = []
    for i in range(node_count):
        home_cluster = i // cluster_size
        for _ in range(edges_per_node):
            if cluster_count > 1 and rng.random() < cross_cluster_probability:
                target_cluster = rng.randrange(cluster_count)
            else:
                target_cluster = home_cluster
            cluster_start = target_cluster * cluster_size
            cluster_end = min(cluster_start + cluster_size, node_count)
            if cluster_end <= cluster_start:
                continue
            target = rng.randrange(cluster_start, cluster_end)
            if target == i:
                continue
            edges.append(
                {
                    "source": f"node_{i}",
                    "target": f"node_{target}",
                    "relation": rng.choice(_RELATIONS),
                    "confidence": rng.choice(_CONFIDENCES),
                    "source_file": nodes[i]["source_file"],
                    "source_location": nodes[i]["source_location"],
                    "weight": 1.0,
                }
            )

    return {"nodes": nodes, "edges": edges}
