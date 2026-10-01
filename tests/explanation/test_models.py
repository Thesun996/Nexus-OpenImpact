"""Explanation contracts accept evidence and cannot invent missing impact facts."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.explanation import (
    ExplanationInput,
    ExplanationResult,
    fallback_explanation,
)
from openimpact.reporting.evidence import EvidenceBuilder

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
CHANGE_DESCRIPTION = "utils.format_date 新增必填参数 timezone"


def _evidences():
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    builder = EvidenceBuilder(DEMO)
    return (builder.build(run.direct.findings[0]),
            builder.build(next(item for item in run.indirect.findings
                               if item.impacted_symbol_id == "page.page")))


def test_direct_evidence_converts_to_json_ready_input():
    direct, _ = _evidences()
    data = ExplanationInput.from_evidence(direct, CHANGE_DESCRIPTION)
    payload = data.to_dict()

    assert payload["target_symbol"] == "utils.format_date"
    assert payload["change_description"] == CHANGE_DESCRIPTION
    assert payload["impact_type"] == "direct"
    assert payload["source_location"] == {
        "file": "report.py", "line": 5, "column": 11, "end_line": 5
    }
    assert payload["source_snippet"] == "    return format_date(date)"
    assert payload["propagation_path"] == []
    json.dumps(payload, ensure_ascii=False)


def test_indirect_evidence_converts_with_complete_path():
    _, indirect = _evidences()
    data = ExplanationInput.from_evidence(indirect, CHANGE_DESCRIPTION)
    path = data.to_dict()["propagation_path"][0]
    assert data.impact_type == "indirect_2hop"
    assert path["symbols"] == [
        "page.page", "dashboard.dashboard", "report.report", "utils.format_date"
    ]
    assert [site["file"] for site in path["call_sites"]] == [
        "page.py", "dashboard.py", "report.py"
    ]
    assert path["direct_evidence_reference"] == "call:report.py:5:11"


def test_input_rejects_missing_evidence_or_invalid_contract():
    direct, indirect = _evidences()
    with pytest.raises(TypeError, match="ImpactEvidence"):
        ExplanationInput.from_evidence(None, CHANGE_DESCRIPTION)
    with pytest.raises(ValueError, match="Evidence 不完整"):
        ExplanationInput.from_evidence(replace(direct, source_snippet=None), CHANGE_DESCRIPTION)
    with pytest.raises(ValueError, match="change_description"):
        ExplanationInput.from_evidence(direct, " ")
    valid = ExplanationInput.from_evidence(direct, CHANGE_DESCRIPTION)
    with pytest.raises(ValueError, match="source_location"):
        replace(valid, source_location=replace(valid.source_location, file=Path("../secret.py")))
    with pytest.raises(ValueError, match="propagation_path"):
        replace(ExplanationInput.from_evidence(indirect, CHANGE_DESCRIPTION),
                propagation_path=())
    indirect_input = ExplanationInput.from_evidence(indirect, CHANGE_DESCRIPTION)
    invalid_path = replace(indirect_input.propagation_path[0],
                           symbols=("page.page", 42, "utils.format_date"))
    with pytest.raises(ValueError, match="propagation_path"):
        replace(indirect_input, propagation_path=(invalid_path,))


def test_output_validates_text_risk_and_confidence():
    valid = ExplanationResult("摘要", "依据", "unknown", "检查调用", 1.0)
    assert valid.to_dict()["confidence"] == 1.0
    with pytest.raises(ValueError, match="summary"):
        replace(valid, summary="")
    with pytest.raises(ValueError, match="risk_level"):
        replace(valid, risk_level="certain")
    for value in (-0.1, 1.1, float("nan"), True):
        with pytest.raises(ValueError, match="confidence"):
            replace(valid, confidence=value)


def test_rule_fallback_explains_direct_without_claiming_business_severity():
    direct, _ = _evidences()
    data = ExplanationInput.from_evidence(direct, CHANGE_DESCRIPTION)
    result = fallback_explanation(data)

    assert "report.py:5" in result.summary
    assert "已确定不兼容" in result.summary
    assert data.rule in result.why_affected
    assert data.reason in result.why_affected
    assert result.risk_level == "unknown"
    assert result.confidence == 1.0
    assert "检查" in result.suggested_check
    json.dumps(result.to_dict(), ensure_ascii=False)


def test_rule_fallback_keeps_indirect_uncertainty_and_path():
    _, indirect = _evidences()
    data = ExplanationInput.from_evidence(indirect, CHANGE_DESCRIPTION)
    result = fallback_explanation(data)

    assert "page.py:5" in result.summary
    assert "page.page → dashboard.dashboard → report.report → utils.format_date" in result.why_affected
    assert "不保证运行时失败" in result.why_affected
    assert result.risk_level == "unknown"
