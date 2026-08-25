"""A confinement rejection is logged with a vault-relative path, never the
vault's absolute filesystem path.

See specs/vault-compiler/spec.md "Vault confinement for every processed path".
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from graphify_daemon.artifact_lifecycle.cold_start import cold_start
from graphify_daemon.vault_compiler.batching import Batch, VaultWatcher
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_watcher_confinement_rejection_logs_relative_path(tmp_path: Path, caplog: object) -> None:
    vault_root = (tmp_path / "vault").resolve()
    vault_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.md"
    target.write_text("secret")

    batches: list[Batch] = []
    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        watcher = VaultWatcher(vault_root, batches.append, debounce_ms=100)
        watcher.start()
        try:
            (vault_root / "linked.md").symlink_to(target)
            time.sleep(0.3)
        finally:
            watcher.stop()

    assert batches == []
    assert any("linked.md" in record.message for record in caplog.records)  # type: ignore[attr-defined]
    assert not any(str(tmp_path) in record.message for record in caplog.records)  # type: ignore[attr-defined]


def test_cold_start_confinement_rejection_logs_relative_path(tmp_path: Path, caplog: object) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret")
    (vault_root / "linked.md").symlink_to(outside / "secret.md")

    cache = ExtractionCache()
    holder = SnapshotHolder()
    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        cold_start(vault_root, cache, holder)

    assert any("linked.md" in record.message for record in caplog.records)  # type: ignore[attr-defined]
    assert not any(str(tmp_path) in record.message for record in caplog.records)  # type: ignore[attr-defined]
