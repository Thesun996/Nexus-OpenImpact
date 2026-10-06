"""Explain partial syntax/call coverage without inventing a completeness percentage."""

from openimpact.analysis.models import CallScope, FunctionDefinition


def coverage_details(index, graph=None):
    excluded = sum(scope.call_count for parsed in index.parsed_files.values()
                   for scope in parsed.unsupported_call_scopes)
    result = {'python_files': len(index.parsed_files),
              'parsed_python_files': len(index.parsed_files) - len(index.parse_diagnostics),
              'named_caller_count': sum(isinstance(item.definition, FunctionDefinition)
                                        for item in index.callers.values()), 'excluded_call_count': excluded}
    scopes = sum(isinstance(item.definition, CallScope) for item in index.callers.values())
    if scopes:
        result['additional_call_scope_count'] = scopes
    if graph is not None:
        result.update(resolved_call_count=len(graph.edges), unresolved_call_count=len(graph.unresolved_calls))
    return result
