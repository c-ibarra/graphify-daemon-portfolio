"""The slow-cadence trigger: 60s of quiet or 25 accumulated changes.

See CONTEXT.md: Slow cadence. Governs both clustering (task group 6) and
disk-artifact writes (artifact-lifecycle, task group 10) — not
clustering-specific, despite clustering being its first consumer.
"""

from __future__ import annotations

import time


class SlowCadenceTracker:
    """Tracks whether the slow-cadence condition has been met.

    `record_batch` resets the quiet timer and accumulates the change count;
    `should_trigger` reports whether either threshold has been crossed since
    the last `reset`.
    """

    def __init__(self, *, quiet_seconds: float = 60.0, change_threshold: int = 25) -> None:
        self._quiet_seconds = quiet_seconds
        self._change_threshold = change_threshold
        self._accumulated_changes = 0
        self._last_batch_at = time.monotonic()

    def record_batch(self, change_count: int) -> None:
        self._accumulated_changes += change_count
        self._last_batch_at = time.monotonic()

    def should_trigger(self) -> bool:
        if self._accumulated_changes >= self._change_threshold:
            return True
        return time.monotonic() - self._last_batch_at >= self._quiet_seconds

    def reset(self) -> None:
        self._accumulated_changes = 0
        self._last_batch_at = time.monotonic()
