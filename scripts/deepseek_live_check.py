"""Opt-in live DeepSeek check using real loopback HTTP and the public demo only."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from getpass import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
from threading import Thread
import time
from unittest.mock import patch
import zipfile

import httpx
import uvicorn

from openimpact.api import app
from openimpact.explanation import provider as provider_module
from openimpact.explanation.deepseek import DeepSeekProvider
from openimpact.repository import zip_inspector

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "signature_change"
CHANGE = {
    "target_symbol_id": "utils.format_date",
    "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"},
}


def demo_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEMO.glob("*.py")):
            info = zipfile.ZipInfo(f"signature_change/{path.name}", (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


@contextmanager
def local_server():
    """Start only a loopback test server; all existing API routes stay unchanged."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("local_server_unavailable")
            time.sleep(0.02)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def workflow(client: httpx.Client, data: bytes) -> tuple[dict, dict]:
    fingerprint = hashlib.sha256(data).hexdigest()
    files = {"file": ("signature_change.zip", data, "application/zip")}
    inspect = client.post("/api/v1/projects/inspect", files=files)
    fields = {"change": json.dumps(CHANGE), "expected_fingerprint": fingerprint}
    validate = client.post("/api/v1/changes/validate", files=files, data=fields)
    analyze = client.post("/api/v1/projects/analyze", files=files, data=fields)
    if any(response.status_code != 200 for response in (inspect, validate, analyze)):
        raise RuntimeError("workflow_http_failure")
    inspected, validated, report = inspect.json(), validate.json(), analyze.json()
    facts = {
        "http_statuses": [inspect.status_code, validate.status_code, analyze.status_code],
        "fingerprint_matches": inspected["project_fingerprint"]
        == validated["project_fingerprint"] == fingerprint,
        "target_found": CHANGE["target_symbol_id"] in {
            item["symbol_id"] for item in inspected["symbols"]
        },
        "change_valid": validated["validation"]["valid"],
        "change_matches": report["change"] == validated["change_spec"],
    }
    return report, facts


def quality_screen(input_data: dict, result: dict) -> list[str]:
    """Flag obvious issues; human review must still assess evidence fidelity."""
    issues = []
    locations = [input_data["source_location"]] + [
        site for path in input_data["propagation_path"] for site in path["call_sites"]
    ]
    files = {site["file"] for site in locations}
    sites = {(site["file"], site["line"]) for site in locations}
    text = "\n".join(result[name] for name in ("summary", "why_affected", "suggested_check"))
    for file in re.findall(r"[a-zA-Z0-9_./\\-]+\.py", text):
        if file not in files:
            issues.append("unprovided_file_reference")
    for file, line in re.findall(r"([a-zA-Z0-9_./\\-]+\.py):(\d+)", text):
        if (file, int(line)) not in sites:
            issues.append("unprovided_source_location")
    symbols = {input_data["target_symbol"]} | {
        symbol for path in input_data["propagation_path"] for symbol in path["symbols"]
    }
    if any(symbol not in symbols for symbol in re.findall(
        r"\b[a-zA-Z_]\w*\.[a-zA-Z_]\w*\b", text
    ) if not symbol.endswith(".py")):
        issues.append("unprovided_symbol_reference")
    call_names = symbols | {symbol.rsplit(".", 1)[-1] for symbol in symbols}
    if any(name not in call_names for name in re.findall(
        r"\b([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*\(", text
    )):
        issues.append("unprovided_function_reference")
    if result["risk_level"] != "unknown":
        issues.append("unsupported_risk_level")
    if re.search(r"(?:改成|替换为|修改为|补上|添加代码|新增代码)", result["suggested_check"]):
        issues.append("possible_concrete_code_change")
    if input_data["impact_type"] != "direct" and re.search(
        r"(?:一定|必然|必定)(?:会)?(?:运行)?(?:失败|报错|崩溃)", text
    ):
        issues.append("indirect_claims_definite_failure")
    return sorted(set(issues))


def run_check(timeout_seconds: float = 20.0) -> dict:
    records = []
    temporary_paths = []
    original_factory = provider_module.create_explanation_provider
    original_directory = zip_inspector.TemporaryDirectory

    class RecordingProvider(DeepSeekProvider):
        def explain(self, input):
            result = super().explain(input)
            input_data, result_data = input.to_dict(), result.to_dict()
            records.append({
                "impact_type": input.impact_type,
                "call": asdict(self.last_call),
                "input": input_data,
                "result": result_data,
                "quality_flags": quality_screen(input_data, result_data),
            })
            return result

    def observed_factory(mode=None):
        provider = original_factory(mode)
        if isinstance(provider, DeepSeekProvider):
            return RecordingProvider(timeout_seconds=timeout_seconds)
        return provider

    def record_directory(*args, **kwargs):
        directory = original_directory(*args, **kwargs)
        temporary_paths.append(Path(directory.name))
        return directory

    with (patch.object(provider_module, "create_explanation_provider", observed_factory),
          patch.object(zip_inspector, "TemporaryDirectory", record_directory),
          local_server() as base_url,
          httpx.Client(base_url=base_url, timeout=timeout_seconds * 3 + 15, trust_env=False) as client):
        with patch.dict(os.environ, {"OPENIMPACT_LLM_PROVIDER": "rule"}):
            rule, rule_flow = workflow(client, demo_zip())
        with patch.dict(os.environ, {"OPENIMPACT_LLM_PROVIDER": "deepseek"}):
            deepseek, deepseek_flow = workflow(client, demo_zip())

    static_fields = ("direct_impacts", "indirect_impacts", "evidences", "coverage",
                     "diagnostics", "summary", "change", "validation")
    same = {name: rule[name] == deepseek[name] for name in static_fields}
    all_model_success = len(records) == 3 and all(
        item["call"]["status"] == "model_success" for item in records
    )
    return {
        "transport": "real_loopback_http_and_real_deepseek_https",
        "rule_workflow": rule_flow,
        "deepseek_workflow": deepseek_flow,
        "static_fields_equal": same,
        "temporary_directories_cleaned": len(temporary_paths) == 6
        and all(not path.exists() for path in temporary_paths),
        "model_calls": records,
        "real_model_success": all_model_success,
        "quality_screening": "automatic_flags_require_human_review",
        "rule_report": rule,
        "deepseek_report": deepseek,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="固定 Demo 的真实 DeepSeek 联调；最多 3 次模型调用")
    parser.add_argument("--prompt-key", action="store_true", help="在终端隐藏输入 Key，仅保存在进程内")
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / "deepseek-live-check")
    args = parser.parse_args()
    if args.prompt_key:
        os.environ["DEEPSEEK_API_KEY"] = getpass("DeepSeek API Key（隐藏输入）: ").strip()
    key = os.getenv("DEEPSEEK_API_KEY", "")
    try:
        result = run_check()
    except Exception:
        print("联调脚本未完成；请检查本地服务依赖和网络。未输出密钥或原始异常。")
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if key:
        serialized = serialized.replace(key, "<redacted>")
    (args.output / "result.json").write_text(serialized + "\n", encoding="utf-8")
    print("真实模型成功:", result["real_model_success"])
    print("静态分析数据一致:", all(result["static_fields_equal"].values()))
    print("临时目录清理:", result["temporary_directories_cleaned"])
    print("调用状态:", [(item["impact_type"], item["call"]["status"],
                         item["call"]["reason_code"]) for item in result["model_calls"]])
    print("脱敏结果:", args.output / "result.json")
    success = (result["real_model_success"] and all(result["static_fields_equal"].values())
               and result["temporary_directories_cleaned"]
               and not any(item["quality_flags"] for item in result["model_calls"]))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
