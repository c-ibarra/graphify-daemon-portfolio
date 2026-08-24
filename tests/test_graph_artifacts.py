"""graph.json atomic writes and KNOWLEDGE.md generation from the snapshot.

See specs/artifact-lifecycle/spec.md "Atomic graph.json writes" and
"KNOWLEDGE.md generated from the resident snapshot".
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from graphify_daemon.artifact_lifecycle.graph_artifacts import (
    generate_knowledge_md,
    write_graph_json,
)
from graphify_daemon.vault_compiler.slow_cadence import SlowCadenceTracker
from graphify_daemon.vault_compiler.snapshot import GraphSnapshot


def _snapshot() -> GraphSnapshot:
    graph = nx.DiGraph()
    graph.add_node("a", label="Alpha", source_file="alpha.md")
    graph.add_node("b", label="Beta", source_file="beta.md")
    graph.add_edge("a", "b", relation="links_to", confidence="EXTRACTED")
    return GraphSnapshot(
        graph=graph,
        trigram_index={},
        community_map={0: ["a", "b"]},
        version=1,
    )


def test_write_graph_json_produces_a_loadable_file(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    write_graph_json(_snapshot(), path)

    assert path.exists()
    data = json.loads(path.read_text())
    assert "nodes" in data or "links" in data or "edges" in data


def test_generate_knowledge_md_reflects_the_snapshot() -> None:
    md = generate_knowledge_md(_snapshot())
    assert "2" in md  # node count somewhere in the summary
    assert isinstance(md, str)
    assert md


def test_graph_json_untouched_by_a_batch_below_the_slow_cadence_threshold(
    tmp_path: Path,
) -> None:
    """write_graph_json is a pure on-demand write -- the "only on slow
    cadence" guarantee comes entirely from the caller consulting
    SlowCadenceTracker (task group 6) first, which this composes to prove."""
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    path = tmp_path / "graph.json"

    tracker.record_batch(1)  # one small batch, well under the threshold
    if tracker.should_trigger():
        write_graph_json(_snapshot(), path)

    assert not path.exists()


def test_generate_knowledge_md_never_touches_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves KNOWLEDGE.md generation succeeds regardless of graph.json's
    state on disk (stale/absent) -- it never reads a file at all."""

    def _forbidden_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("generate_knowledge_md must not open a file")

    monkeypatch.setattr(Path, "open", _forbidden_open)

    md = generate_knowledge_md(_snapshot())
    assert md
