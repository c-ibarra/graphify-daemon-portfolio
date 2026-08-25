"""Cold start never extracts a symlink resolving outside the vault, and
never descends into a symlinked directory pointing outside the vault.

See specs/vault-compiler/spec.md "Vault confinement for every processed path".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.artifact_lifecycle.cold_start import cold_start
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_cold_start_skips_external_file_symlink(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("# Secret\n")
    (vault_root / "linked_file.md").symlink_to(outside / "secret.md")

    cache = ExtractionCache()
    holder = SnapshotHolder()
    cold_start(vault_root, cache, holder)

    assert cache.get(Path("linked_file.md")) is None
    snapshot = holder.current()
    assert snapshot is not None
    assert not any(d.get("source_file") == "linked_file.md" for _, d in snapshot.graph.nodes(data=True))


def test_cold_start_does_not_descend_into_external_symlinked_directory(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.md").write_text("# Secret in a linked dir\n")
    (vault_root / "linked_dir").symlink_to(outside_dir)

    cache = ExtractionCache()
    holder = SnapshotHolder()
    cold_start(vault_root, cache, holder)

    assert cache.get(Path("linked_dir/secret.md")) is None
    snapshot = holder.current()
    assert snapshot is not None
    assert not any("linked_dir" in str(d.get("source_file", "")) for _, d in snapshot.graph.nodes(data=True))
