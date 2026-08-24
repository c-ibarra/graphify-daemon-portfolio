"""run_clustering_subprocess must not deadlock when the clustering result
is larger than the OS pipe buffer.

Found while building benchmarks/ (task group 8): run_clustering_subprocess
called process.join(timeout) before draining result_queue -- the classic
multiprocessing.Queue deadlock. A community-map result bigger than the OS
pipe buffer (~64KB) leaves the child blocked writing it while the parent
blocks in join() without ever reading the pipe; the only way out was the
timeout, which then discarded an already-correctly-computed result.

See specs/vault-compiler/spec.md "Clustering subprocess result retrieval
does not deadlock on large payloads".
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

from graphify.build import build_from_json

from graphify_daemon.vault_compiler.clustering import run_clustering_subprocess

sys.path.insert(0, str(Path(__file__).parent.parent / "benchmarks"))
from synthetic_graph import generate_synthetic_extraction


def test_large_community_map_is_retrieved_without_deadlocking() -> None:
    # 8,000 nodes pickles to comfortably over the ~64KB OS pipe buffer --
    # verified directly (see design.md): ~97KB for this generator/seed.
    extraction = generate_synthetic_extraction(node_count=8_000)
    graph = build_from_json(extraction, directed=True)

    result = run_clustering_subprocess(graph, timeout=20.0)

    assert result is not None, "clustering succeeded but the result was lost to the deadlock/timeout"
    assert len(result) > 0
    # Sanity-check the payload really does exceed one pipe buffer, so this
    # test is actually exercising the bug's precondition.
    assert len(pickle.dumps(("ok", result))) > 65_536
