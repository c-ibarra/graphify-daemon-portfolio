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
import sys
from collections.abc import Awaitable, Callable
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
    generate_knowledge_md,
    write_graph_json,
)
from graphify_daemon.artifact_lifecycle.health import health_check
from graphify_daemon.artifact_lifecycle.metrics import Metrics, collect_metrics
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
        extract_batch(batch, self.vault_root, self.cache, metrics=self.metrics)
        sync_batch(self.vault_index_conn, batch, self.vault_root, self.cache)

        graph = build_graph(self.cache)
        current = self.holder.current()
        community_map = current.community_map if current is not None else {}
        self.holder.publish(graph, community_map)

        self.tracker.record_batch(len(batch.changes))
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
            self.paths.knowledge_md.write_text(generate_knowledge_md(current))
        self.cache.save(self.paths.graph_cache_json)
        self.vault_index_conn.close()

    def shutdown(self) -> None:
        self.watcher.stop()
        self.coordinator.shutdown(self.persist_on_shutdown)


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

    def _handle_sigterm(_signum: int, _frame: object) -> None:
        logger.info("SIGTERM received: draining and persisting")
        daemon.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    daemon.start()
    mcp_server = daemon.build_mcp_server()

    transport.run(
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
