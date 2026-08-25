"""Renaming a file into an excluded location is equivalent to deleting it.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_rename_into_excluded_directory_deletes_source_and_never_extracts_destination(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# A\n")
    excluded_dir = tmp_path / ".trash"
    excluded_dir.mkdir()
    destination = excluded_dir / "a.md"

    cache = ExtractionCache()
    create_batch = Batch(changes=(FileChange(path=source, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, tmp_path, cache)
    assert cache.get(Path("a.md")) is not None

    source.rename(destination)
    rename_batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))
    extract_batch(rename_batch, tmp_path, cache)

    assert cache.get(Path("a.md")) is None
    assert cache.get(Path(".trash/a.md")) is None


def test_rename_into_non_observed_suffix_deletes_source(tmp_path: Path) -> None:
    source = tmp_path / "a.md"
    source.write_text("# A\n")
    destination = tmp_path / "a.png"

    cache = ExtractionCache()
    create_batch = Batch(changes=(FileChange(path=source, kind=ChangeKind.CREATED),))
    extract_batch(create_batch, tmp_path, cache)
    assert cache.get(Path("a.md")) is not None

    source.rename(destination)
    rename_batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))
    extract_batch(rename_batch, tmp_path, cache)

    assert cache.get(Path("a.md")) is None
    assert cache.get(Path("a.png")) is None
