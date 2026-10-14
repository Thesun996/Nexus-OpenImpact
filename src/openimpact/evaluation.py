"""Run an externally annotated function-change benchmark without executing samples.

The evaluator intentionally refuses unlabelled or hash-mismatched data. It is
not a source of ground truth: it only compares the frozen human labels with
the existing static-analysis pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.explanation.fallback import RuleBasedProvider


class BenchmarkError(ValueError):
    """The benchmark layout or its frozen annotations are invalid."""


_REQUIRED_CASE_FIELDS = {
    "case_id", "change_type", "project", "change", "ground_truth",
    "source_hashes", "change_sha256", "ground_truth_sha256",
}
_DIRECT_KEYS = ("caller_symbol_id", "file", "line", "column")
_INDIRECT_KEYS = ("impacted_symbol_id", "impact_type")


def evaluate_benchmark(root: str | Path) -> dict[str, Any]:
    """Validate and evaluate every case in a manifest, retaining failures."""
    benchmark_root, cases = load_benchmark(root)
    results: list[dict[str, Any]] = []
    direct_totals = _empty_counts()
    indirect_totals = _empty_counts()
    coverage_matches = 0

    for case in cases:
        try:
            result = _evaluate_case(benchmark_root, case)
        except (BenchmarkError, ChangeFileError, OSError, ValueError) as error:
            results.append({"case_id": case.get("case_id"), "status": "rejected", "error": str(error)})
            continue

        results.append(result)
        _add_counts(direct_totals, result["direct"]["counts"])
        _add_counts(indirect_totals, result["indirect"]["counts"])
        coverage_matches += int(result["coverage"]["matches"])

    accepted = [item for item in results if item["status"] == "completed"]
    return {
        "benchmark_root": str(benchmark_root),
        "accepted_case_count": len(accepted),
        "rejected_case_count": len(results) - len(accepted),
        "results": results,
        "metrics": {
            "direct": _metric_summary(direct_totals),
            "indirect": _metric_summary(indirect_totals),
            "coverage": {
                "matched_case_count": coverage_matches,
                "evaluated_case_count": len(accepted),
                "accuracy": _ratio(coverage_matches, len(accepted)),
            },
        },
    }


def load_benchmark(root: str | Path) -> tuple[Path, list[dict[str, Any]]]:
    """Load and validate the manifest before any source analysis starts."""
    benchmark_root = Path(root).resolve()
    manifest_path = benchmark_root / "manifest.json"
    manifest = _read_object(manifest_path, "manifest")
    if not isinstance(manifest.get("benchmark_version"), str) or not manifest["benchmark_version"]:
        raise BenchmarkError("manifest.benchmark_version 必须是非空字符串。")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkError("manifest.cases 必须是非空数组。")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise BenchmarkError("manifest.cases 中每项必须是对象。")
        missing = sorted(_REQUIRED_CASE_FIELDS - raw_case.keys())
        if missing:
            raise BenchmarkError(f"案例缺少字段：{', '.join(missing)}。")
        case_id = raw_case["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise BenchmarkError("case_id 必须是非空字符串。")
        if case_id in seen:
            raise BenchmarkError(f"case_id 重复：{case_id}。")
        seen.add(case_id)
        normalized.append(raw_case)
    return benchmark_root, normalized


def _evaluate_case(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    case_id = _string(case, "case_id")
    project = _relative_path(root, case["project"], f"{case_id}.project")
    change_path = _relative_path(root, case["change"], f"{case_id}.change")
    truth_path = _relative_path(root, case["ground_truth"], f"{case_id}.ground_truth")
    if not project.is_dir():
        raise BenchmarkError(f"{case_id}: project 必须是目录。")
    _verify_source_hashes(project, case["source_hashes"], case_id)
    _verify_hash(change_path, case["change_sha256"], f"{case_id}.change_sha256")
    _verify_hash(truth_path, case["ground_truth_sha256"], f"{case_id}.ground_truth_sha256")
    truth = _read_object(truth_path, f"{case_id} ground_truth")
    _validate_truth(case, truth)

    started = time.perf_counter()
    report = build_report(analyze_project(project, load_change_spec(change_path)), explanation_provider=RuleBasedProvider())
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if not report["validation"]["valid"]:
        raise BenchmarkError(f"{case_id}: ChangeSpec 未通过现有 Core 校验，不能纳入有效评测。")

    expected_direct = _site_set(truth["direct_call_sites"], _DIRECT_KEYS, case_id, "direct_call_sites")
    predicted_direct = _site_set(report["direct_impacts"], _DIRECT_KEYS, case_id, "direct_impacts")
    expected_indirect = _site_set(truth["indirect_impacts"], _INDIRECT_KEYS, case_id, "indirect_impacts")
    predicted_indirect = _site_set(report["indirect_impacts"], _INDIRECT_KEYS, case_id, "predicted indirect_impacts")
    expected_coverage = _coverage_status(truth["expected_coverage"], case_id)

    return {
        "case_id": case_id,
        "status": "completed",
        "change_type": case["change_type"],
        "analysis_duration_ms": elapsed_ms,
        "direct": _comparison(expected_direct, predicted_direct),
        "indirect": _comparison(expected_indirect, predicted_indirect),
        "coverage": {"expected": expected_coverage, "actual": report["coverage"]["status"],
                     "matches": expected_coverage == report["coverage"]["status"]},
    }


def _validate_truth(case: dict[str, Any], truth: dict[str, Any]) -> None:
    case_id = _string(case, "case_id")
    for key in ("case_id", "target_symbol_id", "change_type", "annotation", "direct_call_sites", "indirect_impacts", "expected_coverage"):
        if key not in truth:
            raise BenchmarkError(f"{case_id}: ground_truth 缺少 {key}。")
    if truth["case_id"] != case_id or truth["change_type"] != case["change_type"]:
        raise BenchmarkError(f"{case_id}: ground_truth 元数据与 manifest 不一致。")
    annotation = truth["annotation"]
    if not isinstance(annotation, dict) or not all(isinstance(annotation.get(key), str) and annotation[key]
                                                   for key in ("annotator", "reviewer", "label_version")):
        raise BenchmarkError(f"{case_id}: ground_truth.annotation 必须包含 annotator、reviewer、label_version。")
    if not isinstance(truth["direct_call_sites"], list) or not isinstance(truth["indirect_impacts"], list):
        raise BenchmarkError(f"{case_id}: ground_truth 影响集合必须是数组。")


def _verify_source_hashes(project: Path, hashes: object, case_id: str) -> None:
    if not isinstance(hashes, dict) or not hashes:
        raise BenchmarkError(f"{case_id}: source_hashes 必须是非空对象。")
    for relative, digest in hashes.items():
        path = _relative_path(project, relative, f"{case_id}.source_hashes")
        _verify_hash(path, digest, f"{case_id}.source_hashes[{relative!r}]")


def _verify_hash(path: Path, expected: object, label: str) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise BenchmarkError(f"{label} 必须是 64 位 SHA-256。")
    if not path.is_file():
        raise BenchmarkError(f"{label} 指向的文件不存在。")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected.lower():
        raise BenchmarkError(f"{label} 哈希不匹配。")


def _relative_path(root: Path, raw: object, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise BenchmarkError(f"{label} 必须是非空相对路径。")
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise BenchmarkError(f"{label} 不能越出 benchmark 根目录。") from error
    return candidate


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"无法读取 {label}：{error}") from error
    if not isinstance(value, dict):
        raise BenchmarkError(f"{label} 必须是 JSON 对象。")
    return value


def _site_set(items: list[object], keys: tuple[str, ...], case_id: str, label: str) -> set[tuple[object, ...]]:
    values: set[tuple[object, ...]] = set()
    for item in items:
        if not isinstance(item, dict) or any(key not in item for key in keys):
            raise BenchmarkError(f"{case_id}: {label} 条目缺少匹配身份字段。")
        values.add(tuple(item[key] for key in keys))
    return values


def _coverage_status(value: object, case_id: str) -> str:
    status = value.get("status") if isinstance(value, dict) else value
    if status not in {"complete", "partial"}:
        raise BenchmarkError(f"{case_id}: expected_coverage 必须是 complete 或 partial。")
    return status


def _comparison(expected: set[tuple[object, ...]], predicted: set[tuple[object, ...]]) -> dict[str, Any]:
    true_positive = expected & predicted
    false_positive = predicted - expected
    false_negative = expected - predicted
    counts = {"true_positive": len(true_positive), "false_positive": len(false_positive), "false_negative": len(false_negative)}
    return {
        "counts": counts,
        "metrics": _metric_summary(counts),
        "missing": [list(item) for item in sorted(false_negative)],
        "unexpected": [list(item) for item in sorted(false_positive)],
    }


def _empty_counts() -> dict[str, int]:
    return {"true_positive": 0, "false_positive": 0, "false_negative": 0}


def _add_counts(total: dict[str, int], counts: dict[str, int]) -> None:
    for key in total:
        total[key] += counts[key]


def _metric_summary(counts: dict[str, int]) -> dict[str, float | int | None]:
    tp, fp, fn = counts["true_positive"], counts["false_positive"], counts["false_negative"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = None if precision is None or recall is None else _ratio(2 * precision * recall, precision + recall)
    return {**counts, "precision": precision, "recall": recall, "f1": f1}


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise BenchmarkError(f"{key} 必须是非空字符串。")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openimpact-evaluate", description="运行带人工标注的函数变更 Benchmark")
    parser.add_argument("benchmark", help="含 manifest.json 的 Benchmark 目录")
    parser.add_argument("--output", type=Path, help="写入 JSON 结果的文件路径")
    args = parser.parse_args(argv)
    try:
        result = evaluate_benchmark(args.benchmark)
    except BenchmarkError as error:
        parser.error(str(error))
    serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0 if result["rejected_case_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
