"""Quality screening helpers flag review needs without pretending to prove fidelity."""

from pathlib import Path
import json
import runpy
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.explanation import ExplanationInput, RuleBasedProvider
from openimpact.reporting.evidence import EvidenceBuilder

ROOT = Path(__file__).resolve().parents[2]
script = runpy.run_path(str(ROOT / "scripts" / "deepseek_live_check.py"))
screen = script["quality_screen"]
run_check = script["run_check"]


def test_screen_accepts_known_demo_rule_facts():
    demo = ROOT / "examples" / "signature_change"
    run = analyze_project(demo, load_change_spec(demo / "change.json"))
    builder = EvidenceBuilder(demo)
    for finding in (*run.direct.findings, *run.indirect.findings):
        data = ExplanationInput.from_evidence(builder.build(finding), "新增必填参数 timezone")
        result = RuleBasedProvider().explain(data)
        assert screen(data.to_dict(), result.to_dict()) == []


def test_screen_flags_invented_code_risk_and_indirect_failure_claim():
    input_data = {
        "target_symbol": "utils.format_date", "impact_type": "indirect_1hop",
        "source_location": {"file": "dashboard.py", "line": 5},
        "propagation_path": [{
            "symbols": ["dashboard.dashboard", "report.report", "utils.format_date"],
            "call_sites": [{"file": "dashboard.py", "line": 5},
                           {"file": "report.py", "line": 5}],
        }],
    }
    result = {
        "summary": "fake.run() 在 missing.py:9 一定失败。",
        "why_affected": "bad_function()", "risk_level": "high",
        "suggested_check": "修改为其他实现。",
    }
    flags = screen(input_data, result)
    assert set(flags) == {"unprovided_file_reference", "unprovided_source_location",
                         "unprovided_symbol_reference", "unprovided_function_reference",
                         "unsupported_risk_level", "possible_concrete_code_change",
                         "indirect_claims_definite_failure"}


def test_preflight_401_stops_after_one_request_and_skips_http_workflow(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    error = HTTPError("https://api.deepseek.com/chat/completions", 401,
                      "private auth details", {}, None)
    with (patch("openimpact.explanation.deepseek.urlopen", side_effect=error) as network,
          patch.dict(run_check.__globals__, {
              "local_server": lambda: pytest.fail("must not start full workflow after 401"),
          })):
        result = run_check()
    assert network.call_count == 1
    assert result["workflow_skipped"] is True
    assert result["stop_reason"] == "http_401"
    assert result["real_model_success"] is False
    assert result["static_fields_equal"] is None
    assert result["temporary_directory_count"] == 0
    assert result["temporary_directories_cleaned"] is True
    call = result["model_calls"][0]
    assert call["phase"] == "preflight"
    assert call["call"]["status"] == "fallback"
    assert call["call"]["prompt_tokens"] is None
    assert call["elapsed_seconds"] >= 0
    assert "test-secret" not in json.dumps(result)
    assert "private auth details" not in json.dumps(result)


def test_missing_key_stops_without_network_or_workflow(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with patch("openimpact.explanation.deepseek.urlopen") as network:
        result = run_check()
    network.assert_not_called()
    assert result["stop_reason"] == "missing_key"
    assert result["workflow_skipped"] is True
    assert result["model_calls"][0]["network_attempted"] is False


class ModelResponse:
    """Only the remote model is mocked; business requests use loopback HTTP."""

    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, _size):
        content = json.dumps({
            "summary": "按证据检查调用。", "why_affected": "依据输入规则及调用路径。",
            "risk_level": "unknown", "suggested_check": "人工核对已有调用位置。",
            "confidence": 0.9,
        })
        return json.dumps({
            "model": "deepseek-flash", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        }).encode()


@pytest.mark.parametrize("fail_in_workflow", [False, True])
def test_authenticated_workflow_preserves_static_facts_and_cleans_up(monkeypatch, fail_in_workflow):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    responses = [ModelResponse()] * 4
    if fail_in_workflow:
        responses = [ModelResponse(), HTTPError(
            "https://api.deepseek.com/chat/completions", 401, "private", {}, None
        )]
    with patch("openimpact.explanation.deepseek.urlopen", side_effect=responses) as network:
        result = run_check()
    assert network.call_count == (2 if fail_in_workflow else 4)
    assert result["workflow_skipped"] is False
    assert all(result["static_fields_equal"].values())
    assert result["temporary_directory_count"] == 6
    assert result["temporary_directories_cleaned"] is True
    assert result["rule_workflow"]["http_statuses"] == [200, 200, 200]
    assert result["deepseek_workflow"]["http_statuses"] == [200, 200, 200]
    assert result["rule_report"]["summary"]["direct_impact_count"] == 1
    assert result["real_model_success"] is (not fail_in_workflow)
    assert result["model_calls"][0]["call"]["prompt_tokens"] == 10
    assert result["model_calls"][0]["call"]["completion_tokens"] == 5
    if fail_in_workflow:
        assert [item["call"]["reason_code"] for item in result["model_calls"]] == [
            None, "http_401", "authentication_blocked", "authentication_blocked",
        ]
        assert [item["network_attempted"] for item in result["model_calls"]] == [
            True, True, False, False,
        ]
