"""QueryCache: version-scoped LRU cache.

See specs/graph-query-api/spec.md "Version-scoped LRU result cache" and
"Configurable cache size".
"""

from __future__ import annotations

from graphify_daemon.graph_query_api.query_cache import QueryCache


def _key(version: int = 1, question: str = "foo") -> dict:
    return {
        "version": version,
        "question": question,
        "mode": "bfs",
        "depth": 3,
        "token_budget": 2000,
        "context_filters": None,
    }


def test_miss_returns_none() -> None:
    cache = QueryCache()
    assert cache.get(**_key()) is None


def test_set_then_get_returns_the_cached_result() -> None:
    cache = QueryCache()
    cache.set(**_key(), result="the answer")
    assert cache.get(**_key()) == "the answer"


def test_different_version_is_a_different_entry() -> None:
    cache = QueryCache()
    cache.set(**_key(version=1), result="v1 answer")
    assert cache.get(**_key(version=2)) is None


def test_different_question_is_a_different_entry() -> None:
    cache = QueryCache()
    cache.set(**_key(question="foo"), result="foo answer")
    assert cache.get(**_key(question="bar")) is None


def test_hit_rate_is_zero_with_no_lookups() -> None:
    cache = QueryCache()
    assert cache.hit_rate() == 0.0


def test_hit_rate_reflects_hits_and_misses() -> None:
    cache = QueryCache()
    cache.set(**_key(), result="the answer")
    cache.get(**_key())  # hit
    cache.get(**_key(question="other"))  # miss
    cache.get(**_key())  # hit

    assert cache.hit_rate() == 2 / 3


def test_maxsize_evicts_the_least_recently_used_entry() -> None:
    cache = QueryCache(maxsize=2)
    cache.set(**_key(question="a"), result="a-result")
    cache.set(**_key(question="b"), result="b-result")
    cache.set(**_key(question="c"), result="c-result")  # evicts "a" (least recently used)

    assert cache.get(**_key(question="a")) is None
    assert cache.get(**_key(question="b")) == "b-result"
    assert cache.get(**_key(question="c")) == "c-result"
