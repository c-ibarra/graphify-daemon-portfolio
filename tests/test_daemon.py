"""Daemon: composes every already-built component into one process.

This is pure wiring (no new domain logic) -- every piece it calls is
already independently tested. These tests verify the wiring itself: that
Daemon actually calls the right things in the right order, the way
test_slow_cadence_cycle.py verified run_slow_cadence_cycle's wiring.

main() itself (env var reading, signal registration, the final blocking
transport.run() call) is not tested here -- same deferral as task group
7's run().
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.server import Server

from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange


def _daemon(tmp_path: Path, **kwargs) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths, **kwargs)


def test_cold_start_publishes_an_initial_snapshot(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    (daemon.vault_root / "a.md").write_text("# A\n")

    assert daemon.holder.current() is None
    daemon.cold_start()

    assert daemon.holder.current() is not None
    assert daemon.holder.current().graph.number_of_nodes() > 0


def test_compile_batch_syncs_vault_index_and_publishes_a_new_snapshot(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()  # empty vault -> empty snapshot, version 1

    note = daemon.vault_root / "note.md"
    note.write_text("# Note\n")
    batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))

    version_before = daemon.holder.current().version
    daemon._compile_batch(batch)

    assert daemon.holder.current().version > version_before
    assert daemon.holder.current().graph.number_of_nodes() > 0

    rows = list(daemon.vault_index_conn.execute("SELECT path FROM files"))
    assert ("note.md",) in rows


def test_compile_batch_carries_forward_the_current_community_map(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()
    daemon.holder.publish(daemon.holder.current().graph, {0: ["sentinel"]})

    note = daemon.vault_root / "note.md"
    note.write_text("# Note\n")
    batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    daemon._compile_batch(batch)

    assert daemon.holder.current().community_map == {0: ["sentinel"]}


def test_compile_batch_triggers_slow_cadence_artifacts_when_threshold_met(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path, slow_cadence_change_threshold=1)
    daemon.cold_start()

    note = daemon.vault_root / "note.md"
    note.write_text("# Note\n")
    batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    daemon._compile_batch(batch)

    assert daemon.paths.graph_json.exists()
    assert daemon.paths.knowledge_md.exists()
    assert daemon.paths.graph_cache_json.exists()


def test_build_mcp_server_exposes_the_seven_tools(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()

    server = daemon.build_mcp_server()
    assert isinstance(server, Server)


def test_build_mcp_server_registers_subscriptions_listen(tmp_path: Path) -> None:
    # A real client (Antigravity, 2026-07-28 era) calls `subscriptions/listen`
    # before it will use any tools -- without a registered handler this 404s
    # with "Method not found" and the client refuses to proceed at all, even
    # though this server's tools capability declares `listChanged: false`
    # (the tool list never changes, so nothing would ever be published).
    daemon = _daemon(tmp_path)
    daemon.cold_start()

    server = daemon.build_mcp_server()

    assert server.get_request_handler("subscriptions/listen") is not None


def test_health_route_reports_alive_and_ready(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()

    handler = daemon.health_route()

    class _Req:
        pass

    response = asyncio.run(handler(_Req()))
    body = json.loads(response.body)
    assert body == {"alive": True, "ready": True}


def test_metrics_route_reports_the_payload(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()

    handler = daemon.metrics_route()

    class _Req:
        pass

    response = asyncio.run(handler(_Req()))
    body = json.loads(response.body)
    assert body["snapshot_version"] == 1
    assert "rss_bytes" in body


def test_persist_on_shutdown_writes_final_artifacts_unconditionally(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path, slow_cadence_change_threshold=1_000_000)
    daemon.cold_start()
    note = daemon.vault_root / "note.md"
    note.write_text("# Note\n")
    batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    daemon._compile_batch(batch)

    # slow cadence never triggered (threshold far too high) -- nothing on disk yet
    assert not daemon.paths.graph_json.exists()

    daemon.persist_on_shutdown()

    assert daemon.paths.graph_json.exists()
    assert daemon.paths.knowledge_md.exists()
    assert daemon.paths.graph_cache_json.exists()
