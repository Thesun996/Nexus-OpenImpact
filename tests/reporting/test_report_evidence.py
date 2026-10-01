"""Core report evidence remains additive and cannot block impact results."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.api import app

DEMO = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
CHANGE = DEMO / "change.json"


def _report():
    return build_report(analyze_project(DEMO, load_change_spec(CHANGE)))


def test_direct_evidence_appears_with_source_location_and_snippet():
    report = _report()
    direct = next(item for item in report["evidences"] if item["impact_type"] == "direct")
    assert direct["target_symbol"] == "utils.format_date"
    assert direct["location"]["file"] == "report.py"
    assert direct["location"]["line"] == 5
    assert direct["source_snippet"] == "    return format_date(date)"
    assert direct["source_hash"] and len(direct["source_hash"]) == 64
    assert direct["rule"] == report["direct_impacts"][0]["rule_id"]
    assert direct["status"] == "available"
    assert direct["diagnostics"] == []


def test_indirect_evidence_preserves_path_to_direct_call():
    report = _report()
    page = next(item for item in report["evidences"]
                if item["impact_type"] == "indirect_2hop")
    path = page["propagation_path"][0]
    assert path["symbols"] == [
        "page.page", "dashboard.dashboard", "report.report", "utils.format_date"
    ]
    assert [site["file"] for site in path["call_sites"]] == [
        "page.py", "dashboard.py", "report.py"
    ]
    assert path["direct_evidence_reference"] == report["evidences"][0]["evidence_reference"]
    assert page["location"]["file"] == "page.py"
    assert page["status"] == "available"


def test_old_report_fields_and_counts_remain_available():
    report = _report()
    for field in ("direct_impacts", "indirect_impacts", "summary", "diagnostics",
                  "coverage", "validation", "manual_reviews", "pre_existing_problems"):
        assert field in report
    assert report["schema_version"] == 1
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert len(report["evidences"]) == 3


def test_missing_source_returns_unavailable_evidence_without_losing_impact(tmp_path):
    for path in DEMO.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    run = analyze_project(tmp_path, load_change_spec(CHANGE))
    (tmp_path / "report.py").unlink()

    report = build_report(run)
    assert report["summary"]["direct_impact_count"] == 1
    assert report["direct_impacts"][0]["file"] == "report.py"
    direct = report["evidences"][0]
    assert direct["status"] == "unavailable"
    assert direct["source_snippet"] is None
    assert direct["diagnostics"][0]["code"] == "file_missing"


def test_unexpected_evidence_failure_is_isolated_and_does_not_leak_details():
    run = analyze_project(DEMO, load_change_spec(CHANGE))
    with patch("openimpact.analysis.report.EvidenceBuilder.build",
               side_effect=RuntimeError("private server path")):
        report = build_report(run)

    assert report["summary"]["direct_impact_count"] == 1
    assert len(report["evidences"]) == 3
    assert all(item["status"] == "unavailable" for item in report["evidences"])
    assert all(item["diagnostics"][0]["code"] == "evidence_unavailable"
               for item in report["evidences"])
    assert "private server path" not in json.dumps(report)


def test_cli_json_and_demo_api_include_evidence():
    result = subprocess.run(
        [sys.executable, "-m", "openimpact", "analyze", str(DEMO),
         "--change", str(CHANGE), "--format", "json"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["evidences"]) == 3

    with TestClient(app) as client:
        response = client.post("/api/v1/demo/analyze")
    assert response.status_code == 200
    assert len(response.json()["evidences"]) == 3
