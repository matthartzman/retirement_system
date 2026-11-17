"""Financial Insight in worker mode (a user's own planner worker): data location, active plan, view-only, allow-list.

Design: documentation/future/multi-user-insights-design.md. The conftest workspace is the "live" workspace, so
the active plan here is exactly what a worker's pinned workspace gives a user.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from financial_trends_reporter import plan_balance_sync, trends_job, worker_mode
from financial_trends_reporter.main import create_app
from financial_trends_reporter.worker_allowlist import ALLOWED, REFUSED
from src import active_plan, plan_registry, platform_runtime, workspace_context

ROWS = [("2026-11-14", "chk", "Checking", 1000.0), ("2026-11-15", "chk", "Checking", 1100.0),
        ("2026-11-14", "brk", "Brokerage A", 50000.0), ("2026-11-15", "brk", "Brokerage A", 51000.0)]


def _sql(statement: str) -> None:
    with active_plan.workspace_store(platform_runtime.workspace_root(), write=True) as store, store._write() as con:
        con.execute(statement)


def _clear_balances() -> None:
    """The conftest plan is shared by the whole session: leave no Monarch rows behind."""
    _sql("DELETE FROM monarch_balances")
    _sql("DELETE FROM monarch_balance_imports")


@pytest.fixture
def ws():
    root = platform_runtime.workspace_root()
    _clear_balances()
    yield root
    _clear_balances()
    shutil.rmtree(workspace_context.workspace_output_dir() / worker_mode.INSIGHTS_DIRNAME, ignore_errors=True)


@pytest.fixture
def worker(ws, monkeypatch):
    monkeypatch.setattr(worker_mode, "SYNC_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(trends_job, "refresh_prices_in_worker",
                        lambda workspace, **kw: {"refreshed": False, "stale": True, "error": "stubbed"})
    return worker_mode.WorkerListenerApp(create_app(ws, mode="worker"))


def call(app, method, path, body=None):
    raw = json.dumps(body).encode() if body is not None else b""
    resp = app.handle_http(method, path, {"Host": "127.0.0.1:1", "Content-Type": "application/json"}, raw)
    data = resp.get_data()
    try:
        return resp.status_code, json.loads(data)
    except ValueError:
        return resp.status_code, data


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _put_balances(rows):
    with active_plan.workspace_store(platform_runtime.workspace_root(), write=True) as store:
        with store.transaction():
            store.monarch.upsert_balances(rows)
            store.monarch.record_import("2026-11-16T00:00:00", "test", "ok", rows=len(rows),
                                        accounts=len({r[1] for r in rows}), latest_date=max(r[0] for r in rows))


def test_whoami_names_the_listener_and_the_active_plan(worker):
    status, body = call(worker, "GET", "/api/whoami")
    assert status == 200
    assert body["listener"] == "worker" and body["money_view"] == "both"
    assert body["plan"]["id"] == plan_registry.active_plan_id()


def test_routes_outside_the_allow_list_are_refused(worker):
    assert call(worker, "POST", "/api/exit")[0] == 403
    assert call(worker, "POST", "/api/signin", {})[0] == 404
    assert call(worker, "GET", "/api/people")[0] == 404
    assert call(worker, "GET", "/signin")[0] == 404


def test_every_registered_route_is_classified_exactly_once(ws):
    app = create_app(ws, mode="worker")
    registered = {(m, r.rule) for r in app.url_map.iter_rules() for m in r.methods if m not in ("HEAD", "OPTIONS")}
    assert registered == set(ALLOWED) | set(REFUSED), sorted(registered ^ (set(ALLOWED) | set(REFUSED)))
    assert not set(ALLOWED) & set(REFUSED)


def test_stores_sit_in_the_active_plans_folder_and_no_identity_db_is_made(ws, worker):
    identity = ws / "local_state" / "identity.db"
    existed = identity.exists()
    assert call(worker, "GET", "/api/balances")[0] == 200
    folder = workspace_context.workspace_output_dir() / "insights"
    assert (folder / "monarch_balances.sqlite3").is_file()
    assert identity.exists() == existed  # worker mode never opens the people database


def test_balances_follow_the_plans_monarch_rows(worker):
    status, body = call(worker, "GET", "/api/accounts")
    assert status == 200 and body["accounts"] == []
    _put_balances(ROWS)
    status, body = call(worker, "GET", "/api/accounts")
    assert {a["display_name"] for a in body["accounts"]} == {"Checking", "Brokerage A"}
    status, body = call(worker, "GET", "/api/balances")
    assert status == 200 and body["dates"][-1] == "2026-11-15"
    assert call(worker, "POST", "/api/account", {"account_key": "chk", "type": "Cash"})[0] == 200  # a preference survives a re-sync
    _put_balances([("2026-11-16", "chk", "Checking", 1200.0)])
    status, body = call(worker, "GET", "/api/accounts")
    assert {a["account_key"]: a["type"] for a in body["accounts"]}["chk"] == "Cash"


def test_sync_is_idempotent_and_mirrors_removed_accounts(ws, tmp_path):
    db = tmp_path / "insights" / "monarch_balances.sqlite3"
    assert plan_balance_sync.sync(ws, db)["status"] == "no_balances"
    _put_balances(ROWS)
    assert plan_balance_sync.sync(ws, db)["status"] == "ok"
    assert plan_balance_sync.sync(ws, db)["status"] == "unchanged"
    _sql("DELETE FROM monarch_balances WHERE account_key='brk'")
    with active_plan.workspace_store(ws, write=True) as store:
        store.monarch.record_import("2026-11-17T00:00:00", "test", "ok", rows=2, accounts=1, latest_date="2026-11-15")
    assert plan_balance_sync.sync(ws, db)["status"] == "ok"
    from financial_trends_reporter import account_registry
    assert [a["account_key"] for a in account_registry.list_accounts(db)] == ["chk"]


def test_a_full_session_never_changes_the_plan_file(ws, worker):
    plan = active_plan.active_plan_path()
    _put_balances(ROWS)
    before = _sha(plan)
    for path in ("/api/history", "/api/accounts", "/api/balances", "/api/flows", "/api/liquid-change", "/api/live-snapshot",
                 "/api/projections", "/api/realized", "/api/app-accounts", "/api/run-status", "/api/spending?from=2026-01-01&to=2026-11-16"):
        assert call(worker, "GET", path)[0] in (200, 400, 500), path
    status, body = call(worker, "POST", "/api/run-now", {})
    assert status == 200, body
    assert _sha(plan) == before


def test_plan_writes_raise_inside_the_read_only_scope(ws):
    with active_plan.read_only_plan_access():
        with pytest.raises(active_plan.PlanReadOnlyError):
            active_plan.write_workspace_dataset_rows(ws, "holdings", [])
        with pytest.raises(active_plan.PlanReadOnlyError):
            with active_plan.workspace_store(ws, write=True):
                pass
    # and the scope ends with the block
    with active_plan.workspace_store(ws, write=True):
        pass


def test_switching_plans_switches_the_insights_folder(ws, worker):
    first = plan_registry.active_plan_id()
    other = Path(ws) / "saved_plans" / "whatif.rpx"
    other.parent.mkdir(exist_ok=True)
    shutil.copyfile(active_plan.active_plan_path(), other)
    rec = plan_registry.register_plan_file(other, name="What if")
    try:
        call(worker, "GET", "/api/balances")
        plan_registry.activate(rec["plan_id"])
        status, body = call(worker, "GET", "/api/whoami")
        assert body["plan"] == {"id": rec["plan_id"], "name": "What if"}
        call(worker, "GET", "/api/balances")
        folders = sorted(p.name for p in (Path(ws) / "output" / "plans").iterdir() if (p / "insights").is_dir())
        assert {first, rec["plan_id"]} <= set(folders)
    finally:
        plan_registry.activate(first)
        shutil.rmtree(Path(ws) / "output" / "plans" / rec["plan_id"], ignore_errors=True)
        plan_registry.forget(rec["plan_id"])
        other.unlink(missing_ok=True)
