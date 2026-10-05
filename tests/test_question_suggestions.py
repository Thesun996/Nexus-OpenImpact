"""Model-only recommendations over the same trusted report and safe ZIP lifecycle."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from openimpact.api import app


@pytest.fixture
def snapshot(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    root = Path(__file__).resolve().parents[1] / "examples/signature_change"
    stream = BytesIO()
    with ZipFile(stream, "w") as output:
        for path in root.glob("*.py"):
            output.writestr(path.name, path.read_bytes())
    change = {"target_symbol_id": "utils.format_date", "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}
    return stream.getvalue(), change


def post(client, snapshot, **fields):
    data, change = snapshot
    fields.setdefault("expected_fingerprint", sha256(data).hexdigest())
    fields.setdefault("finding_index", "0")
    return client.post("/api/v1/reports/question-suggestions",
                       files={"file": ("chosen.zip", data, "application/zip")},
                       data={"change": json.dumps(change), **fields})


def model_questions(ids=None):
    ids = ["source-1"] if ids is None else ids
    return {"questions": [
        {"question": "report.py 的调用为什么需要先检查 timezone 是否提供？", "citation_ids": ids},
        {"question": "这条代表路径还不能确定哪些运行时情况？", "citation_ids": ids},
    ]}


def test_model_recommendations_use_current_report_and_do_not_change_analysis(snapshot, monkeypatch):
    data, change = snapshot
    with TestClient(app) as client:
        with monkeypatch.context() as offline:
            offline.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
            before = client.post("/api/v1/projects/analyze", files={"file": ("chosen.zip", data)}, data={"change": json.dumps(change)}).json()
        with patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", return_value=json.dumps(model_questions())) as model:
            response = post(client, snapshot)
            assert response.status_code == 200
            result = response.json()
            assert result["provider"] == "deepseek" and result["status"] == "available"
            assert result["questions"][0]["citations"][0]["file"] == "report.py"
            assert result["project_fingerprint"] == sha256(data).hexdigest()
            assert model.call_count == 1  # No model requests while rebuilding explanations.
            messages = model.call_args.args[0]
            context = json.loads(messages[1]["content"])["facts"]
            assert context["change"]["added_parameter"]["name"] == "timezone"
            assert context["evidence"]["source_snippet"].strip() == "return format_date(date)"
            assert "间接影响仅建议检查" in messages[0]["content"]
            assert "test-key-not-real" not in json.dumps(messages)
        with monkeypatch.context() as offline:
            offline.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
            after = client.post("/api/v1/projects/analyze", files={"file": ("chosen.zip", data)}, data={"change": json.dumps(change)}).json()
    assert before == after
    assert before["summary"]["direct_impact_count"] == 1


@pytest.mark.parametrize("payload", [
    "not json", [], {"questions": []}, {"questions": model_questions()["questions"][:1]},
    {"questions": model_questions()["questions"] * 2},
    {"questions": model_questions()["questions"][:1] * 2},
    model_questions(["invented-source"]), model_questions([]),
    {"questions": [{"question": "Where should I inspect?", "citation_ids": ["source-1"]}] * 2},
    {"questions": [{"question": "问题" * 81, "citation_ids": ["source-1"]}] * 2},
    {"questions": [{"question": "为什么需要检查？", "citation_ids": ["source-1"], "answer": "not allowed"}] * 2},
])
def test_invalid_model_recommendations_never_become_fixed_questions(snapshot, payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", return_value=raw):
        result = post(client, snapshot).json()
    assert result["status"] == "unavailable" and result["provider"] == "fallback"
    assert result["questions"] == [] and result["fallback_reason"] == "invalid_model_response"


@pytest.mark.parametrize("mode,key,provider,reason", [
    ("rule", "test-key-not-real", "rule", None),
    ("deepseek", "", "fallback", "missing_key"),
    ("invalid-provider", "test-key-not-real", "fallback", "unsupported_provider"),
])
def test_offline_or_missing_key_has_no_model_request(snapshot, monkeypatch, mode, key, provider, reason):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", mode)
    monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages") as model:
        result = post(client, snapshot).json()
    assert result["provider"] == provider and result["fallback_reason"] == reason
    assert result["status"] == "unavailable" and result["questions"] == []
    model.assert_not_called()


def test_authentication_failure_is_safe_and_not_retried(snapshot):
    failure = HTTPError("https://example", 401, "secret internal path", None, None)
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", side_effect=failure) as model:
        result = post(client, snapshot).json()
    assert result["fallback_reason"] == "http_401" and result["questions"] == []
    assert result["provider"] == "fallback" and model.call_count == 1
    assert "secret internal" not in json.dumps(result)


def test_indirect_partial_and_zero_context_remain_honest(snapshot):
    data, change = snapshot
    stream = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(stream, "w") as output:
        for name in source.namelist():
            output.writestr(name, source.read(name))
        output.writestr("broken.py", "def broken(:")
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", return_value=json.dumps(model_questions())) as model:
        result = post(client, (stream.getvalue(), change), finding_index="2").json()
        context = json.loads(model.call_args.args[0][1]["content"])["facts"]
        assert result["coverage"]["status"] == "partial"
        assert context["evidence"]["impact_type"] == "indirect_2hop"
        assert context["evidence"]["propagation_path"]
        zero = {"target_symbol_id": "page.page", "added_parameter": {"name": "zone", "kind": "positional_or_keyword"}}
        model.return_value = json.dumps({"questions": [
            {"question": "零影响结果还不能证明哪些业务行为？", "citation_ids": []},
            {"question": "当前静态分析覆盖哪些范围？", "citation_ids": []},
        ]})
        result = post(client, (data, zero), finding_index=None).json()
        context = json.loads(model.call_args.args[0][1]["content"])["facts"]
        assert result["status"] == "available" and result["finding_index"] is None
        assert context["evidence"] is None and context["citations"] == []
        assert context["summary"]["direct_impact_count"] == 0


@pytest.mark.parametrize("folder,domain", [("module_rename", "module"), ("symbol_rename", "symbol")])
def test_recommendations_share_module_and_symbol_context(folder, domain, snapshot):
    root = Path(__file__).resolve().parents[1] / "examples" / folder
    stream = BytesIO()
    with ZipFile(stream, "w") as output:
        for path in root.glob("*.py"):
            output.writestr(path.name, path.read_bytes())
    change = json.loads((root / "change.json").read_text(encoding="utf-8"))
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", return_value=json.dumps(model_questions())) as model:
        result = post(client, (stream.getvalue(), change)).json()
    assert result["change_domain"] == domain and result["status"] == "available"
    assert json.loads(model.call_args.args[0][1]["content"])["facts"]["change_domain"] == domain


def test_recommendations_reuse_zip_limits_fingerprint_and_input_guards(snapshot, monkeypatch):
    with TestClient(app) as client, patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages") as model:
        assert post(client, snapshot, expected_fingerprint="0" * 64).status_code == 409
        assert post(client, (b"invalid zip", snapshot[1])).status_code == 400
        assert post(client, snapshot, finding_index="-1").status_code == 422
        assert post(client, snapshot, finding_index="999").status_code == 422
        assert post(client, snapshot, path="C:/secret.py").status_code == 400
        assert post(client, snapshot, expected_fingerprint="not-a-fingerprint").status_code == 422
        repeated = [("file", ("chosen.zip", snapshot[0])), ("change", (None, json.dumps(snapshot[1]))),
                    ("expected_fingerprint", (None, sha256(snapshot[0]).hexdigest())),
                    ("expected_fingerprint", (None, sha256(snapshot[0]).hexdigest()))]
        assert client.post("/api/v1/reports/question-suggestions", files=repeated).status_code == 400
        monkeypatch.setattr("openimpact.repository.zip_inspector.MAX_UPLOAD_BYTES", 32)
        assert post(client, snapshot).status_code == 413
        assert client.post("/api/v1/reports/question-suggestions", content=b"x" * (65 * 1024)).status_code == 413
    model.assert_not_called()


def test_recommendation_snapshots_are_cleaned_on_model_and_internal_failure(snapshot):
    directories = []
    def tracked(*args, **kwargs):
        instance = TemporaryDirectory(*args, **kwargs)
        directories.append(instance.name)
        return instance
    with patch("openimpact.repository.zip_inspector.TemporaryDirectory", tracked), TestClient(app) as client:
        with patch("openimpact.reporting.questions.DeepSeekProvider.complete_messages", side_effect=TimeoutError):
            result = post(client, snapshot).json()
            assert result["status"] == "unavailable"
        with patch("openimpact.workspace_api.suggest_questions", side_effect=RuntimeError("private-key-path")):
            response = post(client, snapshot)
            assert response.status_code == 500 and "private-key-path" not in response.text
        assert client.get("/api/v1/health").status_code == 200
    assert len(directories) == 2 and all(not Path(path).exists() for path in directories)
