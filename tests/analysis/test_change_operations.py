"""Typed intent stays separate from canonical signatures and call assessments."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from openimpact.analysis.call_graph import CallGraph
from openimpact.analysis.change_file import ChangeFileError, change_spec_from_dict, load_change_spec
from openimpact.analysis.change_spec import (
    AddedParameter,
    AddRequiredParameterOperation,
    ChangeOperationError,
    ChangeSpec,
    ChangeType,
    FunctionSignature,
    MakeParameterRequiredOperation,
    RemoveParameterOperation,
    RenameParameterOperation,
    operation_from_dict,
    validate_change_spec,
)
from openimpact.analysis.direct_impact import analyze_direct_impact
from openimpact.analysis.models import Parameter
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.api_change import build_change_spec, parse_change_config

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"


@pytest.fixture
def graph(tmp_path):
    (tmp_path / "utils.py").write_text("def f(a):\n    pass\n", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        "from utils import f\ndef caller(args, kwargs):\n"
        "    f(1)\n    f()\n    f(1, 2)\n    f(1, *args)\n    f(1, **kwargs)\n",
        encoding="utf-8",
    )
    return CallGraph(SymbolIndex(tmp_path).build()).build()


def before_for(graph):
    return FunctionSignature.from_definition(graph.index.symbols["utils.f"].definition)


def operation_data(**extra):
    return {
        "change_type": "add_required_parameter",
        "added_parameter": {"name": "b", "kind": "positional_or_keyword", "required": True},
        **extra,
    }


def test_only_the_approved_operations_are_registered():
    assert list(ChangeType) == [ChangeType.ADD_REQUIRED_PARAMETER, ChangeType.REMOVE_PARAMETER,
                                ChangeType.RENAME_PARAMETER, ChangeType.MAKE_PARAMETER_REQUIRED]
    operation = operation_from_dict(operation_data())
    assert type(operation) is AddRequiredParameterOperation
    assert operation.change_type is ChangeType.ADD_REQUIRED_PARAMETER
    assert type(operation_from_dict({"change_type": "remove_parameter", "parameter_name": "b"})) is RemoveParameterOperation
    assert type(operation_from_dict({"change_type": "rename_parameter", "parameter_name": "b",
                                    "new_parameter_name": "c"})) is RenameParameterOperation
    assert type(operation_from_dict({"change_type": "make_parameter_required", "parameter_name": "b"})) is MakeParameterRequiredOperation


@pytest.mark.parametrize("kind", ["positional_only", "positional_or_keyword", "keyword_only"])
def test_operation_build_and_json_round_trip_preserve_signature_facts(kind):
    before = FunctionSignature("f", (
        Parameter("a", "positional_only", annotation_source="str"),
        Parameter("mode", "positional_or_keyword", True, "'short'", "str"),
        Parameter("args", "var_positional"),
        Parameter("limit", "keyword_only", True, "10", "int"),
        Parameter("kwargs", "var_keyword"),
    ), is_async=True, return_annotation_source="str")
    operation = AddRequiredParameterOperation(
        AddedParameter("b", kind, annotation_source="int"),
        insert_before="mode" if kind == "positional_or_keyword" else None,
    )
    restored_operation = operation_from_dict(json.loads(json.dumps(operation.to_dict())))
    assert restored_operation == operation
    spec = ChangeSpec.from_operation("utils.f", before, operation)
    restored = change_spec_from_dict(json.loads(json.dumps(spec.to_dict())))
    assert restored == spec
    assert restored.operation == operation
    assert restored.before_signature == before
    assert restored.after_signature == operation.build_after(before)
    assert restored.after.is_async is True
    assert restored.after.return_annotation_source == "str"
    assert tuple(p for p in restored.after.parameters if p.name != "b") == before.parameters
    assert next(p for p in restored.after.parameters if p.name == "b").has_default is False
    canonical = spec.to_dict()
    del canonical["added_parameter"]
    del canonical["change_type"]
    assert change_spec_from_dict(canonical) == spec


@pytest.mark.parametrize("payload,code", [
    (None, "invalid_operation_payload"),
    ([], "invalid_operation_payload"),
    ({}, "unsupported_change_type"),
    (operation_data(change_type="remove_parameter"), "invalid_operation_payload"),
    (operation_data(change_type="rename_parameter"), "invalid_operation_payload"),
    (operation_data(change_type="fourth_change"), "unsupported_change_type"),
    (operation_data(change_type=["add_required_parameter"]), "unsupported_change_type"),
    (operation_data(extra="unexpected"), "invalid_operation_payload"),
    (operation_data(insert_before=42), "invalid_operation_payload"),
    (operation_data(insert_before=""), "invalid_operation_payload"),
    (operation_data(added_parameter={"name": "b", "kind": "keyword_only"}), "invalid_operation_payload"),
    (operation_data(added_parameter={"name": "b", "kind": "var_positional", "required": True}),
     "unsupported_parameter_kind"),
    (operation_data(added_parameter={"name": "b", "kind": [], "required": True}),
     "unsupported_parameter_kind"),
    (operation_data(added_parameter={"name": "b", "kind": "keyword_only", "required": False}),
     "added_parameter_not_required"),
    (operation_data(added_parameter={"name": "b", "kind": "keyword_only", "required": 1}),
     "added_parameter_not_required"),
    (operation_data(added_parameter={"name": 42, "kind": "keyword_only", "required": True}),
     "invalid_operation_payload"),
    (operation_data(added_parameter={"name": "b", "kind": "keyword_only", "required": True,
                                     "annotation_source": []}), "invalid_operation_payload"),
    (operation_data(added_parameter={"name": "b", "kind": "keyword_only", "required": True,
                                     "default": 1}), "invalid_operation_payload"),
])
def test_illegal_operation_payload_is_rejected(payload, code):
    with pytest.raises(ChangeOperationError) as error:
        operation_from_dict(payload)
    assert error.value.code == code


def test_concrete_payload_decoder_cannot_accept_another_discriminator():
    with pytest.raises(ChangeOperationError, match="类型"):
        AddRequiredParameterOperation.from_dict(operation_data(change_type="remove_parameter"))


@pytest.mark.parametrize("field,value", [
    ("change_type", "rename_parameter"),
    ("added_parameter", {"name": "other", "kind": "positional_or_keyword", "required": True}),
    ("operation", operation_data(change_type="remove_parameter")),
    ("operation", None),
])
def test_conflicting_legacy_and_operation_fields_are_not_silently_preferred(graph, field, value):
    spec = ChangeSpec.from_operation("utils.f", before_for(graph),
                                     operation_from_dict(operation_data()))
    data = {**spec.to_dict(), field: value}
    with pytest.raises(ChangeFileError):
        change_spec_from_dict(data)


def test_legacy_demo_and_public_report_are_unchanged(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    legacy = load_change_spec(DEMO / "change.json")
    config = parse_change_config(json.dumps({
        "target_symbol_id": "utils.format_date",
        "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"},
    }))
    old_run = analyze_project(DEMO, legacy)
    generated = build_change_spec(old_run.index, config)
    assert generated == legacy
    old_report = build_report(old_run)
    assert build_report(analyze_project(DEMO, generated)) == old_report
    assert old_report["schema_version"] == 1
    assert set(old_report["change"]) == {"change_type", "target_symbol_id", "before", "after", "added_parameter"}
    assert change_spec_from_dict(old_report["change"]) == legacy
    assert old_report["summary"]["direct_impact_count"] == 1
    assert old_report["summary"]["indirect_1hop_count"] == 1
    assert old_report["summary"]["indirect_2hop_count"] == 1
    assert old_report["coverage"]["status"] == "complete"
    assert old_report["evidences"][0]["rule"] == "required_parameter_added_breaks_call"


def test_legacy_constructor_and_effect_classification_stay_compatible(graph):
    before = before_for(graph)
    added = AddedParameter("b", "positional_or_keyword")
    after = FunctionSignature("f", before.parameters + (Parameter("b", added.kind),))
    legacy = ChangeSpec("add_required_parameter", "utils.f", before, after, added)
    typed = ChangeSpec.from_operation("utils.f", before, AddRequiredParameterOperation(added))
    assert typed == legacy
    # No per-operation construction during impact analysis: assess the supplied
    # and validated signatures even when the construction method is unavailable.
    with patch.object(AddRequiredParameterOperation, "build_after", side_effect=AssertionError("rebuild")):
        result = analyze_direct_impact(graph, typed)
    assert result.validation.valid
    assert [(a.before_status, a.after_status, a.effect) for a in result.assessments] == [
        ("compatible", "incompatible", "direct_impact"),
        ("incompatible", "incompatible", "pre_existing_problem"),
        ("incompatible", "compatible", "compatibility_improved"),
        ("manual_review", "manual_review", "manual_review"),
        ("manual_review", "manual_review", "manual_review"),
    ]
    assert result.direct_impact_count == 1
    assert result.findings[0].rule_id == typed.operation.direct_rule_id


def test_canonical_after_controls_actual_binding_not_the_added_name(graph):
    before = before_for(graph)
    added = AddedParameter("b", "positional_or_keyword")
    append = ChangeSpec.from_operation("utils.f", before, AddRequiredParameterOperation(added))
    prepend = ChangeSpec.from_operation("utils.f", before,
                                       AddRequiredParameterOperation(added, insert_before="a"))
    appended = analyze_direct_impact(graph, append).assessments[0]
    prepended = analyze_direct_impact(graph, prepend).assessments[0]
    assert appended.after_reason == "该签名的必填参数 b 未由当前调用提供。"
    assert prepended.after_reason == "该签名的必填参数 a 未由当前调用提供。"
    assert appended.effect == prepended.effect == "direct_impact"


@pytest.mark.parametrize("mutation,code", [
    ("before", "before_mismatch"),
    ("after", "added_parameter_mismatch"),
    ("position", "operation_signature_mismatch"),
])
def test_invalid_declared_signatures_are_rejected_instead_of_reconstructed(graph, mutation, code):
    before = before_for(graph)
    spec = ChangeSpec.from_operation("utils.f", before,
        AddRequiredParameterOperation(AddedParameter("b", "positional_or_keyword"), insert_before="a"))
    if mutation == "before":
        spec = replace(spec, before=FunctionSignature("f", ()))
    elif mutation == "after":
        spec = replace(spec, after=FunctionSignature("f", (Parameter("other", "positional_or_keyword"),
                                                            *before.parameters)))
    else:
        spec = replace(spec, after=FunctionSignature("f", (*before.parameters,
                                                            Parameter("b", "positional_or_keyword"))))
    with patch.object(AddRequiredParameterOperation, "build_after", side_effect=AssertionError("rebuild")):
        result = analyze_direct_impact(graph, spec)
    assert not result.validation.valid
    assert result.validation.diagnostics[0].code == code
    assert result.assessments == result.findings == ()


def test_missing_payload_has_a_diagnostic_and_never_creates_an_impact(graph):
    before = before_for(graph)
    spec = ChangeSpec("add_required_parameter", "utils.f", before, before)
    assert validate_change_spec(graph.index, spec).diagnostics[0].code == "invalid_operation_payload"
    assert analyze_direct_impact(graph, spec).direct_impact_count == 0


def test_operation_construction_validation_and_analysis_do_not_modify_source(graph):
    root = graph.index.scanner.project_path
    original = {p: p.read_bytes() for p in root.glob("*.py")}
    spec = ChangeSpec.from_operation("utils.f", before_for(graph), operation_from_dict(operation_data()))
    assert validate_change_spec(graph.index, spec).valid
    analyze_direct_impact(graph, spec)
    assert {p: p.read_bytes() for p in root.glob("*.py")} == original
