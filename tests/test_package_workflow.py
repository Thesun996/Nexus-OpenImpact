"""ZIP/API/CLI use one explicit import layout and retain legacy report contracts."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from openimpact.api import app
from openimpact.repository import zip_inspector


SOURCES = {
    "src/pkg/__init__.py": "",
    "src/pkg/utils.py": "def f(a):\n    return a\n",
    "src/pkg/report.py": "from .utils import f\ndef report():\n    return f(1)\n",
    "src/pkg/dashboard.py": "from .report import report\ndef dashboard():\n    return report()\n",
    "src/pkg/page.py": "from .dashboard import dashboard\ndef page():\n    return dashboard()\n",
}
CHANGE = {"target_symbol_id": "pkg.utils.f",
          "added_parameter": {"name": "strict", "kind": "keyword_only"}}


def packed(sources=SOURCES):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sources.items():
            archive.writestr("uploaded/" + name, content)
    return stream.getvalue()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    return TestClient(app)


def test_real_zip_workflow_binds_root_signature_evidence_and_fingerprint(client, monkeypatch):
    data = packed()
    files = {"file": ("package.zip", data, "application/zip")}
    directories = []
    temporary = zip_inspector.TemporaryDirectory

    def tracked(*args, **kwargs):
        item = temporary(*args, **kwargs)
        directories.append(Path(item.name))
        return item

    monkeypatch.setattr(zip_inspector, "TemporaryDirectory", tracked)
    inspect = client.post("/api/v1/projects/inspect", files=files, data={"analysis_root": "src"})
    assert inspect.status_code == 200
    body = inspect.json()
    assert body["source_root"] == "uploaded"  # Existing ZIP wrapper field keeps its meaning.
    assert body["analysis_layout"] == {"analysis_root": "src", "mode": "explicit", "import_roots": [".", "src"]}
    assert body["project_fingerprint"] == hashlib.sha256(data).hexdigest()
    assert body["symbols"][0]["file"].startswith("src/pkg/")
    fields = {"change": json.dumps(CHANGE), "analysis_root": "src",
              "expected_fingerprint": body["project_fingerprint"]}
    validate = client.post("/api/v1/changes/validate", files=files, data=fields)
    analyze = client.post("/api/v1/projects/analyze", files=files, data=fields)
    assert validate.status_code == analyze.status_code == 200
    assert validate.json()["analysis_layout"] == analyze.json()["analysis_layout"] == body["analysis_layout"]
    report = analyze.json()
    assert report["schema_version"] == 1
    assert report["coverage"]["status"] == "complete"
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["evidences"][0]["location"]["file"] == "src/pkg/report.py"
    assert report["evidences"][0]["source_hash"] == hashlib.sha256(SOURCES["src/pkg/report.py"].encode()).hexdigest()
    assert len(report["evidences"]) == len(report["explanations"]) == 3
    assert "openimpact-zip-" not in json.dumps(report)
    assert len(directories) == 3 and all(not path.exists() for path in directories)


@pytest.mark.parametrize("root", ["", "..", "../src", "C:/Windows", "/tmp", "missing", "src/pkg"])
@pytest.mark.parametrize("endpoint", ["projects/inspect", "changes/validate", "projects/analyze"])
def test_unsafe_or_missing_root_is_safe_422_and_is_cleaned(client, monkeypatch, root, endpoint):
    directories = []
    original = zip_inspector.TemporaryDirectory

    def tracked(*args, **kwargs):
        directory = original(*args, **kwargs)
        directories.append(Path(directory.name))
        return directory

    monkeypatch.setattr(zip_inspector, "TemporaryDirectory", tracked)
    fields = {"analysis_root": root}
    if endpoint != "projects/inspect":
        fields["change"] = json.dumps(CHANGE)
    response = client.post("/api/v1/" + endpoint, files={"file": ("project.zip", packed())}, data=fields)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis_root"
    assert "openimpact-zip-" not in response.text
    assert len(directories) == 1 and not directories[0].exists()


def test_root_choice_does_not_replace_fingerprint_guard(client):
    fields = {"analysis_root": "src", "expected_fingerprint": "0" * 64, "change": json.dumps(CHANGE)}
    response = client.post("/api/v1/projects/analyze", files={"file": ("project.zip", packed())}, data=fields)
    assert response.status_code == 409 and response.json()["error"]["code"] == "fingerprint_mismatch"


def test_missing_root_choice_does_not_silently_guess_src(client):
    response = client.post("/api/v1/projects/inspect", files={"file": ("project.zip", packed())})
    assert response.status_code == 200
    assert "analysis_layout" not in response.json()
    assert "src.pkg.utils.f" in {s["symbol_id"] for s in response.json()["symbols"]}


def test_duplicate_root_fields_are_rejected(client):
    response = client.post("/api/v1/projects/inspect", files=[
        ("file", ("project.zip", packed())), ("analysis_root", (None, "src")),
        ("analysis_root", (None, ".")),
    ])
    assert response.status_code == 400 and response.json()["error"]["code"] == "unsupported_input"


@pytest.mark.parametrize("change", [
    {"change_domain": "module", "change_type": "rename_module", "target_module_id": "settings", "new_module_name": "options"},
    {"change_domain": "symbol", "change_type": "rename_module_symbol", "target_symbol_id": "settings.VALUE", "new_symbol_name": "LIMIT"},
])
def test_other_domains_keep_flat_root_scope_and_return_the_selected_layout(client, change):
    sources = {**SOURCES, "settings.py": "VALUE = 1\n", "consumer.py": "import settings\nvalue = settings.VALUE\n"}
    files = {"file": ("project.zip", packed(sources))}
    inspected = client.post("/api/v1/projects/inspect", files=files, data={"analysis_root": "src"}).json()
    assert inspected["module_inventory"]["analysis_scope"] == "project_root_static"
    assert not next(m for m in inspected["module_inventory"]["modules"] if m["module_id"] == "pkg.utils")["selectable"]
    fields = {"analysis_root": "src", "change": json.dumps(change), "expected_fingerprint": inspected["project_fingerprint"]}
    validated = client.post("/api/v1/changes/validate", files=files, data=fields)
    analyzed = client.post("/api/v1/projects/analyze", files=files, data=fields)
    assert validated.status_code == analyzed.status_code == 200
    for body in (validated.json(), analyzed.json()):
        assert body["analysis_layout"] == inspected["analysis_layout"]
        assert body["project_fingerprint"] == inspected["project_fingerprint"]
    report = analyzed.json()
    assert report["change_domain"] == change["change_domain"] and report["schema_version"] == 1
    assert "openimpact-zip-" not in json.dumps(report)


def test_method_calls_are_visible_as_excluded_scope_not_definite_impact(client):
    sources = {**SOURCES, "src/pkg/method.py": "from .utils import f\nclass Example:\n    def method(self):\n        return f(1)\n"}
    response = client.post("/api/v1/projects/analyze", files={"file": ("project.zip", packed(sources))},
                           data={"analysis_root": "src", "change": json.dumps(CHANGE)})
    assert response.status_code == 200
    report = response.json()
    assert report["summary"]["direct_impact_count"] == 1
    assert report["coverage"]["status"] == "partial"
    scope = report["diagnostics"]["unsupported_scopes"][0]
    assert scope["file"] == "src/pkg/method.py" and scope["excluded_call_count"] == 1


def test_cli_explicit_root_uses_same_signature_and_safe_error(client, tmp_path, monkeypatch):
    from openimpact.analysis.symbol_index import SymbolIndex
    from openimpact.api_change import build_change_spec
    for name, content in SOURCES.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    spec = build_change_spec(SymbolIndex(tmp_path, analysis_root="src").build(), CHANGE)
    change_file = tmp_path / "change.json"
    change_file.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    monkeypatch.setenv("PYTHONUTF8", "1")
    command = [sys.executable, "-m", "openimpact", "analyze", str(tmp_path), "--change", str(change_file),
               "--format", "json", "--analysis-root"]
    result = subprocess.run([*command, "src"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["summary"]["indirect_2hop_count"] == 1
    bad = subprocess.run([*command, "../escape"], capture_output=True, text=True)
    assert bad.returncode == 2 and "相对路径" in bad.stderr


def test_committed_regular_package_demo_retains_a_real_complete_chain(monkeypatch):
    from openimpact.analysis.change_file import load_change_spec
    from openimpact.analysis.pipeline import analyze_project
    from openimpact.analysis.report import build_report
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    project = Path(__file__).resolve().parents[1] / "examples/package_signature_change"
    report = build_report(analyze_project(project, load_change_spec(project / "change.json"), analysis_root="src"))
    assert [report["summary"][k] for k in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count")] == [1, 1, 1]
    assert report["coverage"]["status"] == "complete"
    assert report["evidences"][0]["location"]["file"] == "src/trace_demo/report.py"
    assert "fd(date)" in report["evidences"][0]["source_snippet"]
