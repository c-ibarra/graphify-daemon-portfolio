"""Renaming from an excluded location into a watched one is equivalent to creating it.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch


def test_rename_out_of_excluded_directory_creates_destination(tmp_path: Path) -> None:
    excluded_dir = tmp_path / ".trash"
    excluded_dir.mkdir()
    source = excluded_dir / "a.md"
    source.write_text("# A\n")
    destination = tmp_path / "a.md"

    cache = ExtractionCache()
    # previous_path was never cached -- it lived in an excluded directory.
    source.rename(destination)
    rename_batch = Batch(changes=(FileChange(path=destination, kind=ChangeKind.RENAMED, previous_path=source),))

    extract_batch(rename_batch, tmp_path, cache)  # must not raise despite missing prior state

    assert cache.get(Path("a.md")) is not None
