"""extract_batch reports each per-file failure to an optional Metrics registry."""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_extraction_failures_increment_the_metrics_counter(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text("# Good\n")
    missing = tmp_path / "missing.md"  # never created — MODIFIED against a missing file is a real extraction failure

    batch = Batch(
        changes=(
            FileChange(path=good, kind=ChangeKind.MODIFIED),
            FileChange(path=missing, kind=ChangeKind.MODIFIED),
        )
    )

    metrics = Metrics()
    cache = ExtractionCache()
    extract_batch(batch, tmp_path, cache, metrics=metrics)

    assert metrics.counter("extraction_errors") == 1


def test_metrics_is_optional(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text("# Good\n")
    batch = Batch(changes=(FileChange(path=good, kind=ChangeKind.MODIFIED),))
    cache = ExtractionCache()
    extract_batch(batch, tmp_path, cache)  # no metrics kwarg -- must not raise
