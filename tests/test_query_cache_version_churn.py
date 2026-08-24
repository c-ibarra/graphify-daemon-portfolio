"""QueryCache stays bounded even under heavy snapshot-version churn.

See specs/graph-query-api/spec.md "Configurable cache size" (churn
scenario).
"""

from __future__ import annotations

from graphify_daemon.graph_query_api.query_cache import QueryCache


def test_cache_never_exceeds_maxsize_across_1000_snapshot_versions() -> None:
    cache = QueryCache(maxsize=50)

    for version in range(1000):
        cache.set(
            version=version,
            question="q",
            mode="bfs",
            depth=3,
            token_budget=2000,
            context_filters=None,
            result=f"result-{version}",
        )
        assert len(cache._entries) <= 50
