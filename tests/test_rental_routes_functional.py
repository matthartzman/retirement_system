"""WP12.6: the Rental Properties routes (``/api/rental/*``) over ``store.rental``.

Reads and writes go through ``RentalRepo``; a write keeps only known keys, is validated by
``parse_rental_properties`` (a bad property is refused and nothing is written), and the page's
estimate (summary, warnings, table) comes from the projection's own rental stage.
"""
from __future__ import annotations

import copy

import pytest

from src import module_catalog as mc
from src.api_contracts import validate_payload
from src.server import app, plan_routes
from tests import rental_fixtures as rf
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
KEY = "rental_property_income"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    for var in ("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
                "RETIREMENT_SYSTEM_FORCE_ALL_MODULES"):
        monkeypatch.delenv(var, raising=False)
    return plan


@pytest.fixture
def client(ws):
    return app.test_client()


@pytest.fixture
def events(monkeypatch):
    out: list = []
    monkeypatch.setattr(plan_routes, "_audit", lambda event, details=None: out.append((event, details)))
    return out


def _post(client, path, body):
    resp = client.post(path, headers=HEADERS, json=body)
    return resp.status_code, resp.get_json()


def _list(client, query=""):
    resp = client.get("/api/rental/properties" + query, headers=HEADERS)
    assert resp.status_code == 200
    return resp.get_json()


def _save(client, prop, **extra):
    return _post(client, "/api/rental/property", {"property": copy.deepcopy(prop), **extra})


def _stored(ws):
    with ws.store(readonly=True) as s:
        return s.rental.properties()


def _feature(client, on):
    assert _post(client, "/api/plan/feature", {"key": KEY, "on": on})[0] == 200


def test_empty_list_is_off_and_carries_field_tiers_and_limits(client):
    out = _list(client)
    assert out["success"] and out["enabled"] is False and out["count"] == 0 and out["properties"] == []
    assert out["max_properties"] == 20 and out["summary"] is None and out["warnings"] == []
    assert validate_payload("GET", "/api/rental/properties", out) == []
    tiers = out["field_tiers"]
    # owner decision 2026-10-13: active participation is a Standard-page field (advanced = the
    # feature's own tier), the approved mockup's Expert fields are tagged expert
    assert tiers["property"]["active_participation"] == "advanced"
    assert tiers["property"]["monthly_rent"] == "advanced"
    for key in ("property_tax_growth", "loan_term_years", "placed_in_service_year", "prior_suspended_loss"):
        assert tiers["property"][key] == "expert"
    assert tiers["improvement"]["amount"] == "expert" and tiers["override"]["gross_rent"] == "expert"


def test_save_adds_updates_and_keeps_order(ws, client, events):
    status, out = _save(client, rf.PROFITABLE)
    assert status == 200 and out["success"] and out["count"] == 1
    assert validate_payload("POST", "/api/rental/property", out) == []
    assert _save(client, rf.LOSS_MAKING)[0] == 200
    assert [p["name"] for p in _stored(ws)] == ["Duplex", "Condo"]
    # a replace keeps the property's place; a rename goes through original_name
    renamed = dict(rf.PROFITABLE, name="Maple duplex", monthly_rent=2600)
    status, out = _save(client, renamed, original_name="Duplex")
    assert status == 200
    rows = _stored(ws)
    assert [p["name"] for p in rows] == ["Maple duplex", "Condo"] and rows[0]["monthly_rent"] == 2600
    assert [e for e, _ in events].count("rental_property_saved") == 3


def test_unknown_keys_are_dropped_not_stored(ws, client):
    prop = dict(rf.PROFITABLE, bogus="x", improvements=[{"year": 2028, "amount": 5000, "zzz": 1}],
                overrides=[{"year": 2030, "gross_rent": 20000, "qqq": 2}])
    status, out = _save(client, prop)
    assert status == 200 and "bogus" not in out["property"]
    stored = _stored(ws)[0]
    assert "bogus" not in stored
    assert stored["improvements"] == [{"year": 2028, "amount": 5000.0}]
    assert stored["overrides"] == [{"year": 2030, "gross_rent": 20000.0}]


def test_bad_property_is_refused_with_the_parsers_message_and_nothing_written(ws, client, events):
    _save(client, rf.PROFITABLE)
    before = _stored(ws)
    events.clear()
    bad = dict(rf.PROFITABLE, name="Broken", purchase_price=None)
    status, out = _save(client, bad)
    assert status == 400 and not out["success"] and "purchase_price is required" in out["error"]
    status, out = _save(client, dict(rf.PROFITABLE, name="Neg", vacancy_rate=2))
    assert status == 400 and "vacancy_rate" in out["error"]
    status, out = _save(client, dict(rf.PROFITABLE, name="  "))
    assert status == 400 and "name is required" in out["error"]
    status, out = _post(client, "/api/rental/property", {"property": "nope"})
    assert status == 400
    assert _stored(ws) == before and events == []


def test_only_one_converted_home_and_twenty_properties(ws, client):
    assert _save(client, rf.CONVERTED_HOME)[0] == 200
    status, out = _save(client, dict(rf.CONVERTED_HOME, name="Second home"))
    assert status == 400 and "Only one property can be the converted home" in out["error"]
    for i in range(19):
        assert _save(client, dict(rf.PROFITABLE, name=f"P{i}"))[0] == 200
    status, out = _save(client, dict(rf.PROFITABLE, name="One too many"))
    assert status == 400 and "At most 20" in out["error"]
    assert len(_stored(ws)) == 20


def test_duplicate_names_differ_ignoring_case(ws, client):
    _save(client, rf.PROFITABLE)
    status, out = _save(client, dict(rf.PROFITABLE, name="duplex"), original_name="Nobody")
    assert status == 400 and "named 'Duplex'" in out["error"].replace('"', "'") or "names must differ" in out["error"]
    assert len(_stored(ws)) == 1


def test_get_one_and_unknown_is_404(client):
    _save(client, rf.PROFITABLE)
    ok = client.get("/api/rental/property?name=duplex", headers=HEADERS)
    assert ok.status_code == 200 and ok.get_json()["property"]["name"] == "Duplex"
    assert client.get("/api/rental/property?name=Nope", headers=HEADERS).status_code == 404


def test_duplicate_copies_with_children_and_refuses_the_converted_home(ws, client, events):
    _save(client, dict(rf.PROFITABLE, overrides=[{"year": 2030, "gross_rent": 1000}]))
    status, out = _post(client, "/api/rental/property/duplicate", {"name": "Duplex"})
    assert status == 200 and out["property"]["name"] == "Duplex (copy)"
    status, out = _post(client, "/api/rental/property/duplicate", {"name": "Duplex"})
    assert out["property"]["name"] == "Duplex (copy 2)"
    rows = _stored(ws)
    assert [p["name"] for p in rows] == ["Duplex", "Duplex (copy 2)", "Duplex (copy)"]
    assert rows[1]["improvements"] == rows[0]["improvements"] and rows[1]["overrides"] == rows[0]["overrides"]
    assert any(e == "rental_property_duplicated" for e, _ in events)
    _save(client, rf.CONVERTED_HOME)
    status, out = _post(client, "/api/rental/property/duplicate", {"name": "Our house"})
    assert status == 400 and "cannot be duplicated" in out["error"]
    assert _post(client, "/api/rental/property/duplicate", {"name": "Nope"})[0] == 404


def test_delete_removes_with_children_and_unknown_is_404(ws, client):
    _save(client, rf.PROFITABLE)
    _save(client, rf.LOSS_MAKING)
    status, out = _post(client, "/api/rental/property/delete", {"name": "duplex"})
    assert status == 200 and out["count"] == 1
    assert [p["name"] for p in _stored(ws)] == ["Condo"]
    assert _post(client, "/api/rental/property/delete", {"name": "Duplex"})[0] == 404
    with ws.store(readonly=True) as s, s._read() as con:  # cascade: no orphan children
        assert con.execute("SELECT COUNT(*) FROM rental_improvements").fetchone()[0] == 0


def test_improvements_and_overrides_replace_one_propertys_lists(ws, client):
    _save(client, rf.PROFITABLE)
    status, out = _post(client, "/api/rental/improvements",
                        {"name": "Duplex", "improvements": [{"year": 2030, "month": 5, "amount": 9000, "description": "roof", "x": 1}]})
    assert status == 200 and out["improvements"] == [{"year": 2030, "month": 5, "amount": 9000, "description": "roof"}]
    assert _stored(ws)[0]["improvements"][0]["amount"] == 9000.0
    status, out = _post(client, "/api/rental/overrides",
                        {"name": "duplex", "overrides": [{"year": 2031, "gross_rent": 33000}, {"year": 2029, "operating_expenses": 9000}]})
    assert status == 200 and [o["year"] for o in _stored(ws)[0]["overrides"]] == [2029, 2031]
    # validation: an improvement without an amount, two overrides for one year, unknown property
    status, out = _post(client, "/api/rental/improvements", {"name": "Duplex", "improvements": [{"year": 2030}]})
    assert status == 400 and "year and amount are required" in out["error"]
    status, out = _post(client, "/api/rental/overrides", {"name": "Duplex", "overrides": [{"year": 2031}, {"year": 2031}]})
    assert status == 400
    assert _post(client, "/api/rental/overrides", {"name": "Nope", "overrides": []})[0] == 404
    assert _post(client, "/api/rental/improvements", {"name": "Duplex", "improvements": "x"})[0] == 400
    assert len(_stored(ws)[0]["improvements"]) == 1 and len(_stored(ws)[0]["overrides"]) == 2
    assert _post(client, "/api/rental/improvements", {"name": "Duplex", "improvements": []})[0] == 200
    assert _stored(ws)[0]["improvements"] == []


def test_off_keeps_data_and_still_lists_an_estimate_for_the_preview(ws, client):
    _save(client, rf.PROFITABLE)
    _save(client, rf.LOSS_MAKING)
    out = _list(client)
    assert out["enabled"] is False and out["count"] == 2
    assert out["estimate"]["available"] and out["summary"]["year"] == out["estimate"]["years"]["first"]
    assert [t["name"] for t in out["table"]] == ["Duplex", "Condo"]
    _feature(client, True)
    assert _list(client)["enabled"] is True
    _feature(client, False)
    assert _list(client)["count"] == 2 and [p["name"] for p in _stored(ws)] == ["Duplex", "Condo"]


def test_table_net_yield_is_rent_minus_operating_expenses_over_value(client):
    _save(client, rf.PROFITABLE)
    row = _list(client)["table"][0]
    rent = 2500 * 12
    opex = 5000 + 1500 + 0.08 * rent * (1 - 0.05)
    assert row["value"] == 450000 and row["annual_rent"] == rent
    assert row["net_yield"] == pytest.approx((rent - opex) / 450000)


def test_summary_is_selectable_by_year_and_matches_the_rental_stage(ws, client):
    _save(client, rf.PROFITABLE)
    first = _list(client)["summary"]
    later = _list(client, "?year=2030")["summary"]
    assert later["year"] == 2030 and first["year"] == _list(client)["estimate"]["years"]["first"]
    # the same numbers the engine's rental stage gives for the same inputs
    from src.projection_stages.rental_property import RentalBook, net_cash_flow, parse_rental_spec
    from src.data_io import parse_client, parse_rental_properties
    c = parse_client(ws.store_data(), "", skip_live_pricing=True)
    props = parse_rental_properties(c, _stored(ws))
    specs = tuple(parse_rental_spec(p, i, c) for i, p in enumerate(props))
    book = RentalBook(specs=specs, plan_start=int(c["plan_start"]))
    for y in range(int(c["plan_start"]), 2031):
        ry = book.year_flows(y)
        book.settle_passive(ry, 0.0, c["filing_status"])
    assert later["net_cash_flow"] == pytest.approx(net_cash_flow(ry))


def test_passive_loss_warning_uses_the_assumed_magi(client):
    _save(client, rf.LOSS_MAKING)
    low = _list(client, "?magi=0")
    high = _list(client, "?magi=150000")
    assert low["estimate"]["magi"] == 0 and high["estimate"]["magi"] == 150000
    warn = [w for w in high["warnings"] if w["kind"] == "passive_limit"]
    assert len(warn) == 1 and warn[0]["level"] == "warn" and "suspended" in warn[0]["text"]
    assert "assumed other income $150,000" in warn[0]["text"] and warn[0]["detail"]
    assert high["summary"]["suspended_loss"] > low["summary"]["suspended_loss"]


def test_double_count_with_other_assets_by_name_or_value_within_5_percent(ws, client):
    _save(client, rf.PROFITABLE)  # value 450,000
    assert _list(client)["warnings"] == []
    with ws.store() as s:
        for k, v in (("type", "Real Estate"), ("name", "duplex"), ("value", "300000")):
            s.set_value("Other Assets", "Other Asset 1", k, v)
        for k, v in (("type", "Real Estate"), ("name", "Lake lot"), ("value", "440000")):
            s.set_value("Other Assets", "Other Asset 2", k, v)
        for k, v in (("type", "Real Estate"), ("name", "Far away"), ("value", "300000")):
            s.set_value("Other Assets", "Other Asset 3", k, v)
    dc = [w for w in _list(client)["warnings"] if w["kind"] == "double_count"]
    assert sorted(w["text"].split('"')[1] for w in dc) == ["Lake lot", "duplex"]
    assert all(w["property"] == "Duplex" and w["action"] == "other_assets" for w in dc)
    assert "by name" in dc[1]["text"] or "by name" in dc[0]["text"]
    # 6% apart is not a match
    with ws.store() as s:
        s.set_value("Other Assets", "Other Asset 2", "value", "420000")
    dc = [w for w in _list(client)["warnings"] if w["kind"] == "double_count"]
    assert [w["text"].split('"')[1] for w in dc] == ["duplex"]


def test_failed_section_121_test_warns_only(ws, client):
    _save(client, rf.CONVERTED_HOME)  # converted 2027, month 7
    assert [w for w in _list(client)["warnings"] if w["kind"] == "section_121"] == []
    with ws.store() as s:
        s.set_value("Other Assets", "Home", "home_sale_year", "2033")
    warns = [w for w in _list(client)["warnings"] if w["kind"] == "section_121"]
    assert len(warns) == 1 and warns[0]["level"] == "bad" and warns[0]["property"] == "Our house"
    assert "warning only" in warns[0]["text"] and "fully taxable" in warns[0]["text"]
    with ws.store() as s:
        s.set_value("Other Assets", "Home", "home_sale_year", "2029")  # sold within the 2-of-5 window
    assert [w for w in _list(client)["warnings"] if w["kind"] == "section_121"] == []


def test_home_prefill_has_no_suggested_rent(client):
    out = client.get("/api/rental/home", headers=HEADERS).get_json()
    home = out["home"]
    assert out["success"] and home["available"] and home["value_today"] > 0
    assert home["conversion_year"] >= 2026 and home["value_at_conversion"] >= home["value_today"] * 0.99
    assert home["depreciable_basis"] > 0
    assert not [k for k in home if "rent" in k]  # owner decision 2026-10-13: ask for rent only


def test_config_rows_carries_the_stored_count_and_suggests_turning_on(ws, client):
    assert client.get("/api/config/rows", headers=HEADERS).get_json()["rental_property_count"] == 0
    _save(client, rf.PROFITABLE)
    out = client.get("/api/config/rows", headers=HEADERS).get_json()
    assert out["rental_property_count"] == 1
    suggest = [s for s in out["feature_suggestions"] if s["key"] == KEY]
    assert suggest and suggest[0]["entered_rows"] == 1
    _feature(client, True)
    assert not [s for s in client.get("/api/config/rows", headers=HEADERS).get_json()["feature_suggestions"] if s["key"] == KEY]


def test_nav_step_is_declared_for_the_feature():
    assert mc.step_gate_map()["rental_properties"] == KEY


def test_writes_need_write_permission_and_the_runtime_write_switch(ws, client, monkeypatch):
    real_require, seen = plan_routes._require, []
    monkeypatch.setattr(plan_routes, "_require", lambda perm: seen.append(perm) or None)
    assert _save(client, rf.PROFITABLE)[0] == 200 and client.get("/api/rental/properties", headers=HEADERS).status_code == 200
    assert seen == ["write_config", "read_config"]
    monkeypatch.setattr(plan_routes, "_require", lambda perm: (plan_routes.jsonify({"success": False}), 403))
    assert client.post("/api/rental/property/delete", headers=HEADERS, json={"name": "Duplex"}).status_code == 403
    assert [p["name"] for p in _stored(ws)] == ["Duplex"]

    class Cfg:
        allow_csv_write = False
    monkeypatch.setattr(plan_routes, "_require", real_require)
    monkeypatch.setattr(plan_routes, "_runtime_config", lambda: Cfg())
    status, out = _save(client, dict(rf.PROFITABLE, name="Other"))
    assert status == 403 and [p["name"] for p in _stored(ws)] == ["Duplex"]


def test_service_key_lists_match_the_repo():
    from src.server_services import rental_service as rs
    from src.stores import rental_repo as rr
    assert rs.PROPERTY_COLUMNS == rr.PROPERTY_COLUMNS
    assert rs.IMPROVEMENT_KEYS == rr.IMPROVEMENT_KEYS and rs.OVERRIDE_KEYS == rr.OVERRIDE_KEYS
