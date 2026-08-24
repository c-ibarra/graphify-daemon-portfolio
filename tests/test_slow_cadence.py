"""SlowCadenceTracker: 60s of quiet or 25 accumulated changes.

See CONTEXT.md: Slow cadence, and
specs/vault-compiler/spec.md "Clustering triggered by slow cadence only".
"""

from __future__ import annotations

import time

from graphify_daemon.vault_compiler.slow_cadence import SlowCadenceTracker


def test_does_not_trigger_below_both_thresholds() -> None:
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    tracker.record_batch(1)
    assert tracker.should_trigger() is False


def test_triggers_once_change_threshold_is_reached() -> None:
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    tracker.record_batch(10)
    tracker.record_batch(15)
    assert tracker.should_trigger() is True


def test_triggers_once_quiet_window_elapses() -> None:
    tracker = SlowCadenceTracker(quiet_seconds=0.05, change_threshold=1000)
    tracker.record_batch(1)
    time.sleep(0.1)
    assert tracker.should_trigger() is True


def test_reset_clears_accumulated_changes_and_restarts_the_quiet_timer() -> None:
    tracker = SlowCadenceTracker(quiet_seconds=60.0, change_threshold=25)
    tracker.record_batch(25)
    assert tracker.should_trigger() is True

    tracker.reset()

    assert tracker.should_trigger() is False
