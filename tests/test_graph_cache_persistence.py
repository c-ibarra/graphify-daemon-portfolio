"""graph_cache.json: slow-cadence persistence of the extraction cache.

See specs/artifact-lifecycle/spec.md "Artifact cadence table". No new
production code needed -- ExtractionCache.save (task group 4) already
does exactly this; the only thing to prove is that it composes correctly
with the slow-cadence gate, same as graph.json.
"""

from __future__ import annotations

from pathlib import Path

from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.slow_cadence import SlowCadenceTracker


def test_graph_cache_untouched_by_a_batch_below_the_slow_cadence_threshold(
    tmp_path: Path,
) -> None:
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []})
    path = tmp_path / "graph_cache.json"

    tracker.record_batch(1)
    if tracker.should_trigger():
        cache.save(path)

    assert not path.exists()


def test_graph_cache_persisted_once_slow_cadence_triggers(tmp_path: Path) -> None:
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [{"id": "n1"}], "edges": []})
    path = tmp_path / "graph_cache.json"

    tracker.record_batch(25)
    if tracker.should_trigger():
        cache.save(path)

    assert path.exists()
    reloaded = ExtractionCache()
    reloaded.load(path)
    assert reloaded.get(Path("a.md")) == {"nodes": [{"id": "n1"}], "edges": []}
