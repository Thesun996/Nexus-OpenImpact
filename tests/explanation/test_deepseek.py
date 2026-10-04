"""DeepSeek requests and fallback behavior are tested without network access."""

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.explanation import (
    DeepSeekProvider,
    ExplanationInput,
    ExplanationProvider,
    ExplanationResult,
    RuleBasedProvider,
    create_explanation_provider,
)
from openimpact.reporting.evidence import EvidenceBuilder

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"


def _input() -> ExplanationInput:
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    evidence = EvidenceBuilder(DEMO).build(run.direct.findings[0])
    return ExplanationInput.from_evidence(
        evidence, "utils.format_date 新增必填参数 timezone"
    )


class FakeResponse:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.body = json.dumps({
            "model": "deepseek-flash", "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            "choices": [{"finish_reason": finish_reason, "message": {"content": content}}]
        }).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _size):
        return self.body


def test_missing_key_uses_rule_fallback_without_network(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    data = _input()
    with patch("openimpact.explanation.deepseek.urlopen") as network:
        result = DeepSeekProvider().explain(data)
    assert result == RuleBasedProvider().explain(data)
    network.assert_not_called()
    provider = DeepSeekProvider(api_key="")
    provider.explain(data)
    assert provider.last_call.status == "fallback"
    assert provider.last_call.reason_code == "missing_key"


def test_valid_mock_response_builds_validated_result_and_evidence_only_prompt():
    data = _input()
    model_output = {
        "summary": "report.py:5 的调用受到参数变化影响。",
        "why_affected": "源码中的 format_date(date) 未提供新增必填参数 timezone。",
        "risk_level": "unknown",
        "suggested_check": "人工核对 report.py:5 的调用参数。",
        "confidence": 0.9,
    }
    with patch("openimpact.explanation.deepseek.urlopen",
               return_value=FakeResponse(json.dumps(model_output, ensure_ascii=False))) as network:
        provider = DeepSeekProvider(api_key="test-key")
        result = provider.explain(data)

    assert isinstance(result, ExplanationResult)
    assert result.to_dict() == model_output
    assert provider.last_call.status == "model_success"
    assert provider.last_call.reason_code is None
    assert provider.last_call.response_model == "deepseek-flash"
    assert provider.last_call.prompt_tokens == 100
    assert provider.last_call.completion_tokens == 20
    request = network.call_args.args[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert body["model"] == "deepseek-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert json.loads(body["messages"][1]["content"]) == data.to_dict()
    system = body["messages"][0]["content"]
    assert "只解释" in system
    assert "不得重新判断影响" in system
    assert "不得提出具体代码修改方案" in system
    assert "人工检查" in system


def test_invalid_json_missing_field_or_wrong_risk_falls_back():
    data = _input()
    expected = RuleBasedProvider().explain(data)
    outputs = (
        "not json",
        json.dumps({"summary": "缺字段"}),
        json.dumps({
            "summary": "摘要", "why_affected": "原因", "risk_level": "high",
            "suggested_check": "检查", "confidence": 0.9,
        }),
    )
    for content in outputs:
        with patch("openimpact.explanation.deepseek.urlopen",
                   return_value=FakeResponse(content)):
            assert DeepSeekProvider(api_key="test-key").explain(data) == expected


def test_network_error_and_truncated_reply_fall_back():
    data = _input()
    expected = RuleBasedProvider().explain(data)
    with patch("openimpact.explanation.deepseek.urlopen", side_effect=TimeoutError):
        assert DeepSeekProvider(api_key="test-key").explain(data) == expected
    with patch("openimpact.explanation.deepseek.urlopen",
               return_value=FakeResponse("{}", finish_reason="length")):
        assert DeepSeekProvider(api_key="test-key").explain(data) == expected


def test_factory_uses_environment_selection_and_provider_interface(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = create_explanation_provider()
    assert isinstance(provider, ExplanationProvider)
    assert isinstance(provider, DeepSeekProvider)
    with patch("openimpact.explanation.deepseek.urlopen") as network:
        assert provider.explain(_input()) == RuleBasedProvider().explain(_input())
    network.assert_not_called()
    assert isinstance(create_explanation_provider("rule"), RuleBasedProvider)


def test_http_auth_failure_has_safe_provenance_and_rule_fallback():
    data = _input()
    provider = DeepSeekProvider(api_key="test-secret-key")
    error = HTTPError("https://api.deepseek.com/chat/completions", 401,
                      "sensitive response detail", {}, None)
    with patch("openimpact.explanation.deepseek.urlopen", side_effect=error):
        result = provider.explain(data)
    assert result == RuleBasedProvider().explain(data)
    diagnostic = asdict(provider.last_call)
    assert diagnostic["status"] == "fallback"
    assert diagnostic["reason_code"] == "http_401"
    assert diagnostic["http_status"] == 401
    assert "test-secret-key" not in json.dumps(diagnostic)
    assert "sensitive response detail" not in json.dumps(diagnostic)


def test_call_provenance_resets_after_previous_success():
    data = _input()
    provider = DeepSeekProvider(api_key="test-key")
    content = json.dumps(RuleBasedProvider().explain(data).to_dict())
    with patch("openimpact.explanation.deepseek.urlopen", return_value=FakeResponse(content)):
        provider.explain(data)
    assert provider.last_call.status == "model_success"
    assert provider.last_call.response_model == "deepseek-flash"
    with patch("openimpact.explanation.deepseek.urlopen", side_effect=TimeoutError):
        provider.explain(data)
    assert provider.last_call.status == "fallback"
    assert provider.last_call.reason_code == "request_timeout"
    assert provider.last_call.response_model is None
    assert provider.last_call.http_status is None
    assert provider.last_call.prompt_tokens is None


def test_key_is_normalized_and_new_provider_reads_current_environment(monkeypatch):
    data = _input()
    content = json.dumps(RuleBasedProvider().explain(data).to_dict())
    monkeypatch.setenv("DEEPSEEK_API_KEY", " old-test-key ")
    old_provider = DeepSeekProvider()
    monkeypatch.setenv("DEEPSEEK_API_KEY", " \tnew-test-key\r\n")
    new_provider = DeepSeekProvider()
    with patch("openimpact.explanation.deepseek.urlopen",
               return_value=FakeResponse(content)) as network:
        new_provider.explain(data)
        assert network.call_args.args[0].get_header("Authorization") == "Bearer new-test-key"
        old_provider.explain(data)
        assert network.call_args.args[0].get_header("Authorization") == "Bearer old-test-key"
        DeepSeekProvider(api_key=" explicit-test-key \n").explain(data)
        assert network.call_args.args[0].get_header("Authorization") == "Bearer explicit-test-key"


def test_whitespace_only_key_skips_network():
    provider = DeepSeekProvider(api_key=" \t\r\n")
    with patch("openimpact.explanation.deepseek.urlopen") as network:
        assert provider.explain(_input()) == RuleBasedProvider().explain(_input())
    network.assert_not_called()
    assert provider.last_call.reason_code == "missing_key"
