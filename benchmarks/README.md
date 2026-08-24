# Benchmarks

Reproducible performance figures for `graphify-daemon`, measured against a
**deterministic synthetic graph** — not the author's personal Obsidian vault.
Anyone cloning this repo can regenerate the same graph and the same figures.

## Why synthetic, not a real vault

The daemon's design was originally informed by a one-time measurement against
a real 21,122-node vault graph (see the main `README.md`'s performance
section). That measurement isn't reproducible by anyone else — it depends on
the author's private notes. The synthetic generator here produces a graph of
the same order of magnitude (default 21,000 nodes) from a fixed seed, so new
figures measured against it are both independently reproducible *and*
roughly comparable in scale to that original measurement.

## Scripts

- `synthetic_graph.py` — `generate_synthetic_extraction(node_count, seed, edges_per_node)`,
  a deterministic node/edge generator in `graphify.build.build_from_json`'s
  expected format. Same inputs always produce the same graph.
- `bench_query_latency.py` — builds a `GraphSnapshot` from the synthetic graph
  (including real community clustering, so `get_community` is exercised
  realistically), runs each of the 7 read tools 500 times, and reports
  p50/p95/p99 latency per tool using the project's own `Metrics` class.
- `bench_clustering.py` — runs `run_clustering_subprocess` against the
  synthetic graph 5 times and reports min/mean/max duration.

## Reproducing the figures in the main README

```bash
uv run python benchmarks/bench_query_latency.py
uv run python benchmarks/bench_clustering.py
```

Both default to a 21,000-node graph (seed 42). Pass `--size N` to benchmark a
different scale, e.g. `--size 50` for something closer to a single real
batch's typical scale, or `--seed N` for a different (still deterministic)
synthetic graph.

Raw output from these scripts is intentionally **not** committed to the
repository — it would go stale. Only the dated figures in the main
`README.md`, alongside the exact command used to produce them, are persisted.
