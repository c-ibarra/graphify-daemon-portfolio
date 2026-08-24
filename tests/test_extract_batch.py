"""Per-file extraction failure isolation across a batch.

See specs/vault-compiler/spec.md "Per-file extraction failure isolation".
"""

from __future__ import annotations

import logging
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_one_failing_file_does_not_abort_the_batch(tmp_path: Path, caplog: object) -> None:
    good_a = tmp_path / "a.md"
    good_a.write_text("# A\n")
    good_b = tmp_path / "b.md"
    good_b.write_text("# B\n")
    missing = tmp_path / "deleted.md"  # never created — simulates a deleted file

    batch = Batch(
        changes=(
            FileChange(path=good_a, kind=ChangeKind.MODIFIED),
            FileChange(path=missing, kind=ChangeKind.DELETED),
            FileChange(path=good_b, kind=ChangeKind.MODIFIED),
        )
    )

    cache = ExtractionCache()
    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        results = extract_batch(batch, tmp_path, cache)

    assert set(results) == {Path("a.md"), Path("b.md")}
    assert cache.get(Path("deleted.md")) is None
    assert any("deleted.md" in record.message for record in caplog.records)  # type: ignore[attr-defined]


def test_pre_existing_cache_entry_survives_a_failed_extraction(tmp_path: Path) -> None:
    missing = tmp_path / "deleted.md"
    cache = ExtractionCache()
    stale_result = {"nodes": [{"id": "stale"}], "edges": []}
    cache.set(Path("deleted.md"), stale_result)

    batch = Batch(changes=(FileChange(path=missing, kind=ChangeKind.DELETED),))
    extract_batch(batch, tmp_path, cache)

    assert cache.get(Path("deleted.md")) == stale_result
