"""Evaluation runner accepts only externally frozen, hash-checked labels."""

import hashlib
import json
from pathlib import Path

import pytest

from openimpact.evaluation import BenchmarkError, evaluate_benchmark, _metric_summary, main


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(tmp_path: Path, case_id="basic") -> Path:
    project = tmp_path / "cases" / "basic" / "project"
    utils_hash = _write(project / "utils.py", "def format_date(date):\n    return date\n")
    _write(project / "report.py", "from utils import format_date\n\ndef report(date):\n    return format_date(date)\n")
    change_path = tmp_path / "cases" / "basic" / "change.json"
    change_hash = _write(change_path, json.dumps({
        "change_type": "add_required_parameter", "target_symbol_id": "utils.format_date",
        "before": {"name": "format_date", "parameters": [{"name": "date", "kind": "positional_or_keyword", "has_default": False}]},
        "after": {"name": "format_date", "parameters": [
            {"name": "date", "kind": "positional_or_keyword", "has_default": False},
            {"name": "timezone", "kind": "positional_or_keyword", "has_default": False},
        ]},
        "added_parameter": {"name": "timezone", "kind": "positional_or_keyword", "required": True},
    }))
    truth_path = tmp_path / "cases" / "basic" / "ground-truth.json"
    truth_hash = _write(truth_path, json.dumps({
        "case_id": case_id, "target_symbol_id": "utils.format_date", "change_type": "add_required_parameter",
        "annotation_status": "locked",
        "annotation": {"annotator": "reviewer-a", "reviewer": "reviewer-b", "label_version": "1"},
        "direct_call_sites": [{"caller_symbol_id": "report.report", "file": "report.py", "line": 4, "column": 11}],
        "indirect_impacts": [], "expected_coverage": "complete",
    }))
    _write(tmp_path / "manifest.json", json.dumps({
        "benchmark_version": "1", "cases": [{
            "case_id": case_id, "change_type": "add_required_parameter", "project": "cases/basic/project",
            "change": "cases/basic/change.json", "ground_truth": "cases/basic/ground-truth.json",
            "source_hashes": {"utils.py": utils_hash, "report.py": hashlib.sha256((project / "report.py").read_bytes()).hexdigest()},
            "change_sha256": change_hash, "ground_truth_sha256": truth_hash,
        }],
    }))
    return tmp_path


def test_evaluate_benchmark_scores_frozen_case(tmp_path):
    result = evaluate_benchmark(_case(tmp_path))

    assert result["accepted_case_count"] == 1
    assert result["rejected_case_count"] == 0
    assert result["metrics"]["direct"]["f1"] == 1.0
    assert result["metrics"]["indirect"]["precision"] is None
    assert result["metrics"]["coverage"]["accuracy"] == 1.0


def test_evaluate_benchmark_rejects_hash_mismatch(tmp_path):
    root = _case(tmp_path)
    (root / "cases" / "basic" / "project" / "utils.py").write_text("changed\n", encoding="utf-8")

    result = evaluate_benchmark(root)

    assert result["accepted_case_count"] == 0
    assert result["rejected_case_count"] == 1
    assert "哈希不匹配" in result["results"][0]["error"]


def test_evaluate_benchmark_rejects_manifest_path_escape(tmp_path):
    _write(tmp_path / "manifest.json", json.dumps({
        "benchmark_version": "1", "cases": [{
            "case_id": "escape", "change_type": "add_required_parameter", "project": "../outside",
            "change": "change.json", "ground_truth": "ground-truth.json", "source_hashes": {"x.py": "a" * 64},
            "change_sha256": "a" * 64, "ground_truth_sha256": "a" * 64,
        }],
    }))

    result = evaluate_benchmark(tmp_path)

    assert result["rejected_case_count"] == 1
    assert "不能越出 benchmark 根目录" in result["results"][0]["error"]


@pytest.mark.parametrize("mutation", ["unlisted_file", "missing_hash"])
def test_frozen_source_inventory_must_match_analyzer_inputs(tmp_path, mutation):
    root = _case(tmp_path)
    if mutation == "unlisted_file":
        _write(root / "cases/basic/project/extra.py", "from utils import format_date\ndef extra():\n    return format_date(1)\n")
    else:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        del manifest["cases"][0]["source_hashes"]["report.py"]
        _write(root / "manifest.json", json.dumps(manifest))
    result = evaluate_benchmark(root)
    assert result["accepted_case_count"] == 0
    assert result["rejected_case_count"] == 1
    assert "源码清单" in result["results"][0]["error"]
    assert result["metrics"]["direct"]["f1"] is None


def test_frozen_inventory_uses_the_same_ignored_directories_as_analysis(tmp_path):
    root = _case(tmp_path)
    _write(root / "cases/basic/project/.venv/ignored.py", "not valid python\n")
    assert evaluate_benchmark(root)["accepted_case_count"] == 1


def _replace_truth(root, update):
    truth_path = root / "cases/basic/ground-truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    update(truth)
    digest = _write(truth_path, json.dumps(truth))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["cases"][0]["ground_truth_sha256"] = digest
    _write(root / "manifest.json", json.dumps(manifest))


@pytest.mark.parametrize("mismatch", ["target", "change_type"])
def test_truth_identity_is_checked_against_the_actual_change(tmp_path, monkeypatch, mismatch):
    root = _case(tmp_path)
    if mismatch == "target":
        _replace_truth(root, lambda truth: truth.update(target_symbol_id="other.unrelated"))
    else:
        _replace_truth(root, lambda truth: truth.update(change_type="remove_parameter"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["cases"][0]["change_type"] = "remove_parameter"
        _write(root / "manifest.json", json.dumps(manifest))
    def must_not_analyze(*args, **kwargs):
        pytest.fail("mismatched truth must be rejected before source analysis")
    monkeypatch.setattr("openimpact.evaluation.analyze_project", must_not_analyze)
    result = evaluate_benchmark(root)
    assert result["accepted_case_count"] == 0
    assert result["rejected_case_count"] == 1
    assert "ChangeSpec" in result["results"][0]["error"]


@pytest.mark.parametrize("status", ["pending", "reviewed", "", None, "missing"])
def test_unlocked_annotations_cannot_produce_formal_metrics(tmp_path, status):
    root = _case(tmp_path)
    _replace_truth(root, lambda truth: truth.pop("annotation_status") if status == "missing"
                   else truth.update(annotation_status=status))
    result = evaluate_benchmark(root)
    assert result["accepted_case_count"] == 0
    assert result["rejected_case_count"] == 1
    assert "locked" in result["results"][0]["error"]
    assert result["metrics"]["direct"]["f1"] is None
    assert result["metrics"]["coverage"]["accuracy"] is None


@pytest.mark.parametrize("tp,fp,fn,precision,recall,f1", [
    (0, 1, 1, 0, 0, 0),
    (0, 0, 1, None, 0, None),
    (0, 1, 0, 0, None, None),
    (0, 0, 0, None, None, None),
    (1, 1, 1, 0.5, 0.5, 0.5),
])
def test_f1_distinguishes_zero_overlap_from_undefined_denominators(tp, fp, fn, precision, recall, f1):
    metrics = _metric_summary({"true_positive": tp, "false_positive": fp, "false_negative": fn})
    assert metrics["precision"] == precision
    assert metrics["recall"] == recall
    assert metrics["f1"] == f1


@pytest.mark.parametrize("collection,field,value", [
    ("direct_call_sites", "file", ["report.py"]),
    ("direct_call_sites", "caller_symbol_id", {}),
    ("direct_call_sites", "file", "  "),
    ("direct_call_sites", "line", True),
    ("direct_call_sites", "line", 0),
    ("direct_call_sites", "line", "4"),
    ("direct_call_sites", "column", False),
    ("direct_call_sites", "column", -1),
    ("direct_call_sites", "column", {}),
    ("indirect_impacts", "impacted_symbol_id", []),
    ("indirect_impacts", "impact_type", {}),
    ("indirect_impacts", "impact_type", "direct"),
    ("indirect_impacts", "impact_type", "indirect_3hop"),
])
def test_invalid_label_values_are_rejected_before_analysis(tmp_path, monkeypatch, collection, field, value):
    root = _case(tmp_path)
    def update(truth):
        if collection == "indirect_impacts":
            truth[collection] = [{"impacted_symbol_id": "page.page", "impact_type": "indirect_1hop"}]
        truth[collection][0][field] = value
    _replace_truth(root, update)
    monkeypatch.setattr("openimpact.evaluation.analyze_project", lambda *a, **kw: pytest.fail("invalid labels reached analysis"))
    result = evaluate_benchmark(root)
    assert result["accepted_case_count"] == 0
    assert result["rejected_case_count"] == 1
    assert field in result["results"][0]["error"]
    assert result["metrics"]["direct"]["f1"] is None


@pytest.mark.parametrize("coverage", [[], {"status": []}, {"status": {}}, None, True])
def test_invalid_coverage_type_is_rejected_before_analysis(tmp_path, monkeypatch, coverage):
    root = _case(tmp_path)
    _replace_truth(root, lambda truth: truth.update(expected_coverage=coverage))
    monkeypatch.setattr("openimpact.evaluation.analyze_project", lambda *a, **kw: pytest.fail("invalid coverage reached analysis"))
    result = evaluate_benchmark(root)
    assert result["accepted_case_count"] == 0
    assert result["rejected_case_count"] == 1
    assert "expected_coverage" in result["results"][0]["error"]


def test_one_bad_label_does_not_discard_other_cli_results(tmp_path):
    cases = []
    for case_id in ("good-before", "bad", "good-after"):
        case_root = _case(tmp_path / case_id, case_id=case_id)
        if case_id == "bad":
            _replace_truth(case_root, lambda truth: truth["direct_call_sites"][0].update(file=["report.py"]))
        case = json.loads((case_root / "manifest.json").read_text(encoding="utf-8"))["cases"][0]
        for key in ("project", "change", "ground_truth"):
            case[key] = f"{case_id}/{case[key]}"
        cases.append(case)
    _write(tmp_path / "manifest.json", json.dumps({"benchmark_version": "1", "cases": cases}))
    output = tmp_path / "output.json"
    assert main([str(tmp_path), "--output", str(output)]) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert [item["status"] for item in result["results"]] == ["completed", "rejected", "completed"]
    assert result["results"][1]["case_id"] == "bad"
    assert result["accepted_case_count"] == 2
    assert result["rejected_case_count"] == 1
    assert result["metrics"]["direct"]["true_positive"] == 2
