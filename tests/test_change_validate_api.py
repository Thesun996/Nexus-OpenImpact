"""Simplified HTTP change configuration uses the existing ZIP importer and Core validator."""

import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openimpact.analysis.change_spec import validate_change_spec as core_validate_change_spec
from openimpact.api import app
from openimpact.repository import zip_inspector


def archive(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for name, content in files.items():
            package.writestr(name, content)
    return buffer.getvalue()


def config(name="timezone", kind="positional_or_keyword", target="utils.format_date", **extra):
    return {
        "target_symbol_id": target,
        "added_parameter": {"name": name, "kind": kind},
        **extra,
    }


def validate(data: bytes, change: dict | str, fingerprint: str | None = None):
    fields = {"change": change if isinstance(change, str) else json.dumps(change)}
    if fingerprint is not None:
        fields["expected_fingerprint"] = fingerprint
    with TestClient(app) as client:
        return client.post(
            "/api/v1/changes/validate",
            data=fields,
            files={"file": ("project.zip", data, "application/zip")},
        )


def test_normal_change_uses_source_signature_and_core_validator():
    data = archive({"sample/utils.py": "def format_date(date: str) -> str:\n    return date\n"})
    fingerprint = hashlib.sha256(data).hexdigest()
    response = validate(data, config(), fingerprint)
    assert response.status_code == 200
    body = response.json()
    assert body["project_fingerprint"] == fingerprint
    assert body["project_name"] == "sample"
    assert body["coverage"]["status"] == "complete"
    assert body["validation"] == {"valid": True, "diagnostics": []}
    spec = body["change_spec"]
    assert spec["change_type"] == "add_required_parameter"
    assert spec["target_symbol_id"] == "utils.format_date"
    assert spec["before"]["parameters"][0]["annotation_source"] == "str"
    assert spec["before"]["return_annotation_source"] == "str"
    assert [p["name"] for p in spec["after"]["parameters"]] == ["date", "timezone"]
    assert spec["added_parameter"]["required"] is True


def test_target_not_found_has_validation_diagnostic():
    response = validate(archive({"utils.py": "def format_date(date): pass\n"}),
                        config(target="missing.format_date"))
    assert response.status_code == 422
    assert response.json()["change_spec"] is None
    assert response.json()["validation"]["diagnostics"][0]["code"] == "target_not_found"


def test_duplicate_parameter_name_is_rejected_by_core_validator():
    response = validate(archive({"utils.py": "def format_date(date): pass\n"}), config(name="date"))
    assert response.status_code == 422
    assert response.json()["validation"]["diagnostics"][0]["code"] == "invalid_after_signature"


@pytest.mark.parametrize("kind", ["var_positional", "var_keyword", "other", ["keyword_only"]])
def test_unsupported_parameter_kind_has_diagnostic(kind):
    response = validate(archive({"utils.py": "def format_date(date): pass\n"}), config(kind=kind))
    assert response.status_code == 422
    assert response.json()["validation"]["diagnostics"][0]["code"] == "unsupported_parameter_kind"


def test_invalid_signature_does_not_guess_placement():
    data = archive({"utils.py": "def format_date(date='today'):\n    pass\n"})
    response = validate(data, config())
    assert response.status_code == 422
    assert response.json()["validation"]["diagnostics"][0]["code"] == "invalid_after_signature"
    explicit = validate(data, config(insert_before="date"))
    assert explicit.status_code == 200
    assert [p["name"] for p in explicit.json()["change_spec"]["after"]["parameters"]] == [
        "timezone", "date"
    ]


def test_positional_only_and_keyword_only_follow_core_rules():
    data = archive({"utils.py": "def format_date(date, /, mode='short', **kwargs): pass\n"})
    positional = validate(data, config(kind="positional_only"))
    assert positional.status_code == 200
    assert [p["kind"] for p in positional.json()["change_spec"]["after"]["parameters"][:2]] == [
        "positional_only", "positional_only"
    ]
    keyword_only = validate(data, config(kind="keyword_only"))
    assert keyword_only.status_code == 200
    assert keyword_only.json()["change_spec"]["after"]["parameters"][-2]["kind"] == "keyword_only"
    unknown_position = validate(data, config(insert_before="missing"))
    assert unknown_position.status_code == 422
    assert unknown_position.json()["validation"]["diagnostics"][0]["code"] == "insert_before_not_found"


def test_fingerprint_mismatch_rejects_different_source():
    original = archive({"utils.py": "def format_date(date): pass\n"})
    changed = archive({"utils.py": "def format_date(date, mode): pass\n"})
    response = validate(changed, config(), hashlib.sha256(original).hexdigest())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fingerprint_mismatch"


def test_invalid_fingerprint_format_and_invalid_zip():
    data = archive({"utils.py": "def format_date(date): pass\n"})
    assert validate(data, config(), "abc").json()["error"]["code"] == "invalid_fingerprint"
    response = validate(b"not zip", config())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_zip"


def test_invalid_json_and_extra_fields_have_diagnostics():
    data = archive({"utils.py": "def format_date(date): pass\n"})
    for change, code in (("{", "invalid_change_json"),
                         (dict(config(), change_type="rename"), "invalid_change_config")):
        response = validate(data, change)
        assert response.status_code == 422
        assert response.json()["validation"]["diagnostics"][0]["code"] == code


def test_source_bytes_unchanged_and_temp_directory_cleaned():
    source = "# 中文注释\ndef format_date(date):\n    return date\n"
    data = archive({"utils.py": source})
    original = data[:]
    temporary_directory = zip_inspector.TemporaryDirectory
    locations: list[Path] = []
    source_checks: list[bytes] = []

    def record_directory(*args, **kwargs):
        directory = temporary_directory(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    def check_core_validation(index, spec):
        path = index.scanner.project_path / "utils.py"
        source_checks.append(path.read_bytes())
        result = core_validate_change_spec(index, spec)
        source_checks.append(path.read_bytes())
        return result

    with (patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory),
          patch("openimpact.api.validate_change_spec", side_effect=check_core_validation)):
        response = validate(data, config())
    assert response.status_code == 200
    assert data == original
    assert source_checks == [source.encode("utf-8"), source.encode("utf-8")]
    assert locations and all(not location.exists() for location in locations)


def test_uploaded_project_code_is_not_executed(tmp_path):
    marker = tmp_path / "executed"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\ndef format_date(date): pass\n"
    response = validate(archive({"utils.py": source}), config())
    assert response.status_code == 200
    assert not marker.exists()


def test_syntax_error_keeps_project_diagnostics():
    data = archive({"utils.py": "def format_date(date): pass\n", "broken.py": "def bad(:\n"})
    response = validate(data, config())
    assert response.status_code == 200
    assert response.json()["coverage"]["status"] == "partial"
    assert response.json()["diagnostics"]["parse_errors"][0]["file"] == "broken.py"
