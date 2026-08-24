"""build_app(): per-request API-key verification on the ASGI transport.

See specs/graph-query-api/spec.md "Mandatory API key" (per-request scenario)
and design.md's Context section on why graphify-mcp isn't reused as-is.
"""

from __future__ import annotations

from mcp.server import Server
from starlette.testclient import TestClient

from graphify_daemon.graph_query_api.transport import build_app


def _app():
    server = Server("graphify-daemon-test")
    return build_app(server, api_key="correct-key")


def test_request_without_api_key_is_rejected_before_reaching_mcp() -> None:
    with TestClient(_app()) as client:
        response = client.post("/mcp", json={})
    assert response.status_code == 401


def test_request_with_wrong_api_key_is_rejected() -> None:
    with TestClient(_app()) as client:
        response = client.post("/mcp", json={}, headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_request_with_correct_api_key_reaches_the_mcp_session_manager() -> None:
    with TestClient(_app()) as client:
        response = client.post("/mcp", json={}, headers={"X-API-Key": "correct-key"})
    # Reaching the session manager means the API-key gate passed -- the
    # manager itself rejects a malformed MCP body, but not with 401.
    assert response.status_code != 401


def test_bearer_token_is_also_accepted() -> None:
    with TestClient(_app()) as client:
        response = client.post("/mcp", json={}, headers={"Authorization": "Bearer correct-key"})
    assert response.status_code != 401
