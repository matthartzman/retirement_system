"""WP4.4a: the asset, estate, insurance and seed endpoints read and write ``plan_rows``.

Each endpoint edits the active plan's rows through ``app_core._edit_active_plan`` (one rows
transaction on the plan file; WP4.5 deleted the CSV write-back). The responses are the ones the
CSV implementation gave, and no edit is lost between endpoints.
"""
from __future__ import annotations

import pytest

import src.server.app_core as app_core
from src.config_backend import load_active_config
from src.server import app, plan_routes
from src.server_services.strategy_asset_service import (HEALTHCARE_OOP_SEED_ROWS, HOUSING_SEED_ROWS,
                                                         LIFE_ILLUSTRATION_SECTIONS)
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}
BUFFERS = [{"start_year": "2031", "end_year": "2036", "years_of_expenses": "2", "reserve_account": "Cash"}]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    return plan


@pytest.fixture
def client(ws):
    return app.test_client()


def _post(client, path, body=None):
    resp = client.post(path, headers=HEADERS, json=body or {})
    return resp.status_code, resp.get_json()


def _rows(ws, section, subsection=None):
    with ws.store(readonly=True) as store:
        return [r for r in store.rows(section) if subsection is None or r["subsection"] == subsection]


def _subs(ws, section):
    out: list[str] = []
    for r in _rows(ws, section):
        if r["subsection"] not in out:
            out.append(r["subsection"])
    return out


def _drop(ws, section, subsection=None):
    """Delete rows through the same edit context the endpoints use."""
    with app_core._edit_active_plan() as edit:
        for r in edit.store.rows(section):
            if subsection is None or r["subsection"] == subsection:
                edit.store.delete_row(r["row_id"])


# ------------------------------------------------------------------------ other assets
def test_add_other_asset_adds_the_seven_rows_and_numbers_after_the_highest(ws, client):
    before = _subs(ws, "Other Assets")
    n = max(int(s.rsplit(" ", 1)[1]) for s in before if s.startswith("Other Asset ")) + 1
    status, out = _post(client, "/api/other-asset/add", {"asset_type": "Boat"})
    assert (status, out) == (200, {"success": True, "section": f"Other Asset {n}", "message": "Added Boat other asset."})
    rows = _rows(ws, "Other Assets", f"Other Asset {n}")
    assert [r["label"] for r in rows] == ["type", "name", "value", "as_of_date", "annual_appreciation_pct", "basis", "sell_date"]
    assert [r["value"] for r in rows][:3] == ["Boat", "Boat", "$0"]
    assert [r["units"] for r in rows][:3] == ["choice", "text", "dollars"]
    assert _subs(ws, "Other Assets") == [*before, f"Other Asset {n}"]
    # the build input sees it
    assert load_active_config()[0]["Other Assets"][f"Other Asset {n}"]["type"] == "Boat"
    status, out = _post(client, "/api/other-asset/add")  # the default type
    assert out["section"] == f"Other Asset {n + 1}" and out["message"] == "Added Auto other asset."


def test_delete_other_asset_validates_then_removes_only_that_section(ws, client):
    assert _post(client, "/api/other-asset/delete", {"subsection": "Home"})[0] == 400
    status, out = _post(client, "/api/other-asset/delete", {"subsection": "Other Asset 99"})
    assert status == 404 and out["error"] == "No other asset section named 'Other Asset 99' was found."
    target = _rows(ws, "Other Assets", "Other Asset 2")
    others = _subs(ws, "Other Assets")
    assert target
    status, out = _post(client, "/api/other-asset/delete", {"subsection": "Other Asset 2"})
    assert status == 200 and out["rows_removed"] == len(target) and out["message"] == "Deleted Other Asset 2."
    assert _subs(ws, "Other Assets") == [s for s in others if s != "Other Asset 2"]
    assert "Other Asset 2" not in load_active_config()[0]["Other Assets"]


# --------------------------------------------------------------------------- notes
def test_note_receivable_add_and_delete_with_its_interest_rows(ws, client):
    assert _subs(ws, "Note Receivable") == ["Note 1", "Note 1 Interest"]
    status, out = _post(client, "/api/note-receivable/add", {"name": "Seller Note"})
    assert (status, out) == (200, {"success": True, "section": "Note 2", "message": "Added note Seller Note."})
    assert [r["label"] for r in _rows(ws, "Note Receivable", "Note 2")] == [
        "name", "face_value", "first_payment", "last_payment", "annual_principal_base_period", "final_principal_2033"]
    assert _rows(ws, "Note Receivable", "Note 2")[0]["value"] == "Seller Note"
    assert _post(client, "/api/note-receivable/add")[1]["message"] == "Added note New Note."
    assert _post(client, "/api/note-receivable/delete", {"subsection": "x"})[0] == 400
    assert _post(client, "/api/note-receivable/delete", {"subsection": "Note 9"})[0] == 404
    interest = len(_rows(ws, "Note Receivable", "Note 1")) + len(_rows(ws, "Note Receivable", "Note 1 Interest"))
    status, out = _post(client, "/api/note-receivable/delete", {"subsection": "Note 1"})
    assert status == 200 and out["rows_removed"] == interest
    assert _subs(ws, "Note Receivable") == ["Note 2", "Note 3"]


# ---------------------------------------------------------------------------- 529
def test_education_529_add_keeps_the_numbering_rule_of_the_csv_code(ws, client):
    status, out = _post(client, "/api/education-529/add")
    # the number is the first digit run of each subsection plus one ("529 Plan 1" -> 530)
    assert (status, out) == (200, {"success": True, "section": "529 Plan 530", "message": "Added 529 Plan 530."})
    assert [r["label"] for r in _rows(ws, "Education Funding", "529 Plan 530")] == [
        "beneficiary", "current_balance", "annual_contribution", "contribution_start_year",
        "contribution_end_year", "expected_use_year"]


# --------------------------------------------------------------------------- estate
def test_estate_state_options_come_from_the_reference_data(client):
    resp = client.get("/api/estate-state-options", headers=HEADERS)
    states = resp.get_json()["states"]
    assert resp.status_code == 200 and any(s["state"] == "New York" for s in states)


def test_add_estate_state_goes_before_the_gifting_rows_and_is_idempotent(ws, client):
    assert _post(client, "/api/estate-state/add", {})[0] == 400
    before = _subs(ws, "Estate Planning")
    status, out = _post(client, "/api/estate-state/add", {"state": "new york"})
    assert status == 200 and out["state"] == "New York" and out["message"] == "Added New York estate rows."
    assert [r["label"] for r in _rows(ws, "Estate Planning", "New York")] == [
        "state_estate_exemption", "state_estate_tax_applies", "state_estate_rate_note"]
    after = _subs(ws, "Estate Planning")
    assert after == [*before[:before.index("Gifting")], "New York", *before[before.index("Gifting"):]]
    revision = ws.store(readonly=True).revision()
    status, out = _post(client, "/api/estate-state/add", {"state": "New York"})
    assert (status, out["message"]) == (200, "New York already exists in Estate Information.")
    assert ws.store(readonly=True).revision() == revision
    # a state the reference data does not know is added as typed
    status, out = _post(client, "/api/estate-state/add", {"state": "Zzz"})
    assert out["state"] == "Zzz" and _rows(ws, "Estate Planning", "Zzz")[1]["value"] == "FALSE"
    assert load_active_config()[0]["Estate Planning"]["New York"]["state_estate_tax_applies"] in {"TRUE", "FALSE"}


def test_add_trust_account_numbers_and_places_the_rows(ws, client):
    assert _post(client, "/api/trust-account/add", {})[0] == 400
    before = _subs(ws, "Estate Planning")
    status, out = _post(client, "/api/trust-account/add", {"account_name": "Family Trust", "trust_type": "QTIP"})
    assert (status, out) == (200, {"success": True, "section": "Trust Account 1", "message": "Added Family Trust trust account."})
    rows = _rows(ws, "Estate Planning", "Trust Account 1")
    assert [(r["label"], r["value"]) for r in rows] == [("account_name", "Family Trust"), ("trust_type", "QTIP"), ("notes", "")]
    # before the first of the QTIP / Credit Shelter / Gifting subsections, as the CSV code did
    assert _subs(ws, "Estate Planning").index("Trust Account 1") == before.index("Gifting")
    status, out = _post(client, "/api/trust-account/add", {"account_name": "Second"})
    assert out["section"] == "Trust Account 2"
    assert _rows(ws, "Estate Planning", "Trust Account 2")[1]["value"] == "Revocable"
    subs = _subs(ws, "Estate Planning")
    assert subs[subs.index("Trust Account 1") + 1] == "Trust Account 2" and subs[subs.index("Trust Account 2") + 1] == "Gifting"
    # the order is the stored order the grid GET serves
    client.get("/api/config/rows", headers=HEADERS)
    assert _subs(ws, "Estate Planning") == subs


# ------------------------------------------------------------------------ insurance
@pytest.mark.parametrize("typ, extra, section_prefix", [
    ("Life", ["beneficiary", "face_amount", "term_end_year"], "Life"),
    ("Disability", ["monthly_benefit", "elimination_days", "benefit_period_years"], "Disability"),
    ("Long-Term Care", ["coverage_limit", "deductible"], "Long_Term_Care"),
])
def test_add_insurance_policy_row_set_depends_on_the_type(ws, client, typ, extra, section_prefix):
    existing = [int(s.rsplit("_", 1)[1]) for s in _subs(ws, "Insurance In Force")
                if s.lower().startswith(section_prefix.lower()) and s.rsplit("_", 1)[-1].isdigit()]
    n = max(existing, default=0) + 1
    status, out = _post(client, "/api/insurance-policy/add", {"policy_type": typ})
    sub = f"{section_prefix}_{n}"
    assert (status, out) == (200, {"success": True, "section": sub, "message": f"Added {typ} policy {n}."})
    labels = [r["label"] for r in _rows(ws, "Insurance In Force", sub)]
    assert labels == ["policy_type", "owner", "insured", *extra, "annual_premium", "premium_end_year", "notes"]
    assert _rows(ws, "Insurance In Force", sub)[0]["value"] == typ
    assert _subs(ws, "Insurance In Force")[-1] == sub


def test_life_illustration_seed_adds_missing_rows_and_delete_removes_them_with_the_policy(ws, client):
    assert _post(client, "/api/life-illustration/seed", {"years": [2030]})[0] == 400
    assert _post(client, "/api/life-illustration/seed", {"policy_key": "Life_9", "years": ["x"]})[0] == 400
    status, out = _post(client, "/api/life-illustration/seed", {"policy_key": "Life_9", "years": [2030, "2031", "x"]})
    assert (status, out) == (200, {"success": True, "seeded": 6, "already_present": 0})
    for section in LIFE_ILLUSTRATION_SECTIONS:
        assert [(r["subsection"], r["label"], r["value"], r["units"]) for r in _rows(ws, section)
                if r["label"] == "Life_9"] == [("2030", "Life_9", "$0", "USD"), ("2031", "Life_9", "$0", "USD")]
    status, out = _post(client, "/api/life-illustration/seed", {"policy_key": "Life_9", "years": [2030, 2032]})
    assert out == {"success": True, "seeded": 3, "already_present": 3}
    status, out = _post(client, "/api/insurance-policy/delete", {"subsection": "Life_9"})
    assert (status, out["rows_removed"]) == (200, 9)  # illustration rows only: there is no Life_9 policy section
    assert not any(r["label"] == "Life_9" for s in LIFE_ILLUSTRATION_SECTIONS for r in _rows(ws, s))


def test_delete_insurance_policy_validates_and_removes_the_section(ws, client):
    assert _post(client, "/api/insurance-policy/delete", {})[0] == 400
    status, out = _post(client, "/api/insurance-policy/delete", {"subsection": "Nope"})
    assert status == 404 and out["error"] == "No insurance policy section named 'Nope' was found."
    count = len(_rows(ws, "Insurance In Force", "Life_Term_Matthew"))
    status, out = _post(client, "/api/insurance-policy/delete", {"subsection": "Life_Term_Matthew"})
    assert status == 200 and out["rows_removed"] >= count > 0
    assert out["message"] == "Deleted insurance policy Life_Term_Matthew."
    assert "Life_Term_Matthew" not in load_active_config()[0]["Insurance In Force"]


# ------------------------------------------------------------------------- seed rows
def test_seed_housing_and_healthcare_add_only_the_missing_keys(ws, client):
    _drop(ws, "Housing", "next_step_2")
    _drop(ws, "Wellness", "Out-of-Pocket")
    with ws.store(readonly=True) as store:
        held = {(r["section"], r["subsection"], r["label"]) for r in store.all_rows()}
    missing_housing = [r for r in HOUSING_SEED_ROWS if tuple(r[:3]) not in held]
    assert any(r[1] == "next_step_2" for r in missing_housing) and len(missing_housing) < len(HOUSING_SEED_ROWS)
    status, out = _post(client, "/api/housing/seed")
    assert (status, out) == (200, {"success": True, "seeded": len(missing_housing), "already_present": len(HOUSING_SEED_ROWS) - len(missing_housing)})
    assert [r["label"] for r in _rows(ws, "Housing", "next_step_2")] == [r[2] for r in missing_housing if r[1] == "next_step_2"]
    assert _post(client, "/api/housing/seed")[1]["seeded"] == 0
    status, out = _post(client, "/api/wellness/seed")
    assert (status, out) == (200, {"success": True, "seeded": 4, "already_present": 0})
    oop = _rows(ws, "Wellness", "Out-of-Pocket")
    assert [(r["label"], r["units"]) for r in oop] == [(r[2], r[4]) for r in HEALTHCARE_OOP_SEED_ROWS]
    assert _post(client, "/api/wellness/seed")[1] == {"success": True, "seeded": 0, "already_present": 4}
    # a value the plan already holds is never overwritten by a seed
    with app_core._edit_active_plan() as edit:
        edit.store.set_value("Wellness", "Out-of-Pocket", "medical_annual", "$1,234")
    _post(client, "/api/wellness/seed")
    assert load_active_config()[0]["Wellness"]["Out-of-Pocket"]["medical_annual"] == "$1,234"


# ------------------------------------------------------ no edit lost between endpoints
def _buffer_1():
    return load_active_config()[0].get("Liquidity Buffer", {}).get("buffer_1", {})


def test_edits_through_several_endpoints_keep_everything(ws, client):
    status, added = _post(client, "/api/note-receivable/add", {"name": "Seller Note"})
    assert status == 200
    resp = client.post("/api/liquidity-buffers", headers=HEADERS, json={"buffers": BUFFERS})
    assert resp.status_code == 200
    assert load_active_config()[0]["Note Receivable"][added["section"]]["name"] == "Seller Note"
    assert _buffer_1()["reserve_account"] == "Cash"
    status, trust = _post(client, "/api/trust-account/add", {"account_name": "T"})
    assert status == 200
    assert _buffer_1()["years_of_expenses"] == "2"
    assert load_active_config()[0]["Estate Planning"][trust["section"]]["account_name"] == "T"


def test_audit_events_are_recorded_after_the_edit(ws, client, monkeypatch):
    events = []
    monkeypatch.setattr(plan_routes, "_audit", lambda event, details=None: events.append((event, details)))
    _post(client, "/api/other-asset/add", {"asset_type": "Art"})
    _post(client, "/api/other-asset/delete", {"subsection": "Other Asset 99"})  # 404: nothing audited
    _post(client, "/api/wellness/seed")  # nothing missing: nothing audited
    assert [e for e, _ in events] == ["other_asset_item_added"]
