"""Cold-start reconciliation by mtime diff.

See specs/artifact-lifecycle/spec.md "Cold-start reconciliation by mtime diff".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify_daemon.artifact_lifecycle.cold_start import cold_start
from graphify_daemon.vault_compiler import extraction as extraction_module
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_restart_with_no_vault_changes_re_extracts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "a.md").write_text("# A\n")
    (vault_root / "b.md").write_text("# B\n")

    cache = ExtractionCache()
    holder = SnapshotHolder()
    snapshot = cold_start(vault_root, cache, holder)
    assert snapshot.graph.number_of_nodes() == 4  # 2 files x (file node + heading node)

    cache_path = tmp_path / "graph_cache.json"
    cache.save(cache_path)

    # Simulate a restart: fresh cache reloaded from disk, fresh holder.
    reloaded_cache = ExtractionCache()
    reloaded_cache.load(cache_path)

    call_count = 0
    real_extract_file = extraction_module.extract_file

    def _counting_extract_file(path, root):
        nonlocal call_count
        call_count += 1
        return real_extract_file(path, root)

    monkeypatch.setattr(extraction_module, "extract_file", _counting_extract_file)

    second_holder = SnapshotHolder()
    second_snapshot = cold_start(vault_root, reloaded_cache, second_holder)

    assert call_count == 0, "no file changed since the last cache -- nothing should be re-extracted"
    assert second_snapshot.graph.number_of_nodes() == 4


def test_changed_file_is_re_extracted_unchanged_file_is_not(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    a = vault_root / "a.md"
    a.write_text("# A\n")
    b = vault_root / "b.md"
    b.write_text("# B\n")

    cache = ExtractionCache()
    holder = SnapshotHolder()
    cold_start(vault_root, cache, holder)

    cache_path = tmp_path / "graph_cache.json"
    cache.save(cache_path)

    reloaded_cache = ExtractionCache()
    reloaded_cache.load(cache_path)

    a.write_text("# A changed\n")
    # Explicit mtime bump: successive writes within one test can land in the
    # same filesystem mtime tick (HFS+/APFS granularity), which would make
    # this assertion flaky rather than deterministic.
    os.utime(a, (a.stat().st_atime, a.stat().st_mtime + 5))

    extracted_paths: list[Path] = []
    real_extract_file = extraction_module.extract_file

    def _tracking_extract_file(path, root):
        extracted_paths.append(path)
        return real_extract_file(path, root)

    monkeypatch.setattr(extraction_module, "extract_file", _tracking_extract_file)

    second_holder = SnapshotHolder()
    cold_start(vault_root, reloaded_cache, second_holder)

    assert extracted_paths == [a]


def test_deleted_file_is_dropped_from_the_cache_and_graph(
    tmp_path: Path,
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    a = vault_root / "a.md"
    a.write_text("# A\n")
    b = vault_root / "b.md"
    b.write_text("# B\n")

    cache = ExtractionCache()
    holder = SnapshotHolder()
    cold_start(vault_root, cache, holder)
    assert holder.current().graph.number_of_nodes() == 4

    b.unlink()

    second_holder = SnapshotHolder()
    snapshot = cold_start(vault_root, cache, second_holder)

    assert snapshot.graph.number_of_nodes() == 2  # 1 remaining file x 2 nodes
    assert cache.get(Path("b.md")) is None
