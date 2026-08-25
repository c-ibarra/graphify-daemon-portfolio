"""Deterministic vault-file extraction and its in-RAM cache.

See specs/vault-compiler/spec.md "Deterministic, non-LLM extraction",
"Source file provenance", "In-RAM extraction cache",
"Extraction cache disk persistence cadence", and
"Per-file extraction failure isolation".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from graphify.extract import extract_python
from graphify.extractors.markdown import extract_markdown

from graphify_daemon.artifact_lifecycle.security import restrict_to_owner
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind
from graphify_daemon.vault_compiler.exclusions import is_excluded, sanitize_log_text

if TYPE_CHECKING:
    # Deferred to avoid a runtime cycle: artifact_lifecycle.metrics imports
    # vault_compiler.snapshot, which imports this module.
    from graphify_daemon.artifact_lifecycle.metrics import Metrics

logger = logging.getLogger(__name__)

_EXTRACTORS = {
    ".md": extract_markdown,
    ".py": extract_python,
}


def extract_file(path: Path, vault_root: Path) -> dict[str, Any]:
    """Extract nodes/edges from one vault file, `source_file` relative to `vault_root`.

    Dispatches to `graphify.extractors.markdown.extract_markdown` for `.md`
    and `graphify.extract.extract_python` for `.py`. Deterministic — no LLM
    call, ever.
    """
    extractor = _EXTRACTORS[path.suffix]
    result = cast("dict[str, Any]", extractor(path))
    relative = str(path.relative_to(vault_root))
    for node in result.get("nodes", []):
        node["source_file"] = relative
    for edge in result.get("edges", []):
        edge["source_file"] = relative
    return result


def extract_file_with_failure_isolation(
    path: Path,
    vault_root: Path,
    relative: Path,
    *,
    log_prefix: str,
    metrics: Metrics | None,
) -> dict[str, Any] | None:
    """Extract one file, isolating both failure modes `extract_file` can hit.

    Shared by `extract_batch` and `cold_start` (artifact-lifecycle), which
    otherwise duplicate this same try/except + `"error"`-check block. On
    either failure mode — `extract_file` raising, or the underlying
    graphify extractor returning an `"error"` key — logs
    `"{log_prefix} for {relative}: {reason}"`, increments the caller's
    `extraction_errors` metric, and returns `None`. Never raises. The
    caller decides what a successful result means for its own cache/mtime
    bookkeeping; this function only isolates the extraction step itself.

    The underlying extractor's own error text can embed the full
    absolute path it tried to open (e.g. a raw `FileNotFoundError`
    message) — `reason` is sanitized via `sanitize_log_text` before
    logging, so `vault_root`'s absolute path never reaches a log line
    through that path. See specs/artifact-lifecycle/spec.md "No
    confidential values in logs".
    """
    try:
        result = extract_file(path, vault_root)
    except Exception as exc:  # noqa: BLE001 - isolated per-file, reported not raised
        logger.warning("%s for %s: %s", log_prefix, relative, sanitize_log_text(str(exc), vault_root))
        if metrics is not None:
            metrics.increment("extraction_errors")
        return None
    if "error" in result:
        logger.warning("%s for %s: %s", log_prefix, relative, sanitize_log_text(str(result["error"]), vault_root))
        if metrics is not None:
            metrics.increment("extraction_errors")
        return None
    return result


class ExtractionCache:
    """In-RAM cache of the last extraction result per vault file, keyed by
    path relative to the vault root.

    `get`/`set` never touch disk — see "In-RAM extraction cache". `save`/`load`
    are the only disk-touching operations, called externally on the slow
    cadence and at shutdown (artifact-lifecycle, task groups 10-11), never
    from `get`/`set` themselves.
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._mtimes: dict[str, float] = {}

    def get(self, relative_path: Path) -> dict[str, Any] | None:
        return self._entries.get(str(relative_path))

    def set(self, relative_path: Path, result: dict[str, Any], *, mtime: float | None = None) -> None:
        key = str(relative_path)
        self._entries[key] = result
        if mtime is not None:
            self._mtimes[key] = mtime

    def mtime(self, relative_path: Path) -> float | None:
        """The mtime recorded when this file was last extracted, or None.

        Used by cold-start reconciliation (artifact-lifecycle, task group
        11) to decide whether a file needs re-extraction.
        """
        return self._mtimes.get(str(relative_path))

    def delete(self, relative_path: Path) -> None:
        """Drop a file's cached result and mtime, e.g. because it no
        longer exists on disk (cold-start reconciliation)."""
        key = str(relative_path)
        self._entries.pop(key, None)
        self._mtimes.pop(key, None)

    def entries(self) -> dict[Path, dict[str, Any]]:
        """A snapshot copy of every cached extraction result, keyed by relative path.

        Used to merge the full corpus into one graph (see `snapshot.build_graph`)
        — a batch's changed files alone aren't enough to rebuild the whole graph.
        """
        return {Path(key): value for key, value in self._entries.items()}

    def save(self, cache_path: Path) -> None:
        cache_path.write_text(json.dumps({"entries": self._entries, "mtimes": self._mtimes}))
        restrict_to_owner(cache_path)

    def load(self, cache_path: Path) -> None:
        data = json.loads(cache_path.read_text())
        self._entries = data["entries"]
        self._mtimes = data["mtimes"]


def extract_batch(
    batch: Batch,
    vault_root: Path,
    cache: ExtractionCache,
    *,
    metrics: Metrics | None = None,
    nested_repo_names: frozenset[str] = frozenset(),
) -> dict[Path, dict[str, Any]]:
    """Extract every file changed in `batch`, isolating per-file failures.

    A file whose extraction fails — either `extract_file` raising, or the
    underlying graphify extractor returning an `"error"` key (its actual
    failure mode: `extract_markdown`/`extract_python` never raise, they
    catch internally and report `error` in the result — a deleted file
    surfaces this way) — is logged and skipped: its prior cache entry (if
    any) is left unchanged, and the rest of the batch still compiles. Never
    aborts the batch. Returns successfully-extracted results keyed by path
    relative to `vault_root`.

    `RENAMED` changes are processed as one logical unit (see
    specs/vault-compiler/spec.md "Rename carries source and destination as
    one logical unit"): `previous_path`'s cache entry is removed first,
    then the destination is extracted exactly once via the same path as a
    `CREATED`/`MODIFIED` change — unless the destination itself is
    excluded (`nested_repo_names` mirrors the watcher's own exclusion
    config), in which case the rename is treated as a pure deletion of
    `previous_path`, with no extraction attempted.
    """
    results: dict[Path, dict[str, Any]] = {}
    for change in batch.changes:
        relative = change.path.relative_to(vault_root)
        if change.kind is ChangeKind.DELETED:
            cache.delete(relative)
            continue
        if change.kind is ChangeKind.RENAMED:
            assert change.previous_path is not None  # enforced by FileChange.__post_init__
            cache.delete(change.previous_path.relative_to(vault_root))
            if is_excluded(change.path, vault_root, nested_repo_names=nested_repo_names):
                continue
        result = extract_file_with_failure_isolation(
            change.path, vault_root, relative, log_prefix="Extraction failed", metrics=metrics
        )
        if result is None:
            continue
        try:
            mtime = change.path.stat().st_mtime
        except FileNotFoundError:
            mtime = None
        cache.set(relative, result, mtime=mtime)
        results[relative] = result
    return results
