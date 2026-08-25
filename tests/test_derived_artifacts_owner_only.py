"""Every derived artifact -- cache, index, graph JSON, knowledge Markdown,
and the log file -- ends up owner-only on POSIX after a real cold-start +
batch-compile + slow-cadence cycle.

See specs/artifact-lifecycle/spec.md "Owner-only permissions on
derived-artifact files and directories".
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from graphify_daemon import logging_config
from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission bits")
def test_all_derived_artifacts_end_up_owner_only(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    daemon = Daemon(vault_root, paths, slow_cadence_change_threshold=1)
    daemon.cold_start()

    note = vault_root / "note.md"
    note.write_text("# Note\n")
    batch = Batch(changes=(FileChange(path=note, kind=ChangeKind.CREATED),))
    daemon._compile_batch(batch)  # threshold=1 -> slow cadence fires inline

    log_file = tmp_path / "logs" / "daemon.log"
    logging_config.configure_logging(log_file, logging.INFO, 10_485_760, 5)

    artifacts = [paths.vault_index_db, paths.graph_json, paths.knowledge_md, paths.graph_cache_json, log_file]
    for path in artifacts:
        assert path.exists(), f"{path} was never created"
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"{path} had mode {oct(mode)}, expected 0o600"
