"""resolve_within_vault: the shared vault-confinement check.

See specs/vault-compiler/spec.md "Vault confinement for every processed path".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.exclusions import resolve_within_vault


def test_in_vault_path_resolves_to_itself(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    note = vault_root / "note.md"
    note.write_text("content")

    assert resolve_within_vault(note, vault_root) == note.resolve()


def test_path_outside_vault_is_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("content")

    assert resolve_within_vault(outside, vault_root) is None


def test_symlink_resolving_outside_vault_is_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    outside_target = tmp_path / "outside.md"
    outside_target.write_text("content")
    symlink = vault_root / "linked.md"
    symlink.symlink_to(outside_target)

    assert resolve_within_vault(symlink, vault_root) is None


def test_symlink_resolving_inside_vault_returns_real_path(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    real_target = vault_root / "real.md"
    real_target.write_text("content")
    symlink = vault_root / "linked.md"
    symlink.symlink_to(real_target)

    assert resolve_within_vault(symlink, vault_root) == real_target.resolve()


def test_not_yet_existing_in_vault_path_still_resolves(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    not_yet_created = vault_root / "new.md"

    assert resolve_within_vault(not_yet_created, vault_root) == not_yet_created.resolve()
