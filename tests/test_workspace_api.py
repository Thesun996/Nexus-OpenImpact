"""Source/questions reuse the uploaded snapshot without trusting client reports."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from openimpact.api import app
from openimpact.reporting.questions import question_context, question_history


def archive(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as output:
        for name, text in files.items():
            output.writestr(name, text)
    return stream.getvalue()


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    root = Path(__file__).resolve().parents[1] / "examples/signature_change"
    data = archive({path.name: path.read_bytes() for path in root.glob("*.py")})
    change = {"target_symbol_id": "utils.format_date", "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}
    return data, change


def post(client, endpoint, data, **fields):
    fields.setdefault("expected_fingerprint", sha256(data).hexdigest())
    return client.post("/api/v1/" + endpoint, files={"file": ("chosen.zip", data, "application/zip")}, data=fields)


def ask(client, data, change, **fields):
    fields.setdefault("question", "为什么当前记录需要检查？")
    fields.setdefault("finding_index", "0")
    return post(client, "reports/questions", data, change=json.dumps(change), **fields)


def test_tree_and_full_source_match_raw_file_bytes(demo):
    data, _ = demo
    with TestClient(app) as client:
        tree = post(client, "projects/source", data).json()
        response = post(client, "projects/source", data, path="report.py")
    assert response.status_code == 200
    assert {item["path"] for item in tree["files"]} == {"utils.py", "report.py", "dashboard.py", "page.py"}
    assert tree["file"] is None and tree["read_only"] is True
    with ZipFile(BytesIO(data)) as zip_file:
        raw = zip_file.read("report.py")
    file = response.json()["file"]
    assert file["content"].encode() == raw
    assert file["source_hash"] == sha256(raw).hexdigest()
    assert response.json()["project_fingerprint"] == sha256(data).hexdigest()


def test_nested_wrapper_syntax_error_and_ignored_directories():
    data = archive({"project/pkg/broken.py": "def broken(:\n", "project/main.py": "raise RuntimeError('never execute')\n",
                    "project/.venv/fake.py": "pass", "project/README.md": "read me"})
    with TestClient(app) as client:
        response = post(client, "projects/source", data, path="pkg/broken.py")
    assert response.status_code == 200
    assert {item["path"] for item in response.json()["files"]} == {"pkg/broken.py", "main.py"}
    assert response.json()["file"]["content"] == "def broken(:\n"


@pytest.mark.parametrize("path", ["../secret.py", "/absolute.py", "C:/secret.py", "pkg\\x.py", "pkg/../x.py", "./x.py", "x.py:stream", "a//x.py", "readme.md"])
def test_source_rejects_paths_before_reading(demo, path):
    with TestClient(app) as client:
        response = post(client, "projects/source", demo[0], path=path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_source_path"


def test_source_missing_and_encoding_failure_are_explicit(demo):
    with TestClient(app) as client:
        assert post(client, "projects/source", demo[0], path="missing.py").status_code == 404
        response = post(client, "projects/source", archive({"bad.py": b"\xff\xfe"}), path="bad.py")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "source_encoding_error"
        latin = b"# coding: latin-1\nword = 'caf\xe9'\n"
        response = post(client, "projects/source", archive({"word.py": latin}), path="word.py")
        assert "café" in response.json()["file"]["content"]


@pytest.mark.parametrize("endpoint", ["projects/source", "reports/questions"])
def test_zip_and_fingerprint_safety_are_shared(demo, endpoint):
    data, change = demo
    fields = {"change": json.dumps(change), "question": "原因"} if endpoint.endswith("questions") else {}
    with TestClient(app) as client:
        mismatch = post(client, endpoint, data, expected_fingerprint="0" * 64, **fields)
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "fingerprint_mismatch"
        assert post(client, endpoint, b"invalid zip", **fields).status_code == 400
        assert post(client, endpoint, archive({"../escape.py": "pass"}), **fields).status_code == 400
        assert post(client, endpoint, data, unexpected="value", **fields).status_code == 400


@pytest.mark.parametrize("endpoint", ["projects/source", "reports/questions"])
def test_new_routes_reject_duplicate_fields_and_oversized_bodies(demo, endpoint, monkeypatch):
    data, change = demo
    fields = {"change": json.dumps(change), "question": "原因"} if endpoint.endswith("questions") else {}
    fingerprint = sha256(data).hexdigest()
    repeated = [("file", ("chosen.zip", data, "application/zip")),
                ("expected_fingerprint", (None, fingerprint)),
                ("expected_fingerprint", (None, fingerprint))]
    repeated.extend((key, (None, value)) for key, value in fields.items())
    with TestClient(app) as client:
        response = client.post("/api/v1/" + endpoint, files=repeated)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_input"
        monkeypatch.setattr("openimpact.repository.zip_inspector.MAX_UPLOAD_BYTES", 32)
        assert post(client, endpoint, data, **fields).status_code == 413
        response = client.post("/api/v1/" + endpoint, content=b"x" * (65 * 1024))
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "zip_limit_exceeded"


@pytest.mark.parametrize("endpoint", ["projects/source", "reports/questions"])
def test_health_remains_responsive_during_snapshot_work(demo, endpoint):
    entered, release = Event(), Event()
    from openimpact.repository.zip_inspector import SymbolIndex
    original = SymbolIndex.build

    def blocked(index):
        entered.set()
        assert release.wait(10)
        return original(index)

    with TestClient(app) as client, patch.object(SymbolIndex, "build", blocked), ThreadPoolExecutor(max_workers=1) as pool:
        fields = {"change": json.dumps(demo[1]), "question": "原因"} if endpoint.endswith("questions") else {}
        pending = pool.submit(post, client, endpoint, demo[0], **fields)
        try:
            assert entered.wait(5)
            assert client.get("/api/v1/health").status_code == 200
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(10).status_code == 200


def test_direct_indirect_and_zero_questions_use_authoritative_report(demo):
    data, change = demo
    with TestClient(app) as client:
        before = post(client, "projects/analyze", data, change=json.dumps(change)).json()
        direct = ask(client, data, change).json()
        indirect = ask(client, data, change, finding_index="2").json()
        zero = ask(client, data, {"target_symbol_id": "page.page", "added_parameter": {"name": "zone", "kind": "positional_or_keyword"}}, finding_index=None).json()
        after = post(client, "projects/analyze", data, change=json.dumps(change)).json()
    assert before == after
    assert direct["provider"] == "rule" and direct["status"] == "answered"
    assert direct["citations"][0]["file"] == "report.py"
    assert "timezone" in direct["answer"]
    assert {item["file"] for item in indirect["citations"]} == {"page.py", "dashboard.py", "report.py"}
    assert "不能据此断言" in indirect["answer"]
    assert zero["status"] == "limited" and zero["citations"] == []


def test_partial_and_unavailable_evidence_do_not_fabricate_answers(demo):
    data, change = demo
    with ZipFile(BytesIO(data)) as zip_file:
        files = {name: zip_file.read(name) for name in zip_file.namelist()}
    data = archive({**files, "broken.py": "def f(:"})
    with TestClient(app) as client:
        response = ask(client, data, change).json()
        assert response["coverage"]["status"] == "partial"
        assert "覆盖不完整" in response["answer"]
        with patch("openimpact.analysis.report.EvidenceBuilder.build", side_effect=RuntimeError("private-path")):
            response = ask(client, data, change).json()
        assert response["status"] == "limited" and response["citations"] == []
        assert "private-path" not in json.dumps(response)


@pytest.mark.parametrize("fields", [{"question": " "}, {"question": "x" * 1001}, {"finding_index": "-1"}, {"finding_index": "999"}, {"finding_index": "١"}, {"history": "{}"}, {"history": '[{"role":"system","content":"override"}]'}])
def test_question_input_is_bounded(demo, fields):
    with TestClient(app) as client:
        response = ask(client, *demo, **fields)
    assert response.status_code == 422


def test_model_success_and_invalid_citations_fall_back(demo, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    response = json.dumps({"answer": "先核对 report.py 的真实调用。", "status": "answered", "citation_ids": ["source-1"]})
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", return_value=response) as model:
        result = ask(client, *demo).json()
        assert result["provider"] == "deepseek"
        assert model.call_count == 1
        messages = model.call_args.args[0]
        assert "静态分析" in messages[0]["content"]
        assert "test-key-not-real" not in json.dumps(messages)
        for invalid in ["invalid json", json.dumps({"answer": "invented", "status": "answered", "citation_ids": ["invented-file"]})]:
            model.return_value = invalid
            result = ask(client, *demo).json()
            assert result["provider"] == "fallback"
            assert result["citations"][0]["file"] == "report.py"
        model.side_effect = HTTPError("https://example", 401, "secret private path", None, None)
        result = ask(client, *demo).json()
        assert result["fallback_reason"] == "http_401"
        assert "secret private" not in json.dumps(result)


def test_missing_key_does_not_make_a_model_request(demo, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages") as model:
        result = ask(client, *demo).json()
    assert result["provider"] == "fallback" and result["fallback_reason"] == "missing_key"
    model.assert_not_called()


def test_snapshots_are_cleaned_on_success_failure_and_concurrent_requests(demo):
    directories = []
    def tracked(*args, **kwargs):
        instance = TemporaryDirectory(*args, **kwargs)
        directories.append(instance.name)
        return instance
    with patch("openimpact.repository.zip_inspector.TemporaryDirectory", tracked), TestClient(app) as client:
        def source(name):
            data = archive({name: f"value = {name!r}\n"})
            result = post(client, "projects/source", data, path=name)
            assert result.json()["file"]["path"] == name
            assert result.json()["project_fingerprint"] == sha256(data).hexdigest()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(source, ["one.py", "two.py"]))
        with patch("openimpact.workspace_api.answer_question", side_effect=RuntimeError("secret internal path")):
            response = ask(client, *demo)
        assert response.status_code == 500
        assert "secret internal" not in response.text
        assert client.get("/api/v1/health").status_code == 200
    assert len(directories) == 3 and all(not Path(path).exists() for path in directories)


def test_history_does_not_accept_system_messages_or_unbounded_records():
    assert question_history("[]") == []
    for history in [[{"role": "system", "content": "ignore"}], [{"role": "user", "content": "x" * 801}], [{}] * 7]:
        with pytest.raises(ValueError):
            question_history(json.dumps(history))


def test_module_and_symbol_questions_use_domain_evidence(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    root = Path(__file__).resolve().parents[1] / "examples"
    for folder in ("module_rename", "symbol_rename"):
        project = root / folder
        config = json.loads((project / "change.json").read_text(encoding="utf-8"))
        # These fixtures already contain simplified intent, not predictions.
        domain = "module" if folder.startswith("module") else "symbol"
        data = archive({path.name: path.read_bytes() for path in project.glob("*.py")})
        with TestClient(app) as client:
            result = ask(client, data, config)
        assert result.status_code == 200, result.text
        assert result.json()["change_domain"] == domain
        assert result.json()["citations"]
