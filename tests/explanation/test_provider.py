"""Provider selection and failures stay separate from static analysis."""

from dataclasses import replace
from pathlib import Path

import pytest

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.explanation import (
    ExplanationInput,
    ExplanationProvider,
    ExplanationResult,
    RuleBasedProvider,
    create_explanation_provider,
    explain_safely,
    fallback_explanation,
)
from openimpact.reporting.evidence import EvidenceBuilder

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"


def _input() -> ExplanationInput:
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    evidence = EvidenceBuilder(DEMO).build(run.direct.findings[0])
    return ExplanationInput.from_evidence(
        evidence, "utils.format_date 新增必填参数 timezone"
    )


class StubProvider(ExplanationProvider):
    def explain(self, input: ExplanationInput) -> ExplanationResult:
        return ExplanationResult(
            f"解释 {input.target_symbol}", input.reason, "unknown", "检查调用", 0.8
        )


class FailingProvider(ExplanationProvider):
    def explain(self, input: ExplanationInput) -> ExplanationResult:
        raise RuntimeError("provider failed")


def test_provider_interface_accepts_implementation_and_invokes_it():
    with pytest.raises(TypeError):
        ExplanationProvider()
    data = _input()
    result = StubProvider().explain(data)
    assert isinstance(result, ExplanationResult)
    assert result.summary == "解释 utils.format_date"


def test_rule_provider_uses_existing_facts_and_risk_semantics():
    data = _input()
    result = RuleBasedProvider().explain(data)
    assert result == fallback_explanation(data)
    assert "report.py:5" in result.summary
    assert data.reason in result.why_affected
    assert result.risk_level == "unknown"
    assert result.confidence == 1.0


def test_missing_input_field_is_rejected_before_provider_call():
    data = _input()
    with pytest.raises(ValueError, match="reason"):
        replace(data, reason="")
    with pytest.raises(TypeError, match="ExplanationInput"):
        RuleBasedProvider().explain(None)


def test_provider_error_falls_back_and_core_analysis_stays_unchanged():
    data = _input()
    result = explain_safely(data, FailingProvider())
    assert result == RuleBasedProvider().explain(data)
    assert explain_safely(data) == result
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    assert run.direct.direct_impact_count == 1
    assert len(run.indirect.findings) == 2


def test_default_factory_is_rule_based_and_unknown_mode_is_rejected():
    assert isinstance(create_explanation_provider(), RuleBasedProvider)
    assert create_explanation_provider("rule").explain(_input()) == RuleBasedProvider().explain(_input())
    with pytest.raises(ValueError, match="不支持"):
        create_explanation_provider("deepseek")


def test_safe_entry_returns_failed_explanation_if_input_is_invalid():
    result = explain_safely(None, FailingProvider())
    assert result.summary == "解释暂不可用。"
    assert result.risk_level == "unknown"
    assert result.confidence == 0.0
