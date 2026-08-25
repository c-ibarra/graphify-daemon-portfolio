"""Slow-cadence orchestration: after each batch, trigger clustering and
the slow-cadence disk artifacts if the condition has been met.

See specs/vault-compiler/spec.md "Clustering triggered by slow cadence
only" and specs/artifact-lifecycle/spec.md "Artifact cadence table".

This is the actual wiring code review found missing (67af7fe...HEAD):
SlowCadenceTracker, run_clustering_cycle, write_graph_json,
generate_knowledge_md, and ExtractionCache.save all existed as
independently-tested primitives, but nothing in production code composed
them -- only test-level "if tracker.should_trigger(): writer(...)" proved
they *could* compose correctly.
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.artifact_lifecycle.graph_artifacts import (
    write_graph_json,
    write_knowledge_md,
)
from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.clustering import (
    DEFAULT_CLUSTERING_TIMEOUT_SECONDS,
    run_clustering_cycle,
)
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.slow_cadence import SlowCadenceTracker
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def run_slow_cadence_cycle(
    tracker: SlowCadenceTracker,
    holder: SnapshotHolder,
    cache: ExtractionCache,
    *,
    graph_json_path: Path,
    knowledge_md_path: Path,
    graph_cache_path: Path,
    clustering_timeout: float = DEFAULT_CLUSTERING_TIMEOUT_SECONDS,
    metrics: Metrics | None = None,
) -> bool:
    """Call after every batch. Returns whether the slow cadence triggered.

    When triggered: runs clustering (its own failure/timeout fallback
    already keeps the previous community assignment — see
    specs/vault-compiler/spec.md "Clustering failure or timeout fallback",
    so this proceeds either way), writes `graph.json`/`KNOWLEDGE.md` from
    whatever snapshot is current afterward, persists `graph_cache.json`,
    then resets `tracker`.
    """
    if not tracker.should_trigger():
        return False

    run_clustering_cycle(holder, timeout=clustering_timeout, metrics=metrics)

    current = holder.current()
    if current is not None:
        write_graph_json(current, graph_json_path)
        write_knowledge_md(current, knowledge_md_path)
    cache.save(graph_cache_path)

    tracker.reset()
    return True
