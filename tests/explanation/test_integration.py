"""Report explanations preserve existing evidence and impact results."""

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.api import app
from openimpact.explanation import ExplanationInput, ExplanationProvider, ExplanationResult

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
CHANGE = DEMO / "change.json"


def _run():
    return analyze_project(DEMO, load_change_spec(CHANGE))


class FailingProvider(ExplanationProvider):
    def explain(self, input: ExplanationInput) -> ExplanationResult:
        raise RuntimeError("provider unavailable")


def test_default_rule_explanations_enter_report_with_one_to_one_evidence(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    report = build_report(_run())

    assert len(report["explanations"]) == len(report["evidences"]) == 3
    assert [item["evidence"] for item in report["explanations"]] == report["evidences"]
    direct = report["explanations"][0]
    assert "report.py:5" in direct["explanation"]["summary"]
    assert "已确定不兼容" in direct["explanation"]["summary"]
    assert direct["explanation"]["risk_level"] == "unknown"
    page = report["explanations"][2]
    assert "page.page → dashboard.dashboard → report.report → utils.format_date" in (
        page["explanation"]["why_affected"]
    )
    assert "不保证运行时失败" in page["explanation"]["why_affected"]


def test_deepseek_mode_mock_result_enters_report(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    mock_result = {
        "summary": "按证据检查调用链。",
        "why_affected": "已给定的调用路径与变更目标相连。",
        "risk_level": "unknown",
        "suggested_check": "人工核对报告中的调用位置。",
        "confidence": 0.8,
    }
    with patch("openimpact.explanation.deepseek.DeepSeekProvider._request_completion",
               return_value=json.dumps(mock_result, ensure_ascii=False)) as request:
        report = build_report(_run())

    assert request.call_count == 3
    assert all(item["explanation"] == mock_result for item in report["explanations"])
    assert report["summary"]["direct_impact_count"] == 1
    assert report["evidences"][0]["source_snippet"] == "    return format_date(date)"


def test_provider_failure_falls_back_without_changing_evidence(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    run = _run()
    baseline = build_report(run)
    failed = build_report(run, explanation_provider=FailingProvider())

    assert failed["evidences"] == baseline["evidences"]
    assert failed["explanations"] == baseline["explanations"]
    assert failed["direct_impacts"] == baseline["direct_impacts"]
    assert failed["indirect_impacts"] == baseline["indirect_impacts"]
    assert failed["summary"] == baseline["summary"]


def test_unavailable_evidence_has_no_explanation_and_keeps_diagnostic(tmp_path):
    for path in DEMO.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run = analyze_project(tmp_path, load_change_spec(CHANGE))
    (tmp_path / "report.py").unlink()

    report = build_report(run)
    direct = report["explanations"][0]
    assert direct["evidence"] == report["evidences"][0]
    assert direct["explanation"] is None
    assert direct["diagnostics"][0]["code"] == "evidence_unavailable"
    assert report["summary"]["direct_impact_count"] == 1


def test_cli_and_demo_api_keep_old_fields_and_add_explanations(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    env = dict(os.environ)
    result = subprocess.run(
        [sys.executable, "-m", "openimpact", "analyze", str(DEMO),
         "--change", str(CHANGE), "--format", "json"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    cli = json.loads(result.stdout)
    with TestClient(app) as client:
        response = client.post("/api/v1/demo/analyze")
    assert response.status_code == 200
    api = response.json()
    for report in (cli, api):
        assert report["summary"]["direct_impact_count"] == 1
        assert len(report["direct_impacts"]) == 1
        assert len(report["indirect_impacts"]) == 2
        assert len(report["evidences"]) == len(report["explanations"]) == 3
        assert "diagnostics" in report
