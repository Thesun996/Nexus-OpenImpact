"""Rename evidence explains both names without changing the source snapshot."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.explanation.fallback import RuleBasedProvider
from openimpact.explanation.provider import ExplanationProvider

DEMO = Path(__file__).resolve().parents[2] / "examples" / "parameter_rename_keyword"


def test_rename_evidence_includes_both_names_real_keyword_and_transition(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    spec = load_change_spec(DEMO / "change.json")
    report = build_report(analyze_project(DEMO, spec))
    assert report["validation"]["valid"]
    assert report["change"]["operation"] == spec.operation.to_dict()
    assert report["change"]["added_parameter"] is None
    assert len(report["evidences"]) == len(report["explanations"]) == 3
    direct = report["direct_impacts"][0]
    assert direct["before_status"] == "compatible"
    assert direct["after_status"] == "incompatible"
    assert direct["after_reason"] == "关键字参数 timeout 无法绑定到该签名。"
    assert direct["rule_id"] == "parameter_renamed_breaks_keyword_call"
    evidence = report["evidences"][0]
    assert evidence["rule"] == direct["rule_id"]
    assert evidence["location"]["file"] == "report.py"
    assert evidence["location"]["line"] == direct["line"] == 5
    assert evidence["source_snippet"] == "    return f(a, timeout=5)"
    assert evidence["call_expression"] == "f(a, timeout=5)"
    assert evidence["reason"] == "utils.f 重命名参数 timeout → delay。" + direct["reason"]
    for item, explanation in zip(report["evidences"], report["explanations"]):
        assert item["source_hash"] == sha256((DEMO / item["location"]["file"]).read_bytes()).hexdigest()
        assert item["status"] == "available"
        assert explanation["evidence"] == item
        assert "重命名参数 timeout → delay" in explanation["explanation"]["why_affected"]
        assert explanation["explanation"]["risk_level"] == "unknown"
    path = report["evidences"][2]["propagation_path"][0]
    assert path["symbols"] == ["page.page", "dashboard.dashboard", "report.report", "utils.f"]
    for key in ("file", "line", "column"):
        assert path["call_sites"][-1][key] == evidence["location"][key]
    assert path["direct_evidence_reference"] == evidence["evidence_reference"]
    assert "静态路径不保证运行时失败" in report["explanations"][2]["explanation"]["why_affected"]
    serialized = json.dumps(report, ensure_ascii=False)
    assert "新增必填参数" not in serialized
    assert "删除参数" not in serialized


def test_explanation_receives_rename_intent_and_only_existing_evidence_facts():
    inputs = []

    class RecordingProvider(ExplanationProvider):
        def explain(self, input):
            inputs.append(input)
            return RuleBasedProvider().explain(input)

    report = build_report(analyze_project(DEMO, load_change_spec(DEMO / "change.json")),
                          explanation_provider=RecordingProvider())
    assert len(inputs) == 3
    for input, evidence in zip(inputs, report["evidences"]):
        assert input.change_description == "utils.f 重命名参数 timeout → delay"
        assert input.reason == evidence["reason"]
        assert input.rule == evidence["rule"]
        assert input.source_snippet == evidence["source_snippet"]
        assert input.target_symbol == evidence["target_symbol"]


def test_unavailable_rename_evidence_degrades_without_erasing_impacts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    for path in DEMO.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run = analyze_project(tmp_path, load_change_spec(DEMO / "change.json"))
    (tmp_path / "report.py").unlink()
    report = build_report(run)
    assert report["summary"]["direct_impact_count"] == 1
    assert report["evidences"][0]["status"] == "unavailable"
    assert report["evidences"][0]["diagnostics"][0]["code"] == "file_missing"
    assert "timeout → delay" in report["evidences"][0]["reason"]
    assert report["explanations"][0]["explanation"] is None


@pytest.mark.parametrize("name", ["signature_change", "parameter_removal"])
def test_existing_add_remove_evidence_reason_is_unchanged(name):
    demo = DEMO.parent / name
    report = build_report(analyze_project(demo, load_change_spec(demo / "change.json")))
    assert report["evidences"][0]["reason"] == report["direct_impacts"][0]["reason"]
