"""WP4.4b: the Roth, strategy and policy endpoints read and write ``plan_rows``.

Withdrawal account order, large discretionary expenses, forced Roth conversions, tax
assumptions, state residency schedule and spending adjustments read the active plan's rows
(``app_core._read_active_plan``) and edit them through ``app_core._edit_active_plan`` (one
rows transaction on the plan file; WP4.5 deleted the CSV write-back). Responses are the ones the
CSV implementation gave; a block that already exists is edited in place (row ids stay) and no
edit is lost between endpoints.
"""
from __future__ import annotations

import pytest

import src.server.app_core as app_core
from src.active_plan import edit_active_plan
from src.config_backend import load_active_config
from src.data_io import parse_client
from src.roth_ui_build_guard import canonicalize_roth_rows
from src.server import app, plan_routes
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
PRE_TAX = ["Member_1_401k", "Member_1_IRA", "Member_2_IRA"]
ACCOUNTS = ["Family_Checking", "Member_1_IRA", "Member_1_Roth", "Member_2_IRA"]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    # holdings are not plan rows: the account lists are the endpoint's own input
    monkeypatch.setattr(plan_routes, "_pre_tax_account_options_from_holdings", lambda: list(PRE_TAX))
    monkeypatch.setattr(plan_routes, "_all_account_ids_from_holdings", lambda: list(ACCOUNTS))
    return plan


@pytest.fixture
def client(ws):
    return app.test_client()


def _get(client, path):
    resp = client.get(path, headers=HEADERS)
    return resp.status_code, resp.get_json()


def _post(client, path, body=None):
    resp = client.post(path, headers=HEADERS, json=body or {})
    return resp.status_code, resp.get_json()


def _rows(ws, section, subsection=None):
    with ws.store(readonly=True) as store:
        return [r for r in store.rows(section) if subsection is None or r["subsection"] == subsection]


def _labels(ws, section, subsection):
    return [(r["label"], r["value"]) for r in _rows(ws, section, subsection)]


def _ids(rows):
    return {(r["subsection"], r["label"]): r["row_id"] for r in rows}


# ------------------------------------------------------------ withdrawal account order
def test_withdrawal_account_order_defaults_save_and_replace(ws, client):
    status, out = _get(client, "/api/withdrawal-account-order")
    assert status == 200 and out["accounts"] == [
        {"account_id": a, "priority": str(i + 1)} for i, a in enumerate(ACCOUNTS)]
    assert _post(client, "/api/withdrawal-account-order", {"accounts": "x"}) == (
        400, {"success": False, "error": "accounts must be a list"})
    status, out = _post(client, "/api/withdrawal-account-order", {"accounts": [
        {"account_id": "Member_1_IRA", "priority": "3"}, {"account_id": "Member_2_IRA", "priority": " 1 "},
        {"account_id": "", "priority": "2"}, {"account_id": "Family_Checking", "priority": ""}, "junk"]})
    assert (status, out) == (200, {"success": True, "saved": 2})
    rows = _rows(ws, "Withdrawal Policy", "Account Order")
    assert [(r["label"], r["value"], r["units"]) for r in rows] == [
        ("Member_1_IRA", "3", "int"), ("Member_2_IRA", "1", "int")]
    assert rows[0]["notes"].startswith("Individual-account withdrawal draw priority")
    assert load_active_config()[0]["Withdrawal Policy"]["Account Order"] == {"Member_1_IRA": "3", "Member_2_IRA": "1"}
    got = _get(client, "/api/withdrawal-account-order")[1]["accounts"]
    assert {a["account_id"]: a["priority"] for a in got} == {
        "Family_Checking": "1", "Member_1_IRA": "3", "Member_1_Roth": "3", "Member_2_IRA": "1"}
    # a second save edits in place and drops the account that is no longer sent
    ids = _ids(rows)
    assert _post(client, "/api/withdrawal-account-order", {"accounts": [
        {"account_id": "Member_2_IRA", "priority": "2"}, {"account_id": "Member_1_Roth", "priority": "1"}]})[1]["saved"] == 2
    rows = _rows(ws, "Withdrawal Policy", "Account Order")
    assert [(r["label"], r["value"]) for r in rows] == [("Member_2_IRA", "2"), ("Member_1_Roth", "1")]
    assert rows[0]["row_id"] == ids[("Account Order", "Member_2_IRA")]
    assert _post(client, "/api/withdrawal-account-order", {"accounts": []}) == (200, {"success": True, "saved": 0})
    assert not _rows(ws, "Withdrawal Policy", "Account Order")


# ------------------------------------------------------------- large discretionary
def test_large_discretionary_reads_the_plan_and_replaces_its_block(ws, client):
    status, out = _get(client, "/api/large-discretionary-expenses")
    assert status == 200 and out["types"] == ["Wedding", "Large Gifts", "Other"]
    first = out["events"][0]
    assert first == {"type": "Wedding", "amount": "$100,000", "year": "2027", "start_year": "", "end_year": "",
                     "comment": "Child Wedding 1"}  # the fixture's "Weddings" reads as Wedding
    before = _rows(ws, "Cashflow", "Large Discretionary Expenses")
    ids = _ids(before)
    count = len(out["events"])
    assert len(before) == 6 * count
    assert _post(client, "/api/large-discretionary-expenses", {"events": "x"}) == (
        400, {"success": False, "error": "events must be a list"})

    events = [{"type": "Wedding", "amount": "150000", "year": "2030", "comment": " A "},
              {"type": "vacation", "amount": "5,000", "start_year": "2031", "end_year": "2035", "comment": "B"},
              "junk"]  # not an object: skipped
    status, out = _post(client, "/api/large-discretionary-expenses", {"events": events})
    assert (status, out) == (200, {"success": True, "count": 2})
    assert _labels(ws, "Cashflow", "Large Discretionary Expenses") == [
        ("extra_1_type", "Wedding"), ("extra_1_amount", "$150,000"), ("extra_1_year", "2030"),
        ("extra_1_start_year", ""), ("extra_1_end_year", ""), ("extra_1_comment", "A"),
        ("extra_2_type", "Other"), ("extra_2_amount", "$5,000"), ("extra_2_year", ""),
        ("extra_2_start_year", "2031"), ("extra_2_end_year", "2035"), ("extra_2_comment", "B")]
    after = _rows(ws, "Cashflow", "Large Discretionary Expenses")
    assert all(ids[(r["subsection"], r["label"])] == r["row_id"] for r in after)  # edited in place
    # the block did not move: the rows around it are as they were
    cash = [r["subsection"] for r in _rows(ws, "Cashflow")]
    assert cash.index("Large Discretionary Expenses") == [r["subsection"] for r in _rows(ws, "Cashflow")].index("Large Discretionary Expenses")
    got = _get(client, "/api/large-discretionary-expenses")[1]["events"]
    assert got == [
        {"type": "Wedding", "amount": "$150,000", "year": "2030", "start_year": "", "end_year": "", "comment": "A"},
        {"type": "Other", "amount": "$5,000", "year": "", "start_year": "2031", "end_year": "2035", "comment": "B"}]
    assert load_active_config()[0]["Cashflow"]["Large Discretionary Expenses"]["extra_2_amount"] == "$5,000"
    # growing the list adds rows after the block; an empty list removes it
    events.append({"type": "Large Gifts", "amount": "$1,000", "year": "2040"})
    _post(client, "/api/large-discretionary-expenses", {"events": events})
    sub = [r["label"] for r in _rows(ws, "Cashflow", "Large Discretionary Expenses")]
    assert sub[-6:] == [f"extra_3_{f}" for f in ("type", "amount", "year", "start_year", "end_year", "comment")]
    rows = [r["subsection"] for r in _rows(ws, "Cashflow")]
    assert rows[rows.index("Large Discretionary Expenses"):].count("Large Discretionary Expenses") == 18
    _post(client, "/api/large-discretionary-expenses", {"events": []})
    assert not _rows(ws, "Cashflow", "Large Discretionary Expenses")
    assert _get(client, "/api/large-discretionary-expenses")[1]["events"] == []


def test_large_discretionary_new_block_goes_after_the_post_sale_rent_rows(ws, client):
    with app_core._edit_active_plan() as edit:
        for r in edit.store.rows("Cashflow"):
            if r["subsection"] == "Large Discretionary Expenses":
                edit.store.delete_row(r["row_id"])
    subs = [r["subsection"] for r in _rows(ws, "Cashflow")]
    assert "Post-House-Sale Rent" in subs and "Large Discretionary Expenses" not in subs
    _post(client, "/api/large-discretionary-expenses", {"events": [{"type": "Other", "amount": "10", "year": "2031"}]})
    subs = [r["subsection"] for r in _rows(ws, "Cashflow")]
    last_rent = max(i for i, s in enumerate(subs) if s == "Post-House-Sale Rent")
    assert subs[last_rent + 1:last_rent + 7] == ["Large Discretionary Expenses"] * 6
    # the order survives the GET-time backfill, which adds unrelated rows
    client.get("/api/config/rows", headers=HEADERS)
    subs = [r["subsection"] for r in _rows(ws, "Cashflow")]
    last_rent = max(i for i, s in enumerate(subs) if s == "Post-House-Sale Rent")
    assert subs[last_rent + 1:last_rent + 7] == ["Large Discretionary Expenses"] * 6


# ---------------------------------------------------------------- forced Roth conversions
def test_forced_roth_conversions_read_validate_and_replace(ws, client):
    status, out = _get(client, "/api/forced-roth-conversions")
    assert (status, out["accounts"]) == (200, PRE_TAX)
    assert out["conversions"] == [{"source_account": "Member_2_IRA", "year": "2026", "amount": "$125,000"}]
    ids = _ids(_rows(ws, "Forced Actions"))
    assert _post(client, "/api/forced-roth-conversions", {"conversions": "x"})[0] == 400
    status, out = _post(client, "/api/forced-roth-conversions", {"conversions": [{"source_account": "Bogus", "year": "2030", "amount": "1"}]})
    assert (status, out["error"]) == (400, "Bogus is not a recognized pre-tax account")
    status, out = _post(client, "/api/forced-roth-conversions", {"conversions": [{"source_account": "Member_1_IRA", "year": "30", "amount": "1"}]})
    assert (status, out["error"]) == (400, "Forced conversion year must be YYYY: 30")
    assert _rows(ws, "Forced Actions") and _ids(_rows(ws, "Forced Actions")) == ids  # nothing changed

    status, out = _post(client, "/api/forced-roth-conversions", {"conversions": [
        {"source_account": "Member_1_IRA", "year": "2030", "amount": "20000"},
        {"source_account": "Member_2_IRA", "year": "2031", "amount": "$30,000"},
        {"source_account": "", "year": "", "amount": ""}]})
    assert (status, out) == (200, {"success": True, "count": 2})
    assert _labels(ws, "Forced Actions", "Roth Conversion 1") == [
        ("source_account", "Member_1_IRA"), ("year", "2030"), ("amount", "$20,000")]
    assert _labels(ws, "Forced Actions", "Roth Conversion 2") == [
        ("source_account", "Member_2_IRA"), ("year", "2031"), ("amount", "$30,000")]
    new = _rows(ws, "Forced Actions", "Roth Conversion 2")
    assert [r["units"] for r in new] == ["choice", "year", "USD"]
    assert new[0]["notes"] == "Member_1_401k | Member_1_IRA | Member_2_IRA; pre-tax account to convert from"
    after = _ids(_rows(ws, "Forced Actions"))
    assert all(after[k] == v for k, v in ids.items())  # Roth Conversion 1 was edited in place
    assert _get(client, "/api/forced-roth-conversions")[1]["conversions"] == [
        {"source_account": "Member_1_IRA", "year": "2030", "amount": "$20,000"},
        {"source_account": "Member_2_IRA", "year": "2031", "amount": "$30,000"}]
    forced = parse_client(load_active_config()[0], "")
    assert forced["forced_roth"] == {2030: 20000.0, 2031: 30000.0}
    assert forced["forced_roth_accounts"][2030] == [{"source_account": "Member_1_IRA", "amount": 20000.0}]
    # shrinking drops the numbers above; an empty list drops the whole section (legacy rows too)
    _post(client, "/api/forced-roth-conversions", {"conversions": [{"source_account": "Member_1_401k", "year": "2033", "amount": "7"}]})
    assert [r["subsection"] for r in _rows(ws, "Forced Actions")] == ["Roth Conversion 1"] * 3
    assert _post(client, "/api/forced-roth-conversions", {"conversions": []})[1]["count"] == 0
    assert not _rows(ws, "Forced Actions")
    assert _get(client, "/api/forced-roth-conversions")[1]["conversions"] == []
    # the section comes back as a new one
    _post(client, "/api/forced-roth-conversions", {"conversions": [{"source_account": "Member_1_IRA", "year": "2034", "amount": "5"}]})
    assert _labels(ws, "Forced Actions", "Roth Conversion 1")[1] == ("year", "2034")


# --------------------------------------------------------------------- residency schedule
def test_residency_schedule_reads_and_replaces_the_period_rows(ws, client):
    assert _get(client, "/api/residency-schedule") == (200, {"success": True, "schedule": []})
    schedule = [{"state": "Illinois", "start_year": "2026", "end_year": "2031"},
                {"state": "Florida", "start_year": "2032", "end_year": ""}]
    assert _post(client, "/api/residency-schedule", {"schedule": "x"})[0] == 400
    assert _post(client, "/api/residency-schedule", {"schedule": [dict(schedule[0], end_year="")]})[0] == 200  # one open row is fine
    status, out = _post(client, "/api/residency-schedule", {"schedule": schedule})
    assert (status, out) == (200, {"success": True, "count": 2})
    assert _labels(ws, "State Residency Schedule", "period_2") == [
        ("state", "Florida"), ("start_year", "2032"), ("end_year", "")]
    assert [r["units"] for r in _rows(ws, "State Residency Schedule", "period_1")] == ["choice", "year", "year"]
    assert _get(client, "/api/residency-schedule")[1]["schedule"] == schedule
    assert load_active_config()[0]["State Residency Schedule"]["period_1"]["state"] == "Illinois"
    assert parse_client(load_active_config()[0], "")["residency_schedule"] == [
        {"state": "Illinois", "start_year": 2026, "end_year": 2031}, {"state": "Florida", "start_year": 2032, "end_year": 9999}]
    # the tax assumptions payload carries each period's model rate
    periods = _get(client, "/api/tax-assumptions")[1]["residency_periods"]
    assert [p["state"] for p in periods] == ["Illinois", "Florida"] and periods[1]["model_rate"] == 0.0
    ids = _ids(_rows(ws, "State Residency Schedule"))
    _post(client, "/api/residency-schedule", {"schedule": [{"state": "Texas", "start_year": "2026", "end_year": ""}]})
    rows = _rows(ws, "State Residency Schedule")
    assert [(r["subsection"], r["label"], r["value"]) for r in rows] == [
        ("period_1", "state", "Texas"), ("period_1", "start_year", "2026"), ("period_1", "end_year", "")]
    assert rows[0]["row_id"] == ids[("period_1", "state")]
    assert _post(client, "/api/residency-schedule", {"schedule": []})[1]["count"] == 0
    assert not _rows(ws, "State Residency Schedule")


@pytest.mark.parametrize("schedule, error", [
    ([{"state": "", "start_year": "2026", "end_year": ""}], "Row 1 is missing a state."),
    ([{"state": "Texas", "start_year": "", "end_year": ""}], "Row 1 is missing a start year."),
    ([{"state": "Texas", "start_year": "2026", "end_year": "2030"}], "The last residency row must be open-ended -- clear its end year."),
    ([{"state": "Texas", "start_year": "2026", "end_year": ""}, {"state": "Utah", "start_year": "2030", "end_year": ""}],
     "Row 1 needs an end year -- only the last row may be open-ended."),
])
def test_residency_schedule_validation_changes_nothing(ws, client, schedule, error):
    revision = ws.store(readonly=True).revision()
    status, out = _post(client, "/api/residency-schedule", {"schedule": schedule})
    assert (status, out) == (400, {"success": False, "error": error})
    assert ws.store(readonly=True).revision() == revision


# ---------------------------------------------------------------------- tax assumptions
def test_tax_assumptions_read_and_save_overrides_in_the_economic_assumptions_rows(ws, client):
    status, out = _get(client, "/api/tax-assumptions")
    assert status == 200 and out["state"] == "Illinois"
    by_key = {lv["key"]: lv for lv in out["levers"]}
    assert by_key["fed_tax_bracket_inflator"]["source"] == "override"  # the fixture's 2.00%
    assert by_key["state_income_tax_rate"]["source"] == "model" and out["law_scenario"]["active"] is False
    before = _ids(_rows(ws, "Economic Assumptions"))
    assert ("", "fed_tax_bracket_inflator") in before and ("", "state_income_tax_rate") not in before
    assert _post(client, "/api/tax-assumptions", {})[0] == 400
    assert _post(client, "/api/tax-assumptions", {"overrides": {"state_income_tax_rate": "40%"}})[0] == 400

    status, out = _post(client, "/api/tax-assumptions", {"overrides": {"fed_tax_bracket_inflator": "3.00%", "state_income_tax_rate": "6%"}})
    assert (status, out) == (200, {"success": True, "count": 2})
    econ = {r["label"]: r for r in _rows(ws, "Economic Assumptions")}
    assert (econ["fed_tax_bracket_inflator"]["value"], econ["state_income_tax_rate"]["value"]) == ("3.00%", "6%")
    assert econ["fed_tax_bracket_inflator"]["row_id"] == before[("", "fed_tax_bracket_inflator")]  # in place
    baseline = econ["tax_model_baseline"]
    assert baseline["units"] == "text" and baseline["row_id"] not in before.values()
    assert "fed_tax_bracket_inflator=" in baseline["value"] and "state_income_tax_rate=" in baseline["value"]
    assert list(econ)[-2:] == ["state_income_tax_rate", "tax_model_baseline"]  # new rows go to the end of the section
    out = _get(client, "/api/tax-assumptions")[1]
    by_key = {lv["key"]: lv for lv in out["levers"]}
    assert by_key["fed_tax_bracket_inflator"]["source"] == "override" and by_key["state_income_tax_rate"]["source"] == "override"
    assert load_active_config()[0]["Economic Assumptions"][""]["state_income_tax_rate"] == "6%"
    # a blank override goes back to Auto and leaves the baseline
    _post(client, "/api/tax-assumptions", {"overrides": {"state_income_tax_rate": ""}})
    assert "state_income_tax_rate=" not in {r["label"]: r for r in _rows(ws, "Economic Assumptions")}["tax_model_baseline"]["value"]
    assert _get(client, "/api/tax-assumptions")[1]["levers"][0]["key"]


def test_tax_assumptions_state_comes_from_the_household_row(ws, client):
    with app_core._edit_active_plan() as edit:
        edit.store.set_value("Household", "", "residence_state", "Atlantis")
    status, out = _get(client, "/api/tax-assumptions")
    assert status == 400 and out["success"] is False


# ----------------------------------------------------------------- no edit lost between endpoints
def test_policy_edits_through_several_endpoints_keep_everything(ws, client):
    assert _post(client, "/api/residency-schedule", {"schedule": [{"state": "Texas", "start_year": "2027", "end_year": ""}]})[0] == 200
    assert _post(client, "/api/forced-roth-conversions", {"conversions": [{"source_account": "Member_1_IRA", "year": "2030", "amount": "9"}]})[0] == 200
    assert _post(client, "/api/liquidity-buffers", {"buffers": [
        {"start_year": "2027", "end_year": "2029", "years_of_expenses": "2", "reserve_account": "Cash"}]})[0] == 200
    data = load_active_config()[0]
    assert data["State Residency Schedule"]["period_1"]["state"] == "Texas"
    assert data["Forced Actions"]["Roth Conversion 1"]["amount"] == "$9"
    assert data["Liquidity Buffer"]["buffer_1"]["reserve_account"] == "Cash"
    assert _post(client, "/api/tax-assumptions", {"overrides": {"fed_tax_bracket_inflator": "3.00%"}})[0] == 200
    assert _post(client, "/api/spending-adjustments", {"adjustments": [{"category": "dining", "start_year": "2035", "change_pct": "-20"}]})[0] == 200
    data = load_active_config()[0]
    assert data["Liquidity Buffer"]["buffer_1"]["years_of_expenses"] == "2"
    assert data["State Residency Schedule"]["period_1"]["state"] == "Texas"
    assert data["Forced Actions"]["Roth Conversion 1"]["amount"] == "$9"
    assert data["Economic Assumptions"][""]["fed_tax_bracket_inflator"] == "3.00%"
    assert data["Cashflow"]["Spending Adjustments"]["adj_1_category"] == "dining"


def test_a_failed_edit_changes_nothing(ws, client, monkeypatch):
    """An edit that raises inside the transaction leaves the plan as it was (every endpoint)."""
    class Failing:
        def __enter__(self):
            raise RuntimeError("the plan file is locked")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(plan_routes, "_edit_active_plan", lambda: Failing())
    revision = ws.store(readonly=True).revision()
    for path, body in [("/api/residency-schedule", {"schedule": []}), ("/api/forced-roth-conversions", {"conversions": []})]:
        status, out = _post(client, path, body)
        assert status == 500 and out["success"] is False and "locked" in out["error"], path
    assert ws.store(readonly=True).revision() == revision


def test_audit_events_are_recorded_after_the_edit(ws, client, monkeypatch):
    events = []
    monkeypatch.setattr(plan_routes, "_audit", lambda event, details=None: events.append((event, details)))
    _post(client, "/api/residency-schedule", {"schedule": [{"state": "Texas", "start_year": "2026", "end_year": ""}]})
    _post(client, "/api/residency-schedule", {"schedule": [{"state": "", "start_year": "2026"}]})  # 400: nothing audited
    _post(client, "/api/withdrawal-account-order", {"accounts": [{"account_id": "Member_1_IRA", "priority": "1"}]})
    _post(client, "/api/spending-adjustments", {"adjustments": []})
    _post(client, "/api/forced-roth-conversions", {"conversions": []})
    assert [e for e, _ in events] == [
        "residency_schedule_saved", "withdrawal_account_order_saved", "spending_adjustments_saved",
        "forced_roth_conversions_saved"]


# ----------------------------------------------------------------- the Roth UI guard on rows
def test_roth_guard_canonicalizes_the_plan_rows_after_an_edit(ws):
    with ws.store() as store:
        store.set_value("Withdrawal Policy", "Roth Conversion", "roth_conversion_policy", "Fill to 22% bracket")
        store.set_value("Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate", "22% bracket")
        assert canonicalize_roth_rows(store) == 2
        assert canonicalize_roth_rows(store) == 0
        data = store.sectioned_data()["Withdrawal Policy"]["Roth Conversion"]
        assert (data["roth_conversion_policy"], data["roth_target_bracket_rate"]) == ("fill_to_bracket", "22.00%")


def test_an_edit_through_the_edit_context_stores_roth_controls_canonical(ws):
    with app_core._edit_active_plan() as edit:
        edit.store.set_value("Withdrawal Policy", "Roth Conversion", "roth_conversion_policy", "Fill to 22% bracket")
        edit.store.set_value("Withdrawal Policy", "Roth Conversion", "irmaa_guardrail_mode", "Warn only")
    with ws.store(readonly=True) as store:
        data = store.sectioned_data()["Withdrawal Policy"]["Roth Conversion"]
    assert (data["roth_conversion_policy"], data["irmaa_guardrail_mode"]) == ("fill_to_bracket", "WARN_ONLY")
