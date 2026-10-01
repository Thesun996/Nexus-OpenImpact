"""Evidence facts remain attached to impact models without changing reports."""

from pathlib import Path

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.direct_impact import ImpactFinding
from openimpact.analysis.pipeline import analyze_project

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"


def test_direct_finding_keeps_target_location_expression_and_reference():
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    finding = run.direct.findings[0]
    assert finding.effect == "direct_impact"
    assert finding.target_symbol == "utils.format_date"
    assert finding.source_file == Path("report.py")
    assert finding.source_location.line == 5
    assert finding.source_location.column == 11
    assert finding.call_expression == "format_date(date)"
    assert finding.assessment.call_expression == finding.call_expression
    assert finding.evidence_reference == "call:report.py:5:11"
    assert "timezone" in finding.reason


def test_indirect_finding_links_upstream_call_path_to_direct_evidence():
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    direct = run.direct.findings[0]
    by_symbol = {finding.impacted_symbol_id: finding for finding in run.indirect.findings}
    dashboard = by_symbol["dashboard.dashboard"]
    page = by_symbol["page.page"]
    assert dashboard.source_file == Path("dashboard.py")
    assert dashboard.call_expression == 'report("2026-10-01")'
    assert page.source_file == Path("page.py")
    assert page.source_location.line == 5
    assert page.call_expression == "dashboard()"
    assert page.target_symbol == "utils.format_date"
    assert page.evidence_reference == direct.evidence_reference
    source = page.sources[0]
    assert source.source_direct_impact is direct
    assert source.evidence_reference == direct.evidence_reference
    assert [edge.caller_symbol_id for edge in source.propagation_path] == [
        "page.page", "dashboard.dashboard", "report.report"
    ]
    assert source.propagation_path[-1].callee_symbol_id == "utils.format_date"


def test_previous_direct_finding_constructor_remains_valid():
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    finding = run.direct.findings[0]
    legacy = ImpactFinding(
        finding.assessment, finding.impact_type, finding.effect,
        finding.rule_id, finding.reason,
    )
    assert legacy.target_symbol is None
    assert legacy.source_file is None
    assert legacy.source_location is None
    assert legacy.call_expression is None
    assert legacy.evidence_reference is None
