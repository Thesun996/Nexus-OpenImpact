import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from openimpact.analysis.change_domain import parse_domain_config
from openimpact.analysis.module_change import ModuleChangeError, build_module_change
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_pipeline import analyze_module_project
from openimpact.analysis.module_report import build_module_report
from openimpact.analysis.symbol_index import SymbolIndex


def analyze(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    before = {path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob("*.py")}
    index = SymbolIndex(tmp_path).build()
    inventory = ModuleInventory.from_index(index)
    spec = build_module_change(inventory, {"change_domain": "module", "change_type": "remove_module", "target_module_id": "utils"})
    report = build_module_report(analyze_module_project(index, spec, inventory))
    after = {path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob("*.py")}
    assert before == after
    return report


@pytest.mark.parametrize("source", ["import utils", "import utils as u", "from utils import f", "from utils import f as fd"])
def test_remove_shared_binding_rules_and_real_evidence(tmp_path, source):
    report = analyze(tmp_path, {"utils.py": "def f():\n    pass", "report.py": source})
    assert report["summary"]["direct_import_count"] == 1
    assert report["change"]["after"] is None
    assert report["evidences"][0]["source_snippet"] == source
    assert report["evidences"][0]["rule"] == "module_removed_breaks_project_import"
    assert "新增必填参数" not in json.dumps(report, ensure_ascii=False)
    assert report["explanations"][0]["explanation"]["risk_level"] == "unknown"


def test_remove_full_chain_and_multiple_direct(tmp_path):
    report = analyze(tmp_path, {"utils.py": "", "report.py": "import utils\nimport utils as u",
                                 "dashboard.py": "import report", "page.py": "import dashboard"})
    assert report["summary"]["direct_import_count"] == 2
    assert report["summary"]["indirect_1hop_module_count"] == 1
    assert report["summary"]["indirect_2hop_module_count"] == 1
    assert len(report["module_indirect_impacts"][0]["source_direct_impacts"]) == 2
    assert report["evidences"][-1]["propagation_path"][0]["modules"] == ["page", "dashboard", "report", "utils"]
    assert report["coverage"]["status"] == "complete"


def test_remove_unresolved_manual_and_no_impact(tmp_path):
    report = analyze(tmp_path, {"utils.py": "", "other.py": "", "report.py": "import other\nimport missing\nif True:\n    import utils\n__import__('utils')"})
    assert report["summary"]["direct_import_count"] == 0
    assert report["summary"]["indirect_1hop_module_count"] == 0
    assert report["summary"]["manual_review_count"] == 2
    assert report["summary"]["unresolved_import_count"] == 1
    assert report["coverage"]["status"] == "partial"


def test_remove_cycle_and_dedup(tmp_path):
    report = analyze(tmp_path, {"utils.py": "import report", "report.py": "import utils\nimport a",
                                "a.py": "import report\nimport b", "b.py": "import a"})
    assert report["summary"]["direct_import_count"] == 1
    assert report["summary"]["indirect_1hop_module_count"] == 1
    assert report["summary"]["indirect_2hop_module_count"] == 1
    assert {item["impacted_module_id"] for item in report["module_indirect_impacts"]} == {"a", "b"}
    own_reference = next(item for item in report["import_assessments"] if item["before"]["source_module"] == "utils")
    assert own_reference["effect"] == "source_removed"
    assert own_reference["after"]["status"] == "not_applicable"


def test_removed_self_import_does_not_break_surviving_source(tmp_path):
    report = analyze(tmp_path, {"utils.py": "import utils"})
    assert report["summary"]["direct_import_count"] == 0
    assert not report["module_indirect_impacts"]
    assert report["import_assessments"][0]["effect"] == "source_removed"


@pytest.mark.parametrize("config", [
    '{"change_domain":"other"}',
    '{"change_domain":"module","change_domain":"function"}',
    '{"change_domain":"module","change_type":"remove_module","target_module_id":"utils","target_module_id":"other"}',
    '[]', '{invalid',
])
def test_invalid_domain_documents(config):
    from openimpact.api_change import ChangeConfigError
    with pytest.raises(ChangeConfigError):
        parse_domain_config(config)


def test_remove_demo_cli_and_legacy_demo(tmp_path):
    root = Path(__file__).resolve().parents[2]
    for name, expected in [("module_removal", "module"), ("signature_change", "function")]:
        project = root / "examples" / name
        process = subprocess.run([sys.executable, "-X", "utf8", "-m", "openimpact", "analyze", str(project), "--change", str(project / "change.json"), "--format", "json"], capture_output=True, text=True, encoding="utf-8")
        assert process.returncode == 0, process.stderr
        report = json.loads(process.stdout)
        assert report.get("change_domain", "function") == expected
        assert report["coverage"]["status"] == "complete"
        assert report["summary"]["direct_import_count" if expected == "module" else "direct_impact_count"] == 1
