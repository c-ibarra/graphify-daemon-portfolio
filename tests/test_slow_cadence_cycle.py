"""run_slow_cadence_cycle: the actual production wiring between
SlowCadenceTracker, clustering, and the slow-cadence disk artifacts.

Found missing in code review (67af7fe...HEAD): SlowCadenceTracker was
never called from run_clustering_cycle, write_graph_json/
generate_knowledge_md, or ExtractionCache.save in any production code
path -- only from tests that composed them inline. This is the real
wiring for specs/vault-compiler/spec.md "Clustering triggered by slow
cadence only" and specs/artifact-lifecycle/spec.md "Artifact cadence table".
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from graphify_daemon.artifact_lifecycle.cadence import run_slow_cadence_cycle
from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.slow_cadence import SlowCadenceTracker
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def _graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("n1", label="N1", source_file="a.md")
    graph.add_node("n2", label="N2", source_file="b.md")
    graph.add_edge("n1", "n2", relation="links_to", confidence="EXTRACTED")
    return graph


def test_triggers_clustering_and_all_slow_cadence_writers_when_threshold_met(
    tmp_path: Path,
) -> None:
    holder = SnapshotHolder()
    holder.publish(_graph(), {})
    cache = ExtractionCache()
    cache.set(Path("a.md"), {"nodes": [], "edges": []})
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=1)
    tracker.record_batch(1)  # meets the threshold
    metrics = Metrics()

    graph_json_path = tmp_path / "graph.json"
    knowledge_md_path = tmp_path / "KNOWLEDGE.md"
    graph_cache_path = tmp_path / "graph_cache.json"

    triggered = run_slow_cadence_cycle(
        tracker,
        holder,
        cache,
        graph_json_path=graph_json_path,
        knowledge_md_path=knowledge_md_path,
        graph_cache_path=graph_cache_path,
        metrics=metrics,
    )

    assert triggered is True
    assert graph_json_path.exists()
    assert knowledge_md_path.exists() and knowledge_md_path.read_text()
    assert graph_cache_path.exists()
    assert tracker.should_trigger() is False, "tracker must reset after acting"
    assert metrics.seconds_since_event("clustering_success") is not None


def test_does_nothing_below_the_slow_cadence_threshold(tmp_path: Path) -> None:
    holder = SnapshotHolder()
    holder.publish(_graph(), {})
    cache = ExtractionCache()
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    tracker.record_batch(1)  # well under the threshold

    graph_json_path = tmp_path / "graph.json"
    knowledge_md_path = tmp_path / "KNOWLEDGE.md"
    graph_cache_path = tmp_path / "graph_cache.json"

    triggered = run_slow_cadence_cycle(
        tracker,
        holder,
        cache,
        graph_json_path=graph_json_path,
        knowledge_md_path=knowledge_md_path,
        graph_cache_path=graph_cache_path,
    )

    assert triggered is False
    assert not graph_json_path.exists()
    assert not knowledge_md_path.exists()
    assert not graph_cache_path.exists()


def test_still_persists_using_the_previous_snapshot_when_clustering_fails(tmp_path: Path, monkeypatch) -> None:
    """Clustering failure/timeout must not block the artifact writes --
    specs/vault-compiler/spec.md "Clustering failure or timeout fallback"
    says the previous community assignment stays intact, not that nothing
    gets persisted."""
    holder = SnapshotHolder()
    holder.publish(_graph(), {0: ["n1", "n2"]})
    cache = ExtractionCache()
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=1)
    tracker.record_batch(1)

    import graphify_daemon.artifact_lifecycle.cadence as cadence_module

    monkeypatch.setattr(cadence_module, "run_clustering_cycle", lambda *a, **k: None)

    graph_json_path = tmp_path / "graph.json"
    triggered = run_slow_cadence_cycle(
        tracker,
        holder,
        cache,
        graph_json_path=graph_json_path,
        knowledge_md_path=tmp_path / "KNOWLEDGE.md",
        graph_cache_path=tmp_path / "graph_cache.json",
    )

    assert triggered is True
    assert graph_json_path.exists()
    assert holder.current().community_map == {0: ["n1", "n2"]}
