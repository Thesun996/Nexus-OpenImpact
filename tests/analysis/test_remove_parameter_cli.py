"""The removal change file is portable across CLI and report serialization."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from openimpact.analysis.change_file import change_spec_from_dict, load_change_spec
from openimpact.analysis.change_spec import ChangeSpec, FunctionSignature, RemoveParameterOperation
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.symbol_index import SymbolIndex

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "examples" / "parameter_removal"


def cli(project, change, format="json"):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(PYTHONIOENCODING="utf-8", OPENIMPACT_LLM_PROVIDER="rule")
    return subprocess.run([sys.executable, "-m", "openimpact", "analyze", str(project),
        "--change", str(change), "--format", format], cwd=ROOT, env=environment,
        capture_output=True, text=True, encoding="utf-8", check=False)


def test_removal_change_file_and_cli_json_complete_the_full_chain():
    original = {path: path.read_bytes() for path in DEMO.iterdir() if path.is_file()}
    spec = load_change_spec(DEMO / "change.json")
    assert isinstance(spec.operation, RemoveParameterOperation)
    run = analyze_project(DEMO, spec)
    assert run.direct.validation.valid
    result = cli(DEMO, DEMO / "change.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert report["change"]["change_type"] == "remove_parameter"
    assert change_spec_from_dict(report["change"]) == spec
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["coverage"]["status"] == "complete"
    assert report["evidences"][2]["propagation_path"][0]["symbols"] == [
        "page.page", "dashboard.dashboard", "report.report", "utils.format_date"]
    assert {path: path.read_bytes() for path in original} == original


def test_removal_cli_chinese_text_uses_the_new_change_semantics():
    result = cli(DEMO, DEMO / "change.json", "text")
    assert result.returncode == 0, result.stderr
    assert "删除参数 timezone" in result.stdout
    assert "新增必填参数" not in result.stdout
    assert "关键字参数 timezone 无法绑定到该签名" in result.stdout
    assert "Direct Impact（1）" in result.stdout
    assert "1-hop Indirect（1）" in result.stdout
    assert "2-hop Indirect（1）" in result.stdout


@pytest.mark.parametrize("mutation,code", [
    ("missing_parameter", "parameter_not_found"),
    ("wrong_after", "operation_signature_mismatch"),
    ("wrong_before", "before_mismatch"),
])
def test_declared_removal_failure_returns_validation_json_and_nonzero_exit(tmp_path, mutation, code):
    data = json.loads((DEMO / "change.json").read_text(encoding="utf-8"))
    if mutation == "missing_parameter":
        data["operation"]["parameter_name"] = "missing"
    elif mutation == "wrong_after":
        data["after"] = data["before"]
    else:
        data["before"]["parameters"] = []
    change = tmp_path / "change.json"
    change.write_text(json.dumps(data), encoding="utf-8")
    result = cli(DEMO, change)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["validation"]["diagnostics"][0]["code"] == code
    assert report["summary"]["direct_impact_count"] == 0
    assert report["indirect_impacts"] == report["evidences"] == report["explanations"] == []


@pytest.mark.parametrize("name", ["args", "kwargs"])
def test_cli_refuses_variadic_parameter_removal(tmp_path, name):
    (tmp_path / "utils.py").write_text("def f(a, *args, **kwargs): pass\n", encoding="utf-8")
    index = SymbolIndex(tmp_path).build()
    before = FunctionSignature.from_definition(index.symbols["utils.f"].definition)
    after = FunctionSignature("f", tuple(p for p in before.parameters if p.name != name))
    spec = ChangeSpec("remove_parameter", "utils.f", before, after,
                      operation=RemoveParameterOperation(name))
    change = tmp_path / "change.json"
    change.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    result = cli(tmp_path, change)
    assert result.returncode == 1
    assert json.loads(result.stdout)["validation"]["diagnostics"][0]["code"] == "unsupported_parameter_kind"


def test_illegal_remove_payload_does_not_produce_a_fake_cli_report(tmp_path):
    data = json.loads((DEMO / "change.json").read_text(encoding="utf-8"))
    del data["operation"]["parameter_name"]
    change = tmp_path / "change.json"
    change.write_text(json.dumps(data), encoding="utf-8")
    result = cli(DEMO, change)
    assert result.returncode == 2
    assert "invalid_operation_payload" in result.stderr
    assert result.stdout == ""


def test_old_add_cli_remains_available_without_an_operation_field():
    demo = ROOT / "examples" / "signature_change"
    assert "operation" not in json.loads((demo / "change.json").read_text(encoding="utf-8"))
    result = cli(demo, demo / "change.json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert set(report["change"]) == {"change_type", "target_symbol_id", "before", "after", "added_parameter"}
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["coverage"]["status"] == "complete"
