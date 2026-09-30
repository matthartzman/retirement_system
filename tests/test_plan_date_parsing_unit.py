"""WI-401 (system review 2026-09-25-2, QA-001): one shared plan-date parser.

Household DOB and retirement dates used to go through three different
two-digit-year rules (raw in ``data_io._y``, +2000 in ``_date_parts``, a pivot
at 40 in the UI/grid-save normalizer). A couple plan whose member_1_dob
reached parse_client as '8/3/62' got birth year 62 and death year 154, so the
member was dead in every plan year and the plan silently projected as a
lone-survivor household. A missing DOB row silently became 8/3/1962.

These tests pin the single rule (``src/plan_dates.py``), the schema 'date'
branch and non-finite rejection in ``validate_value``, the hard error for a
missing/blank/2-digit DOB in parse_client, and the birth-year plausibility
gate in ``ensure_engine_config``.
"""
from __future__ import annotations

import copy

import pytest

from conftest import TEST_INPUT_DIR
from src import plan_dates
from src.data_io import _date_parts, _last_earned_income_year_from_retirement_date, load_csv, parse_client
from src.schema_registry import validate_value
from src.server.app_core import _normalize_date_for_csv


# ---------------------------------------------------------------- shared parser

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("8/3/1962", (1962, 8, 3)),
        ("8/3/62", (1962, 8, 3)),        # yy > 40 -> 19yy
        ("1/1/27", (2027, 1, 1)),        # yy <= 40 -> 20yy
        ("1/1/40", (2040, 1, 1)),        # pivot boundary stays 20yy
        ("1/1/41", (1941, 1, 1)),
        ("1962-08-03", (1962, 8, 3)),
        ("2027-01-01T00:00:00", (2027, 1, 1)),
        ("2027", (2027, 12, 31)),        # bare year keeps the engine's Dec 31 reading
        ("", None),
        ("   ", None),
        (None, None),
        ("not a date", None),
        ("2/30/2027", None),             # calendar-impossible
        ("13/1/2027", None),
        ("nan", None),
    ],
)
def test_parse_plan_date(raw, expected):
    assert plan_dates.parse_plan_date(raw) == expected


def test_bare_year_start_option():
    assert plan_dates.parse_plan_date("2027", bare_year_as="start") == (2027, 1, 1)


@pytest.mark.parametrize("raw", ["8/3/62", "1/1/27", "1962-08-03", "2027", ""])
def test_data_io_date_parts_uses_the_shared_rule(raw):
    assert _date_parts(raw) == plan_dates.parse_plan_date(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [("8/3/62", "1962-08-03"), ("1/1/27", "2027-01-01"), ("8/3/1962", "1962-08-03")],
)
def test_server_grid_normalizer_agrees_with_engine_century_rule(raw, expected):
    assert _normalize_date_for_csv(raw) == expected
    y, m, d = plan_dates.parse_plan_date(raw)
    assert expected == f"{y:04d}-{m:02d}-{d:02d}"


def test_retirement_date_two_digit_year_is_not_a_raw_year():
    # '1/1/27' used to reach _y as int('27'); last earned year is 2026.
    assert _last_earned_income_year_from_retirement_date("1/1/27", 0) == 2026
    assert _last_earned_income_year_from_retirement_date("2027", 0) == 2027


# ------------------------------------------------------------ validate_value

DATE_SPEC = {"type": "date", "required": "TRUE"}


@pytest.mark.parametrize("raw", ["8/3/1962", "1962-08-03", "2027", "06/2029", "2029-06"])
def test_validate_value_accepts_unambiguous_dates(raw):
    assert validate_value(raw, DATE_SPEC) == []


@pytest.mark.parametrize("raw", ["8/3/62", "not a date", "2/30/2027", "nan", "inf"])
def test_validate_value_rejects_bad_dates(raw):
    assert validate_value(raw, DATE_SPEC), raw


def test_validate_value_blank_required_date():
    assert validate_value("", DATE_SPEC) == ["required value missing"]


@pytest.mark.parametrize("typ", ["number", "currency", "integer", "percent"])
@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_validate_value_rejects_non_finite_numbers(typ, raw):
    value = raw + "%" if typ == "percent" else raw
    errors = validate_value(value, {"type": typ, "min": "0", "max": "100"})
    assert any("finite" in e for e in errors), (typ, raw, errors)


# ------------------------------------------------------------- parse_client

@pytest.fixture(scope="module")
def frozen_data():
    return load_csv(TEST_INPUT_DIR / "client_data.csv")


def _with_household(data, **overrides):
    d = copy.deepcopy(data)
    hh = d["Household"][""]
    for k, v in overrides.items():
        if v is None:
            hh.pop(k, None)
        else:
            hh[k] = v
    return d


@pytest.mark.parametrize("label", ["member_1_dob", "member_2_dob"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_couple_plan_missing_or_blank_dob_is_a_hard_error(frozen_data, label, value):
    with pytest.raises(ValueError, match=label):
        parse_client(_with_household(frozen_data, **{label: value}), "")


@pytest.mark.parametrize("label", ["member_1_dob", "member_2_dob"])
def test_couple_plan_two_digit_dob_raises_instead_of_projecting(frozen_data, label):
    with pytest.raises(ValueError, match="2-digit year"):
        parse_client(_with_household(frozen_data, **{label: "8/3/62"}), "")


def test_unparseable_dob_raises(frozen_data):
    with pytest.raises(ValueError, match="member_1_dob"):
        parse_client(_with_household(frozen_data, member_1_dob="sometime in 1962"), "")


def test_single_household_does_not_need_member_2_dob(frozen_data):
    c = parse_client(_with_household(frozen_data, member_2_name="", member_2_dob=None), "")
    assert c["household_size"] == 1
    assert c["h_dob_yr"] == 1962


def test_iso_dob_parses(frozen_data):
    c = parse_client(_with_household(frozen_data, member_1_dob="1962-08-03"), "")
    assert (c["h_dob_yr"], c["h_dob_month"]) == (1962, 8)


def test_implausible_birth_year_is_rejected(frozen_data):
    # A far-future DOB passes every other demographic gate; the plausibility
    # gate in ensure_engine_config must catch it.
    with pytest.raises(ValueError, match="implausible birth year"):
        parse_client(_with_household(frozen_data, member_1_dob="8/3/2090"), "")
