"""A normal (non-exceptional) return from transport.run() still runs
daemon.shutdown() exactly once, via run_forever's owning try/finally.

See specs/artifact-lifecycle/spec.md "Uniform cleanup across SIGTERM,
SIGINT, and normal exit".
"""

from __future__ import annotations

import signal
from pathlib import Path

import pytest

from graphify_daemon import daemon as daemon_module
from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths


def _daemon(tmp_path: Path) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths)


def test_run_forever_calls_shutdown_when_transport_run_returns_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()

    shutdown_calls: list[bool] = []
    monkeypatch.setattr(daemon, "shutdown", lambda: shutdown_calls.append(True))
    monkeypatch.setattr(daemon_module.transport, "run", lambda *args, **kwargs: None)

    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sigint = signal.getsignal(signal.SIGINT)
    try:
        daemon_module.run_forever(daemon, mcp_server=object(), host="127.0.0.1", port=0, api_key="k", extra_routes=[])
    finally:
        signal.signal(signal.SIGTERM, original_sigterm)
        signal.signal(signal.SIGINT, original_sigint)

    assert shutdown_calls == [True]
