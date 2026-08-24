"""Cold-start reconciliation: mtime-diffed re-extraction against the persisted cache.

See specs/artifact-lifecycle/spec.md "Cold-start reconciliation by mtime diff".
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from graphify_daemon.vault_compiler.exclusions import OBSERVED_SUFFIXES, is_excluded
from graphify_daemon.vault_compiler.extraction import (
    ExtractionCache,
    extract_file_with_failure_isolation,
)
from graphify_daemon.vault_compiler.snapshot import GraphSnapshot, SnapshotHolder, build_graph

if TYPE_CHECKING:
    from graphify_daemon.artifact_lifecycle.metrics import Metrics

logger = logging.getLogger(__name__)


def cold_start(
    vault_root: Path,
    cache: ExtractionCache,
    holder: SnapshotHolder,
    *,
    nested_repo_names: frozenset[str] = frozenset(),
    metrics: Metrics | None = None,
) -> GraphSnapshot:
    """Reconcile `cache` against the vault's current state, then build and publish the initial snapshot.

    Walks `vault_root` (respecting the vault exclusion/observed-scope
    rules from `vault_compiler.exclusions`), re-extracting only files
    whose mtime differs from what `cache` has recorded — or that aren't
    cached at all. Files no longer present on disk are dropped from
    `cache`. Pre-warms the trigram index via `holder.publish`, per
    "declaring itself ready" in the spec.

    A file whose extraction fails (raises, or returns an `"error"` key —
    same two failure modes `extract_batch` isolates) is logged and skipped,
    same as a steady-state batch failure, rather than silently dropped.
    """
    observed: set[Path] = set()
    for path in vault_root.rglob("*"):
        if path.is_dir() or path.suffix not in OBSERVED_SUFFIXES:
            continue
        if is_excluded(path, vault_root, nested_repo_names=nested_repo_names):
            continue
        relative = path.relative_to(vault_root)
        observed.add(relative)
        current_mtime = path.stat().st_mtime
        if cache.mtime(relative) == current_mtime:
            continue
        result = extract_file_with_failure_isolation(
            path, vault_root, relative, log_prefix="Cold-start extraction failed", metrics=metrics
        )
        if result is None:
            continue
        cache.set(relative, result, mtime=current_mtime)

    for cached_path in list(cache.entries()):
        if cached_path not in observed:
            cache.delete(cached_path)

    graph = build_graph(cache)
    return holder.publish(graph, {})
