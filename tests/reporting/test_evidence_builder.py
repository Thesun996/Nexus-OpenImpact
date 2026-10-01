"""Evidence is derived from findings and a readable source snapshot."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.models import SourceLocation
from openimpact.analysis.pipeline import analyze_project
from openimpact.reporting.evidence import EvidenceBuilder

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"


def _demo_findings():
    run = analyze_project(DEMO, load_change_spec(DEMO / "change.json"))
    return run.direct.findings[0], run.indirect.findings


def test_direct_evidence_contains_relative_location_snippet_rule_and_hash():
    direct, _ = _demo_findings()
    evidence = EvidenceBuilder(DEMO).build(direct)

    assert evidence.impact_type == "direct"
    assert evidence.target_symbol == "utils.format_date"
    assert evidence.location.file == Path("report.py")
    assert (evidence.location.line, evidence.location.column) == (5, 11)
    assert evidence.source_snippet == "    return format_date(date)"
    assert evidence.call_expression == "format_date(date)"
    assert evidence.source_hash == sha256((DEMO / "report.py").read_bytes()).hexdigest()
    assert evidence.rule == direct.rule_id
    assert evidence.reason == direct.reason
    assert evidence.evidence_reference == direct.evidence_reference
    assert evidence.propagation_path == ()
    assert evidence.diagnostics == ()


def test_indirect_evidence_keeps_upstream_path_and_direct_reference():
    direct, indirect = _demo_findings()
    page = next(item for item in indirect if item.impacted_symbol_id == "page.page")
    evidence = EvidenceBuilder(DEMO).build(page)

    assert evidence.impact_type == "indirect_2hop"
    assert evidence.location.file == Path("page.py")
    assert evidence.source_snippet == "    return dashboard()"
    assert evidence.rule == "resolved_upstream_call_path"
    assert len(evidence.propagation_path) == 1
    path = evidence.propagation_path[0]
    assert path.symbols == (
        "page.page", "dashboard.dashboard", "report.report", "utils.format_date"
    )
    assert [site.file for site in path.call_sites] == [
        Path("page.py"), Path("dashboard.py"), Path("report.py")
    ]
    assert path.direct_evidence_reference == direct.evidence_reference
    assert evidence.diagnostics == ()


def test_hash_is_stable_for_unchanged_bytes_and_changes_with_source(tmp_path):
    direct, _ = _demo_findings()
    original = (DEMO / "report.py").read_bytes()
    (tmp_path / "report.py").write_bytes(original)
    builder = EvidenceBuilder(tmp_path)

    first = builder.build(direct)
    second = builder.build(direct)
    assert first.source_hash == second.source_hash == sha256(original).hexdigest()
    (tmp_path / "report.py").write_bytes(original + b"\n# changed\n")
    assert builder.build(direct).source_hash != first.source_hash


def test_missing_source_file_returns_diagnostic(tmp_path):
    direct, _ = _demo_findings()
    evidence = EvidenceBuilder(tmp_path).build(direct)

    assert evidence.location.file == Path("report.py")
    assert evidence.source_snippet is None
    assert evidence.source_hash is None
    assert [diagnostic.code for diagnostic in evidence.diagnostics] == ["file_missing"]


def test_out_of_range_line_returns_diagnostic_without_fake_snippet():
    direct, _ = _demo_findings()
    changed = replace(direct, source_location=SourceLocation(10000, 0))
    evidence = EvidenceBuilder(DEMO).build(changed)

    assert evidence.source_snippet is None
    assert evidence.source_hash == sha256((DEMO / "report.py").read_bytes()).hexdigest()
    assert [diagnostic.code for diagnostic in evidence.diagnostics] == ["invalid_line"]


def test_source_path_cannot_escape_project(tmp_path):
    direct, _ = _demo_findings()
    changed = replace(direct, source_file=Path("..") / "secret.py")
    evidence = EvidenceBuilder(tmp_path).build(changed)

    assert evidence.location is None
    assert evidence.source_snippet is None
    assert [diagnostic.code for diagnostic in evidence.diagnostics] == ["invalid_path"]
