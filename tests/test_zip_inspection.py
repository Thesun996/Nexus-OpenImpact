"""HTTP and import-boundary checks for uploaded, untrusted ZIP projects."""

import io
import stat
import zipfile
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openimpact.api import app
from openimpact.repository import zip_inspector


def make_zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def upload(data: bytes, filename: str = "project.zip"):
    with TestClient(app) as client:
        return client.post(
            "/api/v1/projects/inspect",
            files={"file": (filename, data, "application/zip")},
        )


def test_normal_multimodule_project_and_parameters():
    data = make_zip({
        "utils.py": "def format_date(date, *, timezone='UTC'):\n    return date\n",
        "report.py": "from utils import format_date\ndef report(x):\n    return format_date(x)\n",
        "README.md": "ignored",
        ".venv/fake.py": "def fake(): pass\n",
    })
    response = upload(data)
    assert response.status_code == 200
    report = response.json()
    assert report["project_name"] == "project"
    assert len(report["project_fingerprint"]) == 64
    assert report["source_root"] is None
    assert {item["module"] for item in report["modules"]} == {"utils", "report"}
    assert {item["symbol_id"] for item in report["symbols"]} == {
        "utils.format_date", "report.report"
    }
    parameters = next(s for s in report["symbols"] if s["symbol_id"] == "utils.format_date")["parameters"]
    assert [(p["name"], p["kind"], p["has_default"]) for p in parameters] == [
        ("date", "positional_or_keyword", False),
        ("timezone", "keyword_only", True),
    ]
    assert report["coverage"]["status"] == "complete"
    assert report["diagnostics"]["parse_errors"] == []


def test_single_wrapper_directory_is_removed_but_package_root_is_preserved():
    wrapped = upload(make_zip({"sample/utils.py": "def f(): pass\n", "sample/report.py": "pass\n"}))
    assert wrapped.status_code == 200
    assert wrapped.json()["source_root"] == "sample"
    assert {item["module"] for item in wrapped.json()["modules"]} == {"utils", "report"}
    package = upload(make_zip({"pkg/__init__.py": "pass\n", "pkg/helpers.py": "def f(): pass\n"}))
    assert package.status_code == 200
    assert package.json()["source_root"] is None
    assert {item["module"] for item in package.json()["modules"]} == {"pkg", "pkg.helpers"}


@pytest.mark.parametrize("data,code", [
    (make_zip({}), "no_python_files"),
    (b"this is not a zip", "invalid_zip"),
    (make_zip({"good.py": "pass\n"})[:-15], "invalid_zip"),
])
def test_empty_corrupt_and_non_zip(data, code):
    response = upload(data)
    assert response.status_code in {400, 422}
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("name", [
    "../escape.py", "/absolute.py", "C:/drive.py", "\\\\server\\share\\file.py",
    "a/../evil.py", "CON.py", "folder//file.py",
    "a./file.py", "a:stream.py",
])
def test_unsafe_paths_rejected(name):
    response = upload(make_zip({name: "pass\n"}))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsafe_zip_entry"


def test_raw_windows_separator_rejected():
    # zipfile's Windows writer normalizes backslashes, so edit both ZIP headers.
    data = make_zip({"a/evil.py": "pass\n"}).replace(b"a/evil.py", b"a\\evil.py")
    response = upload(data)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsafe_zip_entry"


def test_symlink_and_special_file_rejected():
    for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o644):
        buffer = io.BytesIO()
        info = zipfile.ZipInfo("link.py")
        info.create_system = 3
        info.external_attr = mode << 16
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(info, "pass\n")
        response = upload(buffer.getvalue())
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsafe_zip_entry"


def test_unsupported_compression_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_BZIP2) as archive:
        archive.writestr("file.py", "pass\n")
    response = upload(buffer.getvalue())
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_zip_entry"


def test_upload_and_archive_limits():
    data = make_zip({"a.py": "pass\n", "b.py": "pass\n"})
    for limit_name, limit_value in (
        ("MAX_UPLOAD_BYTES", len(data) - 1),
        ("MAX_ENTRIES", 1),
        ("MAX_FILES", 1),
        ("MAX_FILE_BYTES", 1),
        ("MAX_TOTAL_BYTES", 1),
    ):
        with patch.object(zip_inspector, limit_name, limit_value):
            response = upload(data)
        assert response.status_code == 413, limit_name
        assert response.json()["error"]["code"] == "zip_limit_exceeded"


def test_compression_ratio_limit():
    data = make_zip({"bomb.py": "#" * 5000})
    with patch.object(zip_inspector, "MAX_COMPRESSION_RATIO", 2):
        response = upload(data)
    assert response.status_code == 413


def test_syntax_error_gives_partial_coverage_and_no_false_symbols():
    response = upload(make_zip({"good.py": "def ok(): pass\n", "bad.py": "def broken(:\n"}))
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["status"] == "partial"
    assert body["coverage"]["files_with_parse_errors"] == 1
    assert [symbol["symbol_id"] for symbol in body["symbols"]] == ["good.ok"]
    assert body["diagnostics"]["parse_errors"][0]["file"] == "bad.py"


def test_unresolved_import_is_diagnostic():
    response = upload(make_zip({"main.py": "from missing import f\ndef run(): pass\n"}))
    assert response.status_code == 200
    assert response.json()["coverage"]["status"] == "partial"
    assert response.json()["diagnostics"]["unresolved_imports"][0]["reason"] == "module_not_in_project"


def test_temporary_directory_cleaned_after_request():
    original = zip_inspector.TemporaryDirectory
    locations: list[Path] = []

    def record_directory(*args, **kwargs):
        directory = original(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory):
        response = upload(make_zip({"main.py": "def run(): pass\n"}))
    assert response.status_code == 200
    assert locations and all(not location.exists() for location in locations)


def test_uploaded_code_never_executes(tmp_path):
    marker = tmp_path / "executed"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\ndef f(): pass\n"
    response = upload(make_zip({"main.py": source}))
    assert response.status_code == 200
    assert not marker.exists()


def test_no_server_path_or_extra_fields():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects/inspect",
            data={"project_path": "C:/private"},
            files={"file": ("project.zip", make_zip({"main.py": "pass\n"}))},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_input"


def test_multiple_file_fields_rejected():
    data = make_zip({"main.py": "pass\n"})
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects/inspect",
            files=[("file", ("first.zip", data)), ("file", ("second.zip", data))],
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_input"


def test_multipart_body_limit_applies_before_form_parsing():
    with patch.object(zip_inspector, "MAX_UPLOAD_BYTES", 8), TestClient(app) as client:
        response = client.post(
            "/api/v1/projects/inspect",
            content=b"x" * (64 * 1024 + 9),
            headers={"content-type": "multipart/form-data; boundary=unused"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "zip_limit_exceeded"


def test_duplicate_and_file_child_conflicts_rejected():
    for entries in (
        [("a.py", "pass\n"), ("a.py", "def replaced(): pass\n")],
        [("a.py", "pass\n"), ("A.py", "pass\n")],
        [("folder", "content"), ("folder/a.py", "pass\n")],
        [("folder/", ""), ("folder", "content"), ("folder/a.py", "pass\n")],
        [("folder/a.py", "pass\n"), ("folder/./a.py", "pass\n")],
    ):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, content in entries:
                    archive.writestr(name, content)
        with patch.object(zip_inspector, "TemporaryDirectory") as temporary:
            response = upload(buffer.getvalue())
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsafe_zip_entry"
        temporary.assert_not_called()  # Entire archive is checked before any write.


def test_extraction_failure_cleans_temporary_directory():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("first.py", "def first(): pass\n")
        archive.writestr("second.py", "def second(): pass\n")
    data = bytearray(buffer.getvalue())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo("second.py")
        offset = info.header_offset
        name_length = int.from_bytes(data[offset + 26:offset + 28], "little")
        extra_length = int.from_bytes(data[offset + 28:offset + 30], "little")
        data[offset + 30 + name_length + extra_length] ^= 1  # Trigger CRC failure after first write.

    original = zip_inspector.TemporaryDirectory
    locations: list[Path] = []

    def record_directory(*args, **kwargs):
        directory = original(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory):
        response = upload(bytes(data))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_zip"
    assert locations and all(not location.exists() for location in locations)
