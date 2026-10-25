"""Serialize the evidence-backed project call graph for the web client."""

from typing import Any

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.repository.layout import layout_metadata


def build_relation_graph(index: SymbolIndex) -> dict[str, Any]:
    """Return only symbols and calls proven by the existing static index.

    Unresolved calls stay in a separate list so the UI can show review work
    without presenting a guess as a confirmed relationship.
    """
    graph = CallGraph(index).build()
    nodes = [
        {
            "id": symbol.symbol_id,
            "kind": "function",
            "module": symbol.module,
            "name": symbol.qualified_name,
            "file": symbol.file.as_posix(),
            "line": symbol.definition.lineno,
            "end_line": symbol.definition.end_lineno,
            "parameters": [
                {
                    "name": parameter.name,
                    "kind": parameter.kind,
                    "has_default": parameter.has_default,
                }
                for parameter in getattr(symbol.definition, "parameters", ())
            ],
        }
        for _, symbol in sorted(index.symbols.items())
    ]
    edges = [
        {
            "id": f"{edge.caller_symbol_id}->{edge.callee_symbol_id}@{edge.file.as_posix()}:{edge.line}:{edge.col_offset}",
            "source": edge.caller_symbol_id,
            "target": edge.callee_symbol_id,
            "kind": "call",
            "location": {
                "file": edge.file.as_posix(),
                "line": edge.line,
                "column": edge.col_offset,
            },
            "resolution_basis": edge.basis,
        }
        for edge in sorted(
            graph.edges,
            key=lambda item: (item.caller_symbol_id, item.callee_symbol_id,
                              item.file.as_posix(), item.line, item.col_offset),
        )
    ]
    unresolved = [
        {
            "caller": item.caller_symbol_id,
            "file": item.file.as_posix(),
            "line": item.line,
            "column": item.call.col_offset,
            "expression": item.call.expression,
            "reason": item.reason,
        }
        for item in sorted(
            graph.unresolved_calls,
            key=lambda value: (value.file.as_posix(), value.line,
                               value.call.col_offset, value.call.expression),
        )
    ]
    parse_errors = [
        {
            "file": path.as_posix(),
            "kind": diagnostic.kind,
            "line": diagnostic.lineno,
            "column": diagnostic.col_offset,
            "message": diagnostic.message,
        }
        for path, diagnostics in sorted(index.parse_diagnostics.items())
        for diagnostic in diagnostics
    ]
    coverage = {
        "status": "partial" if parse_errors or unresolved or index.ambiguous_modules
        or index.ambiguous_symbols or index.unsupported_scope_diagnostics() else "complete",
        "python_files": len(index.parsed_files),
        "indexed_modules": len(index.modules),
        "indexed_functions": len(index.symbols),
        "resolved_calls": len(edges),
        "unresolved_calls": len(unresolved),
        "files_with_parse_errors": len(index.parse_diagnostics),
    }
    return {
        "schema_version": 1,
        "analysis_layout": layout_metadata(index.analysis_root),
        "graph": {"nodes": nodes, "edges": edges},
        "diagnostics": {
            "unresolved_calls": unresolved,
            "parse_errors": parse_errors,
            "ambiguous_modules": sorted(index.ambiguous_modules),
            "ambiguous_symbols": sorted(index.ambiguous_symbols),
            "unsupported_scopes": index.unsupported_scope_diagnostics(),
        },
        "coverage": coverage,
    }
