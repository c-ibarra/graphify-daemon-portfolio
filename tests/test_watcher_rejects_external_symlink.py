"""The watcher never queues a change for a symlink resolving outside the vault.

See specs/vault-compiler/spec.md "Vault confinement for every processed path".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, VaultWatcher


def test_watcher_rejects_external_symlink(tmp_path: Path) -> None:
    vault_root = (tmp_path / "vault").resolve()
    vault_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.md"
    target.write_text("secret content")

    batches: list[Batch] = []
    watcher = VaultWatcher(vault_root, batches.append, debounce_ms=100)
    watcher.start()
    try:
        (vault_root / "linked.md").symlink_to(target)
        time.sleep(0.3)
    finally:
        watcher.stop()

    assert batches == []
