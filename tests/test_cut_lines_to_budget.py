"""_cut_lines_to_budget: accurate truncation reporting, including when a
single line exceeds the budget (the real "0 more lines cut" bug found
by the audit).

See specs/graph-query-api/spec.md "Accurate truncation reporting for
token-budget cuts".
"""

from __future__ import annotations

from graphify_daemon.graph_query_api.tools import _cut_lines_to_budget


def test_empty_lines_returns_empty_string() -> None:
    assert _cut_lines_to_budget([], 100, "hint") == ""


def test_single_line_exceeding_budget_reports_truncation_not_zero() -> None:
    long_line = "x" * 1000
    result = _cut_lines_to_budget([long_line], 1, "hint")  # ~3-char budget, far under 1000 chars

    assert "TRUNCATED" in result
    assert "0 more lines cut" not in result


def test_negative_budget_does_not_raise() -> None:
    _cut_lines_to_budget(["a", "b", "c"], -1, "hint")  # must not raise
