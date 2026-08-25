"""Configurable logging for the daemon: log level and log-file rotation.

Env vars are read
in `main()` and resolved here as pure functions, per the "env var reading
deferred to main()" pattern used throughout this codebase.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from graphify_daemon.artifact_lifecycle.security import restrict_to_owner
from graphify_daemon.errors import ConfigurationError

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_MAX_BYTES = 10_485_760
DEFAULT_LOG_BACKUP_COUNT = 5


def resolve_log_level(value: str | None) -> int:
    """Resolve `GRAPHIFY_DAEMON_LOG_LEVEL` to a stdlib logging level int.

    `None` (unset) resolves to `INFO`. Raises `ConfigurationError` for any
    value that isn't a recognized logging level name.
    """
    name = value if value is not None else DEFAULT_LOG_LEVEL
    level = logging.getLevelName(name.upper())
    if not isinstance(level, int):
        raise ConfigurationError(f"GRAPHIFY_DAEMON_LOG_LEVEL must be a recognized logging level name, got {name!r}.")
    return level


def resolve_rotation_settings(max_bytes: str | None, backup_count: str | None) -> tuple[int, int]:
    """Resolve `GRAPHIFY_DAEMON_LOG_MAX_BYTES`/`_BACKUP_COUNT` to
    `(max_bytes, backup_count)`. Both unset resolves to
    `(10_485_760, 5)`.
    """
    resolved_max_bytes = int(max_bytes) if max_bytes is not None else DEFAULT_LOG_MAX_BYTES
    resolved_backup_count = int(backup_count) if backup_count is not None else DEFAULT_LOG_BACKUP_COUNT
    return resolved_max_bytes, resolved_backup_count


def configure_logging(log_file: Path, level: int, max_bytes: int, backup_count: int) -> None:
    """Attach a `RotatingFileHandler` to the root logger so the daemon's
    own logging and uvicorn's (given `uvicorn.run(..., log_config=None)`)
    both propagate into one rotated file.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    restrict_to_owner(log_file.parent)
    handler = logging.handlers.RotatingFileHandler(str(log_file), maxBytes=max_bytes, backupCount=backup_count)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    restrict_to_owner(log_file)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
