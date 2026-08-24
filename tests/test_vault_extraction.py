"""Deterministic, non-LLM extraction of a single vault file.

See specs/vault-compiler/spec.md "Deterministic, non-LLM extraction" and
"Source file provenance".
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from graphify_daemon.vault_compiler.extraction import extract_file


def test_identical_content_extracts_identically_with_no_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _forbidden_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("extract_file must not open a network connection (no LLM call)")

    monkeypatch.setattr(socket.socket, "connect", _forbidden_connect)

    note = tmp_path / "notes" / "foo.md"
    note.parent.mkdir()
    note.write_text("# Title\n\nSome content referencing `Bar`.\n")

    first = extract_file(note, tmp_path)
    second = extract_file(note, tmp_path)

    assert first == second
    assert first["nodes"]


def test_source_file_is_relative_to_vault_root(tmp_path: Path) -> None:
    note = tmp_path / "dataScienceKnowledgeBase" / "foo.md"
    note.parent.mkdir()
    note.write_text("# Title\n")

    result = extract_file(note, tmp_path)

    assert result["nodes"]
    for node in result["nodes"]:
        assert node["source_file"] == "dataScienceKnowledgeBase/foo.md"
