"""Recovery exclusively by vault rebuild -- no WAL, replay, or checkpoint mechanism.

See specs/artifact-lifecycle/spec.md "Recovery exclusively by vault rebuild".
"""

from __future__ import annotations

import re
from pathlib import Path

from graphify_daemon.artifact_lifecycle.cold_start import cold_start
from graphify_daemon.vault_compiler.extraction import ExtractionCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"

# Allowed: vault_index.py's own `PRAGMA journal_mode=WAL` (SQLite's transparent
# internal journaling, chosen deliberately for read-concurrency -- not a
# daemon-level durability log we built). Forbidden: anything suggesting this
# daemon replays or checkpoints its own compilation state to survive a crash.
FORBIDDEN_PATTERNS = [
    re.compile(r"\breplay\b", re.IGNORECASE),
    re.compile(r"\bcheckpoint\b", re.IGNORECASE),
    re.compile(r"write.ahead.log", re.IGNORECASE),
]
ALLOWED_FILE = "vault_index.py"


def test_no_daemon_level_durability_log_code_exists() -> None:
    offenders = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name == ALLOWED_FILE:
            continue
        text = path.read_text()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                offenders.append((str(path.relative_to(SRC_ROOT.parent)), pattern.pattern))
    assert not offenders, (
        f"Found durability-log-like code outside {ALLOWED_FILE}: {offenders}. "
        "Recovery must rely exclusively on rebuilding from the vault."
    )


def test_recovery_from_an_empty_cache_matches_a_fresh_build(tmp_path: Path) -> None:
    """Simulates the worst case: a SIGKILL before anything was ever
    persisted. Cold-start from a totally empty cache must still fully
    reconstruct the graph from the vault alone."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "a.md").write_text("# A\n")
    (vault_root / "b.md").write_text("# B\n")
    (vault_root / "c.md").write_text("# C\n")

    empty_cache = ExtractionCache()
    holder = SnapshotHolder()
    recovered = cold_start(vault_root, empty_cache, holder)

    recovered_sources = {d["source_file"] for _, d in recovered.graph.nodes(data=True)}
    assert recovered_sources == {"a.md", "b.md", "c.md"}

    # cold_start itself creates no on-disk artifact of any kind (no daemon-
    # level log survives, because none is ever written in the first place).
    assert list(vault_root.rglob("*.wal")) == []
    assert list(vault_root.rglob("*-wal")) == []
    assert list(vault_root.rglob("*.replay")) == []
