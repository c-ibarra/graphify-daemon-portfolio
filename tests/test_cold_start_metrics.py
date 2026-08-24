"""cold_start reports per-file extraction failures to an optional Metrics registry.

Found missing in code review (67af7fe...HEAD): unlike extract_batch, the
cold-start reconciliation loop silently dropped extraction failures without
logging or counting them, undercounting extraction_error_count during
startup reconciliation.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from graphify_daemon.artifact_lifecycle.cold_start import cold_start
from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_extraction_failure_during_cold_start_increments_metrics_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "good.md").write_text("# Good\n")
    (vault_root / "bad.py").write_text("not valid python syntax {{{")

    import graphify_daemon.vault_compiler.extraction as extraction_module

    real_extract_file = extraction_module.extract_file

    def _flaky_extract_file(path, root):
        if path.name == "bad.py":
            raise RuntimeError("simulated extraction crash")
        return real_extract_file(path, root)

    monkeypatch.setattr(extraction_module, "extract_file", _flaky_extract_file)

    metrics = Metrics()
    cache = ExtractionCache()
    holder = SnapshotHolder()

    with caplog.at_level(logging.WARNING):
        snapshot = cold_start(vault_root, cache, holder, metrics=metrics)

    assert metrics.counter("extraction_errors") == 1
    assert any("bad.py" in record.message for record in caplog.records)
    # the good file still made it into the graph
    sources = {d["source_file"] for _, d in snapshot.graph.nodes(data=True)}
    assert "good.md" in sources


def test_metrics_is_optional(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "a.md").write_text("# A\n")
    cache = ExtractionCache()
    holder = SnapshotHolder()
    cold_start(vault_root, cache, holder)  # no metrics kwarg -- must not raise
