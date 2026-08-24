"""SnapshotHolder: versioning, trigram pre-warm, atomic publish, stable reads.

See specs/vault-compiler/spec.md "Immutable snapshot structure",
"Trigram index pre-warmed before publish", "Atomic snapshot publish",
and "Stable reader reference per request".
"""

from __future__ import annotations

import threading

import networkx as nx

from graphify_daemon.adapters.graphify_query import get_trigram_index
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def _small_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("n1", label="N1")
    return graph


def test_snapshot_version_increases_monotonically_across_publishes() -> None:
    holder = SnapshotHolder()

    first = holder.publish(_small_graph(), {})
    second = holder.publish(_small_graph(), {})

    assert second.version > first.version


def test_trigram_index_is_prewarmed_before_publish() -> None:
    holder = SnapshotHolder()
    graph = _small_graph()

    snapshot = holder.publish(graph, {})

    # get_trigram_index only rebuilds when G.graph["_trigram_index"] is
    # absent; identity here proves publish() already warmed it, not this call.
    assert get_trigram_index(graph) is snapshot.trigram_index


def test_concurrent_reads_during_publish_never_see_a_mixed_snapshot() -> None:
    holder = SnapshotHolder()
    holder.publish(_small_graph(), {})  # version 1, so readers always see something

    publish_count = 50
    observed: list[tuple[int, dict]] = []
    observed_lock = threading.Lock()
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            snapshot = holder.current()
            with observed_lock:
                observed.append((snapshot.version, snapshot.community_map))

    readers = [threading.Thread(target=reader) for _ in range(4)]
    for thread in readers:
        thread.start()

    for i in range(publish_count):
        holder.publish(_small_graph(), {0: [f"call-{i}"]})

    stop.set()
    for thread in readers:
        thread.join()

    expected_marker_by_version = {i + 2: {0: [f"call-{i}"]} for i in range(publish_count)}
    expected_marker_by_version[1] = {}
    for version, community_map in observed:
        assert community_map == expected_marker_by_version[version]


def test_reader_keeps_one_snapshot_reference_across_a_multi_step_query() -> None:
    holder = SnapshotHolder()
    holder.publish(_small_graph(), {0: ["before"]})

    snapshot = holder.current()
    first_read = snapshot.version

    holder.publish(_small_graph(), {0: ["after"]})  # concurrent publish mid-request

    second_read = snapshot.version  # same reference, not a fresh holder.current() call

    assert first_read == second_read
    assert snapshot.community_map == {0: ["before"]}
