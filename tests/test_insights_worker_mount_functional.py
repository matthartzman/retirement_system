"""The /insights mount in a remote worker: token, Host, Origin, prefix stripping, redirect, flag, scrub, errors.

Design: documentation/future/multi-user-insights-design.md (4.3, 5, 8). The FI app is the real one in worker mode
(conftest workspace); the planner and failure cases use small stubs that record what reached them.
"""
from __future__ import annotations

import json
import shutil

import pytest

from financial_trends_reporter import worker_mode
from financial_trends_reporter.main import create_app
from src import platform_runtime, remote_insights_mount, remote_mode, remote_worker, workspace_context
from src.http_runtime.wsgi_facade import Response
from src.remote_insights_mount import PrefixMount

TOKEN = "t0ken-for-mount-tests"
GOOD = {"Host": "127.0.0.1:5000", remote_mode.TOKEN_HEADER: TOKEN}


class Recorder:
    """Stands in for an app: records what it was asked, answers with a canned response."""

    def __init__(self, name, response=None, error=None):
        self.name, self.response, self.error, self.calls = name, response, error, []

    def handle_http(self, method, target, headers=None, body=b"", remote_addr="127.0.0.1"):
        self.calls.append((method, target))
        if self.error:
            raise self.error
        return self.response or Response(json.dumps({"who": self.name}), content_type="application/json")


@pytest.fixture(autouse=True)
def worker_env(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)


@pytest.fixture
def stubs():
    planner, fi = Recorder("planner"), Recorder("insights")
    return planner, fi, PrefixMount(planner, fi)


def call(app, method, target, headers=None, body=None):
    raw = json.dumps(body).encode() if body is not None else b""
    resp = app.handle_http(method, target, headers if headers is not None else dict(GOOD), raw)
    data = resp.get_data()
    try:
        return resp.status_code, json.loads(data)
    except ValueError:
        return resp.status_code, data


def test_prefix_is_stripped_and_planner_paths_are_untouched(stubs):
    planner, fi, mount = stubs
    assert call(mount, "GET", "/insights/api/history?x=1") == (200, {"who": "insights"})
    assert fi.calls == [("GET", "/api/history?x=1")]
    assert call(mount, "GET", "/api/history") == (200, {"who": "planner"})
    assert call(mount, "GET", "/insightsfoo/api") == (200, {"who": "planner"})
    assert planner.calls == [("GET", "/api/history"), ("GET", "/insightsfoo/api")]
    assert len(fi.calls) == 1


def test_planner_paths_get_no_mount_checks(stubs):
    planner, _fi, mount = stubs
    status, _ = call(mount, "GET", "/api/ping", headers={})  # the planner app's own gate decides
    assert status == 200 and planner.calls == [("GET", "/api/ping")]


@pytest.mark.parametrize("headers", [
    {"Host": "127.0.0.1:5000"},
    {"Host": "127.0.0.1:5000", remote_mode.TOKEN_HEADER: "wrong"},
    {"Host": "127.0.0.1:5000", remote_mode.TOKEN_HEADER: ""},
])
def test_missing_or_wrong_token_is_401_before_fi_runs(stubs, headers):
    _planner, fi, mount = stubs
    for target in ("/insights/", "/insights/api/ping", "/insights", "/insights/api/history"):
        assert call(mount, "GET", target, headers=headers)[0] == 401
    assert fi.calls == []


def test_bearer_token_is_accepted(stubs):
    _planner, fi, mount = stubs
    status, _ = call(mount, "GET", "/insights/api/history", headers={"Host": "localhost", "Authorization": f"Bearer {TOKEN}"})
    assert status == 200 and len(fi.calls) == 1


def test_no_worker_token_configured_refuses_everything(stubs, monkeypatch):
    _planner, fi, mount = stubs
    monkeypatch.delenv(remote_mode.TOKEN_ENV)
    assert call(mount, "GET", "/insights/", headers={"Host": "127.0.0.1"})[0] == 401
    assert call(mount, "GET", "/insights/", headers={"Host": "127.0.0.1", remote_mode.TOKEN_HEADER: ""})[0] == 401
    assert fi.calls == []


@pytest.mark.parametrize("host", ["evil.example.com", "evil.example.com:80", "", "10.0.0.5:5000"])
def test_non_loopback_host_is_refused(stubs, host):
    _planner, fi, mount = stubs
    assert call(mount, "GET", "/insights/api/history", headers={"Host": host, remote_mode.TOKEN_HEADER: TOKEN})[0] == 403
    assert fi.calls == []


@pytest.mark.parametrize("header", ["Origin", "Referer"])
def test_cross_origin_is_refused_but_same_origin_passes(stubs, header):
    _planner, fi, mount = stubs
    bad = {**GOOD, header: "https://evil.example.com/page"}
    assert call(mount, "POST", "/insights/api/run-now", headers=bad)[0] == 403
    assert fi.calls == []
    ok = {**GOOD, header: "http://127.0.0.1:5000/insights/"}
    assert call(mount, "POST", "/insights/api/run-now", headers=ok)[0] == 200


def test_slashless_insights_redirects_to_slash_after_the_token_check(stubs):
    _planner, fi, mount = stubs
    resp = mount.handle_http("GET", "/insights?view=trends", dict(GOOD), b"")
    assert resp.status_code == 302 and resp.headers["Location"] == "/insights/?view=trends"
    assert fi.calls == []
    assert call(mount, "GET", "/insights", headers={"Host": "127.0.0.1"})[0] == 401


def test_json_paths_are_scrubbed(stubs, monkeypatch):
    _planner, fi, mount = stubs
    root = str(platform_runtime.workspace_root())
    fi.response = Response(json.dumps({"path": root + "\\output\\x.json", "n": 1}), content_type="application/json")
    status, body = call(mount, "GET", "/insights/api/history")
    assert status == 200 and root not in json.dumps(body) and body["n"] == 1


def test_error_text_never_leaves_the_worker(stubs):
    _planner, fi, mount = stubs
    fi.error = RuntimeError("secret C:/Users/other/plan.db failed")
    status, body = call(mount, "GET", "/insights/api/history")
    assert status == 500 and body["error"] == remote_mode.GENERIC_ERROR and "secret" not in json.dumps(body)
    fi.error = None
    fi.response = Response(json.dumps({"success": False, "error": "OperationalError: no such table x"}), status=500,
                           content_type="application/json")
    status, body = call(mount, "GET", "/insights/api/history")
    assert status == 500 and body["error"] == remote_mode.GENERIC_ERROR


def test_flag_off_leaves_insights_a_planner_404(monkeypatch):
    monkeypatch.delenv(remote_insights_mount.INSIGHTS_ENV, raising=False)
    planner = Recorder("planner")
    assert remote_worker.build_app(platform_runtime.workspace_root(), planner) is planner
    monkeypatch.setenv(remote_insights_mount.INSIGHTS_ENV, "0")
    assert remote_worker.build_app(platform_runtime.workspace_root(), planner) is planner


def test_flag_on_mounts_the_real_app(monkeypatch):
    monkeypatch.setenv(remote_insights_mount.INSIGHTS_ENV, "1")
    planner = Recorder("planner")
    root = platform_runtime.workspace_root()
    try:
        app = remote_worker.build_app(root, planner)
        assert isinstance(app, PrefixMount)
        status, body = call(app, "GET", "/insights/api/whoami")
        assert status == 200 and body["listener"] == "worker"
        assert call(app, "GET", "/api/anything") == (200, {"who": "planner"})
    finally:
        shutil.rmtree(workspace_context.workspace_output_dir() / worker_mode.INSIGHTS_DIRNAME, ignore_errors=True)


def test_the_flag_is_not_forwarded_or_forbidden_by_the_supervisor():
    from src.gateway.supervisor import FORBIDDEN_ENV

    assert remote_insights_mount.INSIGHTS_ENV not in FORBIDDEN_ENV
    assert create_app  # the FI factory stays importable for the mount
