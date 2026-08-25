---
status: accepted
---

# Compile a rename as delete-then-create under the writer lock, not a dedicated fast path

A `RENAMED` change removes `previous_path`'s cache/index state, then extracts the destination through the exact same code path as a `CREATED`/`MODIFIED` change — full re-extraction, not an in-place `source_file` rewrite. Extraction is already the steady-state cost model for every other change kind, so paying it again for a rename isn't a new expense this daemon doesn't already budget for.

## Considered Options

- **A dedicated rename fast-path**: relabel every node/edge's `source_file` from the previous path to the destination in place, skipping re-extraction entirely. Rejected: it needs its own cache/SQLite mutation logic, built and tested in parallel with the already-correct delete and create paths, for a cost (one extra extraction call) that's already negligible next to a batch's other work.
- **Composing the existing delete and create operations** (chosen): reuses two already-correct, already-tested code paths. The invariant this daemon actually needs — destination extracted exactly once, source state gone first — holds by construction rather than by a new code path's own correctness.

## Consequences

A rename of a very large file, or a rename inside an unusually large batch, re-pays extraction's full cost rather than a cheap relabel. Accepted: extraction per file is already fast enough not to be the bottleneck anywhere else in this pipeline; revisit only if a real workload shows renames specifically, not batches in general, dominating compile time.
