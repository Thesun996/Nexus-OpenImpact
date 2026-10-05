"""Reproduce a pinned upstream source audit; never import or run upstream code.

These selected source witnesses are Codex-assisted review notes, not locked
human ground truth. This script calculates no benchmark accuracy metrics.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import zipfile


COMMIT = "16e660d384b942b11879b44500afbbe021650448"
CASES = (
    ("same_file", "src.dotenv.parser.parse_key", "strict"),
    ("cross_file_and_method", "src.dotenv.parser.parse_stream", "strict"),
    ("same_file_public_function", "src.dotenv.main.find_dotenv", "strict"),
    ("package_public_api", "src.dotenv.main.load_dotenv", "strict"),
)
# Selected witnesses were read before generating predictions. Not exhaustive.
WITNESSES = (
    ("same_file", "src/dotenv/parser.py", 147, "key = parse_key(reader)", "module_function"),
    ("cross_file_and_method", "src/dotenv/main.py", 85,
     "for mapping in with_warn_for_invalid_lines(parse_stream(stream)):", "class_method"),
    ("cross_file_and_method", "src/dotenv/main.py", 185,
     "for mapping in with_warn_for_invalid_lines(parse_stream(source)):", "module_function"),
    ("cross_file_and_method", "src/dotenv/main.py", 218,
     "for mapping in with_warn_for_invalid_lines(parse_stream(source)):", "module_function"),
    ("cross_file_and_method", "tests/test_parser.py", 169,
     "result = parse_stream(io.StringIO(test_input))", "module_function"),
    ("same_file_public_function", "src/dotenv/main.py", 354,
     "dotenv_path = find_dotenv()", "module_function"),
    ("same_file_public_function", "src/dotenv/main.py", 391,
     "dotenv_path = find_dotenv()", "module_function"),
    ("package_public_api", "tests/test_main.py", 242,
     "result = dotenv.load_dotenv(dotenv_path)", "module_function"),
)


def config(target, parameter):
    return {"change_type": "add_required_parameter", "target_symbol_id": target,
            "added_parameter": {"name": parameter, "kind": "keyword_only"}}


def source_snapshot(repository):
    actual = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != COMMIT:
        raise ValueError("Expected the pinned python-dotenv v1.1.1 commit")
    dirty = subprocess.run(
        ["git", "-C", str(repository), "diff", "--quiet", "HEAD", "--", "*.py"],
        check=False,
    )
    if dirty.returncode != 0:
        raise ValueError("Pinned upstream Python sources have local modifications")
    paths = subprocess.check_output(
        ["git", "-C", str(repository), "ls-files", "-z"], text=True
    ).split("\0")
    sources = {name: (repository / name).read_bytes()
               for name in sorted(paths) if name.endswith(".py")}
    for _, file, line, text, _ in WITNESSES:
        if sources[file].decode("utf-8").splitlines()[line - 1].strip() != text:
            raise ValueError(f"Selected source witness changed: {file}:{line}")
    return sources


def zip_snapshot(sources):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in sources.items():
            info = zipfile.ZipInfo("python-dotenv-v1.1.1/" + name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return stream.getvalue()


@contextmanager
def local_http(app):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Audit HTTP server failed to start")
            time.sleep(0.02)
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Audit HTTP server did not stop")


def run(repository, output):
    # Force the rule provider before importing the server. No external models.
    os.environ["OPENIMPACT_LLM_PROVIDER"] = "rule"
    from openimpact.api import app
    from openimpact.api_change import build_change_spec
    from openimpact.analysis.call_graph import CallGraph
    from openimpact.analysis.pipeline import analyze_project
    from openimpact.analysis.report import build_report
    from openimpact.analysis.symbol_index import SymbolIndex
    from openimpact.explanation.fallback import RuleBasedProvider
    from openimpact.repository import zip_inspector
    import httpx
    from unittest.mock import patch

    output.mkdir(parents=True, exist_ok=True)
    sources = source_snapshot(repository)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
    # Persist review notes before asking OpenImpact for any prediction.
    notes = {"annotation_status": "not_ground_truth", "reviewer": "Codex-assisted source review",
             "commit": COMMIT, "source_sha256": manifest,
             "selected_witnesses": [dict(zip(
                 ("case", "file", "line", "source", "scope"), witness
             )) for witness in WITNESSES]}
    (output / "source-review.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    index = SymbolIndex(repository).build()
    if {path.as_posix() for path in index.scanner.scan()} != set(sources):
        raise ValueError("Scanned Python files differ from the pinned source manifest")
    graph = CallGraph(index).build()
    results = {"commit": COMMIT, "python_files": len(sources),
               "indexed_modules": len(index.modules), "indexed_functions": len(index.symbols),
               "resolved_call_sites": len(graph.edges),
               "unresolved_call_reasons": dict(Counter(call.reason for call in graph.unresolved_calls)),
               "unresolved_import_reasons": dict(Counter(
                   binding.reason for bindings in index.bindings.values()
                   for binding in bindings.values() if binding.status == "unresolved")),
               "cases": [], "http": {}}
    for name, target, parameter in CASES:
        spec = build_change_spec(index, config(target, parameter))
        started = time.perf_counter()
        report = build_report(analyze_project(repository, spec), explanation_provider=RuleBasedProvider())
        elapsed = time.perf_counter() - started
        report["project_path"] = "."  # Do not publish this machine's absolute path.
        (output / (name + "-report.json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        evidence_checks = []
        for evidence in report["evidences"]:
            location = evidence["location"]
            file = location["file"]
            evidence_checks.append({"file": file, "line": location["line"],
                                    "hash_matches": evidence["source_hash"] == manifest[file]})
        results["cases"].append({"case": name, "target": target, "summary": report["summary"],
                                 "coverage": report["coverage"], "seconds": elapsed,
                                 "direct_sites": [(item["file"], item["line"]) for item in report["direct_impacts"]],
                                 "indirect_symbols": [item["impacted_symbol_id"] for item in report["indirect_impacts"]],
                                 "evidence_checks": evidence_checks})

    data = zip_snapshot(sources)
    (output / "python-dotenv-v1.1.1-sources.zip").write_bytes(data)
    directories = []
    original_temporary = zip_inspector.TemporaryDirectory

    def tracked_directory(*args, **kwargs):
        directory = original_temporary(*args, **kwargs)
        directories.append(Path(directory.name))
        return directory

    with patch.object(zip_inspector, "TemporaryDirectory", tracked_directory):
        with local_http(app) as url, httpx.Client(base_url=url, trust_env=False, timeout=30) as client:
            files = {"file": ("python-dotenv-v1.1.1.zip", data, "application/zip")}
            inspected = client.post("/api/v1/projects/inspect", files=files)
            inspected.raise_for_status()
            inspect = inspected.json()
            (output / "inspect-response.json").write_text(
                json.dumps(inspect, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            results["http"]["inspect"] = {"status": inspected.status_code,
                "coverage": inspect["coverage"],
                "selectable_module_count": sum(m["selectable"] for m in inspect["module_inventory"]["modules"])}
            for name, target, parameter in CASES:
                fields = {"change": json.dumps(config(target, parameter)),
                          "expected_fingerprint": inspect["project_fingerprint"]}
                validated = client.post("/api/v1/changes/validate", files=files, data=fields)
                analyzed = client.post("/api/v1/projects/analyze", files=files, data=fields)
                validated.raise_for_status()
                analyzed.raise_for_status()
                result = analyzed.json()
                (output / (name + "-http-report.json")).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                local = next(item for item in results["cases"] if item["case"] == name)
                fingerprint_matches = (
                    validated.json()["project_fingerprint"] == inspect["project_fingerprint"]
                    == hashlib.sha256(data).hexdigest()
                )
                if local["summary"] != result["summary"] or not fingerprint_matches:
                    raise RuntimeError("Local and HTTP audit snapshots diverged")
                results["http"][name] = {"validate_status": validated.status_code,
                    "analyze_status": analyzed.status_code, "summary": result["summary"],
                    "coverage": result["coverage"], "same_as_local": True,
                    "validate_fingerprint_matches": fingerprint_matches}
            mismatch = client.post("/api/v1/projects/analyze", files=files, data={
                "change": json.dumps(config(CASES[0][1], CASES[0][2])),
                "expected_fingerprint": "0" * 64})
            if mismatch.status_code != 409 or mismatch.json()["error"]["code"] != "fingerprint_mismatch":
                raise RuntimeError("Analyze fingerprint guard failed")
            results["http"]["fingerprint_mismatch"] = {"status": mismatch.status_code, "body": mismatch.json()}
            module = client.post("/api/v1/changes/validate", files=files, data={
                "change": json.dumps({"change_domain": "module", "change_type": "rename_module",
                                      "target_module_id": "src.dotenv.parser", "new_module_name": "formatting"}),
                "expected_fingerprint": inspect["project_fingerprint"]})
            (output / "nested-module-validation.json").write_text(
                json.dumps(module.json(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            results["http"]["nested_module_validation"] = {
                "status": module.status_code, "validation": module.json().get("validation"),
            }
    results["http"]["temporary_directories"] = len(directories)
    results["http"]["temporary_cleanup"] = all(not path.exists() for path in directories)
    if not results["http"]["temporary_cleanup"]:
        raise RuntimeError("Request temporary directories were not cleaned")
    if source_snapshot(repository) != sources:
        raise RuntimeError("Upstream sources changed during the audit")
    results["upstream_sources_unchanged"] = True
    (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, help="Local pinned v1.1.1 checkout; never executed")
    parser.add_argument("--output", type=Path, default=Path(".local/real-project-audit/results"))
    arguments = parser.parse_args()
    run(arguments.repository.resolve(), arguments.output.resolve())
