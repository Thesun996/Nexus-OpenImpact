"""Portable rename change files exercise the real installed CLI."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from openimpact.analysis.change_file import change_spec_from_dict, load_change_spec
from openimpact.analysis.change_spec import ChangeSpec, FunctionSignature, RenameParameterOperation
from openimpact.analysis.symbol_index import SymbolIndex

ROOT = Path(__file__).resolve().parents[2]


def cli(project, change, format="json"):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(PYTHONIOENCODING="utf-8", OPENIMPACT_LLM_PROVIDER="rule")
    return subprocess.run([sys.executable, "-m", "openimpact", "analyze", str(project),
        "--change", str(change), "--format", format], cwd=ROOT, env=environment,
        capture_output=True, text=True, encoding="utf-8", check=False)


@pytest.mark.parametrize("mode,count", [("keyword", 1), ("positional", 0)])
def test_rename_demo_cli_json_reproduces_the_complete_expected_chain(mode, count):
    demo = ROOT / "examples" / f"parameter_rename_{mode}"
    original = {path: path.read_bytes() for path in demo.iterdir() if path.is_file()}
    spec = load_change_spec(demo / "change.json")
    assert isinstance(spec.operation, RenameParameterOperation)
    result = cli(demo, demo / "change.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert report["change"]["change_type"] == "rename_parameter"
    assert report["change"]["added_parameter"] is None
    assert change_spec_from_dict(report["change"]) == spec
    for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"):
        assert report["summary"][key] == count
    assert report["coverage"]["status"] == "complete"
    if count:
        assert report["direct_impacts"][0]["caller_symbol_id"] == "report.report"
        assert report["evidences"][2]["propagation_path"][0]["symbols"] == [
            "page.page", "dashboard.dashboard", "report.report", "utils.f"]
    else:
        assert report["direct_impacts"] == report["indirect_impacts"] == report["evidences"] == report["explanations"] == []
    assert {path: path.read_bytes() for path in original} == original


def test_rename_cli_chinese_text_uses_rename_wording_and_real_keyword_failure():
    demo = ROOT / "examples" / "parameter_rename_keyword"
    result = cli(demo, demo / "change.json", "text")
    assert result.returncode == 0, result.stderr
    assert "重命名参数 timeout → delay" in result.stdout
    assert "关键字参数 timeout 无法绑定到该签名" in result.stdout
    assert "Direct Impact（1）" in result.stdout
    assert "新增必填参数" not in result.stdout
    assert "删除参数" not in result.stdout


@pytest.mark.parametrize("mutation,code", [
    ("missing_parameter", "parameter_not_found"),
    ("wrong_after", "operation_signature_mismatch"),
    ("wrong_before", "before_mismatch"),
])
def test_rename_cli_rejects_invalid_canonical_signatures(tmp_path, mutation, code):
    demo = ROOT / "examples" / "parameter_rename_keyword"
    data = json.loads((demo / "change.json").read_text(encoding="utf-8"))
    if mutation == "missing_parameter":
        data["operation"]["parameter_name"] = "missing"
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


@pytest.mark.parametrize("name", ["timeout", "args", "kwargs"])
def test_rename_cli_explicitly_refuses_unsupported_kinds(tmp_path, name):
    (tmp_path / "utils.py").write_text("def f(timeout, /, *args, **kwargs): pass\n", encoding="utf-8")
    index = SymbolIndex(tmp_path).build()
    before = FunctionSignature.from_definition(index.symbols["utils.f"].definition)
    # Construct a declaration to test rejection without bypassing the validator.
    spec = ChangeSpec("rename_parameter", "utils.f", before, before,
        operation=RenameParameterOperation(name, "delay"))
    change = tmp_path / "change.json"
    change.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    result = cli(tmp_path, change)
    assert result.returncode == 1
    assert json.loads(result.stdout)["validation"]["diagnostics"][0]["code"] == "unsupported_parameter_kind"


def test_rename_cli_missing_new_name_fails_before_producing_a_report(tmp_path):
    demo = ROOT / "examples" / "parameter_rename_keyword"
    data = json.loads((demo / "change.json").read_text(encoding="utf-8"))
    del data["operation"]["new_parameter_name"]
    change = tmp_path / "change.json"
    change.write_text(json.dumps(data), encoding="utf-8")
    result = cli(demo, change)
    assert result.returncode == 2
    assert "invalid_operation_payload" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("name", ["signature_change", "parameter_removal"])
def test_old_add_and_remove_cli_demos_keep_the_same_counts_and_contract(name):
    demo = ROOT / "examples" / name
    spec = load_change_spec(demo / "change.json")
    result = cli(demo, demo / "change.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["change"] == spec.to_dict(include_operation=False)
    assert report["schema_version"] == 1
    assert report["coverage"]["status"] == "complete"
    for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"):
        assert report["summary"][key] == 1
