"""Local startup must fail clearly and clean up only its own processes."""

import importlib.util
import os
from pathlib import Path
import socket
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("local_launcher", Path(__file__).resolve().parents[1] / "scripts/run_local.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_environment_pins_current_source_and_shared_absolute_storage(tmp_path):
    original = {"PYTHONPATH": "another-checkout", "OPENIMPACT_DB_PATH": "state/data.sqlite3",
                "OPENIMPACT_SNAPSHOT_DIR": "state/zips", "DEEPSEEK_API_KEY": "test-key"}
    env = launcher.build_environment(tmp_path, None, original)
    assert env["OPENIMPACT_LLM_PROVIDER"] == "deepseek"
    assert env["PYTHONPATH"] == str(tmp_path / "src")
    assert env["OPENIMPACT_DB_PATH"] == str((tmp_path / "state/data.sqlite3").resolve())
    assert env["OPENIMPACT_SNAPSHOT_DIR"] == str((tmp_path / "state/zips").resolve())
    assert original["PYTHONPATH"] == "another-checkout"


def test_deepseek_missing_key_does_not_silently_select_rule(tmp_path):
    with pytest.raises(launcher.StartupError, match="PromptKey"):
        launcher.build_environment(tmp_path, None, {})
    assert launcher.build_environment(tmp_path, "rule", {})["OPENIMPACT_LLM_PROVIDER"] == "rule"


def test_explicit_provider_overrides_inherited_mode(tmp_path):
    env = launcher.build_environment(tmp_path, "deepseek", {"OPENIMPACT_LLM_PROVIDER": "rule", "DEEPSEEK_API_KEY": "test-key"})
    assert env["OPENIMPACT_LLM_PROVIDER"] == "deepseek"


def test_probe_errors_never_include_raw_process_output(tmp_path, monkeypatch):
    def failed_probe(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="test-secret-key", stderr="test-secret-key")
    monkeypatch.setattr(launcher.subprocess, "run", failed_probe)
    with pytest.raises(launcher.StartupError) as error:
        launcher.probe(["python", "-c", "pass"], tmp_path, {}, "依赖不可用")
    assert str(error.value) == "依赖不可用"


def test_busy_port_is_rejected_without_stopping_its_owner():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(launcher.StartupError, match=str(port)):
            launcher.check_port(port)
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


@pytest.mark.parametrize("version,allowed", [("20.18.0", False), ("20.19.0", True), ("21.0.0", False),
                                               ("22.11.0", False), ("22.12.0", True), ("24.14.0", True)])
def test_node_version_boundaries_follow_frontend_engines(version, allowed):
    assert launcher.supported_node(version) is allowed


class Child:
    def __init__(self, pid, exited=False):
        self.pid = pid
        self.returncode = 0 if exited else None
        self.signals = []

    def poll(self):
        return self.returncode

    def send_signal(self, value):
        self.signals.append(value)
        self.returncode = 0

    def wait(self, timeout):
        assert self.returncode is not None
        return self.returncode


def test_cleanup_signals_owned_live_children_only(monkeypatch):
    live, exited, unrelated = Child(101), Child(102, exited=True), Child(103)
    if os.name != "nt":
        monkeypatch.setattr(launcher.os, "killpg", lambda pid, sig: live.send_signal(sig) if pid == live.pid else pytest.fail("unowned process signalled"))
    launcher.stop_services([("API", live), ("Worker", exited)])
    assert len(live.signals) == 1
    assert not exited.signals
    assert not unrelated.signals


def test_startup_failure_stops_all_children_already_started(tmp_path, monkeypatch):
    children, stopped, environments = [], [], []
    def start(*args, **kwargs):
        child = Child(100 + len(children))
        children.append(child)
        environments.append(kwargs["env"])
        return child
    calls = []
    def ready(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 2:
            raise launcher.StartupError("前端启动失败")
    monkeypatch.setattr(launcher.subprocess, "Popen", start)
    monkeypatch.setattr(launcher, "wait_ready", ready)
    monkeypatch.setattr(launcher, "stop_services", lambda owned: stopped.extend(process for _, process in owned))
    with pytest.raises(launcher.StartupError, match="前端启动失败"):
        launcher.run_services(tmp_path, {"DEEPSEEK_API_KEY": "test-secret-key", "OPENIMPACT_DB_PATH": "shared-db"}, "node", 8000, 5173, 1, False)
    assert len(children) == 3
    assert stopped == children
    assert environments[0]["DEEPSEEK_API_KEY"] == environments[1]["DEEPSEEK_API_KEY"] == "test-secret-key"
    assert "DEEPSEEK_API_KEY" not in environments[2]
    assert all(env["OPENIMPACT_DB_PATH"] == "shared-db" for env in environments)


def test_check_mode_prints_mode_but_no_key_and_starts_no_services(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "preflight", lambda *args: "node")
    monkeypatch.setattr(launcher, "run_services", lambda *args: pytest.fail("check started services"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret-key")
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "deepseek")
    assert launcher.main(["--check"]) == 0
    output = capsys.readouterr().out
    assert "DeepSeek" in output
    assert "test-secret-key" not in output
    assert not (tmp_path / ".local").exists()


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_invalid_startup_timeout_is_rejected(timeout, capsys):
    assert launcher.main(["--startup-timeout", timeout]) == 1
    assert "启动超时" in capsys.readouterr().err


def test_check_cannot_be_mistaken_for_a_smoke_test():
    with pytest.raises(SystemExit) as error:
        launcher.main(["--check", "--smoke-test"])
    assert error.value.code == 2
