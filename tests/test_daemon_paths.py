"""DaemonPaths: this daemon's own output directory.

See design.md's Risks/Trade-offs on strictly separate output paths during
the migration parallel-run window.
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.paths import DEFAULT_OUTPUT_DIR_NAME, DaemonPaths

LEGACY_OUTPUT_DIR_NAME = "graphify-out"  # ~/projects/obsidianKnowledgeCurator/graphify-out/


def test_default_output_dir_name_is_distinct_from_the_legacy_watcher_s() -> None:
    assert DEFAULT_OUTPUT_DIR_NAME != LEGACY_OUTPUT_DIR_NAME


def test_resolves_all_four_artifact_paths_under_the_output_dir(tmp_path: Path) -> None:
    paths = DaemonPaths(tmp_path)
    assert paths.vault_index_db == tmp_path / "vault_index.db"
    assert paths.graph_json == tmp_path / "graph.json"
    assert paths.knowledge_md == tmp_path / "KNOWLEDGE.md"
    assert paths.graph_cache_json == tmp_path / "graph_cache.json"
