---
status: accepted
---

# Clustering subprocess receives a pickled snapshot via spawn, not fork or shared memory

Community clustering runs in an isolated subprocess so a ~748ms Leiden pass never blocks concurrent reads — but the daemon's core invariant is that exactly one copy of the graph exists in memory, scoped to the snapshot served to clients. The clustering subprocess is an explicit, bounded exception: it receives a transient, private copy of the graph that exists only for the duration of its run. We hand off that copy via `multiprocessing` using the `spawn` start method, pickling the current snapshot's graph to the subprocess.

## Considered Options

- **`fork()`**: cheapest in theory — the child gets an OS-level copy-on-write view of the parent's memory, no serialization needed. Rejected: the server process runs a threaded async HTTP stack, and `fork()` from a multi-threaded process is a known hazard (POSIX `fork()` only duplicates the calling thread; locks held by other threads at fork time can deadlock the child forever). macOS is additionally fragile forking a process with native extensions loaded, without an immediate `exec()`.
- **Shared memory** (`multiprocessing.shared_memory` / mmap): would avoid duplicate allocation. Rejected: `nx.Graph` is a nested dict-of-dicts of arbitrary Python objects, not a flat buffer — representing it in shared memory means inventing a bespoke binary format for an operation that runs at most every 60 seconds. Not worth the complexity at this frequency.
- **Re-reading the slow-cadence `graph.json`**: simplest, no live-object serialization at all. Rejected for correctness: that file can lag the live snapshot by up to the slow-cadence window, so the subprocess could cluster a node set that no longer matches what `remap_communities_to_previous()` is later asked to reconcile against.

## Consequences

If pickling a live `nx.Graph` turns out to be expensive, or hits a non-picklable node/edge attribute during implementation, the fallback is a dedicated fresh temp-file dump (`write_json_atomic` + `build_from_json`, ~373ms measured) — not a read of the slow-cadence `graph.json`, for the same staleness reason above.
