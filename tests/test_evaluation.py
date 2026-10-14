"""Evaluation runner accepts only externally frozen, hash-checked labels."""

import hashlib
import json
from pathlib import Path

import pytest

from openimpact.evaluation import BenchmarkError, evaluate_benchmark


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(tmp_path: Path) -> Path:
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
        "case_id": "basic", "target_symbol_id": "utils.format_date", "change_type": "add_required_parameter",
        "annotation": {"annotator": "reviewer-a", "reviewer": "reviewer-b", "label_version": "1"},
        "direct_call_sites": [{"caller_symbol_id": "report.report", "file": "report.py", "line": 4, "column": 11}],
        "indirect_impacts": [], "expected_coverage": "complete",
    }))
    _write(tmp_path / "manifest.json", json.dumps({
        "benchmark_version": "1", "cases": [{
            "case_id": "basic", "change_type": "add_required_parameter", "project": "cases/basic/project",
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
