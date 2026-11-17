"""Admin app process control and live sessions, driven through the WSGI facade with a fake spawner (no real child)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from admin_app.main import create_app
from admin_app.processes import ProcessManager
from admin_app.settings import SettingsService
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest
from src.identity import IdentityStore

HEADERS = {"Host": "127.0.0.1:5056", "Content-Type": "application/json"}
ENDED = "all of this person's sessions, in every app"


class FakeWorld:
    """Pretends to be the OS: which pids live, which ports answer, what was spawned and killed."""

    def __init__(self):
        self.ports: set[int] = set()
        self.pids: set[int] = set()
        self.spawned: list[tuple] = []
        self.killed: list[int] = []
        self.next_pid = 4000

    def popen(self, cmd, **kw):
        self.next_pid += 1
        self.spawned.append((cmd, kw))
        self.pids.add(self.next_pid)
        self.ports.add(5057 if "financial_trends_reporter" in " ".join(cmd) else 5050)
        return SimpleNamespace(pid=self.next_pid)

    def kill(self, pid):
        self.killed.append(pid)
        self.pids.discard(pid)
        self.ports.clear()


@pytest.fixture
def rig(tmp_path):
    world = FakeWorld()
    store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
    manager = ProcessManager(tmp_path, popen=world.popen, probe=lambda p: p in world.ports,
                             alive=lambda pid: pid in world.pids, kill=world.kill)
    app = create_app(store, settings=SettingsService(tmp_path), processes=manager)
    return SimpleNamespace(world=world, store=store, app=app, manager=manager, root=tmp_path)


def call(rig, method, path, body=None, headers=None, peer="127.0.0.1", app=None):
    raw = json.dumps(body).encode() if body is not None else b""
    resp = (app or rig.app).dispatch_request(LocalRequest(method, path, HeaderMap(headers or HEADERS), raw, remote_addr=peer))
    return resp.status_code, json.loads(resp.get_data(as_text=True))


def audit(rig):
    return [(a["action"], a["target_user"], a["details"]) for a in rig.store.read_audit()]


def test_status_lists_both_apps_stopped_with_ports_and_no_pid(rig):
    status, out = call(rig, "GET", "/api/processes")
    assert status == 200
    apps = {a["name"]: a for a in out["apps"]}
    assert apps["planner"]["state"] == "stopped" and apps["planner"]["port"] == 5050 and apps["planner"]["pid"] is None
    assert apps["insights"]["port"] == 5057 and [p["port"] for p in apps["insights"]["extra_ports"]] == [5058]
    assert out["admin"]["state"] == "running" and out["admin"]["pid"]


def test_start_launches_the_launcher_command_detached_and_records_the_pid(rig):
    status, out = call(rig, "POST", "/api/processes/start", {"app": "insights"})
    assert status == 200 and out["app"]["state"] == "running" and out["app"]["pid"] == rig.world.next_pid
    cmd, kw = rig.world.spawned[0]
    assert cmd[1].replace("\\", "/") == "financial_trends_reporter/main.py"
    assert cmd[cmd.index("--retirement-system-dir") + 1] == str(rig.root) and "--no-open" in cmd
    assert kw["stdin"] is not None and kw["cwd"]
    assert (rig.root / "local_state" / "admin_processes" / "insights.json").exists()
    assert ("process.start", "insights", "ok") in audit(rig)


def test_planner_start_passes_the_workspace_by_environment_in_server_mode(rig):
    call(rig, "POST", "/api/processes/start", {"app": "planner"})
    cmd, kw = rig.world.spawned[0]
    assert cmd[1:] == ["main.py", "--mode", "server"]
    assert kw["env"]["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] == str(rig.root)


def test_a_second_start_does_nothing_and_is_not_audited_again(rig):
    call(rig, "POST", "/api/processes/start", {"app": "insights"})
    status, out = call(rig, "POST", "/api/processes/start", {"app": "insights"})
    assert status == 200 and out["already"] and len(rig.world.spawned) == 1
    assert [a for a in audit(rig) if a[0] == "process.start"] == [("process.start", "insights", "ok")]


def test_an_app_already_answering_on_its_port_is_reported_running_and_not_spawned_again(rig):
    rig.world.ports.add(5057)
    status, out = call(rig, "POST", "/api/processes/start", {"app": "insights"})
    assert status == 200 and out["already"] and out["app"]["managed"] is False
    assert rig.world.spawned == []


def test_stop_kills_only_the_recorded_pid_and_clears_the_record(rig):
    call(rig, "POST", "/api/processes/start", {"app": "insights"})
    pid = rig.world.next_pid
    status, out = call(rig, "POST", "/api/processes/stop", {"app": "insights"})
    assert status == 200 and out["app"]["state"] == "stopped" and rig.world.killed == [pid]
    assert not (rig.root / "local_state" / "admin_processes" / "insights.json").exists()
    assert ("process.stop", "insights", "ok") in audit(rig)


def test_stop_refuses_an_app_the_admin_app_did_not_start(rig):
    rig.world.ports.add(5057)  # up, but no record: the Admin app will not guess a pid
    status, out = call(rig, "POST", "/api/processes/stop", {"app": "insights"})
    assert status == 409 and rig.world.killed == []
    assert ("process.stop", "insights", out["error"]) in audit(rig)


def test_a_stale_record_for_a_dead_pid_reads_as_stopped(rig):
    call(rig, "POST", "/api/processes/start", {"app": "insights"})
    rig.world.pids.clear()
    rig.world.ports.clear()
    assert call(rig, "GET", "/api/processes")[1]["apps"][1]["state"] == "stopped"


@pytest.mark.parametrize("payload", [{}, {"app": "admin"}, {"app": "../main.py"}, {"app": ["planner"]}, {"app": 5, "cmd": "calc.exe"}])
def test_only_the_two_known_app_names_are_accepted(rig, payload):
    for path in ("/api/processes/start", "/api/processes/stop"):
        assert call(rig, "POST", path, payload)[0] == 400
    assert rig.world.spawned == [] and rig.world.killed == [] and audit(rig) == []


@pytest.mark.parametrize("path", ["/api/processes/start", "/api/processes/stop", "/api/sessions/end"])
def test_process_and_session_writes_are_refused_off_loopback(rig, path):
    body = {"app": "planner", "user_id": 1}
    assert call(rig, "POST", path, body, peer="203.0.113.9")[0] == 403
    assert call(rig, "POST", path, body, headers={**HEADERS, "Host": "evil.example"})[0] == 421
    assert call(rig, "POST", path, body, headers={**HEADERS, "X-Forwarded-For": "1.2.3.4"})[0] == 403
    assert call(rig, "POST", path, body, headers={**HEADERS, "Origin": "https://evil.example"})[0] == 403
    assert call(rig, "POST", path, body, headers={"Host": "127.0.0.1:5056"})[0] == 415  # not JSON: a cross-site form
    assert rig.world.spawned == [] and rig.world.killed == [] and audit(rig) == []


def test_live_sessions_list_who_where_and_since_when_and_hide_idle_ones(rig):
    uid = rig.store.add_user("Pat Doe", "pat", "correct horse", insights=True)
    now = 1_000_000.0
    rig.store.register_session("tok-a", uid, "insights", "remote", "203.0.113.5", now=now - 300)
    rig.store.touch_session("tok-a", now - 20)
    rig.store.register_session("tok-old", uid, "insights", "remote", "", now=now - 5000)
    app = create_app(rig.store, clock=lambda: now, settings=SettingsService(rig.root), processes=rig.manager)
    _, out = call(rig, "GET", "/api/sessions", headers={"Host": "127.0.0.1:5056"}, app=app)
    rows = out["sessions"]
    assert len(rows) == 1
    assert rows[0]["person"] == "Pat Doe" and rows[0]["app_label"] == "Financial Insights" and rows[0]["where"] == "remote"
    assert rows[0]["source"] == "203.0.113.5" and rows[0]["started_at"] == now - 300 and rows[0]["last_seen"] == now - 20
    assert "tok-a" not in json.dumps(out)


def test_ending_a_session_bumps_the_epoch_clears_the_row_and_is_audited(rig):
    uid = rig.store.add_user("Pat Doe", "pat", "correct horse", insights=True)
    rig.store.register_session("tok-a", uid, "insights", "remote")
    before = rig.store.session_epoch(uid)
    status, _ = call(rig, "POST", "/api/sessions/end", {"user_id": uid})
    assert status == 200 and rig.store.session_epoch(uid) == before + 1
    assert rig.store.list_live_sessions() == []
    assert ("session.end", "pat", ENDED) in audit(rig)
    assert call(rig, "POST", "/api/sessions/end", {"user_id": 999})[0] == 404
    assert call(rig, "POST", "/api/sessions/end", {"user_id": True})[0] == 404
