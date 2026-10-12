"""WP4.5: Start New Plan clears the household facts in the plan rows (``src/blank_plan.py``).

The rule is the retired CSV templates' rule: the policy and settings sections and a few curated
system defaults keep their values, every other value is cleared; the rows (keys, units, notes)
stay. The three flat datasets are blanked by the service as before (covered with the service).
"""
from __future__ import annotations

import pytest

import src.server.app_core as app_core
from src import blank_plan
from src.csv_exchange import PART_FILE_SECTIONS
from src.server import app
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return plan


def test_blanking_matches_the_retired_template_rule_on_the_fixture(ws):
    """Every row of a household-fact file's sections is cleared, every row of the policy,
    optional-functions and optimizer-controls files (bar the preserved defaults) is kept."""
    before = ws.store_data()
    cleared = app_core._blank_plan_rows()
    after = ws.store_data()
    assert cleared > 100
    # a household fact is cleared, a policy setting and a curated default are kept
    assert before["Household"][""]["member_1_name"] and after["Household"][""]["member_1_name"] == ""
    assert before["Cashflow"]["Spending"]["annual_spending_base_year"] and after["Cashflow"]["Spending"]["annual_spending_base_year"] == ""
    assert after["Model Constants"] == before["Model Constants"]
    assert after["Optional Functions"] == before["Optional Functions"]
    assert after["Withdrawal Policy"] == before["Withdrawal Policy"]
    assert after["Economic Assumptions"][""]["inflation_general"] == before["Economic Assumptions"][""]["inflation_general"]
    assert after["Social Security"]["Funding Discount"] == before["Social Security"]["Funding Discount"]
    assert after["HSA Policy"]["Contributions"]["index_hsa_limit"] == before["HSA Policy"]["Contributions"]["index_hsa_limit"]
    assert after["HSA Policy"]["Contributions"]["family_annual_limit_base_year"] == ""
    # nothing but values changed: same keys in the same order
    assert [(s, sub, k) for s, subs in after.items() for sub, vals in subs.items() for k in vals] == \
        [(s, sub, k) for s, subs in before.items() for sub, vals in subs.items() for k in vals]
    assert app_core._blank_plan_rows() == 0  # idempotent


def test_every_section_is_either_kept_or_cleared_by_its_old_file(ws):
    """The kept set is exactly the sections of the policy / optional / optimizer part files (bar HSA Policy)."""
    sections = ws.store_data()
    for section in sections:
        old_files = [f for f, secs in PART_FILE_SECTIONS.items() if section in secs]
        kept_by_files = bool(old_files) and all(f in ("client_policy.csv", "client_optional_functions.csv", "asset_class_optimizer_controls.csv") for f in old_files)
        if section == "HSA Policy":
            continue
        assert (section in blank_plan.KEPT_SECTIONS) == kept_by_files or section == "Plan Settings", section


def test_the_blank_clears_retirement_dates_on_purpose_and_stamps_the_ytd_choice(ws):
    app_core._blank_plan_rows(ytd_blend_enabled=False)
    data = ws.store_data()
    assert data["Household"][""]["member_1_retirement_date"] == ""  # the protected-value rule is off here
    assert data["Cashflow"]["Spending"]["ytd_blend_enabled"] == "FALSE"
    app_core._blank_plan_rows(ytd_blend_enabled=True)
    assert ws.store_data()["Cashflow"]["Spending"]["ytd_blend_enabled"] == "TRUE"


def test_a_blank_plan_then_a_form_edit_round_trip(ws):
    app_core._blank_plan_rows()
    client = app.test_client()
    resp = client.patch("/api/plan/forms/Household/", headers=HEADERS, json={"values": {"member_1_name": "New Person"}})
    assert resp.status_code == 400  # section/subsection needed (the empty subsection is not addressable by PATCH)
    resp = client.post("/api/plan/forms", headers=HEADERS, json={"sections": {"Household": {"": {"member_1_name": "New Person"}}}})
    assert resp.status_code == 200 and ws.store_data()["Household"][""]["member_1_name"] == "New Person"



def test_the_removed_routes_are_gone(ws):
    client = app.test_client()
    assert client.get("/api/csv", headers=HEADERS).status_code == 404
    assert client.post("/api/csv", headers=HEADERS, json={"csv_content": "x"}).status_code == 404
    assert client.post("/api/config/sync", headers=HEADERS, json={}).status_code == 404
    assert client.get("/api/admin/csv-file/plan/client_household.csv", headers=HEADERS).status_code == 404
