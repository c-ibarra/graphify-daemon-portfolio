"""ExtractionCache mtime tracking and deletion, for cold-start reconciliation.

See specs/artifact-lifecycle/spec.md "Cold-start reconciliation by mtime diff".
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.extraction import ExtractionCache


def test_mtime_is_none_when_never_set() -> None:
    cache = ExtractionCache()
    assert cache.mtime(Path("a.md")) is None


def test_mtime_returns_the_value_passed_to_set() -> None:
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []}, mtime=123.456)
    assert cache.mtime(Path("a.md")) == 123.456


def test_set_without_mtime_leaves_mtime_unset() -> None:
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []})
    assert cache.mtime(Path("a.md")) is None


def test_delete_removes_both_result_and_mtime() -> None:
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []}, mtime=1.0)
    cache.delete(Path("a.md"))
    assert cache.get(Path("a.md")) is None
    assert cache.mtime(Path("a.md")) is None


def test_save_then_load_round_trips_mtime(tmp_path: Path) -> None:
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []}, mtime=42.0)
    path = tmp_path / "graph_cache.json"
    cache.save(path)

    reloaded = ExtractionCache()
    reloaded.load(path)
    assert reloaded.mtime(Path("a.md")) == 42.0
