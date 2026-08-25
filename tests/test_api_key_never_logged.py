"""The configured API key never appears in log output, at any level,
whether a request succeeds or is rejected.

See specs/artifact-lifecycle/spec.md "No confidential values in logs".
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from mcp.server import Server
from starlette.testclient import TestClient

from graphify_daemon import logging_config
from graphify_daemon.graph_query_api.transport import build_app

API_KEY = "super-secret-key-value-xyz"


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


def test_api_key_never_appears_in_log_output(tmp_path: Path) -> None:
    log_file = tmp_path / "daemon.log"
    logging_config.configure_logging(log_file, logging.DEBUG, 10_485_760, 5)

    server = Server("graphify-daemon-test")
    app = build_app(server, api_key=API_KEY)

    with TestClient(app) as client:
        client.post("/mcp", json={}, headers={"X-API-Key": API_KEY})  # authorized
        client.post("/mcp", json={}, headers={"X-API-Key": "wrong-key"})  # rejected

    for handler in logging.getLogger().handlers:
        handler.flush()
    contents = log_file.read_text()
    assert API_KEY not in contents
