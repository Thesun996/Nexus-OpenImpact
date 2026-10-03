"""Backend stability over real loopback HTTP, with external models disabled."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from http.client import HTTPResponse
import io
import json
from pathlib import Path, PureWindowsPath
import socket
from threading import Barrier, Event, Lock, Thread
import time
import zipfile

import httpx
import pytest
import uvicorn

from openimpact import api
from openimpact.explanation import provider as provider_module
from openimpact.explanation.fallback import RuleBasedProvider
from openimpact.reporting.evidence import EvidenceBuilder
from openimpact.repository import zip_inspector

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "signature_change"
ROUTES = ("/api/v1/projects/inspect", "/api/v1/changes/validate", "/api/v1/projects/analyze")
CHANGE = {"target_symbol_id": "utils.format_date",
          "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}
PRIVATE_ERROR = "audit-secret-must-not-leak C:/private/server/source Traceback"


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return buffer.getvalue()


def demo_files():
    return {path.name: path.read_bytes() for path in DEMO.glob("*.py")}


def assert_safe(response):
    body = response.json()
    strings = []

    def walk(value, key=None):
        if isinstance(value, dict):
            for name, child in value.items():
                walk(child, name)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            strings.append(value)
            if key in {"file", "project_path"}:
                assert not Path(value).is_absolute()
                assert not PureWindowsPath(value).drive
                assert ".." not in Path(value).parts

    walk(body)
    text = "\n".join(strings)
    assert "openimpact-zip-" not in text
    assert str(ROOT) not in text and ROOT.as_posix() not in text
    assert "Traceback" not in text
    assert "audit-secret-must-not-leak" not in text
    assert "C:/private/server" not in text
    return body


def submit(client, route, data, change=CHANGE, fingerprint=None):
    fields = {}
    if route != ROUTES[0]:
        fields["change"] = change if isinstance(change, str) else json.dumps(change)
        if fingerprint is not None:
            fields["expected_fingerprint"] = fingerprint
    response = client.post(route, data=fields,
                           files={"file": ("project.zip", data, "application/zip")})
    assert_safe(response)
    return response


def workflow(client, data):
    expected = sha256(data).hexdigest()
    inspected = submit(client, ROUTES[0], data)
    validated = submit(client, ROUTES[1], data, fingerprint=expected)
    analyzed = submit(client, ROUTES[2], data, fingerprint=expected)
    assert [item.status_code for item in (inspected, validated, analyzed)] == [200, 200, 200]
    inspect, validate, report = [item.json() for item in (inspected, validated, analyzed)]
    assert inspect["project_fingerprint"] == validate["project_fingerprint"] == expected
    assert "utils.format_date" in {item["symbol_id"] for item in inspect["symbols"]}
    assert validate["validation"]["valid"] is True
    assert report["change"] == validate["change_spec"]
    assert report["summary"]["direct_impact_count"] == 1
    assert report["summary"]["indirect_1hop_count"] == 1
    assert report["summary"]["indirect_2hop_count"] == 1
    assert report["coverage"]["status"] == "complete"
    assert len(report["evidences"]) == len(report["explanations"]) == 3
    for evidence, explanation in zip(report["evidences"], report["explanations"]):
        assert explanation["evidence"] == evidence
        assert evidence["status"] == "available"
        assert evidence["source_snippet"]
        assert evidence["target_symbol"] == "utils.format_date"
        location = evidence["location"]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            source = archive.read(location["file"])
        assert evidence["source_hash"] == sha256(source).hexdigest()
        lines = source.decode().splitlines()
        assert evidence["source_snippet"] == "\n".join(
            lines[location["line"] - 1:location["end_line"] or location["line"]]
        )
        assert explanation["explanation"]["risk_level"] == "unknown"
        assert explanation["diagnostics"] == []
        for path in evidence["propagation_path"]:
            assert path["direct_evidence_reference"] == report["evidences"][0]["evidence_reference"]
            assert path["call_sites"][-1]["file"] == report["evidences"][0]["location"]["file"]
            assert path["call_sites"][-1]["line"] == report["evidences"][0]["location"]["line"]
    assert report["evidences"][2]["propagation_path"][0]["symbols"] == [
        "page.page", "dashboard.dashboard", "report.report", "utils.format_date",
    ]
    return inspect, validate, report


@pytest.fixture
def live_backend(monkeypatch):
    """Every business request uses TCP; patches only observe resources/inject faults."""
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    external_attempts = []

    def deny_external(*_args, **_kwargs):
        external_attempts.append(True)
        raise AssertionError("External model requests are forbidden in this audit")

    monkeypatch.setattr("openimpact.explanation.deepseek.urlopen", deny_external)
    original_directory = zip_inspector.TemporaryDirectory
    directories = []
    lock = Lock()

    def record_directory(*args, **kwargs):
        directory = original_directory(*args, **kwargs)
        with lock:
            directories.append(Path(directory.name))
        return directory

    monkeypatch.setattr(zip_inspector, "TemporaryDirectory", record_directory)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(api.app, log_level="critical", access_log=False))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.01)
        with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
            yield client, url, directories
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
        assert len(set(directories)) == len(directories)
        assert all(not path.exists() for path in directories)
        assert not external_attempts


def test_real_http_full_workflow_evidence_explanation_and_repeatability(live_backend):
    client, _, directories = live_backend
    data = make_zip(demo_files())
    baseline = workflow(client, data)
    assert workflow(client, data) == baseline
    assert workflow(client, data) == baseline
    assert len(directories) == 9
    assert all(not path.exists() for path in directories)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("empty", [False, True], ids=["invalid_zip", "empty_zip"])
def test_real_http_invalid_zip_and_empty_project(live_backend, route, empty):
    client, _, directories = live_backend
    response = submit(client, route, make_zip({}) if empty else b"not a zip")
    assert response.status_code == (422 if empty else 400)
    assert response.json()["error"]["code"] == ("no_python_files" if empty else "invalid_zip")
    assert not directories


def test_real_http_syntax_error_partial_coverage(live_backend):
    client, _, directories = live_backend
    files = demo_files() | {"broken.py": "def broken(:\n"}
    data = make_zip(files)
    for route in ROUTES:
        response = submit(client, route, data)
        assert response.status_code == 200
        body = response.json()
        assert body["coverage"]["status"] == "partial"
        assert body["diagnostics"]["parse_errors"][0]["file"] == "broken.py"
    assert body["summary"]["direct_impact_count"] == 1
    assert "未报告影响不能视为确定无影响" in body["coverage"]["message"]
    assert len(body["evidences"]) == len(body["explanations"]) == 3
    assert len(directories) == 3


@pytest.mark.parametrize("change,code", [
    ("{", "invalid_change_json"),
    ({**CHANGE, "target_symbol_id": "missing.function"}, "target_not_found"),
    ({**CHANGE, "added_parameter": {"name": "date", "kind": "positional_or_keyword"}},
     "invalid_after_signature"),
    ({**CHANGE, "added_parameter": {"name": "timezone", "kind": "bad_kind"}},
     "unsupported_parameter_kind"),
])
def test_real_http_invalid_change(live_backend, change, code):
    client, _, directories = live_backend
    for route in ROUTES[1:]:
        response = submit(client, route, make_zip(demo_files()), change)
        assert response.status_code == 422
        assert response.json()["validation"]["valid"] is False
        assert response.json()["validation"]["diagnostics"][0]["code"] == code
    assert len(directories) == 2


def test_real_http_invalid_signature(live_backend):
    client, _, directories = live_backend
    data = make_zip({"utils.py": "def format_date(date='today'): pass\n"})
    for route in ROUTES[1:]:
        response = submit(client, route, data)
        assert response.status_code == 422
        assert response.json()["validation"]["diagnostics"][0]["code"] == "invalid_after_signature"
    assert len(directories) == 2


def test_real_http_changed_zip_old_fingerprint_stops_before_extraction(live_backend):
    client, _, directories = live_backend
    original = make_zip(demo_files())
    fingerprint = submit(client, ROUTES[0], original).json()["project_fingerprint"]
    changed = make_zip(demo_files() | {"extra.py": "def extra(): pass\n"})
    for route in ROUTES[1:]:
        response = submit(client, route, changed, fingerprint=fingerprint)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "fingerprint_mismatch"
    assert len(directories) == 1


def test_real_http_evidence_failure_isolated_and_next_request_recovers(live_backend, monkeypatch):
    client, _, directories = live_backend
    data = make_zip(demo_files())
    baseline = submit(client, ROUTES[2], data).json()
    original = EvidenceBuilder.build

    def fail_direct(self, finding):
        if finding.impact_type == "direct":
            raise RuntimeError(PRIVATE_ERROR)
        return original(self, finding)

    with monkeypatch.context() as faults:
        faults.setattr(EvidenceBuilder, "build", fail_direct)
        response = submit(client, ROUTES[2], data)
    assert response.status_code == 200
    report = response.json()
    for field in ("summary", "direct_impacts", "indirect_impacts", "coverage", "diagnostics"):
        assert report[field] == baseline[field]
    assert report["evidences"][0]["status"] == "unavailable"
    assert report["explanations"][0]["explanation"] is None
    assert report["explanations"][0]["evidence"] == report["evidences"][0]
    assert report["explanations"][0]["diagnostics"][0]["code"] == "evidence_unavailable"
    assert report["evidences"][1:] == baseline["evidences"][1:]
    assert report["explanations"][1:] == baseline["explanations"][1:]
    assert submit(client, ROUTES[2], data).json() == baseline
    assert len(directories) == 3


def test_real_http_provider_exception_falls_back_without_state_pollution(live_backend, monkeypatch):
    client, _, directories = live_backend
    data = make_zip(demo_files())
    baseline = submit(client, ROUTES[2], data).json()

    class FailingProvider:
        def explain(self, input):
            raise RuntimeError(PRIVATE_ERROR)

    with monkeypatch.context() as faults:
        faults.setattr(provider_module, "create_explanation_provider", lambda: FailingProvider())
        response = submit(client, ROUTES[2], data)
    assert response.status_code == 200
    assert response.json() == baseline
    assert submit(client, ROUTES[2], data).json() == baseline
    assert len(directories) == 3


@pytest.mark.parametrize("route", ROUTES)
def test_real_http_unexpected_index_exception_uses_safe_json_and_cleans_up(
    live_backend, monkeypatch, route
):
    client, url, directories = live_backend
    with monkeypatch.context() as faults:
        def fail_index(_self):
            raise RuntimeError(PRIVATE_ERROR)

        faults.setattr(zip_inspector.SymbolIndex, "build", fail_index)
        response = client.post(route, data={} if route == ROUTES[0] else {"change": json.dumps(CHANGE)},
                               files={"file": ("project.zip", make_zip(demo_files()), "application/zip")})
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert len(response.content) == int(response.headers["content-length"])
    assert_safe(response)
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "internal_error"
    assert len(directories) == 1
    assert all(not path.exists() for path in directories)
    # Starlette re-raises after sending the safe 500; Uvicorn closes that TCP
    # connection. Immediate pool reuse can race the close (Windows ReadError).
    # Check recovery over a new connection, without retrying the failed request.
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as recovered:
        health = recovered.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "version": "0.1.0"}
        assert submit(recovered, route, make_zip(demo_files())).status_code == 200
    assert all(not path.exists() for path in directories)


def test_real_http_unexpected_exception_completes_json_then_closes_tcp(
    live_backend, monkeypatch
):
    """Observe EOF/reset on the actual socket, independent of a client pool."""
    _, url, directories = live_backend
    request = httpx.Request(
        "POST", url + ROUTES[0], headers={"Connection": "keep-alive"},
        files={"file": ("project.zip", make_zip(demo_files()), "application/zip")},
    )
    body = request.read()
    headers = b"\r\n".join(name + b": " + value for name, value in request.headers.raw)
    wire_request = b"POST /api/v1/projects/inspect HTTP/1.1\r\n" + headers + b"\r\n\r\n" + body

    with monkeypatch.context() as faults:
        def fail_index(_self):
            raise RuntimeError(PRIVATE_ERROR)

        faults.setattr(zip_inspector.SymbolIndex, "build", fail_index)
        with socket.create_connection((request.url.host, request.url.port), timeout=5) as connection:
            # Confirm the same socket supports keep-alive before the failure.
            connection.sendall(
                b"GET /api/v1/health HTTP/1.1\r\nHost: "
                + request.headers["host"].encode("ascii")
                + b"\r\nConnection: keep-alive\r\n\r\n"
            )
            with HTTPResponse(connection) as reply:
                reply.begin()
                assert reply.status == 200
                assert json.loads(reply.read()) == {"status": "ok", "version": "0.1.0"}
            connection.sendall(wire_request)
            with HTTPResponse(connection) as reply:
                reply.begin()
                # read() also rejects a truncated Content-Length response.
                response = httpx.Response(reply.status, headers=reply.getheaders(), content=reply.read())
            assert response.status_code == 500
            assert response.headers["content-type"].startswith("application/json")
            assert len(response.content) == int(response.headers["content-length"])
            assert assert_safe(response) == {
                "error": {"code": "internal_error", "message": "后端请求处理失败，请重试。"},
            }
            # The server terminates the connection even though we requested
            # keep-alive. A timeout or further response bytes fail this test.
            try:
                assert connection.recv(1) == b""
            except (ConnectionResetError, ConnectionAbortedError):
                pass  # Windows may report peer closure as a reset instead of EOF.

    assert len(directories) == 1
    assert all(not path.exists() for path in directories)
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as recovered:
        health = recovered.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "version": "0.1.0"}
        assert submit(recovered, ROUTES[0], make_zip(demo_files())).status_code == 200
    assert all(not path.exists() for path in directories)


def test_real_http_demo_does_not_disclose_server_project_path(live_backend):
    client, _, _ = live_backend
    response = client.post("/api/v1/demo/analyze")
    assert response.status_code == 200
    assert_safe(response)
    assert response.json()["summary"]["direct_impact_count"] == 1


def test_real_http_concurrent_independent_uploads_do_not_mix_state(live_backend, monkeypatch):
    _, url, directories = live_backend
    barrier = Barrier(6)
    providers = []
    lock = Lock()

    def track_provider():
        provider = RuleBasedProvider()
        with lock:
            providers.append(provider)
        return provider

    monkeypatch.setattr(provider_module, "create_explanation_provider", track_provider)

    def independent_flow(number):
        files = demo_files() | {
            "utils.py": f"def format_date(date_{number}):\n    return date_{number}\n",
            "report.py": f"from utils import format_date\ndef report():\n    return format_date('request_{number}')\n",
        }
        data = make_zip(files)
        barrier.wait(timeout=10)
        with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
            inspected, validated, report = workflow(client, data)
        assert validated["change_spec"]["before"]["parameters"][0]["name"] == f"date_{number}"
        direct = report["evidences"][0]
        assert direct["source_snippet"] == f"    return format_date('request_{number}')"
        assert direct["source_hash"] == sha256(files["report.py"].encode()).hexdigest()
        assert f"request_{number}" in report["explanations"][0]["explanation"]["why_affected"]
        return inspected["project_fingerprint"]

    with ThreadPoolExecutor(max_workers=6) as executor:
        fingerprints = list(executor.map(independent_flow, range(6)))
    assert len(set(fingerprints)) == 6
    assert len(directories) == 18
    assert all(not path.exists() for path in directories)
    assert len(providers) == len({id(provider) for provider in providers}) == 18


def test_real_http_concurrent_success_and_failures_are_isolated(live_backend):
    client, url, directories = live_backend
    data = make_zip(demo_files())
    barrier = Barrier(4)

    def independent_request(number):
        barrier.wait(timeout=10)
        with httpx.Client(base_url=url, timeout=30, trust_env=False) as independent:
            if number == 1:
                return submit(independent, ROUTES[2], b"not a zip")
            if number == 2:
                return submit(independent, ROUTES[2], data, fingerprint="0" * 64)
            if number == 3:
                return submit(independent, ROUTES[2], data, change="{")
            return submit(independent, ROUTES[2], data)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(independent_request, range(4)))
    assert [response.status_code for response in results] == [200, 400, 409, 422]
    assert results[0].json()["summary"]["direct_impact_count"] == 1
    assert results[1].json()["error"]["code"] == "invalid_zip"
    assert results[2].json()["error"]["code"] == "fingerprint_mismatch"
    assert results[3].json()["validation"]["diagnostics"][0]["code"] == "invalid_change_json"
    assert submit(client, ROUTES[2], data).json() == results[0].json()
    assert len(directories) == 3


def test_real_http_io_failure_is_safe_and_cleans_temp(live_backend, monkeypatch):
    client, _, directories = live_backend

    def fail_extraction(*_args):
        raise OSError(PRIVATE_ERROR)

    with monkeypatch.context() as faults:
        faults.setattr(zip_inspector, "_extract_python", fail_extraction)
        for route in ROUTES:
            response = submit(client, route, make_zip(demo_files()))
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "inspection_unavailable"
    assert len(directories) == 3
    assert all(not path.exists() for path in directories)
    assert submit(client, ROUTES[2], make_zip(demo_files())).status_code == 200


def test_real_http_analysis_failure_is_safe_and_cleans_temp(live_backend, monkeypatch):
    client, _, directories = live_backend

    def fail_analysis(*_args):
        raise RuntimeError(PRIVATE_ERROR)

    with monkeypatch.context() as faults:
        faults.setattr(api, "analyze_project", fail_analysis)
        response = submit(client, ROUTES[2], make_zip(demo_files()))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "analysis_failed"
    assert len(directories) == 1
    assert all(not path.exists() for path in directories)
    assert submit(client, ROUTES[2], make_zip(demo_files())).status_code == 200


@pytest.mark.parametrize("route", ROUTES)
def test_real_http_missing_fields_keep_framework_contract(live_backend, route):
    client, _, directories = live_backend
    response = client.post(route)
    assert response.status_code == 422
    assert set(assert_safe(response)) == {"detail"}
    assert not directories


@pytest.mark.parametrize("route", (*ROUTES, "/api/v1/demo/analyze"))
def test_real_http_health_responds_while_sync_stage_is_blocked(live_backend, monkeypatch, route):
    client, url, directories = live_backend
    entered, release = Event(), Event()
    original_build = zip_inspector.SymbolIndex.build

    def blocked_build(self):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=20), "test must release the blocked sync operation"
        return original_build(self)

    monkeypatch.setattr(zip_inspector.SymbolIndex, "build", blocked_build)
    data = make_zip(demo_files())

    def blocking_request():
        with httpx.Client(base_url=url, timeout=30, trust_env=False) as independent:
            if route == "/api/v1/demo/analyze":
                return independent.post(route)
            return submit(independent, route, data)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(blocking_request)
        try:
            assert entered.wait(timeout=5)
            assert not pending.done()
            # A timeout detects event-loop blocking; ordering uses Events, not sleep.
            health = client.get("/api/v1/health", timeout=5)
            assert health.status_code == 200
            assert health.json() == {"status": "ok", "version": "0.1.0"}
            assert not release.is_set() and not pending.done()
            if route != "/api/v1/demo/analyze":
                assert len(directories) == 1 and directories[0].exists()
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response.status_code == 200
    assert_safe(response)
    assert all(not path.exists() for path in directories)
    if route in (ROUTES[2], "/api/v1/demo/analyze"):
        summary = response.json()["summary"]
        assert [summary[name] for name in (
            "direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"
        )] == [1, 1, 1]
        assert response.json()["coverage"]["status"] == "complete"


@pytest.mark.parametrize("fail_slow", [False, True], ids=["success", "analysis_error"])
def test_real_http_blocked_analysis_preserves_other_project_and_cleanup(
    live_backend, monkeypatch, fail_slow
):
    client, url, directories = live_backend
    entered, release = Event(), Event()
    original_analysis = api.analyze_project
    snapshots = []

    def observed_analysis(path, spec):
        if spec.before.parameters[0].name == "date_slow":
            snapshots.append(Path(path))
            entered.set()
            assert release.wait(timeout=20)
            if fail_slow:
                raise RuntimeError(PRIVATE_ERROR)
        return original_analysis(path, spec)

    monkeypatch.setattr(api, "analyze_project", observed_analysis)

    def project(label):
        files = demo_files() | {
            "utils.py": f"def format_date(date_{label}):\n    return date_{label}\n",
            "report.py": f"from utils import format_date\ndef report():\n    return format_date('request_{label}')\n",
        }
        return make_zip(files)

    slow, fast = project("slow"), project("fast")

    def slow_request():
        with httpx.Client(base_url=url, timeout=30, trust_env=False) as independent:
            return submit(independent, ROUTES[2], slow, fingerprint=sha256(slow).hexdigest())

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(slow_request)
        try:
            assert entered.wait(timeout=5)
            assert snapshots[0].exists()
            assert client.get("/api/v1/health", timeout=5).status_code == 200
            inspected, validated, report = workflow(client, fast)
            assert inspected["project_fingerprint"] == sha256(fast).hexdigest()
            assert validated["change_spec"]["before"]["parameters"][0]["name"] == "date_fast"
            assert report["evidences"][0]["source_snippet"] == "    return format_date('request_fast')"
            assert len(directories) == 4
            assert directories[0].exists()
            assert all(not path.exists() for path in directories[1:])
            assert not release.is_set() and not pending.done()
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert all(not path.exists() for path in directories)
    assert not snapshots[0].exists()
    if fail_slow:
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "analysis_failed"
    else:
        assert response.status_code == 200
        report = response.json()
        assert report["change"]["before"]["parameters"][0]["name"] == "date_slow"
        assert report["evidences"][0]["source_snippet"] == "    return format_date('request_slow')"
        assert report["summary"]["direct_impact_count"] == 1
        assert report["coverage"]["status"] == "complete"
