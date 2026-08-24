"""Metrics: generic, thread-safe telemetry primitives.

See specs/artifact-lifecycle/spec.md "Operational metrics".
"""

from __future__ import annotations

import time

from graphify_daemon.artifact_lifecycle.metrics import Metrics


def test_counter_starts_at_zero_and_increments() -> None:
    metrics = Metrics()
    assert metrics.counter("extraction_errors") == 0
    metrics.increment("extraction_errors")
    metrics.increment("extraction_errors")
    assert metrics.counter("extraction_errors") == 2


def test_gauge_starts_as_none_and_reflects_the_latest_value() -> None:
    metrics = Metrics()
    assert metrics.gauge("queue_depth") is None
    metrics.set_gauge("queue_depth", 3)
    metrics.set_gauge("queue_depth", 7)
    assert metrics.gauge("queue_depth") == 7


def test_event_time_starts_as_none_and_tracks_elapsed_seconds() -> None:
    metrics = Metrics()
    assert metrics.seconds_since_event("clustering_success") is None
    metrics.record_event_time("clustering_success")
    time.sleep(0.05)
    elapsed = metrics.seconds_since_event("clustering_success")
    assert elapsed is not None
    assert elapsed >= 0.04


def test_latency_percentiles_are_zero_with_no_samples() -> None:
    metrics = Metrics()
    assert metrics.latency_percentiles("query") == {"p50": 0.0, "p95": 0.0, "p99": 0.0}


def test_latency_percentiles_reflect_recorded_samples() -> None:
    metrics = Metrics()
    for ms in range(1, 101):  # 0.001s .. 0.100s
        metrics.record_latency("query", ms / 1000)
    percentiles = metrics.latency_percentiles("query")
    # 100 sorted samples, 0-indexed: index = int(n * p)
    assert percentiles["p50"] == 0.051
    assert percentiles["p95"] == 0.096
    assert percentiles["p99"] == 0.100
