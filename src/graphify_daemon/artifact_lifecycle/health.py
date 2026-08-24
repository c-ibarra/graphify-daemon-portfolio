"""Alive-vs-ready health check.

See specs/artifact-lifecycle/spec.md "Alive vs ready health check".
"""

from __future__ import annotations

from typing import Any

from graphify_daemon.vault_compiler.snapshot import SnapshotHolder


def health_check(holder: SnapshotHolder) -> dict[str, Any]:
    """Return `{"alive": True, "ready": bool}`.

    "alive" is trivially true — reaching this function at all means the
    process is running. "ready" is `holder.current() is not None`: a
    snapshot has been built and (per `SnapshotHolder.publish`, task group
    5) its trigram index pre-warmed, before any snapshot is ever published.
    """
    return {"alive": True, "ready": holder.current() is not None}
