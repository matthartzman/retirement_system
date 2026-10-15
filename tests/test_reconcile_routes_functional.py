"""R3 of the reconciliation page: the /api/reconcile routes (against a scratch workspace, not the shared test plan)."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src import active_plan
from src import monarch_balances_import as mbi
from src import ytd_tracking as ytd
from src.server import app, plan_routes

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", [
        {"Account": "Family Checking", "Role": "Cash / spending", "Current Balance": "13000"},
        {"Account": "Brokerage A", "Role": "Investment", "Mapped Investment Account": "Brokerage A", "Current Value": "1000"},
    ])
    with active_plan.workspace_store(base, write=True) as store:
        store.set_value("Other Assets", "Home", "value_as_of_plan_start", "1313000")
    path = base / "Monarch Extractor" / "output" / "balances.csv"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(mbi.EXPECTED_HEADER)
        for key, name, bal in (("family checking", "Family Checking", 13894.27), ("brokerage a", "Brokerage A", 105808.52),
                               ("house", "114 Main St", 1279500.0)):
            w.writerow(["2026-10-14", key, name, bal])
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: base / "input")
    return app.test_client()


def _post(client, url, body):
    r = client.post(url, json=body)
    return r.status_code, r.get_json()


def test_get_rows(client):
    r = client.get("/api/reconcile")
    body = r.get_json()
    assert r.status_code == 200 and body["success"] and body["has_balances"] and body["as_of"] == "2026-10-14"
    rows = {x["id"]: x for x in body["rows"]}
    assert rows["setup:Family Checking"]["difference"] == 894.27 and rows["setup:Family Checking"]["updatable"]
    assert rows["setup:Brokerage A"]["status"] == "report_only"
    assert any(u["account_key"] == "house" for u in body["unmatched"])


def test_bad_inputs_are_400s(client):
    assert client.get("/api/reconcile?tolerance=abc").status_code == 400
    assert client.get("/api/reconcile?as_of=10/14/2026").status_code == 400
    assert _post(client, "/api/reconcile/map", {"account_key": "ghost", "target": "plan:home"})[0] == 400
    assert _post(client, "/api/reconcile/undo", {"change_id": "x"})[0] == 400
    assert _post(client, "/api/reconcile/undo", {"change_id": 999})[0] in (400, 404)


def test_map_preview_apply_undo_flow(client):
    assert _post(client, "/api/reconcile/map", {"account_key": "house", "target": "plan:home"})[0] == 200
    status, prev = _post(client, "/api/reconcile/preview", {"items": [{"id": "plan:home"}, {"id": "setup:Family Checking"}, {"id": "setup:Brokerage A"}]})
    assert status == 200 and [c["id"] for c in prev["changes"]] == ["plan:home", "setup:Family Checking"]
    assert prev["rejected"][0]["id"] == "setup:Brokerage A"
    # nothing written by a preview
    assert client.get("/api/reconcile").get_json()["rows"][0]["status"] != "match"
    status, applied = _post(client, "/api/reconcile/apply", {"items": [{"id": c["id"], "expected_new": c["new"]} for c in prev["changes"]]})
    assert status == 200 and len(applied["applied"]) == 2
    rows = {x["id"]: x for x in client.get("/api/reconcile").get_json()["rows"]}
    assert rows["setup:Family Checking"]["status"] == "match" and rows["plan:home"]["status"] == "match"
    log = client.get("/api/reconcile/log").get_json()["log"]
    assert len(log) == 2
    status, out = _post(client, "/api/reconcile/undo", {"change_id": applied["applied"][0]["change_id"]})
    assert status == 200 and out["success"]
    status, again = _post(client, "/api/reconcile/undo", {"change_id": applied["applied"][0]["change_id"]})
    assert status == 400 and "already undone" in again["error"]


def test_apply_with_a_stale_expected_value_writes_nothing(client):
    status, res = _post(client, "/api/reconcile/apply", {"items": [{"id": "setup:Family Checking", "expected_new": "1.00"}]})
    assert status == 200 and res["applied"] == [] and res["rejected"]
    assert client.get("/api/reconcile/log").get_json()["log"] == []


def test_routes_are_in_the_manifest():
    from src.server.route_manifest import ROUTE_MODULES
    assert set(ROUTE_MODULES["reconcile"]) == {"/api/reconcile", "/api/reconcile/map", "/api/reconcile/preview",
                                              "/api/reconcile/apply", "/api/reconcile/undo", "/api/reconcile/log",
                                              "/api/reconcile/policy", "/api/reconcile/undo-auto", "/api/reconcile/seed"}


def test_policy_undo_auto_and_seed_routes(client):
    code, body = _post(client, "/api/reconcile/map", {"account_key": "family checking", "target": "setup:Family Checking"})
    assert code == 200
    assert _post(client, "/api/reconcile/policy", {"account_key": "family checking", "policy": "auto"})[0] == 200
    assert _post(client, "/api/reconcile/policy", {"account_key": "family checking", "policy": "sometimes"})[0] == 400
    assert _post(client, "/api/reconcile/policy", {"account_key": "nope", "policy": "ask"})[0] == 400
    row = {r["id"]: r for r in client.get("/api/reconcile").get_json()["rows"]}["setup:Family Checking"]
    assert row["policy"] == "auto" and row["auto_hold"] is None
    assert _post(client, "/api/reconcile/undo-auto", {})[1]["undone"] == []
    csv_text = ("Monarch,App Location,App Field,Status,Primary Source\n"
                "Brokerage A,Investment Holdings,Brokerage A,Active,App\n"
                "Ghost,Investment Holdings,X,CLOSED,App\n")
    code, body = _post(client, "/api/reconcile/seed", {"csv_text": csv_text})
    assert code == 200 and [r["monarch"] for r in body["seed"]["saved"]] == ["Brokerage A"] and body["seed"]["saved"][0]["policy"] == "app"
    assert [r["monarch"] for r in body["seed"]["not_in_monarch"]] == ["Ghost"]
    assert _post(client, "/api/reconcile/seed", {"csv_text": ""})[0] == 400
