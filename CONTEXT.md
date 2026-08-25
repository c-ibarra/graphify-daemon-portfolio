# Graphify Daemon

A local daemon that derives a knowledge graph from an Obsidian vault and serves it to concurrent local AI agents over MCP.

## Language

**Vault**:
The Obsidian directory (`~/Documents/Obsidian`) that is the single source of truth for all graph content. State flows from the vault to the graph, never the other way.
_Avoid_: repo, knowledge base

**Vault confinement**:
The invariant that every file this daemon processes — at cold start and in the live watcher — resolves (`Path.resolve(strict=False)`) inside `vault_root`. A path whose resolved real location falls outside the vault, including one reached through a symlink, is rejected rather than read.
_Avoid_: path validation, symlink check

**Derived artifact**:
Any data regenerable from the vault: the in-RAM graph, `graph.json`, `vault_index.db`, `KNOWLEDGE.md`. None of these is a system of record — durability and recovery come from regenerating them, not from backing them up. That's a claim about recovery, not about confidentiality: derived artifacts still carry vault-derived names, relationships, and relative paths, so every one of them is written owner-only.
_Avoid_: source of truth, primary data

**Snapshot**:
An immutable, versioned unit of graph state: a NetworkX graph, a pre-warmed trigram index, and a community map, published together as one atomic reference swap.
_Avoid_: graph state, current graph

**COW (copy-on-write)**:
The publish pattern behind a snapshot: the writer builds a new snapshot and reassigns the reference, rather than mutating the published one in place.

**Batch**:
The set of vault files changed within one debounce window, compiled together in exactly one rebuild operation — never iterated file-by-file.
_Avoid_: lot, chunk

**Slow cadence**:
The trigger condition for infrequent, expensive work (clustering, disk-artifact writes): 60 seconds of quiet or 25 accumulated changes, whichever comes first.
_Avoid_: lazy cadence, background cadence

**Community ID churn**:
The proportion of nodes whose community ID changes between successive clustering runs. Left unmanaged this is severe (88.63%, measured on the legacy pipeline); this daemon targets under 5% by remapping each run's communities against the previous assignment.
_Avoid_: cluster drift

**Accumulation episode**:
The period from `VaultWatcher`'s pending-file count first crossing `pending_warn_threshold` until the next debounce flush. At most one backpressure warning is emitted per episode, no matter how many more files accumulate before the flush; a new episode begins only once a flush resets it.
_Avoid_: backpressure window, warning cycle
