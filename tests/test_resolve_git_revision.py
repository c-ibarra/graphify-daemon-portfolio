"""resolve_git_revision: env vars first, live git query as fallback,
degrades to (None, None) rather than raising.

See specs/artifact-lifecycle/spec.md "Operational metrics" (git_sha/
git_dirty scenarios).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from graphify_daemon.artifact_lifecycle.metrics import resolve_git_revision


def test_env_vars_are_used_verbatim_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHIFY_DAEMON_GIT_SHA", "deadbeef")
    monkeypatch.setenv("GRAPHIFY_DAEMON_GIT_DIRTY", "1")

    sha, dirty = resolve_git_revision()

    assert sha == "deadbeef"
    assert dirty is True


def test_env_var_dirty_flag_parses_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHIFY_DAEMON_GIT_SHA", "deadbeef")
    monkeypatch.setenv("GRAPHIFY_DAEMON_GIT_DIRTY", "0")

    sha, dirty = resolve_git_revision()

    assert sha == "deadbeef"
    assert dirty is False


def _init_git_repo(path: Path) -> str:
    """Create a real git repo at `path` with one commit; returns its HEAD sha."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "a.txt").write_text("a")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_falls_back_to_a_live_git_query_when_env_vars_are_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_SHA", raising=False)
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_DIRTY", raising=False)
    expected_sha = _init_git_repo(tmp_path)

    sha, dirty = resolve_git_revision(cwd=tmp_path)

    assert sha == expected_sha
    assert dirty is False


def test_fallback_detects_a_dirty_working_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_SHA", raising=False)
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_DIRTY", raising=False)
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("changed")

    _sha, dirty = resolve_git_revision(cwd=tmp_path)

    assert dirty is True


def test_degrades_to_none_none_without_a_git_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_SHA", raising=False)
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_DIRTY", raising=False)
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()

    sha, dirty = resolve_git_revision(cwd=not_a_repo)

    assert sha is None
    assert dirty is None


def test_degrades_to_none_none_when_git_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_SHA", raising=False)
    monkeypatch.delenv("GRAPHIFY_DAEMON_GIT_DIRTY", raising=False)

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _raise)

    sha, dirty = resolve_git_revision(cwd=tmp_path)

    assert sha is None
    assert dirty is None
