"""Alive-vs-ready health check.

See specs/artifact-lifecycle/spec.md "Alive vs ready health check".
"""

from __future__ import annotations

import networkx as nx

from graphify_daemon.artifact_lifecycle.health import health_check
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def test_alive_but_not_ready_before_first_snapshot() -> None:
    holder = SnapshotHolder()
    status = health_check(holder)
    assert status == {"alive": True, "ready": False}


def test_ready_once_a_snapshot_is_published() -> None:
    holder = SnapshotHolder()
    graph = nx.DiGraph()
    graph.add_node("n1")
    holder.publish(graph, {})

    status = health_check(holder)
    assert status == {"alive": True, "ready": True}
