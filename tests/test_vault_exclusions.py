"""Vault exclusion filter behavior.

See specs/vault-compiler/spec.md "Vault exclusion list".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.exclusions import is_excluded


def test_normal_markdown_file_is_not_excluded(tmp_path: Path) -> None:
    path = tmp_path / "dataScienceKnowledgeBase" / "foo.md"
    assert is_excluded(path, tmp_path) is False


def test_trashed_note_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / ".trash" / "deleted-note.md"
    assert is_excluded(path, tmp_path) is True


def test_obsidian_internal_file_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / ".obsidian" / "workspace.json"
    assert is_excluded(path, tmp_path) is True


def test_ajson_file_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / "notes" / "foo.md.ajson"
    assert is_excluded(path, tmp_path) is True


def test_nested_repo_is_excluded_when_named(tmp_path: Path) -> None:
    path = tmp_path / "some-project" / "README.md"
    assert is_excluded(path, tmp_path, nested_repo_names=frozenset({"some-project"})) is True


def test_nested_repo_name_not_excluded_when_not_listed(tmp_path: Path) -> None:
    path = tmp_path / "some-project" / "README.md"
    assert is_excluded(path, tmp_path, nested_repo_names=frozenset({"other-project"})) is False
