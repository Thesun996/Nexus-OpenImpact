"""Removal evidence keeps real source facts and supplies operation-specific semantics."""

from hashlib import sha256
import json
from pathlib import Path

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report, render_chinese_report
from openimpact.explanation.fallback import RuleBasedProvider
from openimpact.explanation.provider import ExplanationProvider

DEMO = Path(__file__).resolve().parents[2] / "examples" / "parameter_removal"


def test_remove_report_evidence_and_explanations_keep_true_call_sites(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    spec = load_change_spec(DEMO / "change.json")
    report = build_report(analyze_project(DEMO, spec))
    assert report["validation"]["valid"]
    assert report["change"]["operation"] == spec.operation.to_dict()
    assert len(report["evidences"]) == len(report["explanations"]) == 3
    direct = report["direct_impacts"][0]
    assert direct["after_reason"] == "关键字参数 timezone 无法绑定到该签名。"
    assert direct["rule_id"] == "parameter_removed_breaks_call"
    evidence = report["evidences"][0]
    assert evidence["rule"] == direct["rule_id"]
    assert evidence["location"]["file"] == "report.py"
    assert evidence["location"]["line"] == direct["line"] == 5
    assert evidence["source_snippet"] == '    return format_date(date, timezone="UTC")'
    assert evidence["call_expression"] == 'format_date(date, timezone="UTC")'
    for item, explanation in zip(report["evidences"], report["explanations"]):
        location = item["location"]
        source = (DEMO / location["file"]).read_bytes()
        assert item["source_hash"] == sha256(source).hexdigest()
        assert item["status"] == "available"
        assert explanation["evidence"] == item
        assert "删除参数 timezone" in explanation["explanation"]["why_affected"]
        assert explanation["explanation"]["risk_level"] == "unknown"
    path = report["evidences"][2]["propagation_path"][0]
    assert path["symbols"] == ["page.page", "dashboard.dashboard", "report.report", "utils.format_date"]
    # CallEdge paths preserve start positions; AST call evidence additionally
    # retains end_line. Keep these existing representations unchanged.
    for key in ("file", "line", "column"):
        assert path["call_sites"][-1][key] == evidence["location"][key]
    assert path["call_sites"][-1]["end_line"] is None
    assert path["direct_evidence_reference"] == evidence["evidence_reference"]
    assert "静态路径不保证运行时失败" in report["explanations"][2]["explanation"]["why_affected"]
    assert "新增必填参数" not in json.dumps(report, ensure_ascii=False)
    assert "删除参数 timezone" in render_chinese_report(report)


def test_explanation_provider_receives_removal_intent_from_the_operation_only():
    inputs = []

    class RecordingProvider(ExplanationProvider):
        def explain(self, input):
            inputs.append(input)
            return RuleBasedProvider().explain(input)

    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    report = build_report(run, explanation_provider=RecordingProvider())
    assert len(inputs) == len(report["evidences"]) == 3
    for input, evidence in zip(inputs, report["evidences"]):
        assert input.change_description == "utils.format_date 删除参数 timezone"
        assert input.reason == evidence["reason"]
        assert input.rule == evidence["rule"]
        assert input.source_snippet == evidence["source_snippet"]
        assert input.target_symbol == evidence["target_symbol"]


def test_unavailable_evidence_does_not_erase_the_removal_impact(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    for path in DEMO.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run = analyze_project(tmp_path, load_change_spec(DEMO / "change.json"))
    (tmp_path / "report.py").unlink()
    report = build_report(run)
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["evidences"][0]["status"] == "unavailable"
    assert report["evidences"][0]["diagnostics"][0]["code"] == "file_missing"
    assert report["explanations"][0]["explanation"] is None
    assert report["explanations"][0]["diagnostics"][0]["code"] == "evidence_unavailable"
