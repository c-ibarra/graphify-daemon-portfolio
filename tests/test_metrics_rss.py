"""_rss_bytes reports current (live) RSS, not the historical peak.

Found wrong in code review (67af7fe...HEAD): resource.getrusage(...).ru_maxrss
is a high-water mark that never decreases, contradicting
specs/artifact-lifecycle/spec.md "Operational metrics"' own scenario --
"the metrics endpoint is queried after normal operation... all listed
metrics are present with current values."
"""

from __future__ import annotations

import subprocess

import pytest

from graphify_daemon.artifact_lifecycle import metrics as metrics_module


class _FakeCompletedProcess:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_rss_bytes_reflects_the_live_value_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = iter(["204800", "102400"])  # KB: 200MB, then 100MB

    def _fake_run(*_args: object, **_kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(next(readings))

    monkeypatch.setattr(subprocess, "run", _fake_run)

    first = metrics_module._rss_bytes()
    second = metrics_module._rss_bytes()

    assert first == 204800 * 1024
    assert second == 102400 * 1024
    assert second < first, "a dropping reading must be reflected, not pinned to a historical peak"


def test_rss_bytes_returns_a_real_positive_value() -> None:
    assert metrics_module._rss_bytes() > 0
