"""Full uploaded-project HTTP analysis reuses the ZIP importer and Core report."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.change_spec import validate_change_spec as core_validate_change_spec
from openimpact.analysis.pipeline import analyze_project as core_analyze_project
from openimpact.analysis.report import build_report
from openimpact.api import app
from openimpact.repository import zip_inspector

DEMO = Path(__file__).resolve().parents[1] / "examples" / "signature_change"


def make_zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def demo_zip() -> bytes:
    return make_zip({f"signature_change/{path.name}": path.read_bytes()
                     for path in DEMO.iterdir() if path.is_file()})


def config(target="utils.format_date", name="timezone", kind="positional_or_keyword"):
    return {"target_symbol_id": target, "added_parameter": {"name": name, "kind": kind}}


def request(data: bytes, change: dict | str, fingerprint: str | None = None, **extra):
    form = {"change": change if isinstance(change, str) else json.dumps(change), **extra}
    if fingerprint is not None:
        form["expected_fingerprint"] = fingerprint
    with TestClient(app) as client:
        return client.post(
            "/api/v1/projects/analyze",
            data=form,
            files={"file": ("project.zip", data, "application/zip")},
        )


def test_demo_zip_matches_cli_core_report_with_relative_project_root():
    data = demo_zip()
    with TestClient(app) as client:
        inspected = client.post(
            "/api/v1/projects/inspect",
            files={"file": ("project.zip", data, "application/zip")},
        )
    assert inspected.status_code == 200
    response = request(data, config(), inspected.json()["project_fingerprint"])
    assert response.status_code == 200
    report = response.json()
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["coverage"]["status"] == "complete"
    assert report["project_path"] == "."
    assert report["direct_impacts"][0]["file"] == "report.py"
    assert [item["impacted_symbol_id"] for item in report["indirect_impacts"]] == [
        "dashboard.dashboard", "page.page"
    ]
    assert "openimpact-zip-" not in response.text
    expected = build_report(core_analyze_project(DEMO, load_change_spec(DEMO / "change.json")))
    expected["project_path"] = "."
    assert report == json.loads(json.dumps(expected, ensure_ascii=False))


def test_analyzes_uploaded_project_without_builtin_demo_and_uses_one_snapshot():
    data = make_zip({
        "a.py": "def f(x): return x\n",
        "caller.py": "from a import f\ndef call(): return f(1)\n",
    })
    paths: list[Path] = []

    def validation(index, spec):
        paths.append(index.scanner.project_path)
        return core_validate_change_spec(index, spec)

    def analysis(path, spec):
        paths.append(Path(path))
        return core_analyze_project(path, spec)

    with (patch("openimpact.api._DEMO_DIR", Path("missing-builtin-demo")),
          patch("openimpact.api.validate_change_spec", side_effect=validation),
          patch("openimpact.api.analyze_project", side_effect=analysis)):
        response = request(data, config(target="a.f", name="y"))
    assert response.status_code == 200
    assert response.json()["summary"]["direct_impact_count"] == 1
    assert response.json()["summary"]["indirect_1hop_count"] == 0
    assert paths[0] == paths[1]
    assert not paths[0].exists()


def test_invalid_zip_and_fingerprint_mismatch():
    assert request(b"not zip", config()).json()["error"]["code"] == "invalid_zip"
    response = request(demo_zip(), config(), "0" * 64)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fingerprint_mismatch"


def test_invalid_change_config_and_core_validation_failures():
    data = demo_zip()
    for change, code in (
        ("{", "invalid_change_json"),
        (config(target="missing.f"), "target_not_found"),
        (config(name="date"), "invalid_after_signature"),
    ):
        response = request(data, change)
        assert response.status_code == 422
        assert response.json()["validation"]["valid"] is False
        assert response.json()["validation"]["diagnostics"][0]["code"] == code

    optional = make_zip({"utils.py": "def format_date(date='today'): pass\n"})
    invalid = request(optional, config())
    assert invalid.status_code == 422
    assert invalid.json()["validation"]["diagnostics"][0]["code"] == "invalid_after_signature"


def test_partial_coverage_explicitly_limits_no_impact_conclusion():
    data = make_zip({
        "utils.py": "def format_date(date): pass\n",
        "broken.py": "def broken(:\n",
    })
    response = request(data, config())
    assert response.status_code == 200
    report = response.json()
    assert report["summary"]["direct_impact_count"] == 0
    assert report["coverage"]["status"] == "partial"
    assert "未报告影响不能视为确定无影响" in report["coverage"]["message"]
    assert report["diagnostics"]["parse_errors"][0]["file"] == "broken.py"
    assert "openimpact-zip-" not in response.text


def test_internal_analysis_exception_returns_500_and_cleans_temp():
    data = demo_zip()
    temporary_directory = zip_inspector.TemporaryDirectory
    locations: list[Path] = []

    def record_directory(*args, **kwargs):
        directory = temporary_directory(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with (patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory),
          patch("openimpact.api.analyze_project", side_effect=RuntimeError("internal failure"))):
        response = request(data, config())
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "analysis_failed"
    assert locations and all(not location.exists() for location in locations)
    assert "openimpact-zip-" not in response.text


def test_upload_limits_and_extra_path_field_apply_to_analyze():
    data = demo_zip()
    with patch.object(zip_inspector, "MAX_UPLOAD_BYTES", len(data) - 1):
        too_large = request(data, config())
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "zip_limit_exceeded"
    extra = request(data, config(), project_path="C:/secret")
    assert extra.status_code == 400
    assert extra.json()["error"]["code"] == "unsupported_input"


def test_uploaded_source_never_executes(tmp_path):
    marker = tmp_path / "executed"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\ndef f(x): pass\n"
    response = request(make_zip({"a.py": source}), config(target="a.f", name="y"))
    assert response.status_code == 200
    assert not marker.exists()
