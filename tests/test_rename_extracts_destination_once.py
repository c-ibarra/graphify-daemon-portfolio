"""A RENAMED change extracts its destination exactly once.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

from pathlib import Path

import graphify_daemon.vault_compiler.extraction as extraction_module
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_rename_extracts_destination_exactly_once(tmp_path: Path, monkeypatch: object) -> None:
    source = tmp_path / "a.md"
    destination = tmp_path / "b.md"
    source.write_text("# A\n")
    source.rename(destination)

    calls: list[Path] = []
    original_extract_file = extraction_module.extract_file

    def spy(path: Path, vault_root: Path) -> dict[str, object]:
        calls.append(path)
        return original_extract_file(path, vault_root)

    monkeypatch.setattr(extraction_module, "extract_file", spy)  # type: ignore[attr-defined]

    cache = ExtractionCache()
    batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))
    extract_batch(batch, tmp_path, cache)

    assert calls == [destination]
