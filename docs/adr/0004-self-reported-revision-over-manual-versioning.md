---
status: accepted
---

# Report the running git revision instead of manually bumping a version number

This project does not maintain a manually-bumped SemVer-style version in `pyproject.toml` (it stays at `0.1.0`). Considered and rejected: a rule requiring a version bump on every feature or fix — rejected because it depends on someone remembering to do it, and that discipline already failed once in practice (`harden-graphify-daemon-audit` shipped 9 task groups, including two real bug fixes, with zero version bump). Instead, the daemon reports the exact git commit (and dirty/clean state) it was started from via `GET /metrics` (`resolve_git_revision`, `artifact_lifecycle/metrics.py`) — a fact computed at process start, which cannot drift from reality the way a hand-maintained number can.
