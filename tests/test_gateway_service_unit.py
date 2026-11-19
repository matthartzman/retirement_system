"""Windows service wrapper: parsing, command line, config validation, state machine."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from src.gateway import service

pytestmark = pytest.mark.unit


def _config(tmp_path: Path, **over) -> Path:
    data = {"argv": ["--db", "x.db", "--funnel-port", "5065"]}
    data.update(over)
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_parse_install_defaults_and_overrides():
    args = service.parse_args(["install", "--config", "c.json"])
    assert args.command == "install" and args.name == "RetirementGateway"
    assert args.display_name == "Retirement Planner Gateway" and args.config == Path("c.json")
    args = service.parse_args(["install", "--config", "c.json", "--name", "X", "--display-name", "My Gw"])
    assert (args.name, args.display_name) == ("X", "My Gw")


@pytest.mark.parametrize("cmd", ["remove", "start", "stop", "status"])
def test_parse_simple_commands(cmd):
    assert service.parse_args([cmd]).name == "RetirementGateway"
    assert service.parse_args([cmd, "--name", "Z"]).name == "Z"


def test_parse_run_debug_need_config():
    assert service.parse_args(["run", "--config", "c", "--name", "N"]).command == "run"
    assert service.parse_args(["debug", "--config", "c"]).command == "debug"
    with pytest.raises(SystemExit):
        service.parse_args(["run"])
    with pytest.raises(SystemExit):
        service.parse_args([])


def test_service_command_line_quotes_paths_with_spaces(tmp_path):
    cfg = tmp_path / "my folder" / "gateway.json"
    line = service.service_command_line(cfg, "RetirementGateway")
    script = service.REPO_ROOT / "src" / "gateway" / "service.py"
    assert line.startswith(f'"{sys.executable}" -E -s "{script}" run --config "')
    assert f'"{cfg.resolve() if cfg.is_absolute() else cfg}"' in line or str(cfg) in line
    assert line.endswith('" --name RetirementGateway')
    assert service.service_command_line(cfg, "My Gateway").endswith('--name "My Gateway"')


def test_config_argv_valid(tmp_path):
    assert service.config_argv(_config(tmp_path)) == ["--db", "x.db", "--funnel-port", "5065"]


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '{"argv": "--db x"}', '{"argv": ["a", 5]}', '{}', '{"argv": [], "log_file": 3}'],
)
def test_config_argv_rejects_bad_content(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        service.config_argv(path)


def test_config_argv_missing_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        service.config_argv(tmp_path / "nope.json")


def test_install_refuses_bad_config_before_touching_scm(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_adv", lambda: pytest.fail("SCM must not be touched"))
    with pytest.raises(ValueError):
        service.install_service("N", "D", tmp_path / "missing.json")
    assert service.main(["install", "--config", str(tmp_path / "missing.json")]) == 1


def test_win_error_access_denied_mentions_elevation():
    err = service.win_error(5, "creating service X")
    assert err.errno == 5 and "elevated" in str(err)
    assert "elevated" not in str(service.win_error(1060, "opening"))


_needs_scm = pytest.mark.skipif(sys.platform != "win32", reason="the service-control callback type exists only on Windows")


@_needs_scm
def test_run_service_hint_and_exit_2_when_not_started_by_scm(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service, "_enter_repo_root", lambda: None)
    monkeypatch.setattr(service, "_configure_logging", lambda f: None)

    def fail(name, proc):
        raise OSError(1063, "not started by the SCM")

    monkeypatch.setattr(service, "_start_dispatcher", fail)
    code = service.run_service("N", _config(tmp_path))
    assert code == 2
    assert "debug" in capsys.readouterr().out


@_needs_scm
def test_run_service_other_dispatcher_errors_propagate(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_enter_repo_root", lambda: None)
    monkeypatch.setattr(service, "_configure_logging", lambda f: None)

    def fail(name, proc):
        raise OSError(5, "denied")

    monkeypatch.setattr(service, "_start_dispatcher", fail)
    with pytest.raises(OSError):
        service.run_service("N", _config(tmp_path))


def test_runner_reports_states_and_stops_on_stop_control():
    seen = []
    release = threading.Event()

    def run_fn(stop):
        release.set()
        stop.wait(10)
        return 0

    runner = service.ServiceRunner(run_fn, lambda state, code: seen.append((state, code)))
    runner.start()
    assert release.wait(5)
    assert [s for s, _ in seen] == [service.SERVICE_START_PENDING, service.SERVICE_RUNNING]
    assert runner.handle_control(service.SERVICE_CONTROL_STOP) == 0
    assert runner.stop_event.is_set()
    assert runner.finish() == 0
    assert [s for s, _ in seen] == [
        service.SERVICE_START_PENDING,
        service.SERVICE_RUNNING,
        service.SERVICE_STOP_PENDING,
        service.SERVICE_STOPPED,
    ]


def test_runner_shutdown_control_and_interrogate():
    seen = []
    runner = service.ServiceRunner(lambda stop: (stop.wait(10), 0)[1], lambda s, c: seen.append(s))
    runner.start()
    runner.handle_control(service.SERVICE_CONTROL_INTERROGATE)
    assert seen[-1] == service.SERVICE_RUNNING
    runner.handle_control(service.SERVICE_CONTROL_SHUTDOWN)
    assert runner.stop_event.is_set() and runner.state == service.SERVICE_STOP_PENDING
    runner.finish()
    assert runner.state == service.SERVICE_STOPPED


def test_runner_unknown_control_ignored():
    runner = service.ServiceRunner(lambda stop: 0)
    runner.state = service.SERVICE_RUNNING
    runner.handle_control(99)
    assert not runner.stop_event.is_set() and runner.state == service.SERVICE_RUNNING


def test_runner_reports_gateway_exit_code():
    seen = []
    runner = service.ServiceRunner(lambda stop: 7, lambda s, c: seen.append((s, c)))
    assert runner.run() == 7
    assert seen[-1] == (service.SERVICE_STOPPED, 7)


def test_runner_crash_becomes_nonzero_exit():
    def boom(stop):
        raise RuntimeError("x")

    runner = service.ServiceRunner(boom)
    assert runner.run() == 1


def test_runner_join_timeout_when_gateway_ignores_stop():
    release = threading.Event()
    runner = service.ServiceRunner(lambda stop: (release.wait(10), 0)[1], join_timeout=0.2)
    runner.start()
    runner.handle_control(service.SERVICE_CONTROL_STOP)
    assert runner.finish() == 1
    release.set()


def test_make_run_fn_imports_gateway_lazily(monkeypatch):
    calls = []

    def fake_run_gateway(argv, stop_event):
        calls.append(argv)
        return 3

    monkeypatch.setattr(service, "_import_run_gateway", lambda: fake_run_gateway)
    assert service._make_run_fn(["--a"])(threading.Event()) == 3
    assert calls == [["--a"]]


def test_configure_logging_uses_rotating_file(tmp_path):
    import logging
    import logging.handlers

    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    try:
        service._configure_logging(str(tmp_path / "logs" / "gw.log"))
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1
        handler = added[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == 5 * 1024 * 1024 and handler.backupCount == 5
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
        root.setLevel(level)
