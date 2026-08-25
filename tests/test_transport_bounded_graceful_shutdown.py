"""transport.run bounds uvicorn's graceful-shutdown wait, instead of
leaving it unbounded.

Found live against the real daemon: uvicorn's own graceful shutdown waits
for every open connection to close before it lets control return to this
daemon's SIGTERM/SIGINT handler -- and the MCP `subscriptions/listen`
stream this daemon deliberately keeps open for modern clients (Antigravity
et al.) never closes on its own. Without a bound, `uvicorn.run()` (called
with `timeout_graceful_shutdown=None`, its default) hangs forever whenever
a client is connected, so `run_forever`'s `finally: daemon.shutdown()`
never runs -- the entire drain/persist/idempotent-close path built for
Phase 2 of harden-daemon-lifecycle-safety silently never executes.

See docs/adr -- this is a follow-up fix to that change, found via live
verification against the running production daemon after restarting it.
"""

from __future__ import annotations

import pytest
from mcp.server import Server

from graphify_daemon.graph_query_api.transport import run


def test_run_passes_a_bounded_graceful_shutdown_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_uvicorn_run(_app: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("uvicorn.run", _fake_uvicorn_run)

    run(Server("test"), api_key="secret")

    assert "timeout_graceful_shutdown" in captured
    timeout = captured["timeout_graceful_shutdown"]
    assert timeout is not None, "unbounded (None) is exactly the hang this test guards against"
    assert 0 < timeout <= 30
