"""Default-removal evidence and rule explanations retain real source facts."""

from hashlib import sha256
import json
from pathlib import Path

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.explanation.fallback import RuleBasedProvider
from openimpact.explanation.provider import ExplanationProvider

DEMO = Path(__file__).resolve().parents[2] / "examples" / "parameter_required_missing"


def test_make_required_evidence_explains_original_default_and_new_missing_argument(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    spec = load_change_spec(DEMO / "change.json")
    report = build_report(analyze_project(DEMO, spec))
    assert report["validation"]["valid"]
    assert report["schema_version"] == 1
    assert report["change"]["operation"] == spec.operation.to_dict()
    assert report["change"]["added_parameter"] is None
    assert report["change"]["before"]["parameters"][1]["has_default"] is True
    assert report["change"]["before"]["parameters"][1]["default_source"] == "30"
    assert report["change"]["after"]["parameters"][1]["has_default"] is False
    assert report["change"]["after"]["parameters"][1]["default_source"] is None
    assert len(report["evidences"]) == len(report["explanations"]) == 3
    direct = report["direct_impacts"][0]
    assert direct["before_status"] == "compatible"
    assert direct["after_status"] == "incompatible"
    assert direct["after_reason"] == "该签名的必填参数 timeout 未由当前调用提供。"
    assert direct["rule_id"] == "parameter_became_required_breaks_call"
    evidence = report["evidences"][0]
    assert evidence["rule"] == direct["rule_id"]
    assert evidence["location"]["file"] == "report.py"
    assert evidence["location"]["line"] == direct["line"] == 5
    assert evidence["source_snippet"] == "    return connect(address)"
    assert evidence["call_expression"] == "connect(address)"
    assert evidence["reason"] == spec.describe() + "。" + direct["reason"]
    for item, explanation in zip(report["evidences"], report["explanations"]):
        assert item["source_hash"] == sha256((DEMO / item["location"]["file"]).read_bytes()).hexdigest()
        assert item["status"] == "available"
        assert explanation["evidence"] == item
        assert "从可选变为必填（移除原有默认值）" in explanation["explanation"]["why_affected"]
        assert explanation["explanation"]["risk_level"] == "unknown"
    path = report["evidences"][2]["propagation_path"][0]
    assert path["symbols"] == ["page.page", "dashboard.dashboard", "report.report", "utils.connect"]
    for key in ("file", "line", "column"):
        assert path["call_sites"][-1][key] == evidence["location"][key]
    assert path["direct_evidence_reference"] == evidence["evidence_reference"]
    assert "静态路径不保证运行时失败" in report["explanations"][2]["explanation"]["why_affected"]
    serialized = json.dumps(report, ensure_ascii=False)
    assert "新增必填参数" not in serialized
    assert "删除参数" not in serialized
    assert "重命名参数" not in serialized


def test_rule_provider_receives_only_the_operation_and_current_evidence_facts():
    inputs = []

    class RecordingProvider(ExplanationProvider):
        def explain(self, input):
            inputs.append(input)
            return RuleBasedProvider().explain(input)

    report = build_report(analyze_project(DEMO, load_change_spec(DEMO / "change.json")),
                          explanation_provider=RecordingProvider())
    assert len(inputs) == 3
    for input, evidence in zip(inputs, report["evidences"]):
        assert input.change_description == "utils.connect 参数 timeout 从可选变为必填（移除原有默认值）"
        assert input.reason == evidence["reason"]
        assert input.rule == evidence["rule"]
        assert input.source_snippet == evidence["source_snippet"]
        assert input.target_symbol == evidence["target_symbol"]


def test_evidence_failure_degrades_without_erasing_the_new_impacts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    for path in DEMO.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run = analyze_project(tmp_path, load_change_spec(DEMO / "change.json"))
    (tmp_path / "report.py").unlink()
    report = build_report(run)
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == report["summary"]["indirect_2hop_count"] == 1
    assert report["evidences"][0]["status"] == "unavailable"
    assert report["evidences"][0]["diagnostics"][0]["code"] == "file_missing"
    assert "移除原有默认值" in report["evidences"][0]["reason"]
    assert report["explanations"][0]["explanation"] is None
