"""The Financial Insight allow-list still holds through the /insights mount (real FI app, real mount)."""
from __future__ import annotations

import json
import shutil

import pytest

from financial_trends_reporter import worker_mode
from financial_trends_reporter.main import create_app
from financial_trends_reporter.worker_allowlist import REFUSED
from src import platform_runtime, remote_mode, workspace_context
from src.remote_insights_mount import PrefixMount

TOKEN = "t0ken-for-allowlist-tests"
HEADERS = {"Host": "127.0.0.1:5000", remote_mode.TOKEN_HEADER: TOKEN, "Content-Type": "application/json"}


class _Planner:
    def handle_http(self, *args, **kwargs):  # pragma: no cover - never reached for /insights
        raise AssertionError("planner reached")


@pytest.fixture
def mount(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    fi = worker_mode.WorkerListenerApp(create_app(platform_runtime.workspace_root(), mode="worker"))
    yield PrefixMount(_Planner(), fi)
    shutil.rmtree(workspace_context.workspace_output_dir() / worker_mode.INSIGHTS_DIRNAME, ignore_errors=True)


@pytest.mark.parametrize("path", ["/api/exit", "/api/signin", "/api/people", "/api/activity", "/api/change-password"])
def test_refused_or_unknown_routes_stay_refused(mount, path):
    for method in ("GET", "POST"):
        resp = mount.handle_http(method, "/insights" + path, dict(HEADERS), b"{}")
        assert resp.status_code in (403, 404, 405), (method, path, resp.status_code)
        assert resp.status_code != 200


def test_refused_list_is_not_reachable_through_the_mount(mount):
    for method, rule in sorted(REFUSED):
        path = "/insights" + rule.replace("<", "x").replace(">", "")
        resp = mount.handle_http(method, path, dict(HEADERS), b"{}")
        assert resp.status_code in (403, 404, 405), (method, rule, resp.status_code)


def test_options_is_refused(mount):
    assert mount.handle_http("OPTIONS", "/insights/api/history", dict(HEADERS), b"").status_code in (403, 404, 405)


def test_allowed_route_answers_json(mount):
    resp = mount.handle_http("GET", "/insights/api/whoami", dict(HEADERS), b"")
    assert resp.status_code == 200 and json.loads(resp.get_data())["listener"] == "worker"
