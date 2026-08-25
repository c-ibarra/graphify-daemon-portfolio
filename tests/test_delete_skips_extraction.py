"""A DELETED change never attempts to open or extract the missing file.

See specs/vault-compiler/spec.md "Idempotent deletion".
"""

from __future__ import annotations

import logging
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_deleted_change_does_not_log_an_extraction_failure(tmp_path: Path, caplog: object) -> None:
    missing = tmp_path / "gone.md"  # never created — this is the delete event's whole point
    cache = ExtractionCache()
    batch = Batch(changes=(FileChange(path=missing, kind=ChangeKind.DELETED),))

    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        extract_batch(batch, tmp_path, cache)

    assert not any("gone.md" in record.message for record in caplog.records)  # type: ignore[attr-defined]
    assert not any("Extraction failed" in record.message for record in caplog.records)  # type: ignore[attr-defined]
