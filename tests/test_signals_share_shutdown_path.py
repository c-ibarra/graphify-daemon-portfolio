"""SIGTERM and SIGINT share one shutdown path: the same handler is
registered for both, and that handler only requests shutdown -- it never
compiles or persists anything directly. The actual daemon.shutdown() call
happens exactly once, owned by run_forever's try/finally.

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


def test_signal_handler_only_raises_systemexit_never_touches_the_daemon() -> None:
    handler = daemon_module._build_shutdown_signal_handler()
    with pytest.raises(SystemExit):
        handler(signal.SIGTERM, None)


@pytest.mark.parametrize("triggering_signal", [signal.SIGTERM, signal.SIGINT])
def test_run_forever_registers_one_shared_handler_for_both_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, triggering_signal: signal.Signals
) -> None:
    daemon = _daemon(tmp_path)
    daemon.cold_start()

    shutdown_calls: list[bool] = []
    monkeypatch.setattr(daemon, "shutdown", lambda: shutdown_calls.append(True))

    def fake_transport_run(mcp_server, *, host, port, api_key, extra_routes):
        # Simulate uvicorn's own signal capture: it installs its own
        # handler while running, then restores the original one (the one
        # run_forever just registered) and re-raises the signal once its
        # own graceful shutdown finishes -- see design.md's discussion of
        # uvicorn.Server.capture_signals(). By the time this fake is
        # "running", the real handler is exactly what's registered here.
        handler = signal.getsignal(triggering_signal)
        handler(triggering_signal, None)

    monkeypatch.setattr(daemon_module.transport, "run", fake_transport_run)

    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sigint = signal.getsignal(signal.SIGINT)
    try:
        with pytest.raises(SystemExit):
            daemon_module.run_forever(
                daemon, mcp_server=object(), host="127.0.0.1", port=0, api_key="k", extra_routes=[]
            )
        assert signal.getsignal(signal.SIGTERM) is signal.getsignal(signal.SIGINT)
    finally:
        signal.signal(signal.SIGTERM, original_sigterm)
        signal.signal(signal.SIGINT, original_sigint)

    assert shutdown_calls == [True]
