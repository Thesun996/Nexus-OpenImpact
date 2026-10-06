"""Locate named test candidates on existing definite impact paths; never run them."""

from fnmatch import fnmatchcase

from openimpact.reporting.source_reader import read_source_snapshot


LIMITATIONS = (
    "仅识别 test_*.py 或 *_test.py 中以 test 开头的模块级函数；按 pytest 默认命名筛选，未实际收集或运行测试。",
    "仅复用确定直接影响及最多两层上游的已有代表路径；关联不保证测试会执行到该位置或运行失败。",
    "自定义收集配置、类方法、fixture、动态调用及更深的路径未覆盖；未列出的测试也可能需要检查。",
    "当前覆盖不完整时，测试定位也不完整；不能将空列表视为无需回归测试。",
)


def is_test_file(path):
    return fnmatchcase(path.name, "test_*.py") or fnmatchcase(path.name, "*_test.py")


def unavailable_tests():
    return {"status": "unavailable", "candidates": [], "limitations": list(LIMITATIONS),
            "diagnostics": [{"code": "related_tests_unavailable",
                             "message": "相关测试定位暂不可用，已有影响结果仍可查看。"}]}


def build_related_tests(run):
    """Optional enrichment: no test-shaped files keeps the old report unchanged."""
    files = sorted(file for file in run.index.parsed_files if is_test_file(file))
    if not files:
        return None
    tests = {key: symbol for key, symbol in run.index.symbols.items()
             if is_test_file(symbol.file) and symbol.qualified_name.startswith("test")}
    result = {"status": "available", "scope": "pytest_named_module_functions",
              "max_upstream_hops": 2, "test_file_count": len(files),
              "indexed_test_count": len(tests), "candidates": [],
              "limitations": list(LIMITATIONS), "diagnostics": []}
    if not run.direct.validation.valid:
        return {**result, "status": "unavailable",
                "diagnostics": [{"code": "change_not_validated", "message": "变更未通过校验，不能定位相关测试。"}]}

    edges_by_site = {(edge.caller_symbol_id, edge.callee_symbol_id, edge.file,
                      edge.line, edge.col_offset): edge for edge in run.graph.edges}
    calls_by_site = {(file, call.lineno, call.col_offset): call
                     for module, file in run.index.modules.items()
                     for call in run.index.parsed_modules[module].calls}
    source_cache = {}

    def source_data(edge):
        key = (edge.file, edge.line, edge.col_offset)
        if key not in source_cache:
            call = calls_by_site.get(key)
            snippet, digest = None, None
            diagnostics = []
            try:
                if call is None or not call.call_expression:
                    raise ValueError("missing_original_call")
                _, snippet, digest, errors = read_source_snapshot(
                    run.project_path, edge.file.as_posix(), edge.line, edge.col_offset,
                    call.end_lineno or call.lineno)
                diagnostics = [{"code": error.code, "message": error.message} for error in errors]
                if snippet is not None and not diagnostics:
                    at_column = snippet.splitlines()[0].encode("utf-8")[edge.col_offset:].decode("utf-8")
                    if not at_column.startswith(call.call_expression.splitlines()[0]) or call.call_expression not in snippet:
                        snippet = None
                        diagnostics = [{"code": "source_snapshot_mismatch", "message": "调用源码已变化，请重新分析后定位测试。"}]
            except Exception:
                snippet = None
                diagnostics = [{"code": "test_source_unavailable", "message": "测试关联位置的源码暂不可用，请人工核查。"}]
            source_cache[key] = {"source_snippet": snippet, "source_hash": digest,
                                 "status": "available" if snippet is not None and not diagnostics else "unavailable",
                                 "diagnostics": diagnostics}
        return {"caller_symbol_id": edge.caller_symbol_id, "callee_symbol_id": edge.callee_symbol_id,
                "file": edge.file.as_posix(), "line": edge.line, "column": edge.col_offset,
                **source_cache[key]}

    by_test = {}

    def add_path(symbol_id, path, seed):
        if symbol_id not in tests:
            return
        # Only paths already computed from a definite seed are accepted. Do not
        # infer relationships from file names or include manual/unresolved seeds.
        if (not 1 <= len(path) <= 3 or path[0].caller_symbol_id != symbol_id
                or path[-1].callee_symbol_id != run.change_spec.target_symbol_id
                or any(a.callee_symbol_id != b.caller_symbol_id for a, b in zip(path, path[1:]))
                or any(edge not in run.graph.edges for edge in path)):
            raise ValueError("invalid_existing_test_path")
        symbol = tests[symbol_id]
        candidate = by_test.setdefault(symbol_id, {
            "test_symbol_id": symbol_id, "file": symbol.file.as_posix(),
            "line": symbol.definition.lineno,
            "node_id": f"{symbol.file.as_posix()}::{symbol.qualified_name}", "paths": [],
        })
        key = seed.evidence_reference
        if any(item["direct_evidence_reference"] == key for item in candidate["paths"]):
            return
        sites = [source_data(edge) for edge in path]
        candidate["paths"].append({"direct_evidence_reference": key,
                                   "impact_type": "direct" if len(path) == 1 else f"indirect_{len(path) - 1}hop",
                                   "status": "available" if all(site["status"] == "available" for site in sites) else "unavailable",
                                   "call_sites": sites})

    for seed in run.direct.findings:
        if seed.effect != "direct_impact":
            continue
        call = seed.assessment
        edge = edges_by_site.get((call.caller_symbol_id, call.target_symbol_id,
                                  call.file, call.line, call.col_offset))
        if call.caller_symbol_id in tests:
            if edge is None:
                raise ValueError("missing_direct_test_edge")
            add_path(call.caller_symbol_id, (edge,), seed)
    for finding in run.indirect.findings:
        for source in finding.sources:
            if source.source_direct_impact.effect != "direct_impact":
                continue
            add_path(finding.impacted_symbol_id, source.propagation_path, source.source_direct_impact)

    for candidate in by_test.values():
        candidate["paths"].sort(key=lambda path: (len(path["call_sites"]), path["direct_evidence_reference"]))
        candidate["relationship"] = "direct" if len(candidate["paths"][0]["call_sites"]) == 1 else "upstream"
        candidate["reason"] = (
            "该候选测试包含本次变更新引入的不兼容调用，建议先核对调用与断言。"
            if candidate["relationship"] == "direct" else
            "该候选测试位于已确认直接影响的上游路径，建议检查是否覆盖这条路径及相关断言。"
        )
    result["candidates"] = sorted(by_test.values(), key=lambda item: (
        item["relationship"] != "direct", len(item["paths"][0]["call_sites"]), item["file"], item["line"]))
    return result
