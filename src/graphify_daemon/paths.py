"""This daemon's own output directory, strictly separate from the legacy
watcher's `graphify-out/` (a sibling repo,
~/projects/obsidianKnowledgeCurator/graphify-out/) for the entire
migration parallel-run window (task group 12).

See design.md's Risks/Trade-offs: "Two writers on one `graph.json` — the
single most severe failure mode during migration (lost updates). Mitigated
by keeping the legacy watcher and this daemon on strictly separate output
paths for the entire parallel-run window."
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_OUTPUT_DIR_NAME = "out"


class DaemonPaths:
    """Resolves this daemon's derived-artifact paths under one output directory."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    @property
    def vault_index_db(self) -> Path:
        return self.output_dir / "vault_index.db"

    @property
    def graph_json(self) -> Path:
        return self.output_dir / "graph.json"

    @property
    def knowledge_md(self) -> Path:
        return self.output_dir / "KNOWLEDGE.md"

    @property
    def graph_cache_json(self) -> Path:
        return self.output_dir / "graph_cache.json"
