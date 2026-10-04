"""Removing one default keeps signature facts and generic impact attribution."""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.change_file import ChangeFileError, change_spec_from_dict
from openimpact.analysis.change_spec import (
    AddedParameter, ChangeOperationError, ChangeSpec, ChangeType, FunctionSignature,
    MakeParameterRequiredOperation, operation_from_dict, validate_change_spec,
)
from openimpact.analysis.direct_impact import analyze_direct_impact
from openimpact.analysis.indirect_impact import propagate_indirect_impact
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex


def graph_from(tmp_path, files):
    for name, source in files.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    return CallGraph(SymbolIndex(tmp_path).build()).build()


def spec_for(graph, target="utils.f", name="timeout"):
    before = FunctionSignature.from_definition(graph.index.symbols[target].definition)
    return ChangeSpec.from_operation(target, before, MakeParameterRequiredOperation(name))


@pytest.mark.parametrize("kind", ["positional_only", "positional_or_keyword", "keyword_only"])
def test_immutable_operation_only_removes_the_default_and_round_trips(kind):
    before = FunctionSignature("f", (
        Parameter("timeout", kind, True, "None", "int | None"),
        Parameter("mode", "keyword_only", True, "'x'", "str"),
    ), is_async=True, return_annotation_source="str")
    operation = MakeParameterRequiredOperation("timeout")
    spec = ChangeSpec.from_operation("utils.f", before, operation)
    assert operation.change_type is ChangeType.MAKE_PARAMETER_REQUIRED
    expected = replace(before.parameters[0], has_default=False, default_source=None)
    assert spec.after == replace(before, parameters=(expected, before.parameters[1]))
    assert before.parameters[0].has_default is True
    assert before.parameters[0].default_source == "None"
    assert operation.validate_delta(before, spec.after) is None
    with pytest.raises(FrozenInstanceError):
        operation.parameter_name = "changed"
    assert operation_from_dict(json.loads(json.dumps(operation.to_dict()))) == operation
    for public in (spec.to_dict(), spec.to_dict(include_operation=False)):
        assert public["operation"] == {"change_type": "make_parameter_required", "parameter_name": "timeout"}
        assert public["added_parameter"] is None
        assert change_spec_from_dict(json.loads(json.dumps(public))) == spec


@pytest.mark.parametrize("literal", ["None", "False", "0", "''", '""'])
def test_falsy_default_values_are_still_defaults_in_real_source(tmp_path, literal):
    graph = graph_from(tmp_path, {"utils.py": f"def f(timeout={literal}): pass\n"})
    spec = spec_for(graph)
    assert spec.before.parameters[0].has_default is True
    assert spec.before.parameters[0].default_source is not None
    assert spec.after.parameters[0].has_default is False
    assert spec.after.parameters[0].default_source is None
    assert validate_change_spec(graph.index, spec).valid


@pytest.mark.parametrize("payload,code", [
    ({"change_type": "make_parameter_required"}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": None}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": []}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": "for"}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": ""}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": "bad name"}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": "timeout", "default": None}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_required", "parameter_name": "timeout", "insert_before": "a"}, "invalid_operation_payload"),
    ({"change_type": "make_parameter_optional", "parameter_name": "timeout"}, "unsupported_change_type"),
])
def test_illegal_operation_payloads_are_rejected(payload, code):
    with pytest.raises(ChangeOperationError) as error:
        operation_from_dict(payload)
    assert error.value.code == code


def test_concrete_decoder_rejects_another_operation_discriminator():
    with pytest.raises(ChangeOperationError) as error:
        MakeParameterRequiredOperation.from_dict({"change_type": "remove_parameter", "parameter_name": "timeout"})
    assert error.value.code == "unsupported_change_type"


@pytest.mark.parametrize("name,code", [
    ("missing", "parameter_not_found"), ("a", "parameter_already_required"),
    ("args", "unsupported_parameter_kind"), ("kwargs", "unsupported_parameter_kind"),
])
def test_target_existence_default_presence_and_kind_are_checked(name, code):
    before = FunctionSignature("f", (Parameter("a", "positional_or_keyword"),
        Parameter("timeout", "positional_or_keyword", True, "30"),
        Parameter("args", "var_positional"), Parameter("kwargs", "var_keyword")))
    operation = MakeParameterRequiredOperation(name)
    with pytest.raises(ChangeOperationError) as error:
        operation.build_after(before)
    assert error.value.code == code
    assert operation.validate_delta(before, before).code == code


@pytest.mark.parametrize("declaration,name,valid", [
    ("a=1, timeout=30", "timeout", False),
    ("a=1, timeout=30", "a", True),
    ("a=1, timeout=30, /", "timeout", False),
    ("a=1, /, timeout=30", "timeout", False),
    ("a=1, /, timeout=30", "a", True),
    ("a, /, timeout=30", "timeout", True),
    ("a=1, *, timeout=30", "timeout", True),
    ("a=1, /, *, timeout=30", "timeout", True),
    ("a=1, *args, timeout=30, mode='x', **kwargs", "timeout", True),
])
def test_python_default_ordering_is_enforced_without_reordering(tmp_path, declaration, name, valid):
    graph = graph_from(tmp_path, {"utils.py": f"def f({declaration}): pass\n"})
    before = FunctionSignature.from_definition(graph.index.symbols["utils.f"].definition)
    operation = MakeParameterRequiredOperation(name)
    parameters = tuple(replace(p, has_default=False, default_source=None) if p.name == name else p
                       for p in before.parameters)
    expected = replace(before, parameters=parameters)
    declared = ChangeSpec("make_parameter_required", "utils.f", before, expected, operation=operation)
    validation = validate_change_spec(graph.index, declared)
    assert validation.valid is valid
    diagnostic = operation.validate_delta(before, expected)
    if valid:
        assert diagnostic is None
        assert operation.build_after(before) == expected
    else:
        assert diagnostic.code == "invalid_after_signature"
        with pytest.raises(ChangeOperationError) as error:
            operation.build_after(before)
        assert error.value.code == "invalid_after_signature"
        assert validation.diagnostics[0].code == "invalid_after_signature"
        assert analyze_direct_impact(graph, declared).assessments == ()
    assert [p.name for p in before.parameters] == [p.name for p in expected.parameters]
    assert (tmp_path / "utils.py").read_text(encoding="utf-8") == f"def f({declaration}): pass\n"


@pytest.mark.parametrize("mutation", ["no_change", "default_retained", "other_default", "rename", "kind",
    "annotation", "order", "remove", "insert", "async", "return_annotation", "function_name"])
def test_delta_rejects_every_change_beyond_the_one_default_removal(mutation):
    before = FunctionSignature("f", (Parameter("a", "positional_or_keyword"),
        Parameter("timeout", "positional_or_keyword", True, "30", "int"),
        Parameter("mode", "keyword_only", True, "'x'")))
    operation = MakeParameterRequiredOperation("timeout")
    after = operation.build_after(before)
    if mutation == "no_change":
        after = before
    elif mutation in {"default_retained", "rename", "kind", "annotation"}:
        changes = {"default_retained": {"default_source": "None"}, "rename": {"name": "delay"},
            "kind": {"kind": "keyword_only"}, "annotation": {"annotation_source": "float"}}
        after = replace(after, parameters=(after.parameters[0],
            replace(after.parameters[1], **changes[mutation]), after.parameters[2]))
    elif mutation == "other_default":
        after = replace(after, parameters=(*after.parameters[:2], replace(after.parameters[2], has_default=False, default_source=None)))
    elif mutation == "order":
        after = replace(after, parameters=(after.parameters[1], after.parameters[0], after.parameters[2]))
    elif mutation == "remove":
        after = replace(after, parameters=after.parameters[:1] + after.parameters[2:])
    elif mutation == "insert":
        after = replace(after, parameters=after.parameters + (Parameter("extra", "keyword_only"),))
    else:
        changes = {"async": {"is_async": True}, "return_annotation": {"return_annotation_source": "int"},
            "function_name": {"name": "g"}}
        after = replace(after, **changes[mutation])
    assert operation.validate_delta(before, after).code == "operation_signature_mismatch"


@pytest.mark.parametrize("declaration,call,before_status,after_status,effect,after_rule", [
    ("a, timeout=30", "f(1)", "compatible", "incompatible", "direct_impact", "required_parameter_missing"),
    ("a, timeout=30", "f(1, 10)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, timeout=30", "f(1, timeout=10)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, *, timeout=30", "f(1)", "compatible", "incompatible", "direct_impact", "required_parameter_missing"),
    ("a, *, timeout=30", "f(1, timeout=10)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, timeout=30, /", "f(1)", "compatible", "incompatible", "direct_impact", "required_parameter_missing"),
    ("a, timeout=30, /", "f(1, 10)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, timeout=30, /", "f(1, timeout=10)", "incompatible", "incompatible", "pre_existing_problem", "unexpected_keyword_argument"),
    ("a, timeout=30", "f()", "incompatible", "incompatible", "pre_existing_problem", "required_parameter_missing"),
    ("a, timeout=30", "f(1, extra=5)", "incompatible", "incompatible", "pre_existing_problem", "unexpected_keyword_argument"),
    ("a, timeout=30", "f(1, 2, 3)", "incompatible", "incompatible", "pre_existing_problem", "too_many_positional_arguments"),
    ("a, timeout=30", "f(*args)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout=30", "f(**kwargs)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout=30", "f(1, timeout=10, **kwargs)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout=30, **kwargs", "f(1)", "compatible", "incompatible", "direct_impact", "required_parameter_missing"),
    ("a, *args, timeout=30", "f(1, 10)", "compatible", "incompatible", "direct_impact", "required_parameter_missing"),
])
def test_direct_matrix_uses_canonical_signatures_without_operation_reconstruction(
    tmp_path, declaration, call, before_status, after_status, effect, after_rule
):
    graph = graph_from(tmp_path, {"utils.py": f"def f({declaration}): pass\n",
        "caller.py": f"from utils import f\ndef caller(args, kwargs):\n    {call}\n"})
    spec = spec_for(graph)
    with patch.object(MakeParameterRequiredOperation, "build_after", side_effect=AssertionError("rebuild")):
        result = analyze_direct_impact(graph, spec)
    assert result.validation.valid
    assessment, = result.assessments
    assert (assessment.before_status, assessment.after_status, assessment.effect) == (before_status, after_status, effect)
    assert assessment.after_rule_id == after_rule
    assert result.direct_impact_count == (1 if effect == "direct_impact" else 0)
    if effect == "direct_impact":
        finding, = result.findings
        assert finding.rule_id == "parameter_became_required_breaks_call"
        assert finding.reason == f"修改前调用兼容；修改后{assessment.after_reason}"
        assert (finding.source_file, finding.source_location.line, finding.call_expression) == (Path("caller.py"), 3, call)
    elif effect != "manual_review":
        assert result.findings == ()
    if effect != "direct_impact":
        assert propagate_indirect_impact(graph, result).findings == ()


def test_multiple_direct_seeds_cycles_and_dedup_reuse_existing_propagation(tmp_path):
    graph = graph_from(tmp_path, {
        "utils.py": "def f(a, timeout=30): pass\n",
        "work.py": "from utils import f\n"
            "def report_a():\n    f(1)\n    dashboard()\n"
            "def report_b():\n    f(1)\n"
            "def dashboard():\n    report_a()\n    report_b()\n"
            "def page():\n    dashboard()\n    report_a()\n"
            "def outer():\n    page()\n"
            "def beyond():\n    outer()\n",
    })
    direct = analyze_direct_impact(graph, spec_for(graph))
    indirect = propagate_indirect_impact(graph, direct)
    assert direct.direct_impact_count == 2
    by_symbol = {f.impacted_symbol_id: f for f in indirect.findings}
    assert len(by_symbol) == len(indirect.findings) == 3
    assert {symbol: finding.impact_type for symbol, finding in by_symbol.items()} == {
        "work.dashboard": "indirect_1hop", "work.page": "indirect_1hop", "work.outer": "indirect_2hop"}
    assert "work.beyond" not in by_symbol
    assert len(by_symbol["work.dashboard"].sources) == len(by_symbol["work.page"].sources) == 2
    for finding in indirect.findings:
        assert finding.certainty == "needs_review"
        for source in finding.sources:
            path = source.propagation_path
            symbols = [path[0].caller_symbol_id, *(edge.callee_symbol_id for edge in path)]
            assert len(symbols) == len(set(symbols))
            assert symbols[-1] == "utils.f"
            seed = source.source_direct_impact
            assert seed.effect == "direct_impact"
            assert (path[-1].file, path[-1].line, path[-1].col_offset) == (
                seed.assessment.file, seed.assessment.line, seed.assessment.col_offset)


def test_resolved_target_isolation_invalid_declarations_and_source_immutability(tmp_path):
    graph = graph_from(tmp_path, {
        "utils.py": "def f(a, timeout=30): return a\n", "other.py": "def f(a, timeout=30): return a\n",
        "caller.py": "from utils import f\nfrom other import f as other\nfrom missing import f as unknown\n"
            "def caller():\n    f(1)\n    other(1)\n    unknown(1)\n",
    })
    original = {p: p.read_bytes() for p in tmp_path.glob("*.py")}
    spec = spec_for(graph)
    result = analyze_direct_impact(graph, spec)
    assert len(result.assessments) == result.direct_impact_count == 1
    assert result.assessments[0].target_symbol_id == "utils.f"
    assert result.assessments[0].line == 5
    assert len(graph.unresolved_calls) == 1
    for invalid, code in [
        (replace(spec, before=FunctionSignature("f", ())), "before_mismatch"),
        (replace(spec, after=spec.before), "operation_signature_mismatch"),
        (replace(spec, target_symbol_id="missing.f"), "target_not_found"),
    ]:
        assert validate_change_spec(graph.index, invalid).diagnostics[0].code == code
        assert analyze_direct_impact(graph, invalid).assessments == ()
    with pytest.raises(ChangeOperationError):
        replace(spec, added_parameter=AddedParameter("timeout", "positional_or_keyword"))
    with pytest.raises(ChangeFileError):
        change_spec_from_dict({**spec.to_dict(), "change_type": "remove_parameter"})
    assert {p: p.read_bytes() for p in original} == original
