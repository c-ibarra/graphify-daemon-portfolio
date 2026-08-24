"""run() refuses to start uvicorn on invalid host/api_key configuration."""

from __future__ import annotations

import pytest
from mcp.server import Server

from graphify_daemon.graph_query_api.transport import ConfigurationError, run


def test_run_refuses_non_loopback_host_without_starting_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("uvicorn.run must not be called when config is invalid")

    monkeypatch.setattr("uvicorn.run", _forbidden)

    with pytest.raises(ConfigurationError):
        run(Server("test"), host="0.0.0.0", api_key="secret")


def test_run_refuses_missing_api_key_without_starting_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("uvicorn.run must not be called when config is invalid")

    monkeypatch.setattr("uvicorn.run", _forbidden)

    with pytest.raises(ConfigurationError):
        run(Server("test"), host="127.0.0.1", api_key=None)
