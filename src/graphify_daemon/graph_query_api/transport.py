"""Loopback-only, API-key-gated MCP Streamable HTTP transport scaffold.

See specs/graph-query-api/spec.md "Loopback-only MCP transport" and
"Mandatory API key". Mirrors graphify.serve's own Streamable HTTP
transport pattern (mcp SDK + Starlette + uvicorn + a raw-ASGI API-key
gate) rather than reusing it as-is -- see design.md's Context section
for why graphify-mcp itself isn't reused.
"""

from __future__ import annotations

import contextlib
import hmac
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from typing import Any

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route

from graphify_daemon.errors import ConfigurationError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
ALLOWED_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost"})
MCP_PATH = "/mcp"

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def validate_host(host: str) -> None:
    """Raise ConfigurationError unless `host` is 127.0.0.1 or localhost."""
    if host not in ALLOWED_HOSTS:
        raise ConfigurationError(
            f"GRAPHIFY_DAEMON_HOST must be one of {sorted(ALLOWED_HOSTS)}, got {host!r}. "
            "This daemon never binds to a non-loopback interface."
        )


def validate_api_key(api_key: str | None) -> str:
    """Raise ConfigurationError if `api_key` is unset or empty; otherwise return it."""
    if not api_key:
        raise ConfigurationError(
            "GRAPHIFY_DAEMON_API_KEY must be set to a non-empty value. This daemon never starts unauthenticated."
        )
    return api_key


class _MCPASGIApp:
    """Adapts a `StreamableHTTPSessionManager` to a plain ASGI app."""

    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._manager.handle_request(scope, receive, send)


def _single_header(raw_headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    """Return `name`'s value from `raw_headers` only if it appears exactly once.

    A missing header and a duplicated header are both treated as absent
    (`None`) -- never resolved to "the first" or "the last" value. See
    specs/graph-query-api/spec.md "Duplicate auth header treated as
    absent": a duplicated auth header is a smuggling/spoofing signal in
    itself, not something to tolerate by picking a side.
    """
    matches = [value for key, value in raw_headers if key == name]
    return matches[0] if len(matches) == 1 else None


class _ApiKeyMiddleware:
    """Pure-ASGI API-key gate for the HTTP transport.

    Raw ASGI on purpose, not Starlette's `BaseHTTPMiddleware`: that buffers
    responses and breaks the Streamable HTTP SSE stream. This short-circuits
    with 401 before the request ever reaches the session manager.
    """

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self._expected = api_key.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw_headers = scope.get("headers") or []
        provided = _single_header(raw_headers, b"x-api-key")
        if provided is None:
            authorization = _single_header(raw_headers, b"authorization") or b""
            scheme, _, token = authorization.partition(b" ")
            if scheme.lower() == b"bearer" and token:
                provided = token.strip()
        if provided is None or not hmac.compare_digest(provided, self._expected):
            body = b'{"error": "unauthorized"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def build_app(
    mcp_server: Server,
    *,
    api_key: str,
    port: int = DEFAULT_PORT,
    extra_routes: list[Route] | None = None,
) -> Starlette:
    """Build the Starlette ASGI app: the MCP session manager mounted at /mcp,
    gated by a constant-time API-key check on every request.

    `mcp_server` is an `mcp.server.Server` instance — tool registration
    (task group 8) happens on it before this is called; this module owns
    the transport only, never the tools.

    `extra_routes` (e.g. health/metrics — artifact-lifecycle, task group
    11) are mounted alongside `/mcp`, under the same API-key gate.
    """
    # DNS-rebinding protection checks the raw Host header, which a real
    # client sends port-qualified (`127.0.0.1:8787`) — allowing only the
    # bare hostnames rejects every real request with 421. Mirrors
    # graphify.serve's own _build_http_app, which includes both forms.
    allowed_hosts = set(ALLOWED_HOSTS)
    allowed_hosts |= {f"{host}:{port}" for host in ALLOWED_HOSTS}
    security = TransportSecuritySettings(allowed_hosts=sorted(allowed_hosts))
    manager = StreamableHTTPSessionManager(app=mcp_server, security_settings=security)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    routes = [Route(MCP_PATH, endpoint=_MCPASGIApp(manager)), *(extra_routes or [])]
    return Starlette(
        routes=routes,
        middleware=[Middleware(_ApiKeyMiddleware, api_key=api_key)],
        lifespan=lifespan,
    )


DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 5


def run(
    mcp_server: Server,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    api_key: str | None = None,
    extra_routes: list[Route] | None = None,
    shutdown_timeout: int = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    """Validate host/api_key, build the app, and block serving it via uvicorn.

    Refuses to start (raises ConfigurationError, never starts uvicorn) if
    host or api_key is invalid.

    `log_config=None`: skips uvicorn's own `logging.config.dictConfig` setup
    entirely, so its loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`)
    propagate to whatever the caller already configured on the root logger
    (see `logging_config.configure_logging`) instead of installing their own
    console handlers.

    `timeout_graceful_shutdown=shutdown_timeout`: bounds how long uvicorn
    waits for open connections to close on SIGTERM/SIGINT before forcing
    them shut and returning control to the caller. Left at uvicorn's own
    default (`None`, unbounded) this hangs forever whenever a client holds
    the MCP `subscriptions/listen` stream open (which this daemon
    deliberately keeps alive indefinitely under normal operation) --
    confirmed live against the running daemon, where a real SIGTERM never
    returned control to `run_forever`'s `finally: daemon.shutdown()` at
    all. A bounded wait here is what makes that drain/persist/idempotent-
    close path actually reachable.
    """
    validate_host(host)
    validated_key = validate_api_key(api_key)
    import uvicorn

    app = build_app(mcp_server, api_key=validated_key, port=port, extra_routes=extra_routes)
    uvicorn.run(app, host=host, port=port, log_config=None, timeout_graceful_shutdown=shutdown_timeout)
