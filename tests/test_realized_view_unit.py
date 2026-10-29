"""Sales ledger 4.3: the Realized view payload (pure ``realized_view.build``) and its route."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date

import pytest

from financial_trends_reporter import realized_view as rv
from financial_trends_reporter.main import create_app

TODAY = date(2026, 10, 27)


def _sale(sid, day, symbol, account, tax, proceeds, basis, term, bought, **over):
    return {"sale_id": sid, "sale_date": day, "account": account, "tax_class": tax, "symbol": symbol, "shares": 10.0, "proceeds": proceeds,
            "basis": basis, "gain": proceeds - basis, "holding_period": term, "purchase_date": bought, "source": "manual",
            "wash_flag": "none", "status": "confirmed", "official_gain": None, "official_proceeds": None, **over}


SALES = [
    _sale(1, "2026-03-10", "ITOT", "Member_1_Trust", "taxable", 5500.0, 4000.0, "long", "2025-01-01"),                      # +1500 LT
    _sale(2, "2026-06-05", "AVUV", "Member_1_Trust", "taxable", 2000.0, 2600.0, "short", "2026-02-01", wash_flag="possible"),  # -600 ST
    _sale(3, "2026-08-01", "IXUS", "Member_1_IRA", "pre_tax", 1000.0, 800.0, "long", "2024-01-01"),                           # +200 LT
    _sale(4, "2025-12-15", "ITOT", "Member_1_Trust", "taxable", 900.0, 800.0, "long", "2024-01-01"),                          # last year
    _sale(5, "2026-04-01", "ITOT", "Member_1_Trust", "taxable", 9999.0, 1.0, "long", "2024-01-01", status="voided"),
]
LOTS = [
    {"account": "Member_1_Trust", "symbol": "ITOT", "shares": "6", "purchase_date": "2024-01-10", "purchase_price": "100"},
    {"account": "Member_1_Trust", "symbol": "ITOT", "shares": "20", "purchase_date": "2026-02-01", "purchase_price": "120"},
]
CANDIDATES = [
    {"candidate_id": 1, "source": "monarch", "sale_date": "2026-09-30", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 10.0, "price": None, "amount": 1300.0},
    {"candidate_id": 2, "source": "holdings_diff", "sale_date": "2026-09-01", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 1.0, "price": None, "amount": None},
    {"candidate_id": 3, "source": "monarch", "sale_date": "2026-05-01", "account": "Member_1_Trust", "symbol": None, "shares": None, "price": None, "amount": 500.0},
    {"candidate_id": 4, "source": "monarch", "sale_date": "2025-11-01", "account": "Member_1_Trust", "symbol": "ITOT", "shares": 1.0, "price": None, "amount": 100.0},
]


def _build(**kw):
    return rv.build(sales=SALES, candidates=CANDIDATES, lots=LOTS, today=TODAY, start="2026-01-01", **kw)


def test_summary_is_confirmed_sales_in_the_window_only():
    s = _build()["summary"]                   # sales 1-3 (4 is last year, 5 is voided)
    assert (s["count"], s["proceeds"], s["basis"]) == (3, 8500.0, 7400.0)
    assert (s["st_gain"], s["lt_gain"], s["net"]) == (-600.0, 1700.0, 1100.0)
    assert s["wash_flagged"] == -600.0


def test_scope_start_and_tax_year_set_the_window():
    assert _build()["summary"]["count"] == 3
    assert rv.build(sales=SALES, candidates=[], lots=[], today=TODAY, start="2026-08-01")["summary"]["count"] == 1
    y = rv.build(sales=SALES, candidates=[], lots=[], today=TODAY, start="2026-01-01", tax_year=2025)
    assert y["window"] == {"from": "2025-01-01", "to": "2025-12-31", "tax_year": 2025} and y["summary"]["net"] == 100.0
    assert 2025 in y["years"] and 2026 in y["years"]


def test_filters_taxable_only_and_wash_only():
    t = _build(taxable_only=True)["summary"]
    assert (t["count"], t["lt_gain"], t["net"], t["proceeds"]) == (2, 1500.0, 900.0, 7500.0)
    w = _build(wash_only=True)["summary"]
    assert (w["count"], w["net"]) == (1, -600.0)


def test_groups_by_symbol_or_account_with_their_lots():
    by_symbol = {g["name"]: g for g in _build()["groups"]}
    assert set(by_symbol) == {"AVUV", "IXUS", "ITOT"} and by_symbol["ITOT"]["net"] == 1500.0
    assert [l["sale_id"] for l in by_symbol["ITOT"]["lots"]] == [1]
    by_account = {g["name"]: g for g in _build(group="account")["groups"]}
    assert by_account["Member_1_Trust"]["count"] == 2 and by_account["Member_1_IRA"]["net"] == 200.0
    assert _build(group="nonsense")["group_by"] == "symbol"


def test_1099b_status_per_lot():
    official = [dict(SALES[0], official_gain=1500.0), dict(SALES[1], official_gain=-550.0), SALES[2]]
    out = rv.build(sales=official, candidates=[], lots=[], today=TODAY, start="2026-01-01")
    status = {l["sale_id"]: l["status_1099"] for g in out["groups"] for l in g["lots"]}
    assert status == {1: "matches", 2: "differs", 3: "none"}


def test_unconfirmed_sales_are_counted_and_not_estimated_by_default():
    out = _build()
    assert out["unconfirmed"] == {"count": 3, "not_estimated": None} and out["estimate"] is None
    assert out["summary"]["net"] == 1100.0


def test_estimate_values_a_waiting_monarch_sale_first_in_first_out():
    out = _build(include_unconfirmed=True)
    est = out["estimate"]
    # 10 shares for 1300 (130 each): 6 from the 2024 lot (basis 600, long) and 4 from the 2026 lot (basis 480, short).
    assert (est["count"], est["proceeds"], est["basis"]) == (2, 1300.0, 1080.0)
    assert (est["lt_gain"], est["st_gain"], est["net"]) == (180.0, 40.0, 220.0)
    assert all(l["estimate"] for g in est["groups"] for l in g["lots"])
    assert out["unconfirmed"] == {"count": 3, "not_estimated": 2}          # the holdings event and the bare Monarch row
    assert out["summary"]["net"] == 1100.0                                 # confirmed totals do not move
    assert [l["sale_date"] for g in est["groups"] for l in g["lots"]] == ["2026-09-29", "2026-09-29"]   # prior business day


def test_estimate_with_too_few_lots_leaves_the_rest_without_a_basis():
    out = rv.build(sales=[], candidates=CANDIDATES[:1], lots=LOTS[:1], today=TODAY, start="2026-01-01", include_unconfirmed=True)
    est = out["estimate"]
    assert est["count"] == 2 and est["basis_missing"] == 1 and est["proceeds"] == 1300.0
    assert est["net"] == 180.0                                             # only the slice with a basis has a gain


@contextmanager
def _fake_store(sales, candidates, lots):
    class Sales:
        list_sales = staticmethod(lambda: sales)
        list_candidates = staticmethod(lambda state=None: candidates)

    class Store:
        sales = Sales()
        dataset = staticmethod(lambda name: type("D", (), {"rows": staticmethod(lambda: lots)}))
    yield Store()


def test_load_reads_the_plan_and_survives_a_broken_one(tmp_path, monkeypatch):
    from src import active_plan

    monkeypatch.setattr(active_plan, "workspace_store", lambda root, **k: _fake_store(SALES, CANDIDATES, LOTS))
    assert rv.load(tmp_path) == {"sales": SALES, "candidates": CANDIDATES, "lots": LOTS}

    def broken(root, **k):
        raise OSError("locked")

    monkeypatch.setattr(active_plan, "workspace_store", broken)
    assert rv.load(tmp_path) == {"sales": [], "candidates": [], "lots": []}


def test_route_passes_the_query_to_build(tmp_path, monkeypatch):
    (tmp_path / "workspace" / "input").mkdir(parents=True)
    seen = {}
    monkeypatch.setattr(rv, "load", lambda base: {"sales": SALES, "candidates": CANDIDATES, "lots": LOTS})
    monkeypatch.setattr("financial_trends_reporter.main._today", lambda: TODAY)
    client = create_app(tmp_path / "workspace", log_path=tmp_path / "log.jsonl").test_client()
    body = client.get("/api/realized?from=2026-01-01&group=account&taxable=1&unconfirmed=1").get_json()
    assert body["group_by"] == "account" and body["filters"] == {"taxable_only": True, "wash_only": False, "include_unconfirmed": True}
    assert body["summary"]["net"] == 900.0 and body["estimate"]["count"] == 2
    assert client.get("/api/realized?tax_year=abc").status_code == 400
    assert client.get("/api/realized?tax_year=2025").get_json()["summary"]["net"] == 100.0


def test_percent_only_people_get_group_totals_without_lots(tmp_path, monkeypatch):
    from tests.test_trends_percent_view_functional import _rig

    monkeypatch.setattr(rv, "load", lambda base: {"sales": SALES, "candidates": CANDIDATES, "lots": LOTS})
    monkeypatch.setattr("financial_trends_reporter.main._today", lambda: TODAY)
    rig, t = _rig(tmp_path, basis=lambda: 100000.0, users=(("ann", "percent"), ("dee", "dollars")))
    ann = rig.call(rig.remote, "GET", "/api/realized?from=2026-01-01&unconfirmed=1", cookie=t["ann"])
    assert ann.status_code == 200
    body = ann.get_json()
    assert body["money_view"]["mode"] == "percent" and body["groups"] and "lots" not in str(body) and "shares" not in str(body)
    assert body["summary"]["net"] == 1100.0 / 100000.0 and body["summary"]["count"] == 3
    dee = rig.call(rig.remote, "GET", "/api/realized?from=2026-01-01", cookie=t["dee"]).get_json()
    assert dee["summary"]["net"] == 1100.0 and dee["groups"][0]["lots"]
