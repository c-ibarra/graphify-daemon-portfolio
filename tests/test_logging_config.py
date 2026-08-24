"""logging_config.py: configurable log level, rotation thresholds, and a
consolidated rotating log file for the daemon + uvicorn.

See specs/daemon-logging/spec.md.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import pytest

from graphify_daemon import logging_config
from graphify_daemon.errors import ConfigurationError
from graphify_daemon.logging_config import DEFAULT_LOG_MAX_BYTES


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """configure_logging mutates the root logger's handlers. Save/restore
    around every test so tests don't leak handlers into each other."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


def test_log_level_unset_defaults_to_info() -> None:
    assert logging_config.resolve_log_level(None) == logging.INFO


def test_log_level_explicit_valid_value_is_applied() -> None:
    assert logging_config.resolve_log_level("DEBUG") == logging.DEBUG


def test_log_level_invalid_value_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        logging_config.resolve_log_level("VERBOSE")


def test_rotation_settings_unset_use_defaults() -> None:
    assert logging_config.resolve_rotation_settings(None, None) == (10_485_760, 5)


def test_rotation_settings_explicit_values_are_applied() -> None:
    assert logging_config.resolve_rotation_settings("1000", "2") == (1000, 2)


def test_configure_logging_attaches_rotating_file_handler_to_root(tmp_path: Path) -> None:
    log_file = tmp_path / "daemon.log"

    logging_config.configure_logging(log_file, logging.DEBUG, max_bytes=1000, backup_count=3)

    root = logging.getLogger()
    handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1
    handler = handlers[0]
    assert Path(handler.baseFilename) == log_file
    assert handler.maxBytes == 1000
    assert handler.backupCount == 3
    assert root.level == logging.DEBUG


def test_configure_logging_captures_app_and_uvicorn_access_logs_in_one_file(tmp_path: Path) -> None:
    log_file = tmp_path / "daemon.log"
    logging_config.configure_logging(log_file, logging.INFO, max_bytes=DEFAULT_LOG_MAX_BYTES, backup_count=5)

    logging.getLogger("graphify_daemon.daemon").info("app message: batch compiled")
    logging.getLogger("uvicorn.access").info('access message: "GET /health HTTP/1.1" 200 OK')

    for handler in logging.getLogger().handlers:
        handler.flush()
    contents = log_file.read_text()
    assert "app message: batch compiled" in contents
    assert 'access message: "GET /health HTTP/1.1" 200 OK' in contents


def test_configure_logging_rotates_past_max_bytes(tmp_path: Path) -> None:
    log_file = tmp_path / "daemon.log"
    logging_config.configure_logging(log_file, logging.INFO, max_bytes=200, backup_count=2)

    logger = logging.getLogger("graphify_daemon.daemon")
    for i in range(50):
        logger.info("padding line to exceed the rotation threshold %d", i)

    assert log_file.exists()
    assert (tmp_path / "daemon.log.1").exists()
