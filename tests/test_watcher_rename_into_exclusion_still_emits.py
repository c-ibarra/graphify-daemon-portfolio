"""A rename into an excluded location must still reach a batch as a RENAMED
change, so the compile-time cleanup of previous_path's state actually runs.

Found while implementing task group 3: the watcher's existing exclusion
check ran on the destination path *before* constructing a FileChange for
RENAMED events, silently dropping the whole event (and the previous path's
state along with it) instead of letting it through for compile-time
handling. See specs/vault-compiler/spec.md "Rename carries source and
destination as one logical unit".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, VaultWatcher


def test_rename_into_excluded_directory_still_emits_a_renamed_change(tmp_path: Path) -> None:
    vault_root = tmp_path.resolve()
    (vault_root / ".trash").mkdir()
    source = vault_root / "a.md"
    destination = vault_root / ".trash" / "a.md"
    source.write_text("content")

    batches: list[Batch] = []
    watcher = VaultWatcher(vault_root, batches.append, debounce_ms=100)
    watcher.start()
    try:
        time.sleep(0.3)  # let the CREATED event from write_text flush first
        batches.clear()
        source.rename(destination)
        time.sleep(0.3)
    finally:
        watcher.stop()

    renamed = [c for b in batches for c in b.changes if c.kind is ChangeKind.RENAMED]
    assert len(renamed) == 1
    assert renamed[0].previous_path == source
