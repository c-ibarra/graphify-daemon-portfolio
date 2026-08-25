"""Reaching the change-count threshold runs the slow-cadence cycle
immediately and cancels the idle timer; a batch that does NOT cross the
threshold schedules one instead. Either way, the idle timer only ever
runs the cycle once for a given triggering condition.

See specs/vault-compiler/spec.md "Slow-cadence idle trigger fires without
a subsequent batch".
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from graphify_daemon import daemon as daemon_module
from graphify_daemon.daemon import Daemon
from graphify_daemon.paths import DaemonPaths
from graphify_daemon.vault_compiler.batching import Batch, ChangeKind, FileChange


def _daemon(tmp_path: Path, **kwargs: object) -> Daemon:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    paths = DaemonPaths(tmp_path / "out")
    return Daemon(vault_root, paths, **kwargs)  # type: ignore[arg-type]


def test_threshold_crossing_cancels_idle_and_schedules_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = _daemon(tmp_path, slow_cadence_change_threshold=1, slow_cadence_quiet_seconds=42.0)

    schedule_calls: list[tuple[object, float]] = []
    cancel_calls: list[bool] = []
    monkeypatch.setattr(daemon.watcher, "schedule_idle", lambda cb, secs: schedule_calls.append((cb, secs)))
    monkeypatch.setattr(daemon.watcher, "cancel_idle", lambda: cancel_calls.append(True))

    def fake_run_slow_cadence_cycle(tracker, holder, cache, **kwargs):
        tracker.reset()
        return True  # simulate the change-count threshold having been crossed

    monkeypatch.setattr(daemon_module, "run_slow_cadence_cycle", fake_run_slow_cadence_cycle)

    a = daemon.vault_root / "a.md"
    a.write_text("# A\n")
    batch = Batch(changes=(FileChange(path=a, kind=ChangeKind.MODIFIED),))
    daemon._on_batch(batch)

    assert cancel_calls == [True]
    assert schedule_calls == []


def test_non_triggering_batch_schedules_idle_with_configured_quiet_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = _daemon(tmp_path, slow_cadence_change_threshold=1000, slow_cadence_quiet_seconds=42.0)

    schedule_calls: list[tuple[object, float]] = []
    cancel_calls: list[bool] = []
    monkeypatch.setattr(daemon.watcher, "schedule_idle", lambda cb, secs: schedule_calls.append((cb, secs)))
    monkeypatch.setattr(daemon.watcher, "cancel_idle", lambda: cancel_calls.append(True))

    def fake_run_slow_cadence_cycle(tracker, holder, cache, **kwargs):
        return False  # simulate the threshold not having been crossed

    monkeypatch.setattr(daemon_module, "run_slow_cadence_cycle", fake_run_slow_cadence_cycle)

    a = daemon.vault_root / "a.md"
    a.write_text("# A\n")
    batch = Batch(changes=(FileChange(path=a, kind=ChangeKind.MODIFIED),))
    daemon._on_batch(batch)

    assert cancel_calls == []
    assert len(schedule_calls) == 1
    _callback, seconds = schedule_calls[0]
    assert seconds == 42.0


def test_idle_timer_eventually_runs_the_cycle_exactly_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # run_slow_cadence_cycle is already called synchronously once per batch
    # today, regardless of whether it actually triggers (existing,
    # unrelated behavior) -- so the count starts at 1, not 0. What's new
    # here is the idle timer adding exactly one more call later, and never
    # a third.
    daemon = _daemon(tmp_path, slow_cadence_change_threshold=1000, slow_cadence_quiet_seconds=0.1)

    calls: list[str] = []
    second_call = threading.Event()

    def fake_run_slow_cadence_cycle(tracker, holder, cache, **kwargs):
        calls.append("cycle")
        tracker.reset()
        if len(calls) == 2:
            second_call.set()
        return False

    monkeypatch.setattr(daemon_module, "run_slow_cadence_cycle", fake_run_slow_cadence_cycle)

    a = daemon.vault_root / "a.md"
    a.write_text("# A\n")
    batch = Batch(changes=(FileChange(path=a, kind=ChangeKind.MODIFIED),))
    daemon._on_batch(batch)

    assert calls == ["cycle"]  # the existing synchronous per-batch call

    assert second_call.wait(timeout=1.0), "the idle timer never ran a second cycle"
    assert calls == ["cycle", "cycle"]

    time.sleep(0.3)  # comfortably past another quiet period, to catch a stray reschedule
    assert calls == ["cycle", "cycle"], "the idle timer fired a third, unexpected cycle"
