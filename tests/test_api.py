"""HTTP contract for the fixed Demo service, with no Core rule changes."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.change_spec import ChangeSpec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.api import _DEMO_CHANGE, _DEMO_DIR, app


class APIContractTests(unittest.TestCase):
    def test_health(self):
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "version": "0.1.0"})

    def test_demo_analyze_returns_exact_core_json_report(self):
        expected = build_report(analyze_project(_DEMO_DIR, load_change_spec(_DEMO_CHANGE)))
        expected_json = json.loads(json.dumps(expected, ensure_ascii=False))
        with TestClient(app) as client:
            response = client.post("/api/v1/demo/analyze")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_json)
        summary = response.json()["summary"]
        self.assertEqual(summary["direct_impact_count"], 1)
        self.assertEqual(summary["indirect_1hop_count"], 1)
        self.assertEqual(summary["indirect_2hop_count"], 1)
        self.assertEqual(response.json()["coverage"]["status"], "complete")

    def test_demo_rejects_request_input(self):
        with TestClient(app) as client:
            responses = (
                client.post("/api/v1/demo/analyze", json={"project_path": "elsewhere"}),
                client.post("/api/v1/demo/analyze?project_path=elsewhere"),
            )
        for response in responses:
            with self.subTest(response=response):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "unsupported_input")

    def test_missing_demo_file_has_documented_error_shape(self):
        with patch("openimpact.api._DEMO_CHANGE", Path("missing-change-file.json")), TestClient(app) as client:
            response = client.post("/api/v1/demo/analyze")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(response.json()), {"error"})
        self.assertEqual(response.json()["error"]["code"], "demo_unavailable")
        self.assertIsInstance(response.json()["error"]["message"], str)

    def test_invalid_builtin_change_has_documented_error_shape(self):
        spec = load_change_spec(_DEMO_CHANGE)
        invalid = ChangeSpec(spec.change_type, "missing.format_date",
                             spec.before, spec.after, spec.added_parameter)
        with patch("openimpact.api.load_change_spec", return_value=invalid), TestClient(app) as client:
            response = client.post("/api/v1/demo/analyze")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "demo_invalid")


if __name__ == "__main__":
    unittest.main()
