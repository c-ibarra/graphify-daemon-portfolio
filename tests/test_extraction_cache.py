"""ExtractionCache in-RAM behavior and its explicit disk persistence.

See specs/vault-compiler/spec.md "In-RAM extraction cache" and
"Extraction cache disk persistence cadence".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify_daemon.vault_compiler.extraction import ExtractionCache


def test_get_and_set_never_touch_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ExtractionCache.get/set must not perform disk I/O")

    monkeypatch.setattr(Path, "open", _forbidden_open)

    cache = ExtractionCache()
    relative_path = Path("notes/foo.md")
    result = {"nodes": [{"id": "n1"}], "edges": []}

    cache.set(relative_path, result)
    assert cache.get(relative_path) == result
    assert cache.get(Path("notes/missing.md")) is None


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    cache = ExtractionCache()
    relative_path = Path("notes/foo.md")
    result = {"nodes": [{"id": "n1"}], "edges": []}
    cache.set(relative_path, result)

    cache_file = tmp_path / "extraction_cache.json"
    cache.save(cache_file)

    reloaded = ExtractionCache()
    reloaded.load(cache_file)

    assert reloaded.get(relative_path) == result
