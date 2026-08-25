"""VaultWatcher rename handling: previous_path must survive to the batch.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, VaultWatcher


def test_rename_produces_a_change_with_previous_path(tmp_path: Path) -> None:
    vault_root = tmp_path.resolve()
    source = vault_root / "a.md"
    destination = vault_root / "b.md"
    source.write_text("content")

    batches: list[Batch] = []
    watcher = VaultWatcher(vault_root, batches.append, debounce_ms=100)
    watcher.start()
    try:
        time.sleep(0.3)  # let the CREATED event from write_text above flush first
        batches.clear()
        source.rename(destination)
        time.sleep(0.3)
    finally:
        watcher.stop()

    renamed = [c for b in batches for c in b.changes if c.kind is ChangeKind.RENAMED]
    assert len(renamed) == 1
    assert renamed[0].path == destination
    assert renamed[0].previous_path == source
