"""Loopback-only bind check.

See specs/graph-query-api/spec.md "Loopback-only MCP transport".
"""

from __future__ import annotations

import pytest

from graphify_daemon.graph_query_api.transport import ConfigurationError, validate_host


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_hosts_are_accepted(host: str) -> None:
    validate_host(host)  # must not raise


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "::", "example.com"])
def test_non_loopback_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ConfigurationError):
        validate_host(host)
