"""Mandatory API key: startup gating.

See specs/graph-query-api/spec.md "Mandatory API key".
"""

from __future__ import annotations

import pytest

from graphify_daemon.graph_query_api.transport import ConfigurationError, validate_api_key


@pytest.mark.parametrize("api_key", [None, ""])
def test_missing_or_empty_api_key_is_rejected(api_key: str | None) -> None:
    with pytest.raises(ConfigurationError):
        validate_api_key(api_key)


def test_valid_api_key_is_returned_unchanged() -> None:
    assert validate_api_key("secret-key-123") == "secret-key-123"
