"""The installed CLI preserves canonical make-required intent and old demos."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from openimpact.analysis.change_file import change_spec_from_dict, load_change_spec
from openimpact.analysis.change_spec import MakeParameterRequiredOperation

ROOT = Path(__file__).resolve().parents[2]


def cli(project, change, format="json"):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(PYTHONIOENCODING="utf-8", OPENIMPACT_LLM_PROVIDER="rule")
    return subprocess.run([sys.executable, "-m", "openimpact", "analyze", str(project),
        "--change", str(change), "--format", format], cwd=ROOT, env=environment,
        capture_output=True, text=True, encoding="utf-8", check=False)


@pytest.mark.parametrize("mode,count", [("missing", 1), ("explicit", 0)])
def test_make_required_cli_demos_keep_the_expected_complete_chain(mode, count):
    demo = ROOT / "examples" / f"parameter_required_{mode}"
    original = {p: p.read_bytes() for p in demo.iterdir() if p.is_file()}
    spec = load_change_spec(demo / "change.json")
    assert isinstance(spec.operation, MakeParameterRequiredOperation)
    result = cli(demo, demo / "change.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert report["change"]["change_type"] == "make_parameter_required"
    assert report["change"]["added_parameter"] is None
    assert change_spec_from_dict(report["change"]) == spec
    assert report["coverage"]["status"] == "complete"
    for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"):
        assert report["summary"][key] == count
    if count:
        assert report["direct_impacts"][0]["caller_symbol_id"] == "report.report"
        assert report["evidences"][2]["propagation_path"][0]["symbols"] == [
            "page.page", "dashboard.dashboard", "report.report", "utils.connect"]
    else:
        assert report["direct_impacts"] == report["indirect_impacts"] == report["evidences"] == report["explanations"] == []
    assert {p: p.read_bytes() for p in original} == original


def test_make_required_cli_chinese_report_uses_default_removal_semantics():
    demo = ROOT / "examples" / "parameter_required_missing"
    result = cli(demo, demo / "change.json", "text")
    assert result.returncode == 0, result.stderr
    assert "参数 timeout 从可选变为必填（移除原有默认值）" in result.stdout
    assert "必填参数 timeout 未由当前调用提供" in result.stdout
    assert "Direct Impact（1）" in result.stdout
    assert "新增必填参数" not in result.stdout
    assert "删除参数" not in result.stdout


@pytest.mark.parametrize("mutation,code", [
    ("missing_parameter", "parameter_not_found"),
    ("already_required", "parameter_already_required"),
    ("wrong_after", "operation_signature_mismatch"),
    ("wrong_before", "before_mismatch"),
])
def test_make_required_cli_rejects_invalid_intent_or_declared_signatures(tmp_path, mutation, code):
    demo = ROOT / "examples" / "parameter_required_missing"
    data = json.loads((demo / "change.json").read_text(encoding="utf-8"))
    if mutation == "missing_parameter":
        data["operation"]["parameter_name"] = "missing"
    elif mutation == "already_required":
        data["operation"]["parameter_name"] = "address"
    elif mutation == "wrong_after":
        data["after"] = data["before"]
    else:
        data["before"]["parameters"] = []
    change = tmp_path / "change.json"
    change.write_text(json.dumps(data), encoding="utf-8")
    result = cli(demo, change)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["validation"]["diagnostics"][0]["code"] == code
    assert report["summary"]["direct_impact_count"] == 0
    assert report["indirect_impacts"] == report["evidences"] == report["explanations"] == []


def test_cli_rejects_nondefault_after_default_without_repairing_source(tmp_path):
    source = "def f(a=1, b=2): pass\n"
    (tmp_path / "utils.py").write_text(source, encoding="utf-8")
    data = {"target_symbol_id": "utils.f", "change_type": "make_parameter_required",
        "before": {"name": "f", "parameters": [
            {"name": "a", "kind": "positional_or_keyword", "has_default": True, "default_source": "1"},
            {"name": "b", "kind": "positional_or_keyword", "has_default": True, "default_source": "2"}]},
        "after": {"name": "f", "parameters": [
            {"name": "a", "kind": "positional_or_keyword", "has_default": True, "default_source": "1"},
            {"name": "b", "kind": "positional_or_keyword", "has_default": False}]},
        "operation": {"change_type": "make_parameter_required", "parameter_name": "b"}}
    change = tmp_path / "change.json"
    change.write_text(json.dumps(data), encoding="utf-8")
    result = cli(tmp_path, change)
    assert result.returncode == 1
    assert json.loads(result.stdout)["validation"]["diagnostics"][0]["code"] == "invalid_after_signature"
    assert (tmp_path / "utils.py").read_text(encoding="utf-8") == source


def test_make_required_missing_payload_field_cannot_produce_a_fake_report(tmp_path):
    demo = ROOT / "examples" / "parameter_required_missing"
    data = json.loads((demo / "change.json").read_text(encoding="utf-8"))
    del data["operation"]["parameter_name"]
    change = tmp_path / "change.json"
    change.write_text(json.dumps(data), encoding="utf-8")
    result = cli(demo, change)
    assert result.returncode == 2
    assert "invalid_operation_payload" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("name,count", [("signature_change", 1), ("parameter_removal", 1),
    ("parameter_rename_keyword", 1), ("parameter_rename_positional", 0)])
def test_old_three_types_still_work_in_the_installed_cli(name, count):
    demo = ROOT / "examples" / name
    spec = load_change_spec(demo / "change.json")
    result = cli(demo, demo / "change.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["change"] == spec.to_dict(include_operation=False)
    assert report["schema_version"] == 1
    assert report["coverage"]["status"] == "complete"
    for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"):
        assert report["summary"][key] == count
