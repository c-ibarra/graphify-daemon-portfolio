"""Shared error types with no home in a single feature module.

`ConfigurationError` started in `graph_query_api/transport.py` (host/API-key
startup validation) but is a generic "daemon refuses to start with this
config" signal, not a transport-specific one -- `logging_config.py` raises
it too. Lives here so neither module has to import the other just to reuse
an exception class.
"""

from __future__ import annotations


class ConfigurationError(Exception):
    """Raised when the daemon's startup configuration is invalid."""
