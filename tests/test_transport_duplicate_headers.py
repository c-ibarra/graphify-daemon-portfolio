"""A duplicated auth header is treated as absent, never resolved to one
of its values -- even if one of the duplicates is the correct key.

See specs/graph-query-api/spec.md "Duplicate auth header treated as
absent".
"""

from __future__ import annotations

from mcp.server import Server
from starlette.testclient import TestClient

from graphify_daemon.graph_query_api.transport import build_app


def _app():
    server = Server("graphify-daemon-test")
    return build_app(server, api_key="correct-key")


def test_duplicated_api_key_correct_value_first_is_rejected() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers=[("X-API-Key", "correct-key"), ("X-API-Key", "wrong-key")],
        )
    assert response.status_code == 401


def test_duplicated_api_key_correct_value_second_is_rejected() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers=[("X-API-Key", "wrong-key"), ("X-API-Key", "correct-key")],
        )
    assert response.status_code == 401


def test_duplicated_authorization_correct_value_first_is_rejected() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers=[("Authorization", "Bearer correct-key"), ("Authorization", "Bearer wrong-key")],
        )
    assert response.status_code == 401


def test_duplicated_authorization_correct_value_second_is_rejected() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers=[("Authorization", "Bearer wrong-key"), ("Authorization", "Bearer correct-key")],
        )
    assert response.status_code == 401
