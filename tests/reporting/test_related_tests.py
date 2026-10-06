"""Named test candidates require existing definite paths, never names alone."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import zipfile

import pytest
from fastapi.testclient import TestClient

from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report, render_chinese_report
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.api_change import build_change_spec
from openimpact.api import app
from openimpact.repository import zip_inspector


ADD = {"target_symbol_id": "utils.f", "added_parameter": {"name": "strict", "kind": "keyword_only"}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")


def write(root, sources):
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def analyze(root, sources, config=ADD, analysis_root="."):
    write(root, sources)
    spec = build_change_spec(SymbolIndex(root, analysis_root=analysis_root).build(), config)
    return analyze_project(root, spec, analysis_root=analysis_root)


def chain():
    return {"utils.py": "def f(a):\n    return a\n",
            "report.py": "from utils import f\ndef report():\n    return f(1)\n",
            "page.py": "from report import report\ndef page():\n    return report()\n",
            "tests/test_suite.py": "from utils import f\nfrom report import report\nfrom page import page\n"
                                   "def test_direct():\n    return f(1)\n"
                                   "def test_report():\n    return report()\n"
                                   "def test_page():\n    return page()\n"
                                   "def test_unrelated():\n    return 42\n"}


def test_direct_and_two_upstream_tests_use_real_sites_hashes_and_unique_symbols(tmp_path):
    sources = chain()
    run = analyze(tmp_path, sources)
    snapshot = {name: (tmp_path / name).read_bytes() for name in sources}
    report = build_report(run)
    related = report["related_tests"]
    assert related["status"] == "available" and related["indexed_test_count"] == 4
    candidates = related["candidates"]
    assert [item["test_symbol_id"] for item in candidates] == [
        "tests.test_suite.test_direct", "tests.test_suite.test_report", "tests.test_suite.test_page"]
    assert [len(item["paths"][0]["call_sites"]) for item in candidates] == [1, 2, 3]
    assert [item["line"] for item in candidates] == [4, 6, 8]
    assert candidates[0]["node_id"] == "tests/test_suite.py::test_direct"
    seeds = {item.evidence_reference for item in run.direct.findings if item.effect == "direct_impact"}
    for candidate in candidates:
        for path in candidate["paths"]:
            assert path["direct_evidence_reference"] in seeds
            assert path["status"] == "available"
            for site in path["call_sites"]:
                assert not Path(site["file"]).is_absolute()
                assert site["source_hash"] == hashlib.sha256(snapshot[site["file"]]).hexdigest()
                assert site["source_snippet"] in sources[site["file"]]
    assert snapshot == {name: (tmp_path / name).read_bytes() for name in sources}
    assert report["summary"]["direct_impact_count"] == 2
    assert report["coverage"]["status"] == "complete"
    assert "未实际收集或运行测试" in render_chinese_report(report)


@pytest.mark.parametrize("signature,call,config", [
    ("a", "1", ADD),
    ("a, b=2", "1, b=3", {"target_symbol_id": "utils.f", "change_type": "remove_parameter", "parameter_name": "b"}),
    ("a, timeout=5", "1, timeout=3", {"target_symbol_id": "utils.f", "change_type": "rename_parameter", "parameter_name": "timeout", "new_parameter_name": "delay"}),
    ("a, timeout=5", "1", {"target_symbol_id": "utils.f", "change_type": "make_parameter_required", "parameter_name": "timeout"}),
])
def test_four_operations_share_the_same_candidate_path_logic(tmp_path, signature, call, config):
    run = analyze(tmp_path, {"utils.py": f"def f({signature}):\n    return a\n",
                             "tests/test_api.py": f"from utils import f\ndef test_api():\n    return f({call})\n"}, config)
    report = build_report(run)
    assert report["summary"]["direct_impact_count"] == 1
    assert report["related_tests"]["candidates"][0]["relationship"] == "direct"


def test_name_similarity_non_test_helpers_and_same_named_other_function_do_not_create_candidates(tmp_path):
    sources = chain()
    sources["other.py"] = "def f(a):\n    return a\n"
    sources["tests/test_suite.py"] = "from other import f\ndef test_format():\n    return f(1)\n"
    sources["helpers.py"] = "from utils import f\ndef test_looks_related():\n    return f(1)\n"
    sources["tests/api_test.py"] = "from utils import f\ndef helper():\n    return f(1)\n"
    result = build_report(analyze(tmp_path, sources))["related_tests"]
    assert result["indexed_test_count"] == 1
    assert result["candidates"] == []


@pytest.mark.parametrize("call,effect", [("*values", "manual_review"), ("**values", "manual_review"), ("1, bad=2", "pre_existing_problem")])
def test_uncertain_and_pre_existing_calls_never_seed_test_recommendations(tmp_path, call, effect):
    run = analyze(tmp_path, {"utils.py": "def f(a):\n    return a\n",
                             "test_cases.py": f"from utils import f\ndef test_case(values):\n    return f({call})\n"})
    assert run.direct.assessments[0].effect == effect
    assert build_report(run)["related_tests"]["candidates"] == []


def test_zero_impact_and_compatibility_improved_have_no_false_test_candidates(tmp_path):
    config = {"target_symbol_id": "utils.f", "change_type": "rename_parameter", "parameter_name": "timeout", "new_parameter_name": "delay"}
    sources = {"utils.py": "def f(a, timeout=5):\n    return a\n",
               "test_api.py": "from utils import f\ndef test_positional():\n    return f(1, 5)\ndef test_improved():\n    return f(1, delay=5)\n"}
    run = analyze(tmp_path, sources, config)
    assert {item.effect for item in run.direct.assessments} == {"no_impact", "compatibility_improved"}
    report = build_report(run)
    assert report["summary"]["direct_impact_count"] == 0
    assert report["related_tests"]["candidates"] == []


def test_multiple_seeds_and_cycles_keep_one_test_with_real_representative_paths(tmp_path):
    sources = {"utils.py": "def f(a):\n    return a\n",
               "report.py": "from utils import f\ndef report():\n    f(1); f(2)\n",
               "test_cycle.py": "from report import report\ndef test_first():\n    report()\n    test_second()\ndef test_second():\n    test_first()\n"}
    report = build_report(analyze(tmp_path, sources))
    candidates = report["related_tests"]["candidates"]
    assert len(candidates) == 2
    assert all(len(item["paths"]) == 2 for item in candidates)
    assert len({path["direct_evidence_reference"] for path in candidates[0]["paths"]}) == 2


def test_src_layout_aliases_and_tests_outside_src_use_current_module_identities(tmp_path):
    sources = {"src/pkg/__init__.py": "", "src/pkg/utils.py": "def f(a):\n    return a\n",
               "src/pkg/report.py": "from .utils import f as render\ndef report():\n    return render(1)\n",
               "tests/test_report.py": "from pkg.report import report as render\ndef testReport():\n    return render()\n"}
    config = {**ADD, "target_symbol_id": "pkg.utils.f"}
    report = build_report(analyze(tmp_path, sources, config, "src"))
    candidate = report["related_tests"]["candidates"][0]
    assert candidate["node_id"] == "tests/test_report.py::testReport"
    sites = candidate["paths"][0]["call_sites"]
    assert [site["callee_symbol_id"] for site in sites] == ["pkg.report.report", "pkg.utils.f"]
    assert sites[1]["file"] == "src/pkg/report.py"


def test_partial_syntax_class_fixture_and_deep_paths_are_not_silently_promised(tmp_path):
    sources = chain()
    sources.update({"tests/test_broken.py": "def broken(:\n",
                    "tests/test_class.py": "from utils import f\nclass TestApi:\n    def test_method(self):\n        return f(1)\n",
                    "outer.py": "from page import page\ndef outer():\n    return page()\n",
                    "test_deep.py": "from outer import outer\ndef test_deep():\n    return outer()\n"})
    report = build_report(analyze(tmp_path, sources))
    assert report["coverage"]["status"] == "partial"
    candidates = report["related_tests"]["candidates"]
    assert all("test_deep" not in item["test_symbol_id"] and "test_method" not in item["test_symbol_id"] for item in candidates)
    assert any("fixture" in text and "更深" in text for text in report["related_tests"]["limitations"])


@pytest.mark.parametrize("failure", ["missing", "changed"])
def test_missing_or_changed_source_never_borrows_old_test_evidence(tmp_path, failure):
    run = analyze(tmp_path, chain())
    path = tmp_path / "tests/test_suite.py"
    if failure == "missing":
        path.unlink()
    else:
        path.write_text(path.read_text(encoding="utf-8").replace("f(1)", "f(99)"), encoding="utf-8")
    candidate = build_report(run)["related_tests"]["candidates"][0]
    site = candidate["paths"][0]["call_sites"][0]
    assert site["status"] == "unavailable" and site["source_snippet"] is None
    assert site["diagnostics"]


def test_enrichment_failure_keeps_all_existing_report_fields(tmp_path):
    run = analyze(tmp_path, chain())
    baseline = build_report(run)
    with patch("openimpact.analysis.report.build_related_tests", side_effect=RuntimeError("private path or secret")):
        failed = build_report(run)
    assert {key: value for key, value in failed.items() if key != "related_tests"} == {
        key: value for key, value in baseline.items() if key != "related_tests"}
    assert failed["related_tests"]["status"] == "unavailable"
    assert "private path or secret" not in json.dumps(failed)


def test_without_test_files_the_old_demo_report_is_unchanged():
    from openimpact.analysis.change_file import load_change_spec
    demo = Path(__file__).resolve().parents[2] / "examples/signature_change"
    report = build_report(analyze_project(demo, load_change_spec(demo / "change.json")))
    assert "related_tests" not in report
    assert [report["summary"][key] for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count")] == [1, 1, 1]


def test_real_zip_workflow_keeps_fingerprint_paths_source_bytes_and_cleanup(tmp_path):
    sources = chain()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for file, content in sources.items():
            archive.writestr("uploaded/" + file, content)
    data = stream.getvalue()
    fingerprint = hashlib.sha256(data).hexdigest()
    directories = []
    original = zip_inspector.TemporaryDirectory
    def record(*args, **kwargs):
        directory = original(*args, **kwargs)
        directories.append(Path(directory.name))
        return directory
    with patch.object(zip_inspector, "TemporaryDirectory", side_effect=record), TestClient(app) as client:
        files = {"file": ("chosen.zip", data, "application/zip")}
        inspected = client.post("/api/v1/projects/inspect", files=files)
        assert inspected.json()["project_fingerprint"] == fingerprint
        fields = {"change": json.dumps(ADD), "expected_fingerprint": fingerprint}
        validated = client.post("/api/v1/changes/validate", files=files, data=fields)
        response = client.post("/api/v1/projects/analyze", files=files, data=fields)
        assert validated.status_code == response.status_code == 200
        assert len(response.json()["related_tests"]["candidates"]) == 3
        mismatch = client.post("/api/v1/projects/analyze", files=files, data={**fields, "expected_fingerprint": "0" * 64})
        assert mismatch.status_code == 409
    assert len(directories) == 3 and all(not path.exists() for path in directories)
    assert all(str(path) not in response.text for path in directories)
    assert hashlib.sha256(data).hexdigest() == fingerprint


def test_uploaded_code_is_never_executed_and_cli_returns_test_locations(tmp_path):
    sources = chain()
    sources["test_side_effect.py"] = "from utils import f\nraise RuntimeError('must not execute')\ndef test_case():\n    return f(1)\n"
    run = analyze(tmp_path, sources)
    change = tmp_path / "change.json"
    change.write_text(json.dumps(run.change_spec.to_dict()), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "openimpact", "analyze", str(tmp_path), "--change", str(change), "--format", "json"],
                            text=True, encoding="utf-8", capture_output=True, check=True)
    report = json.loads(result.stdout)
    assert any(item["node_id"] == "test_side_effect.py::test_case" for item in report["related_tests"]["candidates"])
