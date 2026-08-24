"""build_app's DNS-rebinding protection must accept the real Host header
a client sends (host:port), not just the bare host.

Found via a live smoke test (not caught by the existing TestClient-based
tests, whose default base_url doesn't include a port): curl against a
running daemon on 127.0.0.1:8799 sent `Host: 127.0.0.1:8799` and got
421 Misdirected Request, because build_app's TransportSecuritySettings
only allowed the bare "127.0.0.1"/"localhost", never the port-qualified
form -- unlike graphify.serve's own _build_http_app, which explicitly
includes both.
"""

from __future__ import annotations

from mcp.server import Server
from starlette.testclient import TestClient

from graphify_daemon.graph_query_api.transport import build_app


def test_request_with_port_qualified_host_header_is_accepted() -> None:
    app = build_app(Server("test"), api_key="secret", port=8799)
    with TestClient(app, base_url="http://127.0.0.1:8799") as client:
        response = client.post("/mcp", json={}, headers={"X-API-Key": "secret"})
    assert response.status_code != 421


def test_request_with_spoofed_host_header_is_rejected() -> None:
    """Exercises the real wiring end-to-end (the full ASGI app, a real
    request, TransportSecuritySettings as build_app actually constructs
    it) -- not just validate_host in isolation
    (test_transport_host_validation.py)."""
    app = build_app(Server("test"), api_key="secret", port=8799)
    with TestClient(app, base_url="http://evil.example.com:8799") as client:
        response = client.post("/mcp", json={}, headers={"X-API-Key": "secret"})
    assert response.status_code == 421
