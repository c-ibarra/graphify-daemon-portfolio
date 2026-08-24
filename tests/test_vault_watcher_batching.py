"""VaultWatcher debounce-batching behavior.

See specs/vault-compiler/spec.md "Debounce batching".
"""

from __future__ import annotations

import time
from pathlib import Path

from graphify_daemon.vault_compiler.batching import Batch, VaultWatcher


def test_rapid_successive_file_changes_form_one_batch(tmp_path: Path) -> None:
    batches: list[Batch] = []
    watcher = VaultWatcher(tmp_path, batches.append, debounce_ms=100)
    watcher.start()
    try:
        (tmp_path / "a.md").write_text("a")
        time.sleep(0.02)
        (tmp_path / "b.md").write_text("b")
        time.sleep(0.02)
        (tmp_path / "c.md").write_text("c")
        time.sleep(0.3)  # comfortably past the 100ms debounce window
    finally:
        watcher.stop()

    assert len(batches) == 1
    changed_paths = {change.path for change in batches[0].changes}
    assert changed_paths == {tmp_path / "a.md", tmp_path / "b.md", tmp_path / "c.md"}


def test_excluded_paths_never_reach_a_batch(tmp_path: Path) -> None:
    (tmp_path / ".trash").mkdir()
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "vendor-repo").mkdir()

    batches: list[Batch] = []
    watcher = VaultWatcher(
        tmp_path,
        batches.append,
        debounce_ms=100,
        nested_repo_names=frozenset({"vendor-repo"}),
    )
    watcher.start()
    try:
        (tmp_path / ".trash" / "deleted-note.md").write_text("gone")
        (tmp_path / ".obsidian" / "workspace.json").write_text("{}")
        (tmp_path / "vendor-repo" / "README.md").write_text("readme")
        (tmp_path / "kept.md.ajson").write_text("{}")
        time.sleep(0.3)
    finally:
        watcher.stop()

    assert batches == []


def test_non_observed_suffixes_never_reach_a_batch(tmp_path: Path) -> None:
    batches: list[Batch] = []
    watcher = VaultWatcher(tmp_path, batches.append, debounce_ms=100)
    watcher.start()
    try:
        (tmp_path / "image.png").write_text("not a vault file")
        (tmp_path / "notes.pdf").write_text("not a vault file")
        time.sleep(0.3)
    finally:
        watcher.stop()

    assert batches == []
