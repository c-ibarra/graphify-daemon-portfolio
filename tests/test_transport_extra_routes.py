"""build_app accepts extra routes (health/metrics), gated by the same
API-key middleware as /mcp."""

from __future__ import annotations

from mcp.server import Server
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from graphify_daemon.graph_query_api.transport import build_app


async def _health(_request):
    return JSONResponse({"alive": True, "ready": False})


def test_extra_route_is_reachable_with_the_correct_api_key() -> None:
    app = build_app(
        Server("test"),
        api_key="secret",
        extra_routes=[Route("/health", _health)],
    )
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    assert response.json() == {"alive": True, "ready": False}


def test_extra_route_is_gated_by_the_api_key() -> None:
    app = build_app(
        Server("test"),
        api_key="secret",
        extra_routes=[Route("/health", _health)],
    )
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 401


def test_extra_routes_is_optional() -> None:
    app = build_app(Server("test"), api_key="secret")
    with TestClient(app) as client:
        # A valid key reaches routing -- /health simply doesn't exist when
        # extra_routes wasn't passed, which is the thing under test here
        # (the API-key gate firing first, on any path, is covered above).
        response = client.get("/health", headers={"X-API-Key": "secret"})
    assert response.status_code == 404
