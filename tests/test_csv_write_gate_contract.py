"""PR-07: with the operator's "CSV writes disabled" switch off, every plan-data write route is refused, in one place."""
from __future__ import annotations

import dataclasses

import pytest

from src.server import app, app_core
from src.server import csv_write_gate as gate
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """An isolated workspace: nothing here may touch a real plan."""
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    return plan


class _Off:
    allow_csv_write = False


class _On:
    allow_csv_write = True


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/sales"), ("POST", "/api/sales/batch"), ("POST", "/api/sales/7/void"), ("POST", "/api/sales/wash/refresh"),
    ("POST", "/api/sales/candidates/3/confirm"), ("POST", "/api/sales/candidates/bulk/confirm"),
    ("POST", "/api/sales/1099b/apply"), ("POST", "/api/sales/broker/commit"), ("POST", "/api/transactions"),
    ("POST", "/api/transactions/9/void"), ("POST", "/api/transactions/transfer"), ("POST", "/api/cash/year-close"),
    ("POST", "/api/cash-accounts"), ("POST", "/api/cash-accounts/delete"), ("POST", "/api/year-end/confirm"),
    ("POST", "/api/reconcile/apply"), ("POST", "/api/reconcile/seed"), ("POST", "/api/ytd/transactions"),
    ("PUT", "/api/ytd/transactions/3"), ("DELETE", "/api/ytd/transactions/3"), ("POST", "/api/ytd/account-setup"),
    ("POST", "/api/spending/budget"), ("POST", "/api/spending/category"), ("DELETE", "/api/spending/category/4"),
    ("POST", "/api/spending/rules/save"), ("POST", "/api/housing/seed"), ("POST", "/api/wellness/seed"),
    ("POST", "/api/plans/switch"), ("POST", "/api/plans/delete"), ("POST", "/api/plans/forget"),
    ("POST", "/api/investment-income/symbol-type"),
])
def test_write_routes_are_classified_as_gated(method, path):
    assert gate.is_csv_write_request(method, path)


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/sales"), ("GET", "/api/transactions"), ("GET", "/api/spending/budget"), ("GET", "/api/plans"),
    ("POST", "/api/ytd/transactions/preview"), ("POST", "/api/sales/1099b/preview"), ("POST", "/api/sales/broker/preview"),
    ("POST", "/api/sales/candidates/bulk/review"), ("POST", "/api/sales/candidates/bulk/validate"),
    ("POST", "/api/reconcile/preview"), ("POST", "/api/housing/optimize"), ("POST", "/api/housing/zip-screen"),
    ("POST", "/api/build/start"), ("POST", "/api/plan/save-as"), ("POST", "/api/salesforce"), ("POST", "/api/cashflow"),
])
def test_reads_previews_and_other_areas_are_not_gated(method, path):
    assert not gate.is_csv_write_request(method, path)


def _is_gated_write_route(rule_path: str, methods) -> bool:
    return bool(set(methods) & gate.WRITE_METHODS) and gate.is_csv_write_request("POST", rule_path)


def test_every_registered_route_in_a_gated_area_is_either_gated_or_a_listed_preview():
    """A new write route under a gated prefix is covered automatically; only the explicit preview list escapes."""
    routes = [(r.rule, r.methods) for r in app.url_map.iter_rules()] if hasattr(app, "url_map") else []
    if not routes:  # the facade keeps its own table
        routes = [(rule, methods) for rule, methods, *_ in getattr(app, "routes", [])]
    assert routes, "could not enumerate the app's routes"
    prefixes = gate.GATED_PREFIXES
    for rule, methods in routes:
        stripped = rule.replace("<int:", "<").replace("<path:", "<")
        concrete = stripped.replace("<sale_id>", "1").replace("<candidate_id>", "1").replace("<index>", "1") \
            .replace("<txn_id>", "1").replace("<cat_id>", "1").replace("<import_id>", "1").replace("<account>", "a")
        if any(gate._under(concrete, p) for p in prefixes) and set(methods) & gate.WRITE_METHODS:
            ok = gate.is_csv_write_request(sorted(set(methods) & gate.WRITE_METHODS)[0], concrete)
            assert ok or concrete in gate.READ_ONLY_POSTS, f"{rule} is under a gated prefix but not gated"


def test_the_hook_refuses_gated_writes_when_the_switch_is_off_and_lets_everything_else_through(ws, monkeypatch):
    client = app.test_client()
    real = app_core._runtime_config()  # the rest of the config stays real: the security gate reads it too
    monkeypatch.setattr(app_core, "_runtime_config", lambda: dataclasses.replace(real, allow_csv_write=False))
    for path in ("/api/sales", "/api/transactions", "/api/plans/switch", "/api/housing/seed", "/api/ytd/transactions"):
        r = client.post(path, headers=HEADERS, json={})
        assert r.status_code == 403 and r.get_json() == {"success": False, "error": "CSV writes are disabled"}, path
    assert client.get("/api/transactions", headers=HEADERS).get_json() != {"success": False, "error": "CSV writes are disabled"}  # reads are never gated
    r = client.post("/api/ytd/transactions/preview", headers=HEADERS, json={})
    assert r.get_json() != {"success": False, "error": "CSV writes are disabled"}  # a preview reads; it is not refused
    monkeypatch.setattr(app_core, "_runtime_config", lambda: dataclasses.replace(real, allow_csv_write=True))
    r = client.post("/api/sales", headers=HEADERS, json={})
    assert r.get_json() != {"success": False, "error": "CSV writes are disabled"}


def test_an_unreadable_config_fails_closed():
    def boom():
        raise OSError("config unreadable")
    assert gate.writes_allowed(boom) is False and gate.writes_allowed(lambda: _On()) is True


def test_decorator_form_for_a_single_route():
    calls = []

    @gate.csv_write_gate(lambda: _Off())
    def view():
        calls.append(1)
        return "ran"
    body, status = view()
    assert status == 403 and calls == []

    @gate.csv_write_gate(lambda: _On())
    def view2():
        return "ran"
    assert view2() == "ran"
