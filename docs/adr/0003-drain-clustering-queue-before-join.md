---
status: accepted
---

# Drain the clustering subprocess's result queue before joining it, not after

`run_clustering_subprocess` (see ADR 0001) used to call `process.join(timeout)` before reading `result_queue` — the classic `multiprocessing.Queue` deadlock: a community-map result larger than the OS pipe buffer (~64KB, already exceeded past ~8,000 nodes) leaves the child blocked writing it to a full pipe, while the parent blocks in `join()` without ever reading that pipe. The only exit was the configured timeout, which then terminated the child and discarded a result that had, in fact, already been computed correctly — confirmed directly: at the 60s mark, `process.is_alive()` was still `True`, yet the queue already held a valid, complete result.

Fix: call `result_queue.get(timeout=timeout)` first, treating `queue.Empty` as the unified timeout/crash failure case, and only call `process.join()` (with a short grace period) once the result is already in hand — the child can only exit after its queue-feeder thread finishes flushing, which requires something to be reading the other end.

## Consequences

The old code's separate `process.exitcode != 0` fast-fail check is gone; an abnormal child exit before producing anything is now indistinguishable from a genuine timeout (both surface as `queue.Empty`). Accepted: `_cluster_worker` already catches every `Exception` internally and reports it through the queue rather than crashing, so this was already an untested, unlikely edge case (OS-level crash, bad pickle) rather than a load-bearing behavior.
