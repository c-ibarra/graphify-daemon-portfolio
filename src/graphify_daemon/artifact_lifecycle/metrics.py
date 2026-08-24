"""Generic, thread-safe telemetry primitives + the metrics endpoint payload.

See specs/artifact-lifecycle/spec.md "Operational metrics".

`Metrics` is deliberately generic (named counters/gauges/latencies/
event-times) rather than one bespoke method per data point, so each
already-shipped module that needs to report something (extract_batch's
error count, VaultWatcher's queue depth, run_clustering_cycle's last
success, tools.py's query latency) only needs a one-line hook, injected
as an optional keyword-only parameter — same low-blast-radius pattern as
`ExtractionCache.set`'s new `mtime` parameter in this same task group.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from graphify_daemon.graph_query_api.query_cache import QueryCache
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder

DEFAULT_LATENCY_WINDOW = 1000


class Metrics:
    """A small, generic, thread-safe telemetry registry."""

    def __init__(self, *, latency_window: int = DEFAULT_LATENCY_WINDOW) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._event_times: dict[str, float] = {}
        self._latencies: dict[str, deque[float]] = {}
        self._latency_window = latency_window

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def counter(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def gauge(self, name: str) -> float | None:
        with self._lock:
            return self._gauges.get(name)

    def record_event_time(self, name: str) -> None:
        with self._lock:
            self._event_times[name] = time.monotonic()

    def seconds_since_event(self, name: str) -> float | None:
        with self._lock:
            at = self._event_times.get(name)
        return None if at is None else time.monotonic() - at

    def record_latency(self, name: str, seconds: float) -> None:
        with self._lock:
            window = self._latencies.setdefault(name, deque(maxlen=self._latency_window))
            window.append(seconds)

    def latency_percentiles(self, name: str) -> dict[str, float]:
        with self._lock:
            samples = sorted(self._latencies.get(name, ()))
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        def _pct(p: float) -> float:
            index = min(len(samples) - 1, int(len(samples) * p))
            return samples[index]

        return {"p50": _pct(0.50), "p95": _pct(0.95), "p99": _pct(0.99)}


def _rss_bytes() -> int:
    """Current (not peak) resident set size, in bytes.

    `resource.getrusage(...).ru_maxrss` is the high-water mark since
    process start, not "current" — it never decreases even after the
    resident graph shrinks, contradicting the spec's "current values"
    scenario. `ps -o rss=` reports live RSS (in KB) on both Darwin and
    Linux, so this shells out rather than using the stdlib-only peak.
    """
    output = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(os.getpid())],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(output.strip()) * 1024


_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_git_revision(*, cwd: Path | None = None) -> tuple[str | None, bool | None]:
    """Identify the git commit (and dirty/clean state) this process was started from.

    See specs/artifact-lifecycle/spec.md "Operational metrics" (git_sha/
    git_dirty scenarios). Tries, in order:

    1. `GRAPHIFY_DAEMON_GIT_SHA` / `GRAPHIFY_DAEMON_GIT_DIRTY` env vars —
       meant to be set once by the launch wrapper (`.daemon-run/run.sh`),
       so the common (launchd-managed) case never shells out to `git` at
       all.
    2. A live `git rev-parse HEAD` / dirty-check against `cwd` (defaults
       to this repo's root) — covers running the daemon directly in
       development, without the wrapper.

    Degrades to `(None, None)` if neither resolves (no env vars, and
    either no `git` on `PATH` or `cwd` isn't a git checkout) — never
    raises, never blocks startup. This is diagnostic data, not something
    the daemon's operation depends on.
    """
    env_sha = os.environ.get("GRAPHIFY_DAEMON_GIT_SHA")
    if env_sha:
        env_dirty = os.environ.get("GRAPHIFY_DAEMON_GIT_DIRTY", "").strip().lower()
        return env_sha, env_dirty in ("1", "true")

    repo_root = cwd if cwd is not None else _REPO_ROOT
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except Exception:  # noqa: BLE001 - diagnostic data only, degrade to (None, None)
        return None, None

    return sha, bool(status.strip())


def collect_metrics(metrics: Metrics, holder: SnapshotHolder, query_cache: QueryCache) -> dict[str, Any]:
    """Assemble the metrics endpoint payload: queue depth, snapshot
    version, LRU cache hit rate, query latency (p50/p95/p99), time since
    last successful clustering, RSS, and extraction error count.
    """
    snapshot = holder.current()
    git_sha, git_dirty = resolve_git_revision()
    return {
        "queue_depth": metrics.gauge("queue_depth") or 0,
        "snapshot_version": snapshot.version if snapshot is not None else None,
        "lru_cache_hit_rate": query_cache.hit_rate(),
        "query_latency_seconds": metrics.latency_percentiles("query"),
        "seconds_since_last_clustering": metrics.seconds_since_event("clustering_success"),
        "rss_bytes": _rss_bytes(),
        "extraction_error_count": metrics.counter("extraction_errors"),
        "git_sha": git_sha,
        "git_dirty": git_dirty,
    }
