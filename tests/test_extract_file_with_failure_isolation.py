"""extract_file_with_failure_isolation: the shared failure-isolation step
used by both extract_batch and cold_start.

See specs/vault-compiler/spec.md; the DRY refactor itself has no spec
delta (pure internal consolidation of already-duplicated logic), but
this function is the interface confirmed for it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.extraction import extract_file_with_failure_isolation


def test_successful_extraction_returns_the_result(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text("# Good\n")

    result = extract_file_with_failure_isolation(
        good, tmp_path, Path("good.md"), log_prefix="Extraction failed", metrics=None
    )

    assert result is not None
    assert "error" not in result


def test_extract_file_raising_is_isolated(tmp_path: Path, caplog: object) -> None:
    unsupported = tmp_path / "notes.txt"  # no extractor registered for .txt
    unsupported.write_text("hello")
    metrics = Metrics()

    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        result = extract_file_with_failure_isolation(
            unsupported,
            tmp_path,
            Path("notes.txt"),
            log_prefix="Extraction failed",
            metrics=metrics,
        )

    assert result is None
    assert metrics.counter("extraction_errors") == 1
    assert any(
        "notes.txt" in record.message and "Extraction failed" in record.message
        for record in caplog.records  # type: ignore[attr-defined]
    )


def test_error_key_in_result_is_isolated(tmp_path: Path, caplog: object) -> None:
    missing = tmp_path / "deleted.md"  # never created -- extractor reports "error"
    metrics = Metrics()

    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        result = extract_file_with_failure_isolation(
            missing,
            tmp_path,
            Path("deleted.md"),
            log_prefix="Cold-start extraction failed",
            metrics=metrics,
        )

    assert result is None
    assert metrics.counter("extraction_errors") == 1
    assert any(
        "deleted.md" in record.message and "Cold-start extraction failed" in record.message
        for record in caplog.records  # type: ignore[attr-defined]
    )


def test_metrics_is_optional_on_failure(tmp_path: Path) -> None:
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("hello")

    result = extract_file_with_failure_isolation(
        unsupported, tmp_path, Path("notes.txt"), log_prefix="Extraction failed", metrics=None
    )

    assert result is None
