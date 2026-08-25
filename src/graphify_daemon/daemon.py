"""The daemon's actual entrypoint: wires every already-built component
into one running process.

See design.md and every task group's deferred "actual process-level
wiring belongs to a future entrypoint" notes (task groups 7 and 11) --
this is that entrypoint. `Daemon` is pure composition: every method calls
already-independently-tested pieces from earlier task groups. `main()`
is the only place in the codebase that reads `os.environ` for runtime
config, per the "pure functions, env var reading deferred" pattern used
throughout (host/api_key validation in task group 7, etc).
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from collections.abc import Awaitable, Callable
from enum import Enum
from pathlib import Path

from mcp.server import Server
from mcp.server.subscriptions import InMemorySubscriptionBus, ListenHandler
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from graphify_daemon import logging_config
from graphify_daemon.artifact_lifecycle.cadence import run_slow_cadence_cycle
from graphify_daemon.artifact_lifecycle.cold_start import cold_start as run_cold_start
from graphify_daemon.artifact_lifecycle.graph_artifacts import (
    write_graph_json,
    write_knowledge_md,
)
from graphify_daemon.artifact_lifecycle.health import health_check
from graphify_daemon.artifact_lifecycle.metrics import Metrics, collect_metrics
from graphify_daemon.artifact_lifecycle.security import restrict_to_owner
from graphify_daemon.artifact_lifecycle.shutdown import ShutdownCoordinator
from graphify_daemon.artifact_lifecycle.vault_index import (
    connect as connect_vault_index,
)
from graphify_daemon.artifact_lifecycle.vault_index import init_schema, sync_batch
from graphify_daemon.graph_query_api import transport
from graphify_daemon.graph_query_api.query_cache import DEFAULT_LRU_SIZE, QueryCache
from graphify_daemon.graph_query_api.tools import build_handlers
from graphify_daemon.paths import DEFAULT_OUTPUT_DIR_NAME, DaemonPaths
from graphify_daemon.vault_compiler.batching import (
    DEFAULT_PENDING_WARN_THRESHOLD,
    Batch,
    BatchConsumer,
    VaultWatcher,
)
from graphify_daemon.vault_compiler.extraction import ExtractionCache, extract_batch
from graphify_daemon.vault_compiler.slow_cadence import SlowCadenceTracker
from graphify_daemon.vault_compiler.snapshot import SnapshotHolder, build_graph

logger = logging.getLogger(__name__)


class DaemonState(Enum):
    """The daemon's lifecycle state, transitioning only forward:
    RUNNING -> STOPPING -> STOPPED. See
    specs/artifact-lifecycle/spec.md "Explicit lifecycle states gate
    event acceptance" and "Shutdown is idempotent".
    """

    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class Daemon:
    """Owns every long-lived component and the batch-processing pipeline.

    Constructed with everything already resolved (vault root, output
    paths, tuning knobs) — reading environment variables happens only in
    `main()`, keeping this class testable without env-var mocking.
    """

    def __init__(
        self,
        vault_root: Path,
        paths: DaemonPaths,
        *,
        nested_repo_names: frozenset[str] = frozenset(),
        debounce_ms: int = 300,
        slow_cadence_quiet_seconds: float = 60.0,
        slow_cadence_change_threshold: int = 25,
        lru_size: int = DEFAULT_LRU_SIZE,
        pending_warn_threshold: int = DEFAULT_PENDING_WARN_THRESHOLD,
    ) -> None:
        self.vault_root = vault_root
        self.paths = paths
        self.nested_repo_names = nested_repo_names
        self._state = DaemonState.RUNNING
        self._shutdown_lock = threading.Lock()

        self.holder = SnapshotHolder()
        self.cache = ExtractionCache()
        self.metrics = Metrics()
        self.query_cache = QueryCache(maxsize=lru_size)
        self.tracker = SlowCadenceTracker(
            quiet_seconds=slow_cadence_quiet_seconds,
            change_threshold=slow_cadence_change_threshold,
        )
        self.coordinator = ShutdownCoordinator()

        self.paths.output_dir.mkdir(parents=True, exist_ok=True)
        restrict_to_owner(self.paths.output_dir)
        self.vault_index_conn = connect_vault_index(self.paths.vault_index_db)
        init_schema(self.vault_index_conn)

        self._batch_consumer = BatchConsumer(self._compile_batch)
        self.watcher = VaultWatcher(
            vault_root,
            self._on_batch,
            debounce_ms=debounce_ms,
            nested_repo_names=nested_repo_names,
            metrics=self.metrics,
            pending_warn_threshold=pending_warn_threshold,
        )

    def cold_start(self) -> None:
        """Load `graph_cache.json` if present, reconcile against the
        vault, publish the initial snapshot. Call once before `start()`.
        """
        if self.paths.graph_cache_json.exists():
            self.cache.load(self.paths.graph_cache_json)
        run_cold_start(
            self.vault_root,
            self.cache,
            self.holder,
            nested_repo_names=self.nested_repo_names,
            metrics=self.metrics,
        )

    def start(self) -> None:
        self.watcher.start()

    def _on_batch(self, batch: Batch) -> None:
        self.coordinator.run_batch(lambda: self._batch_consumer.consume(batch))

    def _compile_batch(self, batch: Batch) -> None:
        extract_batch(
            batch, self.vault_root, self.cache, metrics=self.metrics, nested_repo_names=self.nested_repo_names
        )
        sync_batch(self.vault_index_conn, batch, self.vault_root, self.cache, nested_repo_names=self.nested_repo_names)

        graph = build_graph(self.cache)
        current = self.holder.current()
        community_map = current.community_map if current is not None else {}
        self.holder.publish(graph, community_map)

        self.tracker.record_batch(len(batch.changes))
        triggered = run_slow_cadence_cycle(
            self.tracker,
            self.holder,
            self.cache,
            graph_json_path=self.paths.graph_json,
            knowledge_md_path=self.paths.knowledge_md,
            graph_cache_path=self.paths.graph_cache_json,
            metrics=self.metrics,
        )
        if triggered:
            # The change-count threshold already ran the cycle inline --
            # cancel any timer from a prior batch so it can't also fire
            # and run a second, duplicate cycle later.
            self.watcher.cancel_idle()
        else:
            self.watcher.schedule_idle(self._on_idle_cadence, self.tracker.quiet_seconds)

    def _on_idle_cadence(self) -> None:
        """Idle-timer callback: run the slow-cadence cycle under the same
        writer lock as a regular batch, so it never interleaves with one.
        Runs at most once per scheduled idle timer -- not rescheduled
        after firing, since the next `schedule_idle` call only comes from
        a subsequent real batch. See specs/vault-compiler/spec.md
        "Slow-cadence idle trigger fires without a subsequent batch".
        """
        self.coordinator.run_batch(self._run_slow_cadence_cycle)

    def _run_slow_cadence_cycle(self) -> None:
        run_slow_cadence_cycle(
            self.tracker,
            self.holder,
            self.cache,
            graph_json_path=self.paths.graph_json,
            knowledge_md_path=self.paths.knowledge_md,
            graph_cache_path=self.paths.graph_cache_json,
            metrics=self.metrics,
        )

    def build_mcp_server(self) -> Server:
        """The `mcp.server.Server` exposing this daemon's seven tools —
        hand this to `graph_query_api.transport.run`.

        `on_subscriptions_listen`: the tool list never changes here (see
        `listChanged: false` in this server's capabilities), so nothing is
        ever published on the bus -- but registering the handler still lets
        a client's `subscriptions/listen` request get acknowledged and its
        stream held open, instead of 404ing with `-32601 Method not found`.
        A real client (observed: Antigravity) that requires this handshake
        to succeed before it will use any tools would otherwise fail
        outright, even though this server declares no capability that
        would make the listen stream itself useful.
        """
        on_list_tools, on_call_tool = build_handlers(
            self.holder.current,
            metrics=self.metrics,
            query_cache=self.query_cache,
        )
        return Server(
            "graphify-daemon",
            on_list_tools=on_list_tools,
            on_call_tool=on_call_tool,
            on_subscriptions_listen=ListenHandler(InMemorySubscriptionBus()),
        )

    def health_route(self) -> Callable[[Request], Awaitable[JSONResponse]]:
        async def _health(_request: Request) -> JSONResponse:
            return JSONResponse(health_check(self.holder))

        return _health

    def metrics_route(self) -> Callable[[Request], Awaitable[JSONResponse]]:
        async def _metrics(_request: Request) -> JSONResponse:
            return JSONResponse(collect_metrics(self.metrics, self.holder, self.query_cache))

        return _metrics

    def persist_on_shutdown(self) -> None:
        """Unconditional final flush — SIGTERM's "persist artifacts", not
        gated by the slow-cadence tracker (a one-time drain, not a
        routine cycle)."""
        current = self.holder.current()
        if current is not None:
            write_graph_json(current, self.paths.graph_json)
            write_knowledge_md(current, self.paths.knowledge_md)
        self.cache.save(self.paths.graph_cache_json)
        self.vault_index_conn.close()

    def shutdown(self) -> None:
        """Stop accepting new events, drain and compile whatever's still
        pending in the debounce window, wait for any in-flight batch,
        then persist final artifacts and close resources — exactly once,
        safely callable more than once.

        See specs/artifact-lifecycle/spec.md "Shutdown drains the
        pending debounce batch before persisting", "Shutdown is
        idempotent", and "Uniform cleanup across SIGTERM, SIGINT, and
        normal exit".
        """
        with self._shutdown_lock:
            if self._state is not DaemonState.RUNNING:
                return
            self._state = DaemonState.STOPPING

        self.watcher.reject_new_events()
        pending = self.watcher.drain_pending_batch()
        if pending is not None:
            self.coordinator.run_batch(lambda: self._batch_consumer.consume(pending))

        self.watcher.stop()
        self.coordinator.shutdown(self.persist_on_shutdown)

        with self._shutdown_lock:
            self._state = DaemonState.STOPPED


def _build_shutdown_signal_handler() -> Callable[[int, object], None]:
    """Build a signal handler that only requests shutdown: logs which
    signal arrived and raises `SystemExit(0)` to unwind into
    `run_forever`'s owning `try`/`finally`, which is the only place that
    calls `daemon.shutdown()`. Never touches the daemon directly — per
    design.md, heavy drain/compile/persist work must not run inside a
    signal handler. The same handler is registered for both `SIGTERM`
    and `SIGINT` (see `run_forever`), so both signals share this one
    path. See specs/artifact-lifecycle/spec.md "Uniform cleanup across
    SIGTERM, SIGINT, and normal exit".
    """

    def _handle_shutdown_signal(signum: int, _frame: object) -> None:
        logger.info("Shutdown requested (%s)", signal.Signals(signum).name)
        raise SystemExit(0)

    return _handle_shutdown_signal


def run_forever(
    daemon: Daemon,
    mcp_server: Server,
    *,
    host: str,
    port: int,
    api_key: str | None,
    extra_routes: list[Route],
) -> None:
    """Serve `mcp_server` until `SIGTERM`, `SIGINT`, or a normal return
    from `transport.run`, then run `daemon.shutdown()` exactly once —
    the same cleanup path regardless of which of the three actually
    happened. `uvicorn` (inside `transport.run`) installs its own
    SIGTERM/SIGINT handlers while serving and restores whatever was
    registered here once its own graceful shutdown finishes, re-raising
    the signal so the handler registered below still runs.
    """
    handler = _build_shutdown_signal_handler()
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    try:
        transport.run(mcp_server, host=host, port=port, api_key=api_key, extra_routes=extra_routes)
    finally:
        daemon.shutdown()


def main() -> None:
    log_file_env = os.environ.get("GRAPHIFY_DAEMON_LOG_FILE")
    log_file = Path(log_file_env).expanduser() if log_file_env else Path.cwd() / "logs" / "daemon.log"
    log_level = logging_config.resolve_log_level(os.environ.get("GRAPHIFY_DAEMON_LOG_LEVEL"))
    log_max_bytes, log_backup_count = logging_config.resolve_rotation_settings(
        os.environ.get("GRAPHIFY_DAEMON_LOG_MAX_BYTES"),
        os.environ.get("GRAPHIFY_DAEMON_LOG_BACKUP_COUNT"),
    )
    logging_config.configure_logging(log_file, log_level, log_max_bytes, log_backup_count)

    vault_root = Path(os.environ["GRAPHIFY_DAEMON_VAULT_ROOT"]).expanduser()
    output_dir_env = os.environ.get("GRAPHIFY_DAEMON_OUT_DIR")
    output_dir = Path(output_dir_env).expanduser() if output_dir_env else Path.cwd() / DEFAULT_OUTPUT_DIR_NAME
    paths = DaemonPaths(output_dir)
    lru_size = int(os.environ.get("GRAPHIFY_DAEMON_LRU_SIZE", DEFAULT_LRU_SIZE))
    pending_warn_threshold = int(
        os.environ.get("GRAPHIFY_DAEMON_PENDING_WARN_THRESHOLD", DEFAULT_PENDING_WARN_THRESHOLD)
    )

    daemon = Daemon(vault_root, paths, lru_size=lru_size, pending_warn_threshold=pending_warn_threshold)
    daemon.cold_start()

    daemon.start()
    mcp_server = daemon.build_mcp_server()

    run_forever(
        daemon,
        mcp_server,
        host=os.environ.get("GRAPHIFY_DAEMON_HOST", transport.DEFAULT_HOST),
        port=int(os.environ.get("GRAPHIFY_DAEMON_PORT", transport.DEFAULT_PORT)),
        api_key=os.environ.get("GRAPHIFY_DAEMON_API_KEY"),
        extra_routes=[
            Route("/health", daemon.health_route()),
            Route("/metrics", daemon.metrics_route()),
        ],
    )


if __name__ == "__main__":
    main()
