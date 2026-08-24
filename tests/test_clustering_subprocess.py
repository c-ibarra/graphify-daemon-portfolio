"""Clustering runs in an isolated subprocess, never inline.

See specs/vault-compiler/spec.md "Clustering runs in an isolated subprocess"
and design.md Decision 4.
"""

from __future__ import annotations

import logging
import threading
import time

import networkx as nx
import pytest

from graphify_daemon.vault_compiler.clustering import run_clustering_subprocess


def _random_graph(n: int) -> nx.Graph:
    graph = nx.erdos_renyi_graph(n, 0.01, seed=42)
    return nx.relabel_nodes(graph, {i: str(i) for i in graph.nodes()})


def test_clustering_subprocess_does_not_block_concurrent_work() -> None:
    graph = _random_graph(600)
    result_holder: dict[str, object] = {}

    def do_clustering() -> None:
        result_holder["result"] = run_clustering_subprocess(graph, timeout=30.0)

    clustering_thread = threading.Thread(target=do_clustering)
    clustering_thread.start()

    counter = 0
    start = time.monotonic()
    while clustering_thread.is_alive() and time.monotonic() - start < 10:
        counter += 1

    clustering_thread.join(timeout=30)

    assert not clustering_thread.is_alive()
    assert counter > 100_000, (
        "a tight loop on another thread made too little progress while "
        "clustering ran -- clustering may be holding the GIL inline "
        "instead of running in a subprocess"
    )
    assert result_holder["result"] is not None


def test_clustering_handoff_cost_is_measured_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = _random_graph(50)

    with caplog.at_level(logging.INFO):
        run_clustering_subprocess(graph, timeout=30.0)

    assert any("handoff" in record.message.lower() for record in caplog.records), (
        "expected a log record measuring the pickling/subprocess handoff cost"
    )
