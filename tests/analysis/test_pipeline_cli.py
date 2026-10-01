"""Exercise the fixed demo, report contract, CLI, and partial coverage."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report, render_chinese_report

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "examples" / "signature_change"
CHANGE = DEMO / "change.json"


class PipelineAndCLITests(unittest.TestCase):
    def cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "openimpact", "analyze", *arguments],
            cwd=ROOT, env=environment, capture_output=True, text=True,
            encoding="utf-8", check=False,
        )

    def test_fixed_demo_pipeline_and_evidence(self):
        run = analyze_project(DEMO, load_change_spec(CHANGE))
        report = build_report(run)
        self.assertEqual(report["validation"], {"valid": True, "diagnostics": []})
        self.assertEqual(report["coverage"]["status"], "complete")
        self.assertEqual(report["summary"]["direct_impact_count"], 1)
        self.assertEqual(report["summary"]["indirect_1hop_count"], 1)
        self.assertEqual(report["summary"]["indirect_2hop_count"], 1)
        self.assertEqual(report["direct_impacts"][0]["caller_symbol_id"], "report.report")
        self.assertEqual(report["direct_impacts"][0]["file"], "report.py")
        by_symbol = {item["impacted_symbol_id"]: item for item in report["indirect_impacts"]}
        self.assertEqual(set(by_symbol), {"dashboard.dashboard", "page.page"})
        self.assertEqual(by_symbol["dashboard.dashboard"]["impact_type"], "indirect_1hop")
        self.assertEqual(by_symbol["page.page"]["impact_type"], "indirect_2hop")
        page_source = by_symbol["page.page"]["sources"][0]
        self.assertEqual(
            [(edge["caller_symbol_id"], edge["callee_symbol_id"])
             for edge in page_source["propagation_path"]],
            [("page.page", "dashboard.dashboard"),
             ("dashboard.dashboard", "report.report"),
             ("report.report", "utils.format_date")],
        )
        self.assertEqual(page_source["propagation_path"][-1]["line"],
                         report["direct_impacts"][0]["line"])
        self.assertEqual(page_source["direct_call"]["file"], "report.py")
        self.assertIn("1-hop Indirect（1）", render_chinese_report(report))

    def test_cli_text_and_json_succeed(self):
        arguments = (str(DEMO), "--change", str(CHANGE))
        text_result = self.cli(*arguments)
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn("Direct Impact（1）", text_result.stdout)
        self.assertIn("page.page → dashboard.dashboard → report.report → utils.format_date",
                      text_result.stdout)
        json_result = self.cli(*arguments, "--format", "json")
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        report = json.loads(json_result.stdout)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["summary"]["direct_impact_count"], 1)

    def test_missing_project_and_change_file_fail_nonzero(self):
        with TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing")
            project_result = self.cli(missing, "--change", str(CHANGE))
            self.assertNotEqual(project_result.returncode, 0)
            self.assertIn("错误", project_result.stderr)
            change_result = self.cli(str(DEMO), "--change", missing)
            self.assertNotEqual(change_result.returncode, 0)
            self.assertIn("ChangeSpec", change_result.stderr)

    def test_invalid_json_and_structure_fail_nonzero(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "change.json"
            path.write_text("{invalid", encoding="utf-8")
            result = self.cli(str(DEMO), "--change", str(path))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("JSON 无效", result.stderr)
            path.write_text('{"change_type": "add_required_parameter"}', encoding="utf-8")
            with self.assertRaises(ChangeFileError):
                load_change_spec(path)
            self.assertNotEqual(self.cli(str(DEMO), "--change", str(path)).returncode, 0)

    def test_unknown_target_returns_validation_report_and_failure(self):
        with TemporaryDirectory() as directory:
            data = json.loads(CHANGE.read_text(encoding="utf-8"))
            data["target_symbol_id"] = "missing.format_date"
            path = Path(directory) / "change.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = self.cli(str(DEMO), "--change", str(path), "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["validation"]["valid"])
            self.assertEqual(report["validation"]["diagnostics"][0]["code"],
                             "target_not_found")
            self.assertEqual(report["summary"]["direct_impact_count"], 0)

    def test_syntax_and_encoding_failures_are_reported_with_partial_coverage(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            for filename in ("utils.py", "report.py", "dashboard.py", "page.py"):
                (project / filename).write_bytes((DEMO / filename).read_bytes())
            (project / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            (project / "encoded.py").write_bytes(b"# coding: made-up-codec\nx = 1\n")
            report = build_report(analyze_project(project, load_change_spec(CHANGE)))
            self.assertEqual(report["summary"]["direct_impact_count"], 1)
            self.assertEqual(report["coverage"]["status"], "partial")
            self.assertEqual(report["coverage"]["files_with_parse_errors"], 2)
            self.assertEqual({item["kind"] for item in report["diagnostics"]["parse_errors"]},
                             {"syntax_error", "encoding_error"})
            cli_result = self.cli(str(project), "--change", str(CHANGE),
                                  "--format", "json")
            self.assertEqual(cli_result.returncode, 0, cli_result.stderr)
            self.assertEqual(json.loads(cli_result.stdout)["coverage"]["status"], "partial")

    def test_report_separates_manual_preexisting_and_unresolved(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            for filename in ("utils.py", "dashboard.py", "page.py"):
                (project / filename).write_bytes((DEMO / filename).read_bytes())
            (project / "report.py").write_text(
                "from utils import format_date\nfrom missing import unknown\n"
                "def report(date):\n    format_date(date)\n"
                "def existing():\n    format_date()\n"
                "def uncertain(args):\n    format_date(1, *args)\n"
                "def unresolved():\n    unknown()\n",
                encoding="utf-8",
            )
            report = build_report(analyze_project(project, load_change_spec(CHANGE)))
            summary = report["summary"]
            self.assertEqual(summary["direct_impact_count"], 1)
            self.assertEqual(summary["manual_review_count"], 1)
            self.assertEqual(summary["pre_existing_problem_count"], 1)
            self.assertEqual(summary["unresolved_call_count"], 1)
            self.assertEqual(report["coverage"]["status"], "partial")
            output = render_chinese_report(report)
            self.assertIn("人工检查（1）", output)
            self.assertIn("既有问题（1）", output)
            self.assertIn("未解析／诊断：调用 1", output)

    def test_target_syntax_error_is_a_validation_failure_with_diagnostic(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "utils.py").write_text("def format_date(:\n", encoding="utf-8")
            result = self.cli(str(project), "--change", str(CHANGE), "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual(report["validation"]["diagnostics"][0]["code"],
                             "target_not_found")
            self.assertEqual(report["diagnostics"]["parse_errors"][0]["kind"],
                             "syntax_error")


if __name__ == "__main__":
    unittest.main()
