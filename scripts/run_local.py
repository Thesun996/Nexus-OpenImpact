"""Run the local API, Worker and Vite together, without installing dependencies."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from getpass import getpass
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[1]


class StartupError(RuntimeError):
    pass


def build_environment(root: Path, provider: str | None, variables: dict[str, str]) -> dict[str, str]:
    env = dict(variables)
    selected = provider or env.get("OPENIMPACT_LLM_PROVIDER") or "deepseek"
    if selected not in {"deepseek", "rule"}:
        raise StartupError("解释模式不受支持，请选择 deepseek 或 rule。")
    if selected == "deepseek" and not env.get("DEEPSEEK_API_KEY", "").strip():
        raise StartupError("DeepSeek 密钥未设置。请使用 -PromptKey 隐藏输入；规则测试可使用 -Provider rule。")
    env.update(OPENIMPACT_LLM_PROVIDER=selected, PYTHONPATH=str(root / "src"),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    for name, default in (("OPENIMPACT_DB_PATH", ".openimpact/openimpact.sqlite3"),
                          ("OPENIMPACT_SNAPSHOT_DIR", ".openimpact/snapshots")):
        env[name] = str((root / (env.get(name) or default)).resolve())
    return env


def check_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise StartupError("端口必须在 1 到 65535 之间。")
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    except OSError:
        raise StartupError(f"端口 {port} 已被占用或无法绑定。请关闭对应服务，或指定 -ApiPort / -FrontendPort。") from None


def probe(command: list[str], cwd: Path, env: dict[str, str], message: str) -> dict:
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                encoding="utf-8", timeout=15, check=False)
        if result.returncode:
            raise StartupError(message)
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        # Dependency diagnostics may include environment values; never echo raw output.
        raise StartupError(message) from None


def supported_node(version: str) -> bool:
    major, minor, _ = map(int, version.lstrip("v").split("."))
    return (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22


def preflight(root: Path, env: dict[str, str], api_port: int, frontend_port: int) -> str:
    if sys.version_info < (3, 11):
        raise StartupError("需要 Python 3.11 或更新版本，请通过 -Python 指定项目环境。")
    if api_port == frontend_port:
        raise StartupError("API 和前端必须使用不同端口。")
    check_port(api_port)
    check_port(frontend_port)
    python = probe([sys.executable, "-c", "import sys,json,fastapi,uvicorn,multipart,openimpact;"
                    "print(json.dumps({'version':sys.version.split()[0],'source':openimpact.__file__}))"], root, env,
                   "Python 依赖不可用。请在当前解释器安装项目依赖：python -m pip install -e .")
    if Path(python["source"]).resolve() != (root / "src/openimpact/__init__.py").resolve():
        raise StartupError("Python 指向了其他项目源码，请检查解释器和 PYTHONPATH。")
    frontend = root / "frontend"
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise StartupError("未找到 Node.js / npm。需要 Node 20.19 或 22.12 及以上受支持版本。")
    runtime = probe([node, "-p", "JSON.stringify({version:process.versions.node})"], frontend, env,
                    "无法运行 Node.js，请检查 Node.js 安装。")
    if not supported_node(runtime["version"]):
        raise StartupError("Node.js 版本不满足 frontend/package.json 要求：20.19 或 22.12 及以上。")
    probe([node, "-e", "const p=require('./package.json');"
           "for(const name of Object.keys({...p.dependencies,...p.devDependencies})) require.resolve(name);"
           "console.log('{}')"], frontend, env, "前端依赖不完整。请进入 frontend 执行 npm ci。")
    if not (frontend / "node_modules/vite/bin/vite.js").is_file():
        raise StartupError("未找到本项目 Vite。请进入 frontend 执行 npm ci。")
    try:
        database = Path(env["OPENIMPACT_DB_PATH"])
        if database.is_dir():
            raise StartupError("数据库路径指向目录，请检查 OPENIMPACT_DB_PATH。")
        for directory in (database.parent, Path(env["OPENIMPACT_SNAPSHOT_DIR"])):
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory):
                pass
    except OSError:
        raise StartupError("数据库或快照目录无法写入，请检查配置及权限。") from None
    print(f"Python {python['version']}：{sys.executable}")
    print(f"Node.js {runtime['version']}：{node}")
    return node


def check_children(children: list[tuple[str, subprocess.Popen]]) -> None:
    for name, process in children:
        if process.poll() is not None:
            raise StartupError(f"{name} 已退出（退出码 {process.returncode}），请查看本次启动日志。")


def wait_ready(children: list, url: str, timeout: float, *, html: bool = False) -> None:
    opener = build_opener(ProxyHandler({}))  # Loopback health checks must not use the user's network proxy.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_children(children)
        try:
            with opener.open(url, timeout=1) as response:
                data = response.read(65536)
            payload = None if html else json.loads(data)
            ready = b"@vite/client" in data if html else isinstance(payload, dict) and payload.get("status") == "ok"
            if ready:
                check_children(children)
                return
        except (URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(0.1)
    raise StartupError("服务启动超时，请查看本次启动日志。")


def stop_services(children: list[tuple[str, subprocess.Popen]]) -> None:
    for _, process in reversed(children):
        if process.poll() is not None:
            continue
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            try:
                process.terminate()
            except OSError:
                pass  # It may have exited between the poll and the signal.
    failures = []
    for name, process in reversed(children):
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Only PIDs started by this launcher are eligible for forced tree cleanup.
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, timeout=10, check=False)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except (OSError, subprocess.TimeoutExpired):
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                failures.append(f"{name} PID={process.pid}")
    if failures:
        raise StartupError("未能确认进程停止，请检查：" + "、".join(failures))


def run_services(root: Path, env: dict[str, str], node: str, api_port: int, frontend_port: int,
                 timeout: float, smoke: bool) -> None:
    logs = root / ".local/run-local" / uuid.uuid4().hex[:8]
    logs.mkdir(parents=True)
    print(f"本次日志：{logs}", flush=True)
    children = []
    with ExitStack() as streams:
        def start(name, command, cwd, environment=None):
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(command, cwd=cwd, env=env if environment is None else environment, stdin=subprocess.DEVNULL,
                                       stdout=streams.enter_context((logs / f"{name}.log").open("wb")),
                                       stderr=subprocess.STDOUT, **options)
            children.append((name, process))
            print(f"{name} PID={process.pid}", flush=True)

        try:
            start("API", [sys.executable, "-m", "uvicorn", "openimpact.api:app", "--host", "127.0.0.1", "--port", str(api_port)], root)
            wait_ready(children, f"http://127.0.0.1:{api_port}/api/v1/health", timeout)
            start("Worker", [sys.executable, "-m", "openimpact.worker"], root)
            frontend_env = {key: value for key, value in env.items() if key != "DEEPSEEK_API_KEY"}
            start("Frontend", [node, str(root / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(frontend_port)], root / "frontend", frontend_env)
            url = f"http://127.0.0.1:{frontend_port}"
            wait_ready(children, url, timeout, html=True)
            wait_ready(children, url + "/api/v1/health", timeout)
            check_children(children)
            print(f"启动完成：{url}，API / Worker / 前端均已启动，代理已验证。", flush=True)
            if smoke:
                print("启动探测通过，正在停止本次进程。", flush=True)
                return
            print("请保持此终端打开；按 Ctrl+C 统一停止本次服务。", flush=True)
            while True:
                check_children(children)
                time.sleep(0.5)
        finally:
            stop_services(children)
            print("本次启动的服务已停止。", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统一启动 Nexus OpenImpact 本地工作台")
    parser.add_argument("--provider", choices=("deepseek", "rule"))
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查环境，不启动服务")
    mode.add_argument("--smoke-test", action="store_true", help="启动并验证服务后自动停止")
    parser.add_argument("--prompt-key", action="store_true", help="隐藏输入 DeepSeek 密钥，仅传给本次进程")
    parser.add_argument("--startup-timeout", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.startup_timeout) or args.startup_timeout <= 0:
            raise StartupError("启动超时必须是大于 0 的有限秒数。")
        variables = dict(os.environ)
        if args.prompt_key:
            variables["DEEPSEEK_API_KEY"] = getpass("DeepSeek API Key（隐藏输入）: ")
        env = build_environment(ROOT, args.provider, variables)
        env["OPENIMPACT_API_TARGET"] = f"http://127.0.0.1:{args.api_port}"
        node = preflight(ROOT, env, args.api_port, args.frontend_port)
        print(f"项目源码：{ROOT / 'src'}")
        print("解释模式：" + ("DeepSeek（密钥已设置；未验证外网可用性）" if env["OPENIMPACT_LLM_PROVIDER"] == "deepseek" else "规则测试（不调用 DeepSeek）"))
        print(f"共用数据库：{env['OPENIMPACT_DB_PATH']}")
        print(f"共用快照目录：{env['OPENIMPACT_SNAPSHOT_DIR']}")
        print(f"Vite /api 代理：http://127.0.0.1:{args.api_port}", flush=True)
        if args.check:
            print("环境自检通过；未启动服务，未调用模型。")
            return 0
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        if os.name == "nt":
            signal.signal(signal.SIGBREAK, interrupted)
        run_services(ROOT, env, node, args.api_port, args.frontend_port, args.startup_timeout, args.smoke_test)
        return 0
    except KeyboardInterrupt:
        return 0
    except (StartupError, OSError) as error:
        print(f"启动失败：{error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
