"""WI-402 (system review 2026-09-25-2, QA-002): the frozen fixture's household
fields must actually be READ by parse_client.

The frozen fixture's member_1_dob (8/3/1962), member_2_dob (5/30/1961),
member_1_retirement_date (2027-01-01) and mortality ages (92/95) coincide with
the literal fallbacks parse_client historically used when those rows were
missing. So if parse_client stopped reading one of them (e.g. after a label
rename), the pinned terminal NW and lifetime tax would not move and the golden
master would stay green.

This test closes that blind spot independently of whether parse_client still
has fallbacks: it first checks parse_client's output against values derived
straight from the fixture CSV rows, then re-parses with every household field
replaced by a sentinel that matches no fallback, and asserts the sentinels
come through. A planted rename of any of these labels in parse_client fails
the second half even though the first half would still coincide.
"""
from __future__ import annotations

import copy
import csv
from pathlib import Path

import pytest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client

FIXTURE_HOUSEHOLD = Path(__file__).resolve().parent / "fixtures" / "sample_plan_frozen" / "client_household.csv"

LABELS = (
    "member_1_dob",
    "member_2_dob",
    "member_1_retirement_date",
    "member_2_retirement_date",
    "member_1_mortality_age",
    "member_2_mortality_age",
)


def _fixture_household_rows() -> dict[str, str]:
    out = {}
    with FIXTURE_HOUSEHOLD.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if (row.get("section") or "").strip() == "Household" and (row.get("label") or "").strip() in LABELS:
                out[row["label"].strip()] = (row.get("value") or "").strip()
    return out


def _year(raw: str) -> int:
    # Independent of src/plan_dates on purpose: the fixture uses only
    # M/D/YYYY and YYYY-MM-DD, both of which carry a 4-digit year.
    return int(raw[:4]) if "-" in raw else int(raw.split("/")[-1])


@pytest.fixture(scope="module")
def frozen_data():
    return load_csv(TEST_INPUT_DIR / "client_data.csv")


def test_fixture_has_every_household_row():
    rows = _fixture_household_rows()
    assert set(rows) == set(LABELS), f"frozen fixture is missing household rows: {set(LABELS) - set(rows)}"


def test_parse_client_matches_fixture_csv_rows(frozen_data):
    rows = _fixture_household_rows()
    c = parse_client(copy.deepcopy(frozen_data), "")
    assert c["h_dob_yr"] == _year(rows["member_1_dob"])
    assert c["w_dob_yr"] == _year(rows["member_2_dob"])
    assert c["h_ret_yr"] == _year(rows["member_1_retirement_date"])
    assert c["w_ret_yr"] == _year(rows["member_2_retirement_date"])
    assert c["h_mort_age"] == float(rows["member_1_mortality_age"])
    assert c["w_mort_age"] == float(rows["member_2_mortality_age"])


def test_parse_client_reads_each_household_field_not_a_fallback(frozen_data):
    """Sentinels that match no parse_client fallback literal must come through."""
    data = copy.deepcopy(frozen_data)
    hh = data["Household"][""]
    hh["member_1_dob"] = "4/11/1958"
    hh["member_2_dob"] = "9/17/1964"
    hh["member_1_retirement_date"] = "7/1/2029"
    hh["member_2_retirement_date"] = "3/15/2030"
    hh["member_1_mortality_age"] = "97"
    hh["member_2_mortality_age"] = "88"

    c = parse_client(data, "")

    assert (c["h_dob_yr"], c["h_dob_month"]) == (1958, 4)
    assert (c["w_dob_yr"], c["w_dob_month"]) == (1964, 9)
    assert c["h_ret_yr"] == 2029
    assert c["w_ret_yr"] == 2030
    assert c["h_earned_last_year"] == 2029  # mid-year retirement keeps that year's earnings
    assert c["h_mort_age"] == 97
    assert c["w_mort_age"] == 88
    assert c["h_death_yr"] == 1958 + 97
    assert c["w_death_yr"] == 1964 + 88
