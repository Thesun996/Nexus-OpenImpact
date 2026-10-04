"""Rename intent is validated separately from canonical call compatibility."""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.change_file import ChangeFileError, change_spec_from_dict
from openimpact.analysis.change_spec import (
    AddedParameter, ChangeOperationError, ChangeSpec, ChangeType, FunctionSignature,
    RenameParameterOperation, operation_from_dict, validate_change_spec,
)
from openimpact.analysis.direct_impact import analyze_direct_impact
from openimpact.analysis.indirect_impact import propagate_indirect_impact
from openimpact.analysis.models import Parameter
from openimpact.analysis.symbol_index import SymbolIndex


def graph_from(tmp_path, files):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return CallGraph(SymbolIndex(tmp_path).build()).build()


def spec_for(graph, target="utils.f", old="timeout", new="delay"):
    before = FunctionSignature.from_definition(graph.index.symbols[target].definition)
    return ChangeSpec.from_operation(target, before, RenameParameterOperation(old, new))


@pytest.mark.parametrize("kind", ["positional_or_keyword", "keyword_only"])
def test_rename_is_immutable_and_preserves_every_other_signature_fact(kind):
    before = FunctionSignature("f", (
        Parameter("a", "positional_only", annotation_source="str"),
        Parameter("timeout", kind, True, "5", "int"),
        Parameter("kwargs", "var_keyword"),
    ), is_async=True, return_annotation_source="str")
    operation = RenameParameterOperation("timeout", "delay")
    spec = ChangeSpec.from_operation("utils.f", before, operation)
    assert operation.change_type is ChangeType.RENAME_PARAMETER
    assert spec.after == replace(before, parameters=(before.parameters[0],
        replace(before.parameters[1], name="delay"), before.parameters[2]))
    assert operation.validate_delta(before, spec.after) is None
    with pytest.raises(FrozenInstanceError):
        operation.new_parameter_name = "changed"
    assert operation_from_dict(json.loads(json.dumps(operation.to_dict()))) == operation
    for public in (spec.to_dict(), spec.to_dict(include_operation=False)):
        assert public["operation"] == {"change_type": "rename_parameter",
            "parameter_name": "timeout", "new_parameter_name": "delay"}
        assert public["added_parameter"] is None
        assert change_spec_from_dict(json.loads(json.dumps(public))) == spec
    assert "timeout → delay" in spec.describe()


@pytest.mark.parametrize("name", [None, 1, [], "", "bad name", "2delay", "for", "class", "delay\n"])
def test_new_name_must_be_a_python_identifier_and_not_a_keyword(name):
    with pytest.raises(ChangeOperationError) as error:
        RenameParameterOperation("timeout", name)
    assert error.value.code == "invalid_parameter_name"


def test_unicode_python_identifier_is_accepted():
    before = FunctionSignature("f", (Parameter("timeout", "keyword_only"),))
    assert RenameParameterOperation("timeout", "延迟").build_after(before).parameters[0].name == "延迟"


def test_unicode_names_use_the_same_normalization_as_python_keyword_calls(tmp_path):
    graph = graph_from(tmp_path, {"utils.py": "def f(a, timeout): pass\n",
        "caller.py": "from utils import f\ndef caller():\n    f(1, ｄｅｌａｙ=5)\n"})
    spec = spec_for(graph, old="ｔｉｍｅｏｕｔ", new="ｄｅｌａｙ")
    assert spec.operation.parameter_name == "timeout"
    assert spec.operation.new_parameter_name == "delay"
    assert spec.after.parameters[1].name == "delay"
    assert change_spec_from_dict(spec.to_dict()) == spec
    assessment, = analyze_direct_impact(graph, spec).assessments
    assert assessment.effect == "compatibility_improved"


def test_normalized_unicode_name_collision_is_rejected():
    before = FunctionSignature("f", (Parameter("a", "positional_or_keyword"),
        Parameter("timeout", "positional_or_keyword")))
    with pytest.raises(ChangeOperationError) as error:
        RenameParameterOperation("timeout", "ａ").build_after(before)
    assert error.value.code == "parameter_name_conflict"
    with pytest.raises(ChangeOperationError) as error:
        RenameParameterOperation("timeout", "ｔｉｍｅｏｕｔ")
    assert error.value.code == "parameter_name_unchanged"
    with pytest.raises(ChangeOperationError) as error:
        RenameParameterOperation("timeout", "ｆｏｒ")
    assert error.value.code == "invalid_parameter_name"


@pytest.mark.parametrize("payload,code", [
    ({"change_type": "rename_parameter"}, "invalid_operation_payload"),
    ({"change_type": "rename_parameter", "parameter_name": "timeout"}, "invalid_operation_payload"),
    ({"change_type": "rename_parameter", "new_parameter_name": "delay"}, "invalid_operation_payload"),
    ({"change_type": "rename_parameter", "parameter_name": None, "new_parameter_name": "delay"}, "invalid_operation_payload"),
    ({"change_type": "rename_parameter", "parameter_name": "timeout", "new_parameter_name": "delay", "insert_before": "a"}, "invalid_operation_payload"),
    ({"change_type": "fourth_change", "parameter_name": "timeout", "new_parameter_name": "delay"}, "unsupported_change_type"),
])
def test_wrong_rename_payload_is_rejected(payload, code):
    with pytest.raises(ChangeOperationError) as error:
        operation_from_dict(payload)
    assert error.value.code == code


def test_concrete_rename_decoder_checks_the_discriminator():
    with pytest.raises(ChangeOperationError) as error:
        RenameParameterOperation.from_dict({"change_type": "remove_parameter",
            "parameter_name": "timeout", "new_parameter_name": "delay"})
    assert error.value.code == "unsupported_change_type"


@pytest.mark.parametrize("old,new,code", [
    ("missing", "delay", "parameter_not_found"),
    ("a", "delay", "unsupported_parameter_kind"),
    ("args", "delay", "unsupported_parameter_kind"),
    ("kwargs", "delay", "unsupported_parameter_kind"),
    ("timeout", "a", "parameter_name_conflict"),
    ("timeout", "args", "parameter_name_conflict"),
    ("timeout", "kwargs", "parameter_name_conflict"),
])
def test_target_kind_and_name_conflicts_are_explicit(old, new, code):
    before = FunctionSignature("f", (Parameter("a", "positional_only"),
        Parameter("timeout", "positional_or_keyword"), Parameter("args", "var_positional"),
        Parameter("kwargs", "var_keyword")))
    operation = RenameParameterOperation(old, new)
    with pytest.raises(ChangeOperationError) as error:
        operation.build_after(before)
    assert error.value.code == code
    assert operation.validate_delta(before, before).code == code


def test_unchanged_name_is_not_a_rename():
    with pytest.raises(ChangeOperationError) as error:
        RenameParameterOperation("timeout", "timeout")
    assert error.value.code == "parameter_name_unchanged"


@pytest.mark.parametrize("mutation", ["wrong_name", "other_name", "remove", "insert", "kind",
    "default", "optional", "annotation", "order", "async", "return_annotation", "function_name"])
def test_delta_only_allows_the_one_declared_parameter_name_change(mutation):
    before = FunctionSignature("f", (Parameter("a", "positional_or_keyword"),
        Parameter("timeout", "positional_or_keyword", True, "5", "int"),
        Parameter("mode", "keyword_only", True, "'x'")))
    operation = RenameParameterOperation("timeout", "delay")
    after = operation.build_after(before)
    if mutation in {"wrong_name", "kind", "default", "optional", "annotation"}:
        changes = {"wrong_name": {"name": "other"}, "kind": {"kind": "keyword_only"},
            "default": {"default_source": "6"}, "optional": {"has_default": False},
            "annotation": {"annotation_source": "float"}}
        after = replace(after, parameters=(after.parameters[0],
            replace(after.parameters[1], **changes[mutation]), after.parameters[2]))
    elif mutation == "other_name":
        after = replace(after, parameters=(replace(after.parameters[0], name="other"), *after.parameters[1:]))
    elif mutation == "remove":
        after = replace(after, parameters=after.parameters[:1] + after.parameters[2:])
    elif mutation == "insert":
        after = replace(after, parameters=after.parameters + (Parameter("extra", "keyword_only"),))
    elif mutation == "order":
        after = replace(after, parameters=(after.parameters[1], after.parameters[0], after.parameters[2]))
    else:
        changes = {"async": {"is_async": True}, "return_annotation": {"return_annotation_source": "int"},
            "function_name": {"name": "g"}}
        after = replace(after, **changes[mutation])
    assert operation.validate_delta(before, after).code == "operation_signature_mismatch"


@pytest.mark.parametrize("declaration,call,before_status,after_status,effect,after_rule", [
    ("a, timeout", "f(1, 5)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, timeout", "f(1, timeout=5)", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, timeout", "f(a=1, timeout=5)", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, timeout", "f(1, delay=5)", "incompatible", "compatible", "compatibility_improved", "arguments_bind"),
    ("a, timeout", "f(1, timeout=5, extra=1)", "incompatible", "incompatible", "pre_existing_problem", "unexpected_keyword_argument"),
    ("a, timeout", "f()", "incompatible", "incompatible", "pre_existing_problem", "required_parameter_missing"),
    ("a, *, timeout=5", "f(1, timeout=6)", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, *, timeout=5", "f(1)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, *, timeout", "f(1, timeout=5)", "compatible", "incompatible", "direct_impact", "unexpected_keyword_argument"),
    ("a, *, timeout", "f(1, delay=5)", "incompatible", "compatible", "compatibility_improved", "arguments_bind"),
    ("a, timeout", "f(1, *args)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout", "f(1, **kwargs)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout", "f(**kwargs)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout", "f(1, timeout=5, **kwargs)", "manual_review", "manual_review", "manual_review", "argument_expansion_unknown"),
    ("a, timeout, **kwargs", "f(1, timeout=5)", "compatible", "incompatible", "direct_impact", "required_parameter_missing"),
    ("a, timeout=5, **kwargs", "f(1, timeout=6)", "compatible", "compatible", "no_impact", "arguments_bind"),
    ("a, timeout, **kwargs", "f(1, delay=5)", "incompatible", "compatible", "compatibility_improved", "arguments_bind"),
])
def test_rename_matrix_uses_canonical_signatures_without_engine_branches(
    tmp_path, declaration, call, before_status, after_status, effect, after_rule
):
    graph = graph_from(tmp_path, {"utils.py": f"def f({declaration}):\n    pass\n",
        "caller.py": f"from utils import f\ndef caller(args, kwargs):\n    {call}\n"})
    spec = spec_for(graph)
    with patch.object(RenameParameterOperation, "build_after", side_effect=AssertionError("rebuild")):
        result = analyze_direct_impact(graph, spec)
    assert result.validation.valid
    assessment, = result.assessments
    assert (assessment.before_status, assessment.after_status, assessment.effect) == (before_status, after_status, effect)
    assert assessment.after_rule_id == after_rule
    assert result.direct_impact_count == (1 if effect == "direct_impact" else 0)
    if effect == "direct_impact":
        finding, = result.findings
        assert finding.rule_id == "parameter_renamed_breaks_keyword_call"
        assert finding.reason == f"修改前调用兼容；修改后{assessment.after_reason}"
        assert (finding.source_file, finding.source_location.line, finding.call_expression) == (Path("caller.py"), 3, call)
    elif effect != "manual_review":
        assert result.findings == ()
    if effect != "direct_impact":
        assert propagate_indirect_impact(graph, result).findings == ()


def test_multiple_seeds_cycles_dedup_and_real_paths_reuse_reverse_propagation(tmp_path):
    graph = graph_from(tmp_path, {
        "utils.py": "def f(a, timeout): pass\n",
        "work.py": "from utils import f\n"
            "def report_a():\n    f(1, timeout=5)\n    dashboard()\n"
            "def report_b():\n    f(1, timeout=5)\n"
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
    assert {symbol: item.impact_type for symbol, item in by_symbol.items()} == {
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


def test_target_isolation_validation_and_source_immutability(tmp_path):
    graph = graph_from(tmp_path, {
        "utils.py": "def f(a, timeout): return a\n", "other.py": "def f(a, timeout): return a\n",
        "caller.py": "from utils import f\nfrom other import f as other\nfrom missing import f as unknown\n"
            "def caller():\n    f(1, timeout=5)\n    other(1, timeout=5)\n    unknown(1, timeout=5)\n",
    })
    original = {p: p.read_bytes() for p in tmp_path.glob("*.py")}
    spec = spec_for(graph)
    result = analyze_direct_impact(graph, spec)
    assert result.direct_impact_count == len(result.assessments) == 1
    assert result.assessments[0].target_symbol_id == "utils.f"
    assert result.assessments[0].line == 5
    assert len(graph.unresolved_calls) == 1
    for invalid, code in [
        (replace(spec, before=FunctionSignature("f", ())), "before_mismatch"),
        (replace(spec, after=spec.before), "operation_signature_mismatch"),
        (replace(spec, target_symbol_id="missing.f"), "target_not_found"),
        (replace(spec, after=replace(spec.after, parameters=(spec.after.parameters[0],
            replace(spec.after.parameters[1], name="a")))), "invalid_after_signature"),
    ]:
        assert validate_change_spec(graph.index, invalid).diagnostics[0].code == code
        rejected = analyze_direct_impact(graph, invalid)
        assert rejected.assessments == rejected.findings == ()
    with pytest.raises(ChangeOperationError):
        replace(spec, added_parameter=AddedParameter("delay", "positional_or_keyword"))
    with pytest.raises(ChangeFileError):
        change_spec_from_dict({**spec.to_dict(), "change_type": "remove_parameter"})
    assert {p: p.read_bytes() for p in original} == original
