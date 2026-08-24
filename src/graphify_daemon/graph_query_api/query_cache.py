"""Version-scoped LRU cache for query_graph results.

See specs/graph-query-api/spec.md "Version-scoped LRU result cache" and
"Configurable cache size".
"""

from __future__ import annotations

import threading
from collections import OrderedDict

DEFAULT_LRU_SIZE = 512

CacheKey = tuple[int, str, str, int, int, tuple[str, ...] | None]


class QueryCache:
    """A bounded LRU cache keyed by (snapshot version, question, mode,
    depth, token_budget, context_filters).

    Entries for an old snapshot version simply age out via normal LRU
    eviction once nothing looks them up again — no explicit invalidation
    code exists, per the spec's "unreachable by construction" requirement.
    Thread-safe: query_graph calls run concurrently via asyncio.to_thread
    (task group 8).
    """

    def __init__(self, *, maxsize: int = DEFAULT_LRU_SIZE) -> None:
        self._maxsize = maxsize
        self._entries: OrderedDict[CacheKey, str] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def hit_rate(self) -> float:
        with self._lock:
            total = self._hits + self._misses
            return 0.0 if total == 0 else self._hits / total

    @staticmethod
    def _key(
        version: int,
        question: str,
        mode: str,
        depth: int,
        token_budget: int,
        context_filters: tuple[str, ...] | None,
    ) -> CacheKey:
        return (version, question, mode, depth, token_budget, context_filters)

    def get(
        self,
        *,
        version: int,
        question: str,
        mode: str,
        depth: int,
        token_budget: int,
        context_filters: tuple[str, ...] | None,
    ) -> str | None:
        key = self._key(version, question, mode, depth, token_budget, context_filters)
        with self._lock:
            if key not in self._entries:
                self._misses += 1
                return None
            self._hits += 1
            self._entries.move_to_end(key)
            return self._entries[key]

    def set(
        self,
        *,
        version: int,
        question: str,
        mode: str,
        depth: int,
        token_budget: int,
        context_filters: tuple[str, ...] | None,
        result: str,
    ) -> None:
        key = self._key(version, question, mode, depth, token_budget, context_filters)
        with self._lock:
            self._entries[key] = result
            self._entries.move_to_end(key)
            if len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
