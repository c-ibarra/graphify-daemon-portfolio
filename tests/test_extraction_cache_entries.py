"""ExtractionCache.entries() — full-corpus accessor used by snapshot building."""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.extraction import ExtractionCache


def test_entries_returns_every_cached_result() -> None:
    cache = ExtractionCache()
    a_result = {"nodes": [{"id": "a"}], "edges": []}
    b_result = {"nodes": [{"id": "b"}], "edges": []}
    cache.set(Path("a.md"), a_result)
    cache.set(Path("b.md"), b_result)

    entries = cache.entries()

    assert entries == {Path("a.md"): a_result, Path("b.md"): b_result}


def test_entries_is_a_copy_not_a_live_view() -> None:
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []})

    entries = cache.entries()
    entries[Path("b.md")] = {"nodes": [], "edges": []}

    assert cache.entries() == {Path("a.md"): {"nodes": [], "edges": []}}
