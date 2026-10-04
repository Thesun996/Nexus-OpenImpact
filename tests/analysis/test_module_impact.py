import json
import subprocess
import sys
from pathlib import Path

import pytest

from openimpact.analysis.module_change import build_module_change
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_impact import propagate_module_impact
from openimpact.analysis.module_pipeline import analyze_module_project
from openimpact.analysis.module_report import build_module_report
from openimpact.analysis.symbol_index import SymbolIndex


def run_project(tmp_path, files=None, kind="rename_module", target="utils"):
    files = files or {"utils.py": "def format_date(x):\n    return x\n",
                      "report.py": "from utils import format_date\ndef report():\n    return format_date(1)\n",
                      "dashboard.py": "from report import report\ndef dashboard():\n    return report()\n",
                      "page.py": "from dashboard import dashboard\ndef page():\n    return dashboard()\n",
                      "outer.py": "from page import page\n"}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    index = SymbolIndex(tmp_path).build()
    inventory = ModuleInventory.from_index(index)
    config = {"change_domain": "module", "change_type": kind, "target_module_id": target}
    if kind == "rename_module":
        config["new_module_name"] = "formatting"
    return analyze_module_project(index, build_module_change(inventory, config), inventory)


def test_rename_chain_exact_evidence_and_depth(tmp_path):
    run = run_project(tmp_path)
    report = build_module_report(run)
    assert len(run.direct) == 1
    assert [(finding.impacted_module_id, finding.hop) for finding in run.indirect] == [("dashboard", 1), ("page", 2)]
    assert all(finding.impacted_module_id != "outer" for finding in run.indirect)
    assert report["summary"]["direct_import_count"] == 1
    assert report["coverage"]["status"] == "complete"
    direct = report["import_impacts"][0]
    assert direct["before_resolution"]["status"] == "resolved_project"
    assert direct["after_resolution"]["status"] == "unresolved"
    evidence = report["evidences"][0]
    assert evidence["location"]["file"] == "report.py"
    assert evidence["source_snippet"] == "from utils import format_date"
    assert evidence["rule"] == "module_renamed_breaks_project_import"
    assert report["evidences"][2]["propagation_path"][0]["modules"] == ["page", "dashboard", "report", "utils"]
    assert report["evidences"][2]["propagation_path"][0]["source_direct_impact"] == direct["finding_id"]
    assert len(report["evidences"]) == len(report["explanations"]) == 3
    assert report["explanations"][0]["evidence_reference"] == evidence["evidence_reference"]
    assert report["explanations"][0]["explanation"]["risk_level"] == "unknown"
    assert "direct_impacts" not in report
    assert "signature" not in json.dumps(report)
    assert not (tmp_path / "formatting.py").exists()


@pytest.mark.parametrize("source", ["import utils", "import utils as u", "from utils import format_date", "from utils import format_date as fd"])
def test_rename_four_imports(tmp_path, source):
    run = run_project(tmp_path, {"utils.py": "def format_date(x):\n    return x", "report.py": source})
    assert len(run.direct) == 1
    assert run.direct[0].assessment.before.syntax.source_text == source


def test_multiple_seeds_and_paths_deduplicate_modules(tmp_path):
    run = run_project(tmp_path, {"utils.py": "", "a.py": "import utils\ndef a():\n    pass", "b.py": "import utils\ndef b():\n    pass",
                                  "page.py": "from a import a\nfrom b import b", "outer.py": "import page"})
    assert len(run.direct) == 2
    by_module = {finding.impacted_module_id: finding for finding in run.indirect}
    assert len(by_module) == 2
    assert by_module["page"].hop == 1
    assert len(by_module["page"].sources) == 2
    assert by_module["outer"].hop == 2


def test_cycle_and_duplicate_reference(tmp_path):
    run = run_project(tmp_path, {"utils.py": "import dashboard", "report.py": "import utils\ndef report():\n    pass",
                                  "dashboard.py": "from report import report"})
    assert len(run.indirect) == 2
    assert len({finding.impacted_module_id for finding in run.indirect}) == 2
    assert not propagate_module_impact(run.graph, run.direct, max_depth=0)
    with pytest.raises(ValueError):
        propagate_module_impact(run.graph, run.direct, max_depth=3)


def test_unresolved_manual_and_improvement_are_not_seeds(tmp_path):
    run = run_project(tmp_path, {"utils.py": "def f():\n    pass", "report.py": "import missing\nimport formatting\nfrom utils import unknown\ndef report():\n    pass",
                                  "page.py": "from report import report"})
    assert not run.direct and not run.indirect
    effects = {item.effect for item in run.assessments}
    assert effects == {"unresolved", "resolution_improved", "manual_review", "no_impact"}
    assert build_module_report(run)["coverage"]["status"] == "partial"


def test_partial_keeps_confirmed_impact_and_diagnostics(tmp_path):
    run = run_project(tmp_path, {"utils.py": "", "report.py": "import utils\nif True:\n    import utils\n__import__('utils')",
                                  "bad.py": "def broken(:", "pkg/report.py": "import utils"})
    report = build_module_report(run)
    assert report["summary"]["direct_import_count"] == 1
    assert report["summary"]["manual_review_count"] == 3
    assert report["coverage"]["status"] == "partial"
    assert report["diagnostics"]["parse_errors"][0]["file"] == "bad.py"
    assert str(tmp_path) not in json.dumps(report)


def test_no_import_and_unrelated_module(tmp_path):
    run = run_project(tmp_path, {"utils.py": "", "other.py": "", "report.py": "import other"})
    report = build_module_report(run)
    assert not run.direct and not run.indirect
    assert report["summary"]["direct_import_count"] == 0
    assert report["evidences"] == [] and report["explanations"] == []
    assert report["coverage"]["status"] == "complete"


def test_missing_or_changed_source_downgrades_evidence_only(tmp_path):
    run = run_project(tmp_path)
    (tmp_path / "report.py").unlink()
    report = build_module_report(run)
    assert report["summary"]["direct_import_count"] == 1
    assert report["evidences"][0]["status"] == "unavailable"
    assert report["explanations"][0]["status"] == "unavailable"
    (tmp_path / "page.py").write_text("# changed", encoding="utf-8")
    changed = build_module_report(run)
    assert changed["evidences"][2]["status"] == "unavailable"
    assert changed["evidences"][2]["source_snippet"] is None


def test_builder_and_explanation_failure_do_not_destroy_report(tmp_path, monkeypatch):
    run = run_project(tmp_path)
    def fail(*args, **kwargs):
        raise RuntimeError("SECRET /server/internal")
    monkeypatch.setattr("openimpact.analysis.module_report.ImportEvidenceBuilder.build", fail)
    report = build_module_report(run)
    assert report["summary"]["direct_import_count"] == 1
    assert all(evidence["status"] == "unavailable" for evidence in report["evidences"])
    assert "SECRET" not in json.dumps(report)


def test_rename_cli(tmp_path):
    run_project(tmp_path)
    change = tmp_path / "change.json"
    change.write_text(json.dumps({"change_domain": "module", "change_type": "rename_module", "target_module_id": "utils", "new_module_name": "formatting"}))
    process = subprocess.run([sys.executable, "-X", "utf8", "-m", "openimpact", "analyze", str(tmp_path), "--change", str(change), "--format", "json"], capture_output=True, text=True, encoding="utf-8")
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["summary"]["direct_import_count"] == 1
