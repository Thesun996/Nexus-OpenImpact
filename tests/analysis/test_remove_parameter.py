"""Removing a parameter uses canonical signature binding and existing propagation."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.change_file import ChangeFileError, change_spec_from_dict
from openimpact.analysis.change_spec import (
    AddedParameter, ChangeOperationError, ChangeSpec, ChangeType, FunctionSignature,
    RemoveParameterOperation, operation_from_dict, validate_change_spec,
)
from openimpact.analysis.direct_impact import analyze_direct_impact
from openimpact.analysis.indirect_impact import propagate_indirect_impact
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex


def graph_from(tmp_path, files):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return CallGraph(SymbolIndex(tmp_path).build()).build()


def spec_for(graph, name="b", target="utils.f"):
    before = FunctionSignature.from_definition(graph.index.symbols[target].definition)
    return ChangeSpec.from_operation(target, before, RemoveParameterOperation(name))


@pytest.mark.parametrize("name", ["a", "b", "mode"])
def test_supported_kinds_preserve_all_remaining_signature_facts(name):
    before = FunctionSignature("f", (
        Parameter("a", "positional_only", annotation_source="str"),
        Parameter("b", "positional_or_keyword", True, "2", "int"),
        Parameter("args", "var_positional"),
        Parameter("mode", "keyword_only", True, "'x'", "str"),
        Parameter("kwargs", "var_keyword"),
    ), is_async=True, return_annotation_source="str")
    operation = RemoveParameterOperation(name)
    spec = ChangeSpec.from_operation("utils.f", before, operation)
    assert spec.after.parameters == tuple(p for p in before.parameters if p.name != name)
    assert spec.after.name == before.name
    assert spec.after.is_async == before.is_async
    assert spec.after.return_annotation_source == before.return_annotation_source
    assert operation.validate_delta(before, spec.after) is None
    assert operation.change_type is ChangeType.REMOVE_PARAMETER
    assert spec.added_parameter is None
    assert operation_from_dict(json.loads(json.dumps(operation.to_dict()))) == operation
    assert change_spec_from_dict(json.loads(json.dumps(spec.to_dict()))) == spec
    public = spec.to_dict(include_operation=False)
    assert public["operation"] == {"change_type": "remove_parameter", "parameter_name": name}
    assert public["added_parameter"] is None
    assert change_spec_from_dict(public) == spec


@pytest.mark.parametrize("payload,code", [
    ({"change_type": "remove_parameter"}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": None}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": 1}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": []}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": ""}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": "bad name"}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": "for"}, "invalid_operation_payload"),
    ({"change_type": "remove_parameter", "parameter_name": "b", "insert_before": "a"}, "invalid_operation_payload"),
    ({"change_type": "rename_parameter", "parameter_name": "b"}, "invalid_operation_payload"),
])
def test_invalid_remove_payload_is_rejected(payload, code):
    with pytest.raises(ChangeOperationError) as error:
        operation_from_dict(payload)
    assert error.value.code == code


@pytest.mark.parametrize("name,code", [
    ("missing", "parameter_not_found"), ("args", "unsupported_parameter_kind"),
    ("kwargs", "unsupported_parameter_kind"),
])
def test_missing_and_variadic_parameters_are_explicitly_rejected(name, code):
    before = FunctionSignature("f", (Parameter("a", "positional_or_keyword"),
        Parameter("args", "var_positional"), Parameter("kwargs", "var_keyword")))
    operation = RemoveParameterOperation(name)
    with pytest.raises(ChangeOperationError) as error:
        operation.build_after(before)
    assert error.value.code == code
    assert operation.validate_delta(before, before).code == code


@pytest.mark.parametrize("mutation", ["wrong_parameter", "two_parameters", "rename", "kind", "default",
                                          "annotation", "reorder", "async", "return_annotation", "function_name"])
def test_remove_delta_cannot_modify_any_other_signature_fact(mutation):
    before = FunctionSignature("f", (Parameter("a", "positional_only"),
        Parameter("b", "positional_or_keyword"), Parameter("c", "positional_or_keyword", True, "2", "int"),
        Parameter("mode", "keyword_only", True, "'x'")))
    operation = RemoveParameterOperation("b")
    after = operation.build_after(before)
    if mutation == "wrong_parameter":
        after = replace(after, parameters=(before.parameters[1], *before.parameters[2:]))
    elif mutation == "two_parameters":
        after = replace(after, parameters=after.parameters[1:])
    elif mutation in {"rename", "kind", "default", "annotation"}:
        changes = {"rename": {"name": "other"}, "kind": {"kind": "keyword_only"},
                   "default": {"default_source": "3"}, "annotation": {"annotation_source": "float"}}
        after = replace(after, parameters=(after.parameters[0],
            replace(after.parameters[1], **changes[mutation]), after.parameters[2]))
    elif mutation == "reorder":
        after = replace(after, parameters=tuple(reversed(after.parameters)))
    else:
        changes = {"async": {"is_async": True}, "return_annotation": {"return_annotation_source": "int"},
                   "function_name": {"name": "g"}}
        after = replace(after, **changes[mutation])
    assert operation.validate_delta(before, after).code == "operation_signature_mismatch"


@pytest.mark.parametrize("declaration,call,name,before_status,after_status,effect,after_rule", [
    ("a, b", "f(1, 2)", "b", "compatible", "incompatible", "direct_impact", "too_many_positional_arguments"),
    ("a, b", "f(a=1, b=2)", "b", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, b", "f(1, b=2)", "b", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, b=2", "f(1)", "b", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, b=2", "f(1, 2)", "b", "compatible", "incompatible", "direct_impact", "too_many_positional_arguments"),
    ("a, b=2", "f(1, b=2)", "b", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, *, mode='x'", "f(1, mode='y')", "mode", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, *, mode='x'", "f(1)", "mode", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, b, /", "f(1, 2)", "b", "compatible", "incompatible", "direct_impact", "too_many_positional_arguments"),
    ("a, b, /", "f(a=1, b=2)", "b", "incompatible", "incompatible", "pre_existing_problem", "unexpected_keyword_argument"),
    ("a, b", "f()", "b", "incompatible", "incompatible", "pre_existing_problem", "required_parameter_missing"),
    ("a, b", "f(1, 2, 3)", "b", "incompatible", "incompatible", "pre_existing_problem", "too_many_positional_arguments"),
    ("a, b", "f(1)", "b", "incompatible", "compatible", "compatibility_improved", "arguments_bind"),
    ("a, b", "f(1, *args)", "b", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, b", "f(1, **kwargs)", "b", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, b, *args", "f(1, 2)", "b", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, b, **kwargs", "f(1, b=2)", "b", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, b, c=3", "f(1, 2)", "b", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, b, c", "f(1, 2, c=3)", "b", "compatible", "incompatible", "direct_impact", "multiple_values_for_parameter"),
])
def test_direct_matrix_uses_only_canonical_signatures(
    tmp_path, declaration, call, name, before_status, after_status, effect, after_rule
):
    graph = graph_from(tmp_path, {"utils.py": f"def f({declaration}):\n    pass\n",
        "caller.py": f"from utils import f\ndef caller(args, kwargs):\n    {call}\n"})
    spec = spec_for(graph, name)
    with patch.object(RemoveParameterOperation, "build_after", side_effect=AssertionError("rebuild")):
        result = analyze_direct_impact(graph, spec)
    assert result.validation.valid
    assert len(result.assessments) == 1
    assessment = result.assessments[0]
    assert (assessment.before_status, assessment.after_status, assessment.effect) == (before_status, after_status, effect)
    assert assessment.after_rule_id == after_rule
    assert result.direct_impact_count == (1 if effect == "direct_impact" else 0)
    if effect == "direct_impact":
        finding = result.findings[0]
        assert finding.rule_id == "parameter_removed_breaks_call"
        assert finding.reason == f"修改前调用兼容；修改后{assessment.after_reason}"
        assert (finding.source_file, finding.source_location.line, finding.call_expression) == (Path("caller.py"), 3, call)
    if effect in {"no_impact", "pre_existing_problem", "compatibility_improved"}:
        assert result.findings == ()


def test_only_exact_resolved_symbol_calls_are_assessed(tmp_path):
    graph = graph_from(tmp_path, {
        "utils.py": "def f(a, b): pass\n", "other.py": "def f(a, b): pass\n",
        "caller.py": "from utils import f\nfrom other import f as other\nfrom missing import f as unknown\n"
                     "def caller():\n    f(1, 2)\n    other(1, 2)\n    unknown(1, 2)\n",
    })
    result = analyze_direct_impact(graph, spec_for(graph))
    assert result.direct_impact_count == 1
    assert len(result.assessments) == 1
    assert result.assessments[0].target_symbol_id == "utils.f"
    assert result.assessments[0].line == 5
    assert len(graph.unresolved_calls) == 1


def test_multiple_seeds_cycles_and_paths_reuse_existing_reverse_propagation(tmp_path):
    graph = graph_from(tmp_path, {
        "utils.py": "def f(a, b): pass\n",
        "work.py": "from utils import f\n"
            "def report_a():\n    f(1, 2)\n    dashboard()\n"
            "def report_b():\n    f(1, 2)\n"
            "def dashboard():\n    report_a()\n    report_b()\n"
            "def page():\n    dashboard()\n    report_a()\n"
            "def outer():\n    page()\n"
            "def beyond():\n    outer()\n",
    })
    direct = analyze_direct_impact(graph, spec_for(graph))
    indirect = propagate_indirect_impact(graph, direct)
    assert direct.direct_impact_count == 2
    by_symbol = {finding.impacted_symbol_id: finding for finding in indirect.findings}
    assert len(by_symbol) == len(indirect.findings) == 3
    assert {symbol: item.impact_type for symbol, item in by_symbol.items()} == {
        "work.dashboard": "indirect_1hop", "work.page": "indirect_1hop", "work.outer": "indirect_2hop"}
    assert "work.beyond" not in by_symbol
    assert len(by_symbol["work.dashboard"].sources) == len(by_symbol["work.page"].sources) == 2
    page_paths = by_symbol["work.page"].sources
    assert {len(source.propagation_path) for source in page_paths} == {2, 3}
    for item in indirect.findings:
        assert item.certainty == "needs_review"
        for source in item.sources:
            path = source.propagation_path
            symbols = [path[0].caller_symbol_id, *(edge.callee_symbol_id for edge in path)]
            assert len(symbols) == len(set(symbols))
            assert symbols[-1] == "utils.f"
            seed = source.source_direct_impact
            assert seed.effect == "direct_impact"
            assert (path[-1].file, path[-1].line, path[-1].col_offset) == (
                seed.assessment.file, seed.assessment.line, seed.assessment.col_offset)


@pytest.mark.parametrize("declaration,call,effect", [
    ("a, b=2", "f(1)", "no_impact"),
    ("a, b", "f()", "pre_existing_problem"),
    ("a, b", "f(1)", "compatibility_improved"),
    ("a, b", "f(1, *args)", "manual_review"),
    ("a, b", "f(1, **kwargs)", "manual_review"),
])
def test_non_definite_results_never_seed_indirect_propagation(tmp_path, declaration, call, effect):
    graph = graph_from(tmp_path, {"utils.py": f"def f({declaration}): pass\n",
        "work.py": f"from utils import f\ndef report(args, kwargs):\n    {call}\n"
                   "def page():\n    report((), {})\n"})
    direct = analyze_direct_impact(graph, spec_for(graph))
    assert direct.assessments[0].effect == effect
    assert direct.direct_impact_count == 0
    assert propagate_indirect_impact(graph, direct).findings == ()


def test_invalid_source_before_or_delta_cannot_enter_analysis(tmp_path):
    graph = graph_from(tmp_path, {"utils.py": "def f(a, b): pass\n",
        "caller.py": "from utils import f\ndef caller():\n    f(1, 2)\n"})
    spec = spec_for(graph)
    for invalid, code in [
        (replace(spec, before=FunctionSignature("f", ())), "before_mismatch"),
        (replace(spec, after=spec.before), "operation_signature_mismatch"),
        (replace(spec, target_symbol_id="missing.f"), "target_not_found"),
    ]:
        result = analyze_direct_impact(graph, invalid)
        assert result.validation.diagnostics[0].code == code
        assert result.assessments == result.findings == ()
        assert propagate_indirect_impact(graph, result).findings == ()


def test_remove_never_accepts_added_parameter_intent(tmp_path):
    graph = graph_from(tmp_path, {"utils.py": "def f(a, b): pass\n"})
    spec = spec_for(graph)
    with pytest.raises(ChangeOperationError, match="不一致"):
        replace(spec, added_parameter=AddedParameter("b", "positional_or_keyword"))
    with pytest.raises(ChangeFileError, match="不一致"):
        change_spec_from_dict({**spec.to_dict(), "change_type": "add_required_parameter"})


def test_source_is_unchanged_after_remove_construction_and_analysis(tmp_path):
    graph = graph_from(tmp_path, {"utils.py": "def f(a, b=2): pass\n",
        "caller.py": "from utils import f\ndef caller():\n    f(1, 2)\n"})
    original = {path: path.read_bytes() for path in tmp_path.glob("*.py")}
    spec = spec_for(graph)
    assert validate_change_spec(graph.index, spec).valid
    analyze_direct_impact(graph, spec)
    assert {path: path.read_bytes() for path in tmp_path.glob("*.py")} == original
