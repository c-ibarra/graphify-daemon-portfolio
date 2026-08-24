"""The seven MCP read tools, executed off the event loop against the resident snapshot.

See specs/graph-query-api/spec.md "Minimum read tool surface",
"No disk reads on the query path", and "Off-event-loop query execution".

`get_neighbors` deliberately omits graphify.serve's cross-file ambiguity
warning (`find_node_ambiguity`) -- that symbol is not among the 5 authorized
graphify-adapter private symbols (task group 2), and extending that
confinement list wasn't warranted for this one behavior. It takes the first
match, same as `get_node`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import jsonschema
from graphify.analyze import god_nodes as _god_nodes
from graphify.build import edge_data
from graphify.security import sanitize_label
from mcp import types

from graphify_daemon.adapters import graphify_query as adapter
from graphify_daemon.artifact_lifecycle.metrics import Metrics
from graphify_daemon.graph_query_api.query_cache import DEFAULT_LRU_SIZE, QueryCache
from graphify_daemon.vault_compiler.snapshot import GraphSnapshot

# Schemas copied verbatim from graphify.serve for client compatibility --
# see specs/graph-query-api/spec.md "Minimum read tool surface".
TOOL_DEFINITIONS: tuple[types.Tool, ...] = (
    types.Tool(
        name="query_graph",
        description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural language question or keyword search"},
                "mode": {
                    "type": "string",
                    "enum": ["bfs", "dfs"],
                    "default": "bfs",
                    "description": "bfs=broad context, dfs=trace a specific path",
                },
                "depth": {
                    "type": "integer",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 6,
                    "description": "Traversal depth (1-6)",
                },
                "token_budget": {
                    "type": "integer",
                    "default": 2000,
                    "minimum": 1,
                    "maximum": 20000,
                    "description": "Max output tokens",
                },
                "context_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 50,
                    "description": "Optional explicit edge-context filter, e.g. ['call', 'field']",
                },
            },
            "required": ["question"],
        },
    ),
    types.Tool(
        name="get_node",
        description="Get full details for a specific node by label or ID.",
        inputSchema={
            "type": "object",
            "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
            "required": ["label"],
        },
    ),
    types.Tool(
        name="get_neighbors",
        description="Get all direct neighbors of a node with edge details.",
        inputSchema={
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                "token_budget": {
                    "type": "integer",
                    "default": 2000,
                    "minimum": 1,
                    "maximum": 20000,
                    "description": "Max output tokens",
                },
            },
            "required": ["label"],
        },
    ),
    types.Tool(
        name="get_community",
        description="Get all nodes in a community by community ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "community_id": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Community ID (0-indexed by size)",
                },
                "token_budget": {
                    "type": "integer",
                    "default": 2000,
                    "minimum": 1,
                    "maximum": 20000,
                    "description": "Max output tokens",
                },
            },
            "required": ["community_id"],
        },
    ),
    types.Tool(
        name="god_nodes",
        description="Return the most connected nodes - the core abstractions of the knowledge graph.",
        inputSchema={
            "type": "object",
            "properties": {"top_n": {"type": "integer", "default": 10, "minimum": 1, "maximum": 500}},
        },
    ),
    types.Tool(
        name="graph_stats",
        description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="shortest_path",
        description=(
            "Find the shortest path between two concepts in the knowledge graph. "
            "Follows stored edge direction by default; set undirected=true to ignore it."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source concept label or keyword"},
                "target": {"type": "string", "description": "Target concept label or keyword"},
                "max_hops": {
                    "type": "integer",
                    "default": 8,
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Maximum hops to consider",
                },
                "undirected": {
                    "type": "boolean",
                    "default": False,
                    "description": "Ignore stored edge direction when searching",
                },
            },
            "required": ["source", "target"],
        },
    ),
)


def _cut_lines_to_budget(lines: list[str], token_budget: int, narrow_hint: str) -> str:
    """Render `lines` under a ~3-chars/token budget, cut at a line boundary
    with a count and a narrowing hint instead of flooding the caller's
    context window."""
    output = "\n".join(lines)
    char_budget = token_budget * 3
    if not lines or len(output) <= char_budget:
        return output
    cut_at = output[:char_budget].rfind("\n")
    cut_at = cut_at if cut_at > 0 else char_budget
    kept = output[:cut_at]
    shown = kept.count("\n") + 1
    cut_count = len(lines) - shown
    if cut_count == 0 and kept != "\n".join(lines[:shown]):
        # The single remaining line itself exceeds the budget: no whole
        # line was cut, but the shown one was cut off mid-line -- reporting
        # "0 more lines cut" here would be misleading about real truncation.
        return f"[!] TRUNCATED: this line exceeds the ~{token_budget}-token budget on its own. {narrow_hint}\n\n" + kept
    return (
        f"[!] TRUNCATED: showing {shown} of {len(lines)} lines "
        f"(~{token_budget}-token budget). {narrow_hint}\n\n"
        + kept
        + f"\n... (truncated — {cut_count} more lines cut by ~{token_budget}-token budget. "
        + narrow_hint
        + ")"
    )


def _community_header(cid: int, community_name: object) -> str:
    base = f"Community {cid}"
    if community_name:
        clean = sanitize_label(str(community_name))
        if clean and clean != base:
            return f"{base} — {clean}"
    return base


def _tool_query_graph(arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    return adapter.query_graph_text(
        snapshot.graph,
        arguments["question"],
        mode=arguments.get("mode", "bfs"),
        depth=int(arguments.get("depth", 3)),
        token_budget=int(arguments.get("token_budget", 2000)),
        context_filters=arguments.get("context_filter"),
    )


def _tool_get_node(arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    label = arguments["label"].lower()
    graph = snapshot.graph
    matches = [
        (nid, d) for nid, d in graph.nodes(data=True) if label in (d.get("label") or "").lower() or label == nid.lower()
    ]
    if not matches:
        return f"No node matching '{label}' found."
    nid, d = matches[0]
    return "\n".join(
        [
            f"Node: {sanitize_label(d.get('label', nid))}",
            f"  ID: {sanitize_label(nid)}",
            f"  Source: {sanitize_label(str(d.get('source_file', '')))} "
            f"{sanitize_label(str(d.get('source_location', '')))}",
            f"  Type: {sanitize_label(str(d.get('file_type', '')))}",
            f"  Community: {sanitize_label(str(d.get('community_name') or d.get('community', '')))}",
            f"  Degree: {graph.degree(nid)}",
        ]
    )


def _tool_get_neighbors(arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    label = arguments["label"].lower()
    rel_filter = arguments.get("relation_filter", "").lower()
    graph = snapshot.graph
    matches = adapter.find_node(graph, label)
    if not matches:
        return f"No node matching '{label}' found."
    nid = matches[0]

    def _edge_at(d: dict[str, Any]) -> str:
        loc = str(d.get("source_location") or "")
        return f" at={sanitize_label(str(d.get('source_file') or ''))}:{sanitize_label(loc)}" if loc else ""

    lines = [f"Neighbors of {sanitize_label(graph.nodes[nid].get('label', nid))}:"]
    for nb in graph.successors(nid):
        d = edge_data(graph, nid, nb)
        rel = d.get("relation", "")
        if rel_filter and rel_filter not in rel.lower():
            continue
        lines.append(
            f"  --> {sanitize_label(graph.nodes[nb].get('label', nb))} "
            f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]{_edge_at(d)}"
        )
    for nb in graph.predecessors(nid):
        d = edge_data(graph, nb, nid)
        rel = d.get("relation", "")
        if rel_filter and rel_filter not in rel.lower():
            continue
        lines.append(
            f"  <-- {sanitize_label(graph.nodes[nb].get('label', nb))} "
            f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]{_edge_at(d)}"
        )
    budget = int(arguments.get("token_budget", 2000))
    return _cut_lines_to_budget(lines, budget, "Narrow with relation_filter or use get_node for a specific symbol")


def _tool_get_community(arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    cid = int(arguments["community_id"])
    nodes = snapshot.community_map.get(cid, [])
    if not nodes:
        return f"Community {cid} not found."
    graph = snapshot.graph
    header = _community_header(cid, graph.nodes[nodes[0]].get("community_name"))
    lines = [f"{header} ({len(nodes)} nodes):"]
    for n in nodes:
        d = graph.nodes[n]
        lines.append(f"  {sanitize_label(d.get('label', n))} [{sanitize_label(str(d.get('source_file', '')))}]")
    budget = int(arguments.get("token_budget", 2000))
    return _cut_lines_to_budget(lines, budget, "Raise token_budget or use get_node for specific members")


def _tool_god_nodes(arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    nodes = _god_nodes(snapshot.graph, top_n=int(arguments.get("top_n", 10)))
    lines = ["God nodes (most connected):"]
    lines += [f"  {i}. {n['label']} - {n['degree']} edges" for i, n in enumerate(nodes, 1)]
    return "\n".join(lines)


def _tool_graph_stats(_arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    graph = snapshot.graph
    confs = [d.get("confidence", "EXTRACTED") for _, _, d in graph.edges(data=True)]
    total = len(confs) or 1
    return (
        f"Nodes: {graph.number_of_nodes()}\n"
        f"Edges: {graph.number_of_edges()}\n"
        f"Communities: {len(snapshot.community_map)}\n"
        f"EXTRACTED: {round(confs.count('EXTRACTED') / total * 100)}%\n"
        f"INFERRED: {round(confs.count('INFERRED') / total * 100)}%\n"
        f"AMBIGUOUS: {round(confs.count('AMBIGUOUS') / total * 100)}%\n"
    )


def _tool_shortest_path(arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    return adapter.shortest_path_text(snapshot.graph, arguments)


_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any], GraphSnapshot], str]] = {
    "query_graph": _tool_query_graph,
    "get_node": _tool_get_node,
    "get_neighbors": _tool_get_neighbors,
    "get_community": _tool_get_community,
    "god_nodes": _tool_god_nodes,
    "graph_stats": _tool_graph_stats,
    "shortest_path": _tool_shortest_path,
}


def execute_tool(name: str, arguments: dict[str, Any], snapshot: GraphSnapshot) -> str:
    """Run one of the seven tools synchronously against `snapshot`.

    Reads only `snapshot.graph`/`snapshot.community_map` — never touches
    disk. Raises KeyError for an unknown tool name.
    """
    return _TOOL_HANDLERS[name](arguments, snapshot)


_TOOL_DEFINITIONS_BY_NAME: dict[str, types.Tool] = {tool.name: tool for tool in TOOL_DEFINITIONS}


def _error_result(message: str) -> types.CallToolResult:
    """Build a clean CallToolResult(isError=True, ...) for any dispatch failure.

    See specs/graph-query-api/spec.md "Malformed and out-of-range MCP
    requests fail cleanly".
    """
    return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=message)])


def build_handlers(
    get_snapshot: Callable[[], GraphSnapshot | None],
    *,
    cache_size: int = DEFAULT_LRU_SIZE,
    metrics: Metrics | None = None,
    query_cache: QueryCache | None = None,
) -> tuple[
    Callable[..., Awaitable[types.ListToolsResult]],
    Callable[..., Awaitable[types.CallToolResult]],
]:
    """Build (on_list_tools, on_call_tool) callables for `mcp.server.Server`.

    `get_snapshot` (typically `SnapshotHolder.current`) is called exactly
    once per request — task group 5's take-reference-once pattern — then
    `execute_tool` runs entirely against that one snapshot reference via
    `asyncio.to_thread`, so one slow query never blocks another.

    `query_graph` results are cached in a version-scoped `QueryCache`
    (task group 9) — see specs/graph-query-api/spec.md "Version-scoped
    LRU result cache". No other tool is cached.

    If `metrics` is given, every call's total duration (cache hit or not)
    is recorded under the "query" name — see
    specs/artifact-lifecycle/spec.md "Operational metrics".

    `query_cache`, if given, is used instead of constructing one
    internally — lets a caller (the daemon entrypoint) keep its own
    reference for reading `hit_rate()` in the metrics endpoint, without
    changing this function's `(on_list_tools, on_call_tool)` return shape.
    """

    if query_cache is None:
        query_cache = QueryCache(maxsize=cache_size)

    async def on_list_tools(_ctx: object, _params: object) -> types.ListToolsResult:
        return types.ListToolsResult(tools=list(TOOL_DEFINITIONS))

    async def on_call_tool(_ctx: object, params: types.CallToolRequestParams) -> types.CallToolResult:
        start = time.monotonic()
        try:
            return await _dispatch(params, get_snapshot(), query_cache)
        finally:
            if metrics is not None:
                metrics.record_latency("query", time.monotonic() - start)

    async def _dispatch(
        params: types.CallToolRequestParams,
        snapshot: GraphSnapshot | None,
        query_cache: QueryCache,
    ) -> types.CallToolResult:
        tool = _TOOL_DEFINITIONS_BY_NAME.get(params.name)
        if tool is None:
            return _error_result(f"Unknown tool: {params.name!r}")

        if snapshot is None:
            return _error_result("Graph not ready yet")

        arguments = params.arguments or {}
        try:
            jsonschema.validate(arguments, tool.input_schema)
        except jsonschema.ValidationError as exc:
            return _error_result(f"Invalid arguments for {params.name}: {exc.message}")

        try:
            if params.name == "query_graph":
                context_filter = arguments.get("context_filter")
                cache_kwargs = {
                    "version": snapshot.version,
                    "question": arguments["question"],
                    "mode": arguments.get("mode", "bfs"),
                    "depth": int(arguments.get("depth", 3)),
                    "token_budget": int(arguments.get("token_budget", 2000)),
                    "context_filters": tuple(context_filter) if context_filter else None,
                }
                cached = query_cache.get(**cache_kwargs)
                if cached is not None:
                    return types.CallToolResult(content=[types.TextContent(type="text", text=cached)])
                text = await asyncio.to_thread(execute_tool, params.name, arguments, snapshot)
                query_cache.set(**cache_kwargs, result=text)
            else:
                text = await asyncio.to_thread(execute_tool, params.name, arguments, snapshot)
        except Exception as exc:  # noqa: BLE001 - reported to the caller as a clean MCP error, not raised
            return _error_result(f"Tool {params.name} failed: {exc}")

        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])

    return on_list_tools, on_call_tool
