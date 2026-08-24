"""Contract tests for the graphify-adapter confinement module.

Verifies two things independently:
1. `graphify.serve` (the vendored private API) still exposes the 5 authorized
   symbols with the exact signature this project depends on. This must fail
   loudly, naming the broken symbol, if a future `graphifyy` upgrade changes
   or removes one of them.
2. `graphify_daemon.adapters.graphify_query` wraps all 5 symbols under a
   public (non-underscore) name with a matching call signature.
"""

from __future__ import annotations

import inspect

import pytest

# Signature shape: (parameter names in declaration order, set of keyword-only names).
# Mirrors graphify.serve as installed at graphifyy==0.9.34.
EXPECTED_SIGNATURES: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "_query_graph_text": (
        ("G", "question", "mode", "depth", "token_budget", "context_filters"),
        frozenset({"mode", "depth", "token_budget", "context_filters"}),
    ),
    "_get_trigram_index": (("G",), frozenset()),
    "_communities_from_graph": (("G",), frozenset()),
    "_shortest_path_text": (("G", "arguments"), frozenset()),
    "_find_node": (("G", "label"), frozenset()),
}

WRAPPER_NAMES = {
    "_query_graph_text": "query_graph_text",
    "_get_trigram_index": "get_trigram_index",
    "_communities_from_graph": "communities_from_graph",
    "_shortest_path_text": "shortest_path_text",
    "_find_node": "find_node",
}


def _signature_shape(func) -> tuple[tuple[str, ...], frozenset[str]]:
    sig = inspect.signature(func)
    names = tuple(sig.parameters)
    keyword_only = frozenset(
        name for name, param in sig.parameters.items() if param.kind is inspect.Parameter.KEYWORD_ONLY
    )
    return names, keyword_only


@pytest.mark.parametrize("symbol_name", sorted(EXPECTED_SIGNATURES))
def test_graphify_serve_symbol_signature_unchanged(symbol_name: str) -> None:
    from graphify import serve

    assert hasattr(serve, symbol_name), (
        f"graphify.serve.{symbol_name} is missing — the graphifyy dependency "
        "no longer provides a symbol this adapter relies on."
    )
    actual = _signature_shape(getattr(serve, symbol_name))
    expected = EXPECTED_SIGNATURES[symbol_name]
    assert actual == expected, (
        f"graphify.serve.{symbol_name} signature changed: "
        f"expected params={expected[0]} keyword_only={sorted(expected[1])}, "
        f"got params={actual[0]} keyword_only={sorted(actual[1])}"
    )


@pytest.mark.parametrize("symbol_name", sorted(EXPECTED_SIGNATURES))
def test_adapter_wraps_authorized_symbol(symbol_name: str) -> None:
    from graphify_daemon.adapters import graphify_query as adapter

    wrapper_name = WRAPPER_NAMES[symbol_name]
    assert hasattr(adapter, wrapper_name), (
        f"graphify_daemon.adapters.graphify_query is missing a wrapper "
        f"for graphify.serve.{symbol_name} (expected `{wrapper_name}`)"
    )
    wrapper = getattr(adapter, wrapper_name)
    assert callable(wrapper)
    expected_params, expected_keyword_only = EXPECTED_SIGNATURES[symbol_name]
    actual_params, actual_keyword_only = _signature_shape(wrapper)
    assert actual_params == expected_params, (
        f"adapter.{wrapper_name} parameter names {actual_params} do not match "
        f"graphify.serve.{symbol_name}'s {expected_params}"
    )
    assert actual_keyword_only == expected_keyword_only
