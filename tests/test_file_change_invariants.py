"""FileChange.previous_path invariants.

See specs/vault-compiler/spec.md "Rename carries source and destination as
one logical unit".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify_daemon.vault_compiler.batching import ChangeKind, FileChange


def test_renamed_without_previous_path_raises() -> None:
    with pytest.raises(ValueError, match="previous_path"):
        FileChange(path=Path("b.md"), kind=ChangeKind.RENAMED)


@pytest.mark.parametrize("kind", [ChangeKind.CREATED, ChangeKind.MODIFIED, ChangeKind.DELETED])
def test_non_renamed_with_previous_path_raises(kind: ChangeKind) -> None:
    with pytest.raises(ValueError, match="previous_path"):
        FileChange(path=Path("a.md"), kind=kind, previous_path=Path("old.md"))


def test_renamed_with_previous_path_is_valid() -> None:
    change = FileChange(path=Path("b.md"), kind=ChangeKind.RENAMED, previous_path=Path("a.md"))
    assert change.path == Path("b.md")
    assert change.previous_path == Path("a.md")


@pytest.mark.parametrize("kind", [ChangeKind.CREATED, ChangeKind.MODIFIED, ChangeKind.DELETED])
def test_non_renamed_without_previous_path_is_valid(kind: ChangeKind) -> None:
    change = FileChange(path=Path("a.md"), kind=kind)
    assert change.previous_path is None
