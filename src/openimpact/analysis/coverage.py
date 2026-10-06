"""Explain partial syntax/call coverage without inventing a completeness percentage."""


def coverage_details(index, graph=None):
    excluded = sum(scope.call_count for parsed in index.parsed_files.values()
                   for scope in parsed.unsupported_call_scopes)
    result = {'python_files': len(index.parsed_files),
              'parsed_python_files': len(index.parsed_files) - len(index.parse_diagnostics),
              'named_caller_count': len(index.callers), 'excluded_call_count': excluded}
    if graph is not None:
        result.update(resolved_call_count=len(graph.edges), unresolved_call_count=len(graph.unresolved_calls))
    return result
