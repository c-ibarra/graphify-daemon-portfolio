"""Isolated-subprocess community clustering with stable-ID remap.

See specs/vault-compiler/spec.md "Clustering runs in an isolated subprocess",
"Clustering triggered by slow cadence only", "Community ID stability via remap",
"Reads continue serving previous communities during clustering", and
"Clustering failure or timeout fallback". See design.md Decision 4.
"""

from __future__ import annotations

import logging
import multiprocessing
import queue
import time
from typing import cast

import networkx as nx
from graphify.cluster import cluster, remap_communities_to_previous

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.snapshot import GraphSnapshot, SnapshotHolder

logger = logging.getLogger(__name__)

DEFAULT_CLUSTERING_TIMEOUT_SECONDS = 30.0


def _cluster_worker(graph: nx.Graph, result_queue: multiprocessing.Queue[tuple[str, object]]) -> None:
    try:
        result_queue.put(("ok", cluster(graph)))
    except Exception as exc:  # noqa: BLE001 - reported to the parent, not raised here
        result_queue.put(("error", str(exc)))


def run_clustering_subprocess(
    graph: nx.Graph,
    *,
    timeout: float = DEFAULT_CLUSTERING_TIMEOUT_SECONDS,
) -> dict[int, list[str]] | None:
    """Run `graphify.cluster.cluster` in an isolated `multiprocessing` (spawn) subprocess.

    Sends a pickled copy of `graph` to the child — never a second copy
    served to any client (design.md Decision 4). Measures and logs the
    pickling/handoff cost. Returns None (logging the failure) on subprocess
    failure or on exceeding `timeout`, rather than raising — callers treat
    that uniformly with "clustering didn't produce a usable result".

    Drains `result_queue` *before* joining the process: a community-map
    result larger than the OS pipe buffer (~64KB — a graph as small as
    ~8,000 nodes already produces this) leaves the child blocked writing
    it to a full pipe. Calling `process.join()` first, before anything
    reads that pipe, is the classic `multiprocessing.Queue` deadlock — see
    specs/vault-compiler/spec.md "Clustering subprocess result retrieval
    does not deadlock on large payloads".
    """
    ctx = multiprocessing.get_context("spawn")
    result_queue: multiprocessing.Queue[tuple[str, object]] = ctx.Queue()

    handoff_start = time.monotonic()
    process = ctx.Process(target=_cluster_worker, args=(graph, result_queue))
    process.start()
    handoff_duration = time.monotonic() - handoff_start
    logger.info("Clustering subprocess handoff (pickle + spawn) took %.3fs", handoff_duration)

    try:
        status, payload = result_queue.get(timeout=timeout)
    except queue.Empty:
        logger.warning("Clustering subprocess exceeded timeout of %.1fs; terminating", timeout)
        process.terminate()
        process.join()
        return None

    # The result is drained, so the child's queue-feeder thread can finish
    # flushing and the process can exit -- it should do so almost
    # immediately now; terminate only as a fallback if it somehow doesn't.
    process.join(timeout=5.0)
    if process.is_alive():
        logger.warning("Clustering subprocess did not exit after producing a result; terminating")
        process.terminate()
        process.join()

    if status != "ok":
        logger.warning("Clustering subprocess failed: %s", payload)
        return None

    return cast("dict[int, list[str]]", payload)


def build_previous_node_community(community_map: dict[int, list[str]]) -> dict[str, int]:
    """Invert a community map into node -> community_id, for `remap_communities_to_previous`."""
    return {node: cid for cid, nodes in community_map.items() for node in nodes}


def run_clustering_cycle(
    holder: SnapshotHolder,
    *,
    timeout: float = DEFAULT_CLUSTERING_TIMEOUT_SECONDS,
    metrics: Metrics | None = None,
) -> GraphSnapshot | None:
    """Cluster the currently-published snapshot's graph and republish with updated communities.

    Captures `holder.current()` once and clusters exactly that graph — the
    republished snapshot uses that same graph object, never whatever is
    current when clustering finishes (confirmed design choice for task
    group 6: simplest option, self-heals on the next batch-driven publish
    if one landed mid-clustering). Reads keep serving the previous community
    assignment via `holder.current()` for the whole run, since nothing here
    touches the holder until a result is ready. On failure or timeout, logs
    and returns None without publishing — the previous assignment stays
    intact.
    """
    current = holder.current()
    if current is None:
        return None

    raw_communities = run_clustering_subprocess(current.graph, timeout=timeout)
    if raw_communities is None:
        return None

    previous_node_community = build_previous_node_community(current.community_map)
    remapped = remap_communities_to_previous(raw_communities, previous_node_community)
    new_snapshot = holder.publish(current.graph, remapped)
    if metrics is not None:
        metrics.record_event_time("clustering_success")
    return new_snapshot
