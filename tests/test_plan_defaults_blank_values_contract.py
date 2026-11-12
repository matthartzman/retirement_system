"""Blank plan values mean the schema default, never one household's figures.

System review 2026-11-10, W1-04 / QA-001. Contract tests:
* a blank-mortgage / blank-home plan projects no mortgage and no home;
* every constant default a parser passes to ``_v`` equals the schema.csv default
  (the remaining known disagreements are listed, and the list may only shrink);
* the household-specific dollar literals are gone from the CSV parser;
* an unreadable dollar or rate value is a validation error;
* /api/build/start refuses to start while preflight reports blockers.
"""
from __future__ import annotations

import ast
import csv
import re
from pathlib import Path

import pytest

import src.server.app_core as app_core
from src.data_io import parse_client
from src.server import app
from tests.plan_fixture import make_plan

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    return plan


def _blank_plan_config(ws):
    app_core._blank_plan_rows()
    data = ws.store_data()
    # A blank plan cannot be parsed until these identity facts are entered; everything
    # else in the assertions below stays blank.
    data["Household"][""]["member_1_dob"] = "1/1/1960"
    data["Household"][""]["member_2_dob"] = "1/1/1962"
    data["Household"][""]["residence_state"] = "Illinois"
    return parse_client(data, "", skip_live_pricing=True)


def test_blank_plan_has_no_mortgage_no_home_and_no_earned_income(ws):
    c = _blank_plan_config(ws)
    assert c["mort_bal"] == 0 and c["mort_pmt"] == 0 and c["mort_rate"] == 0
    assert c["home_val"] == 0
    assert c["earned"] == 0
    assert c["ltc_face"] == 0
    assert all(v == 0 for v in c["mort_schedule"].values())
    assert all(v == 0 for v in c["mort_interest_schedule"].values())


def test_blank_s_corp_salary_is_the_schema_default(ws):
    c = _blank_plan_config(ws)
    assert c["scorp_salary"] == 60000  # reference_src/schema.csv default, not the old 80000


def test_household_specific_dollar_literals_are_gone_from_the_csv_parser():
    text = (ROOT / "src" / "parsing" / "client_sections.py").read_text(encoding="utf-8")
    for literal in ("293284", "1313000", "290000", "225000", "0.0199"):
        assert not re.search(r"[\s'\"(,]" + re.escape(literal) + r"[\s'\"),]", text), literal


# --- parser defaults agree with the schema ------------------------------------------------

# Pre-existing disagreements between a parser literal and schema.csv. None is a dollar figure
# from the QA-001 list. This set may only shrink: fix the parser (or the schema) and delete the row.
KNOWN_DEFAULT_DISAGREEMENTS = {
    ("Household", "", "member_1_name"): "household name literal",
    ("Household", "", "member_2_name"): "household name literal",
    ("Household", "", "member_1_retirement_date"): "household date literal",
    ("Household", "", "member_2_retirement_date"): "household date literal",
    ("Cashflow", "Earned Income", "entity_type"): "sole_prop vs schema s_corp",
    ("Model Constants", "Retirement", "member_1_rmd_start_age"): "blank means statutory age",
    ("Model Constants", "Retirement", "member_2_rmd_start_age"): "blank means statutory age",
    ("Economic Assumptions", "", "annuity_default_dividend_rate"): "5.75% vs 5.00%",
    ("Wellness", "Medicare", "part_d_base_premium_monthly"): "40 vs 55",
    ("Wellness", "Out-of-Pocket", "annual_oop_estimate_today"): "8000 vs 10000",
    ("Scenarios", "Sell Home", "home_sale_year"): "2035 vs 2045",
    ("Model Constants", "Capital Gains", "ltcg_0pct_top_mfj_base_year"): "blank means tax-law table",
    ("Model Constants", "Capital Gains", "ltcg_15pct_top_mfj_base_year"): "blank means tax-law table",
    ("Economic Assumptions", "", "fed_tax_bracket_inflator"): "blank means engine default",
    ("Economic Assumptions", "", "tax_law_scenario"): "blank means engine default",
    ("Other Assets", "Home", "home_sale_proceeds_account"): "blank means no account",
    ("Scenarios", "Sell Home", "home_sale_proceeds_account"): "blank means no account",
    ("Model Constants", "Monte Carlo", "mc_simulations"): "1000 vs 300",
    ("Model Constants", "Monte Carlo", "mc_sensitivity_simulations"): "200 vs 25",
    ("Household", "", "mfs_lived_apart"): "blank vs FALSE",
    ("DAF", "Settings", "grant_start_year"): "household year literal",
    ("DAF", "Settings", "grant_end_year"): "household year literal",
}


def _norm(text):
    text = str(text).strip()
    if text == "":
        return 0.0  # a blank numeric default means zero
    try:
        if text.endswith("%"):
            return round(float(text[:-1].replace(",", "")) / 100, 10)
        return round(float(text.replace(",", "").replace("$", "")), 10)
    except ValueError:
        return text.lower()


def _constant_v_defaults():
    schema = {}
    with open(ROOT / "reference_src" / "schema.csv", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            schema[(row["section"].strip(), row["subsection"].strip(), row["label"].strip())] = row["default"]
    found = {}
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_v"
                and len(node.args) >= 5
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args[1:5])
            ):
                key = tuple(a.value for a in node.args[1:4])
                if key in schema and _norm(schema[key]) != _norm(node.args[4].value):
                    found[key] = f"{path.name}:{node.lineno} default {node.args[4].value!r} vs schema {schema[key]!r}"
    return found


def test_every_parser_default_equals_the_schema_default():
    disagreements = _constant_v_defaults()
    new = {k: v for k, v in disagreements.items() if k not in KNOWN_DEFAULT_DISAGREEMENTS}
    assert not new, f"parser default disagrees with reference_src/schema.csv: {new}"
    stale = [k for k in KNOWN_DEFAULT_DISAGREEMENTS if k not in disagreements]
    assert not stale, f"fixed; remove from KNOWN_DEFAULT_DISAGREEMENTS: {stale}"


# --- unreadable values ----------------------------------------------------------------------

def test_an_unreadable_dollar_value_is_reported_and_blocks_validation(ws):
    from src.schema_registry import load_schema, validate_value

    data = ws.store_data()
    data["Cashflow"]["Mortgage"]["balance_as_of_plan_start"] = "about 300k"
    c = parse_client(data, "", skip_live_pricing=True)
    assert {"section": "Cashflow", "subsection": "Mortgage", "label": "balance_as_of_plan_start",
            "value": "about 300k"} in c["unreadable_values"]
    spec = load_schema()[("Cashflow", "Mortgage", "balance_as_of_plan_start")]
    assert validate_value("about 300k", spec), "schema validation must reject an unreadable dollar value"
    assert not validate_value("293,284", spec)


def test_a_clean_plan_reports_no_unreadable_values(ws):
    assert parse_client(ws.store_data(), "", skip_live_pricing=True)["unreadable_values"] == []


# --- build start ------------------------------------------------------------------------------

def test_build_start_is_refused_while_preflight_has_blockers(ws):
    app_core._blank_plan_rows()  # required Plan Data values are now blank
    client = app.test_client()
    resp = client.post("/api/build/start", headers=HEADERS)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["success"] is False and body["blockers"] and "job_id" not in body
