"""Remote mode (``RETIREMENT_SYSTEM_REMOTE_MODE=1``): the worker contract the multi-user gateway
relies on (documentation/future/multi-user-server-plan.md, "Remote mode (Phase 1 contract)").

Every check runs in-process against the session workspace with the flag switched on through the
environment (the flag is read per call). A companion off-by-default test pins that desktop mode
is unchanged. The worker process itself (port reporting, provisioning, watchdog, upload into an
empty workspace) is covered by ``test_remote_worker_integration.py``.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from src import platform_runtime, remote_mode
from src.server import app_core, create_app
from src.server import remote_allowlist

TOKEN = "test-worker-token-0123456789"


@pytest.fixture(autouse=True)
def _live_workspace_constant(monkeypatch):
    """``app_core.WORKSPACE_ROOT`` is frozen when ``app_core`` is first imported. A real worker
    pins the workspace before that import; in a shared pytest worker another test may have
    imported it under a different, monkeypatched workspace, and then the resolver (which checks
    the live root) would rightly refuse every path built from the stale constant."""
    from src.server import base_routes, plan_routes, workbook_routes

    live = platform_runtime.workspace_root()
    for module in (app_core, base_routes, plan_routes, workbook_routes):
        monkeypatch.setattr(module, "WORKSPACE_ROOT", live, raising=False)


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    return create_app().test_client()


def _auth(extra: dict | None = None) -> dict:
    headers = {"X-API-Token": TOKEN}
    headers.update(extra or {})
    return headers


def _no_server_paths(text: str) -> None:
    for root in (platform_runtime.workspace_root(), platform_runtime.package_root()):
        for spelling in {str(root), str(root.resolve()), str(root).replace("\\", "/"), str(root).replace("\\", "\\\\")}:
            assert spelling not in text, f"server path {spelling!r} leaked"


# ---------------------------------------------------------------- off by default

def test_remote_mode_is_off_by_default(monkeypatch):
    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    assert not remote_mode.enabled()
    client = create_app().test_client()
    ping = client.get("/api/ping")
    assert ping.status_code == 200
    assert "package_root" in ping.get_json()  # desktop payload unchanged
    assert client.get("/api/config/rows").status_code == 200  # no token needed on loopback
    env = remote_mode.subprocess_env()
    assert env == dict(os.environ)


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("yes", True), ("0", False), ("", False), ("no", False)])
def test_flag_values(monkeypatch, value, expected):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, value)
    assert remote_mode.enabled() is expected


# ---------------------------------------------------------------- item 1: token everywhere

def test_startup_refused_without_token(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.delenv(remote_mode.TOKEN_ENV, raising=False)
    with pytest.raises(remote_mode.RemoteModeError):
        remote_mode.assert_startup_ok()
    monkeypatch.setenv(remote_mode.TOKEN_ENV, "   ")
    with pytest.raises(remote_mode.RemoteModeError):
        remote_mode.assert_startup_ok()
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    remote_mode.assert_startup_ok()


@pytest.mark.parametrize("method,path", [("GET", "/api/ping"), ("OPTIONS", "/api/ping"), ("GET", "/api/config/rows"),
                                         ("GET", "/frontend/index.html"), ("GET", "/api/auth/session"), ("GET", "/no/such/route")])
def test_token_required_on_every_request(remote, method, path):
    resp = remote.open(path, method=method)
    assert resp.status_code == 401
    assert remote.open(path, method=method, headers={"X-API-Token": "wrong"}).status_code == 401


def test_token_accepted_as_header_or_bearer(remote):
    assert remote.get("/api/ping", headers=_auth()).status_code == 200
    assert remote.get("/api/ping", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_stored_token_is_not_an_auth_source(remote, monkeypatch):
    """Remote mode trusts only the token the supervisor put in the environment."""
    monkeypatch.setattr("src.security.get_server_token", lambda: "stored-in-app-db")
    assert remote.get("/api/ping", headers={"X-API-Token": "stored-in-app-db"}).status_code == 401


def test_token_check_runs_even_on_non_loopback_config(remote, monkeypatch):
    class Cfg:
        dashboard_host = "plans.example"

    monkeypatch.setattr(app_core, "_runtime_config", lambda: Cfg())
    assert remote.get("/api/ping", headers={"Host": "plans.example"}).status_code == 401
    assert remote.get("/api/ping", headers=_auth({"Host": "plans.example"})).status_code == 200


# ---------------------------------------------------------------- item 2: deny-by-default allow-list

def _registered_routes() -> set[tuple[str, str]]:
    out = set()
    for rule in create_app().url_map.iter_rules():
        for method in rule.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.add((method, rule.rule))
    return out


def test_every_route_is_classified_exactly_once():
    registered = _registered_routes()
    allowed = set(remote_allowlist.ALLOWED)
    refused = set(remote_allowlist.REFUSED)
    assert not (allowed & refused), sorted(allowed & refused)
    assert allowed | refused == registered, {
        "unclassified": sorted(registered - allowed - refused),
        "stale": sorted((allowed | refused) - registered),
    }


def test_contract_always_refused_routes_are_on_the_refused_list():
    must_refuse = {
        ("POST", "/api/shutdown"), ("POST", "/api/admin/server/shutdown"),
        ("POST", "/api/plan/monarch-autoupdate/config"), ("POST", "/api/plan/monarch-autoupdate/run"),
        ("GET", "/api/conversion/status"), ("POST", "/api/conversion/check"), ("POST", "/api/conversion/run"),
        ("POST", "/api/secrets"),
        ("POST", "/api/plan/save-as"), ("POST", "/api/plan/load-file"), ("POST", "/api/ytd/account-setup/recover"),
        ("POST", "/api/plan/backups/config"), ("GET", "/api/build/events/<job_id>"),
    }
    assert must_refuse <= set(remote_allowlist.REFUSED)
    for key in must_refuse:
        assert remote_allowlist.REFUSED[key], f"{key} needs a reason"


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/shutdown"), ("POST", "/api/admin/server/shutdown"),
    ("POST", "/api/plan/monarch-autoupdate/config"), ("POST", "/api/conversion/run"), ("POST", "/api/secrets"),
    ("POST", "/api/plan/save-as"), ("POST", "/api/plan/load-file"), ("GET", "/api/plan/engine-assumptions"),
])
def test_refused_routes_answer_403_and_do_nothing(remote, method, path):
    resp = remote.open(path, method=method, json={"path": "C:/Windows/evil.rpx"}, headers=_auth())
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False
    assert "not available" in body["error"]


def test_allowed_route_is_served(remote):
    assert remote.get("/api/config/rows", headers=_auth()).status_code == 200


def test_unknown_route_is_404_not_dispatched(remote):
    assert remote.get("/api/no-such-thing", headers=_auth()).status_code == 404


# ---------------------------------------------------------------- item 3: workspace confinement

def test_confine_path_inside_outside_and_escape(monkeypatch, tmp_path):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    root = platform_runtime.workspace_root()
    assert remote_mode.confine_path("saved_plans/x.rpx") == (root / "saved_plans" / "x.rpx").resolve()
    assert remote_mode.confine_path(root / "output") == (root / "output").resolve()
    for bad in (tmp_path / "elsewhere", "../outside.rpx", "saved_plans/../../outside", "C:/Windows/system32"):
        with pytest.raises(remote_mode.PathOutsideWorkspace):
            remote_mode.confine_path(bad, what="test path")


def test_confine_path_is_a_no_op_when_off(monkeypatch, tmp_path):
    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    assert remote_mode.confine_path(tmp_path / "anywhere") == tmp_path / "anywhere"


def test_backup_dir_outside_workspace_is_refused(monkeypatch, tmp_path):
    from src import local_backup_scheduler

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    with pytest.raises(remote_mode.PathOutsideWorkspace):
        local_backup_scheduler.resolve_backup_dir(platform_runtime.workspace_root(), {"backup_dir": str(tmp_path)})
    inside = local_backup_scheduler.resolve_backup_dir(platform_runtime.workspace_root(), {"backup_dir": "saved_plans/auto_backups"})
    assert inside.is_relative_to(platform_runtime.workspace_root().resolve())


def test_monarch_source_dir_outside_workspace_is_refused(monkeypatch, tmp_path):
    from src import monarch_autoupdate

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    with pytest.raises(remote_mode.PathOutsideWorkspace):
        monarch_autoupdate.resolve_source_dir(platform_runtime.workspace_root(), {"source_dir": str(tmp_path)})


def test_sqlite_db_setting_outside_workspace_is_refused(monkeypatch, tmp_path):
    from src.runtime_config import RuntimeConfig

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setattr(app_core, "_runtime_config", lambda: RuntimeConfig(sqlite_db=str(tmp_path / "other.db")))
    with pytest.raises(remote_mode.PathOutsideWorkspace):
        app_core._sqlite_db()


def test_output_dir_setting_outside_workspace_is_refused(monkeypatch, tmp_path):
    from src import workspace_context
    from src.runtime_config import RuntimeConfig

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setattr(workspace_context, "_runtime_cfg", lambda: RuntimeConfig(output_dir=str(tmp_path)))
    with pytest.raises(remote_mode.PathOutsideWorkspace):
        workspace_context.workspace_output_dir()


def test_app_db_env_outside_workspace_is_refused(monkeypatch, tmp_path):
    from src import app_state

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(app_state.APP_DB_ENV, str(tmp_path / "app.db"))
    with pytest.raises(remote_mode.PathOutsideWorkspace):
        app_state.app_store_path()


def test_pinned_environment_wins_over_stored_setting(monkeypatch):
    """The supervisor pins the paths through the environment; a stored setting cannot move them."""
    from src import runtime_config

    monkeypatch.setenv("RETIREMENT_SYSTEM_SQLITE_DB", "local_state/pinned.db")
    monkeypatch.setenv("RETIREMENT_SYSTEM_OUTPUT_DIR", "output")
    data = {"System Configuration": {"Runtime": {"sqlite_db": "C:/elsewhere/x.db", "output_dir": "C:/elsewhere/out"}}}
    monkeypatch.setattr(runtime_config, "load_system_config", lambda _path=None: data)
    cfg = runtime_config.load_runtime_config()
    assert cfg.sqlite_db == "local_state/pinned.db"
    assert cfg.output_dir == "output"


def test_registry_refuses_plan_files_outside_workspace(monkeypatch, tmp_path):
    from src import plan_registry

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    with pytest.raises(plan_registry.PlanRegistryError):
        plan_registry.register_plan_file(tmp_path / "outside.rpx")


def test_registry_refuses_to_activate_a_stored_outside_path(monkeypatch, tmp_path):
    """A record written before remote mode (or by hand) pointing outside cannot be switched to."""
    from src import plan_registry

    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    outside = tmp_path / "outside.rpx"
    rec = plan_registry.register_plan_file(outside, name="outside")
    try:
        monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
        monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
        client = create_app().test_client()
        resp = client.post("/api/plans/switch", json={"plan_id": rec["plan_id"]}, headers=_auth())
        assert resp.status_code == 400
        assert plan_registry.active_record()["plan_id"] != rec["plan_id"]
    finally:
        monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
        plan_registry.forget(rec["plan_id"])


def test_desktop_download_folder_cannot_be_set(remote):
    resp = remote.post("/api/settings/workbook-download", json={"desktop_download_folder": "C:/Users/Public"}, headers=_auth())
    assert resp.status_code == 400


# ---------------------------------------------------------------- item 4: fallbacks and environment

def test_legacy_output_fallback_is_disabled(monkeypatch):
    from src.server import workbook_routes

    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    assert workbook_routes._legacy_output_fallback() is not None
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    assert workbook_routes._legacy_output_fallback() is None


def test_index_does_not_fall_back_to_package_output(remote, monkeypatch):
    from src.server import base_routes

    monkeypatch.setattr(base_routes, "BASE_DIR", Path("Z:/no/such/package"))
    resp = remote.get("/", headers=_auth())
    assert resp.status_code == 404


def test_demo_csv_seed_read_is_disabled(monkeypatch):
    from src.server import plan_routes

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    with pytest.raises(remote_mode.RemoteModeError):
        plan_routes._demo_csv_dir()


def test_subprocess_environment_is_scrubbed(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    monkeypatch.setenv("OWNER_PRIVATE_SETTING", "do-not-pass")
    monkeypatch.setenv("GATEWAY_SESSION_SECRET", "do-not-pass")
    monkeypatch.setenv("RETIREMENT_MC_SIMS", "16")
    env = remote_mode.subprocess_env()
    assert remote_mode.TOKEN_ENV not in env
    assert "OWNER_PRIVATE_SETTING" not in env
    assert "GATEWAY_SESSION_SECRET" not in env
    assert env["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] == os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"]
    assert env["RETIREMENT_MC_SIMS"] == "16"
    for key in ("SYSTEMROOT", "PATH"):
        if key in os.environ:
            assert key in {k.upper() for k in env}


def test_build_routes_use_the_scrubbed_environment(remote, monkeypatch):
    """``/api/build/start`` hands the build thread the scrubbed environment."""
    from src.server import workbook_routes

    seen = {}

    class _Thread:
        def __init__(self, target, args, daemon):
            seen["env"] = args[3]

        def start(self):
            pass

    monkeypatch.setenv("OWNER_PRIVATE_SETTING", "do-not-pass")
    monkeypatch.setattr(workbook_routes.threading, "Thread", _Thread)
    monkeypatch.setattr(workbook_routes, "_build_preflight_payload", lambda: {"blockers": []})
    resp = remote.post("/api/build/start", json={}, headers=_auth())
    assert resp.status_code == 200, resp.get_json()
    assert "OWNER_PRIVATE_SETTING" not in seen["env"]
    assert remote_mode.TOKEN_ENV not in seen["env"]
    assert seen["env"]["RETIREMENT_SYSTEM_PLAN_DB"]


# ---------------------------------------------------------------- item 5: no leaks

def test_unhandled_error_body_is_generic(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    resp, status = app_core._json_unhandled_error(RuntimeError(r"cannot open C:\Users\someone\secret\plan.rpx"))
    body = resp.get_json()
    assert status == 500
    assert "secret" not in json.dumps(body)
    assert "RuntimeError" not in json.dumps(body)
    assert body["error_id"]


def test_unhandled_error_body_unchanged_when_off(monkeypatch):
    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    resp, _status = app_core._json_unhandled_error(RuntimeError("boom"))
    assert resp.get_json()["error"] == "RuntimeError: boom"


def test_facade_fallback_error_body_is_generic(monkeypatch):
    app = create_app()
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    body = app._exception_response(ValueError(r"D:\private\thing")).get_json()
    assert "private" not in json.dumps(body)


def test_ping_has_no_package_root(remote):
    body = remote.get("/api/ping", headers=_auth()).get_json()
    assert "package_root" not in body and "base_dir" not in body
    assert body["running"] is True
    assert body["remote_mode"] is True


@pytest.mark.parametrize("path", ["/api/status", "/api/runtime", "/api/plans", "/api/plan/demo-status", "/api/plan/backups"])
def test_info_routes_leak_no_server_paths(remote, path):
    resp = remote.get(path, headers=_auth())
    assert resp.status_code == 200
    _no_server_paths(resp.get_data(as_text=True))


def test_save_response_leaks_no_server_paths(remote):
    rows = remote.get("/api/config/rows", headers=_auth()).get_json()
    row = next(r for r in rows["rows"] if r.get("label") == "inflation_general")
    update = {"row_index": row.get("row_index", row.get("row_id")), "value": row.get("value", "")}
    resp = remote.post("/api/config/rows", json={"updates": [update]}, headers=_auth())
    assert resp.status_code == 200, resp.get_data(as_text=True)[:500]
    _no_server_paths(resp.get_data(as_text=True))


def test_scrub_rewrites_paths_inside_nested_json(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    root = platform_runtime.workspace_root()
    pkg = platform_runtime.package_root()
    data = {"a": [str(root / "output" / "x.xlsx"), {"b": f"error at {pkg / 'src' / 'y.py'}"}], "n": 3}
    out = remote_mode.scrub(data)
    text = json.dumps(out)
    assert str(root) not in text and str(pkg) not in text
    assert out["n"] == 3
    assert out["a"][0].endswith("x.xlsx")


# ---------------------------------------------------------------- item 6: browser upload and download

def test_plan_download_returns_the_active_plan_file(remote):
    resp = remote.get("/api/plan/download", headers=_auth())
    assert resp.status_code == 200
    assert resp.get_data()[:16] == b"SQLite format 3\x00"
    assert ".rpx" in resp.headers.get("Content-Disposition", "")


@pytest.mark.parametrize("body,expect", [
    ({}, 400),
    ({"content_base64": "%%%not-base64%%%"}, 400),
    ({"content_base64": base64.b64encode(b"not a plan file").decode()}, 400),
    ({"content_base64": base64.b64encode(b"x").decode(), "mode": "sideways"}, 400),
])
def test_plan_upload_rejects_bad_input(remote, body, expect):
    resp = remote.post("/api/plan/upload", json=body, headers=_auth())
    assert resp.status_code == expect
    assert resp.get_json()["success"] is False
    _no_server_paths(resp.get_data(as_text=True))


def test_plan_upload_open_registers_inside_the_workspace(remote):
    from src import plan_registry

    before = plan_registry.active_record()["plan_id"]
    content = remote.get("/api/plan/download", headers=_auth()).get_data()
    resp = remote.post("/api/plan/upload", json={"filename": "../../My Plan.rpx", "content_base64": base64.b64encode(content).decode(),
                                                 "mode": "open"}, headers=_auth())
    body = resp.get_json()
    try:
        assert resp.status_code == 200, body
        assert body["success"] is True
        rec = plan_registry.get_plan(body["plan"]["plan_id"])
        saved = Path(rec["path"]).resolve()
        assert saved.is_relative_to((platform_runtime.workspace_root() / "saved_plans").resolve())
        assert saved.suffix == ".rpx"
        _no_server_paths(resp.get_data(as_text=True))
    finally:
        plan_registry.activate(before)
        if body.get("plan"):
            rec = plan_registry.get_plan(body["plan"]["plan_id"])
            plan_registry.forget(rec["plan_id"])
            Path(rec["path"]).unlink(missing_ok=True)
