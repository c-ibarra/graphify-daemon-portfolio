"""The vault's absolute filesystem path never appears in a log line, even
when the underlying extractor's own error message embeds it (its raw
FileNotFoundError text includes the full path it tried to open).

See specs/artifact-lifecycle/spec.md "No confidential values in logs".
"""

from __future__ import annotations

import logging
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_extraction_failure_log_never_contains_the_vault_absolute_path(tmp_path: Path, caplog: object) -> None:
    vault_root = (tmp_path / "my-distinctive-vault-name").resolve()
    vault_root.mkdir()
    missing = vault_root / "broken.md"  # never created -- MODIFIED against it is a real extraction failure

    cache = ExtractionCache()
    batch = Batch(changes=(FileChange(path=missing, kind=ChangeKind.MODIFIED),))

    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        extract_batch(batch, vault_root, cache)

    assert any("broken.md" in record.message for record in caplog.records)  # type: ignore[attr-defined]
    assert not any(str(vault_root) in record.message for record in caplog.records)  # type: ignore[attr-defined]
    assert not any(str(tmp_path) in record.message for record in caplog.records)  # type: ignore[attr-defined]
