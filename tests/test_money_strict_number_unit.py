"""WI-008 / QA-003: one strict shared number parser (src/money.py) used by the CSV validator and
the data_io holdings/liabilities blocks. nan/inf/garbage never reach the engine."""
from __future__ import annotations

import logging
import math
from decimal import Decimal

import pytest

import src.plan_datasets as plan_datasets
from src.csv_exchange.core import parse, validate
from src.data_io import parse_client
from src.money import (cents_from_user_value, decimal_from_user_value, is_strict_number,
                       parse_strict_number, strict_float)
from tests.golden_pricing import frozen_holdings_prices
from tests.plan_fixture import plan_data
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace

BAD = ["nan", "NaN", "inf", "-inf", "Infinity", "abc", "1e999", "12abc", "--5", "(5,000", "1_000"]


# --------------------------------------------------------------------------- money helpers
@pytest.mark.parametrize("raw,expected", [
    ("1000", "1000"), ("$1,000.50", "1000.50"), ("(5,000)", "-5000"), ("($5,000.25)", "-5000.25"),
    ("-3", "-3"), ("+3", "3"), (" 7 ", "7"), ("6%", "0.06"), ("(2%)", "-0.02"), (12, "12"),
    (1.5, "1.5"), (Decimal("2.5"), "2.5"), ("€1,000", "1000"), (".5", "0.5"),
])
def test_parse_strict_number_accepts(raw, expected):
    assert parse_strict_number(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", BAD + ["", "  ", None, True, float("nan"), float("inf")])
def test_parse_strict_number_rejects(raw):
    with pytest.raises(ValueError):
        parse_strict_number(raw)


def test_blank_uses_default_and_percent_flag():
    assert parse_strict_number("", 0) == Decimal(0)
    assert parse_strict_number(None, Decimal("3")) == Decimal(3)
    assert parse_strict_number("6%", percent_as_fraction=False) == Decimal(6)
    assert strict_float("(5,000)") == -5000.0 and isinstance(strict_float("1"), float)
    assert strict_float("", 2.5) == 2.5
    with pytest.raises(ValueError):
        strict_float("nan", 0.0)  # a default never masks a bad (non-blank) cell


@pytest.mark.parametrize("raw,ok", [("1", True), ("(5,000)", True), ("$1,000.00", True), ("nan", False),
                                    ("inf", False), ("abc", False), ("", False)])
def test_is_strict_number(raw, ok):
    assert is_strict_number(raw) is ok


def test_legacy_helpers_still_default_and_round():
    assert decimal_from_user_value("") == Decimal(0)
    assert decimal_from_user_value("$1,234.50") == Decimal("1234.50")
    assert decimal_from_user_value("5%") == Decimal("0.05")
    assert decimal_from_user_value("garbage", Decimal(9)) == Decimal(9)
    assert cents_from_user_value("$1.005") == 101
    assert cents_from_user_value(None, 250) == 250


# --------------------------------------------------------------------------- CSV validator
@pytest.mark.parametrize("cell,is_error", [("nan", True), ("inf", True), ("abc", True),
                                           ("(5,000)", False), ("$1,000.00", False)])
@pytest.mark.parametrize("dataset,body", [
    ("holdings", "account,symbol,shares,purchase_price\nA,VTI,10,\"{cell}\"\n"),
    ("liabilities", "liability_id,type,label,balance\nL1,auto,Car,\"{cell}\"\n"),
])
def test_validator_flags_bad_numeric_cells(dataset, body, cell, is_error):
    last = "purchase_price" if dataset == "holdings" else "balance"
    errs = [i for i in validate(parse(body.format(cell=cell), dataset))
            if i.level == "error" and i.column == last]
    assert bool(errs) is is_error


# --------------------------------------------------------------------------- data_io blocks
def _build(monkeypatch, **texts):
    real = plan_datasets.active_dataset_text
    monkeypatch.setattr(plan_datasets, "active_dataset_text",
                        lambda name, **kw: texts[name] if name in texts else real(name, **kw))
    with empty_workspace(), frozen_holdings_prices():
        return parse_client(plan_data("sample_frozen"), "")


LIAB_HEAD = "liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year\n"
GOOD_LIAB = "L1,auto,Car,10000,0.05,300,2024,2030\n"


@pytest.mark.parametrize("cell", ["nan", "inf", "abc"])
@pytest.mark.parametrize("column", ["balance", "interest_rate", "monthly_payment"])
def test_liabilities_bad_cell_skips_row_warns_and_keeps_others(monkeypatch, caplog, cell, column):
    row = {"balance": "7000", "interest_rate": "0.06", "monthly_payment": "100"}
    row[column] = cell
    bad = f"L2,credit_card,Card,{row['balance']},{row['interest_rate']},{row['monthly_payment']},2024,2030\n"
    with caplog.at_level(logging.WARNING, logger="src.data_io"):
        c = _build(monkeypatch, liabilities=LIAB_HEAD + GOOD_LIAB + bad)
    assert [l["liability_id"] for l in c["liabilities"]] == ["L1"], "good liability must survive"
    assert any("L2" in m and "skipped" in m for m in c["config_contract_warnings"])
    assert any("L2" in r.getMessage() for r in caplog.records)


def test_liabilities_parenthesised_values_are_numbers_not_failures(monkeypatch):
    # (5,000) is -5000: a valid number. As a balance it is dropped by the existing balance <= 0 rule,
    # without emptying the list and without a skip warning.
    c = _build(monkeypatch, liabilities=LIAB_HEAD + GOOD_LIAB + 'L2,other,X,"(5,000)",0.05,100,2024,2030\n')
    assert [l["liability_id"] for l in c["liabilities"]] == ["L1"]
    assert not any("skipped" in m for m in c.get("config_contract_warnings", []))


def test_liabilities_all_good_unchanged(monkeypatch):
    c = _build(monkeypatch, liabilities=LIAB_HEAD + GOOD_LIAB + 'L2,other,X,"$2,500",6%,100,2024,2030\n')
    assert [l["balance"] for l in c["liabilities"]] == [10000.0, 2500.0]
    assert c["liabilities"][1]["interest_rate"] == pytest.approx(0.06)
    for l in c["liabilities"]:
        assert all(math.isfinite(v) for v in l.values() if isinstance(v, float))


HOLD_HEAD = "account,symbol,shares,purchase_price,purchase_date,lot_type\n"


@pytest.mark.parametrize("cell", ["nan", "inf", "abc"])
@pytest.mark.parametrize("column", ["shares", "purchase_price"])
def test_holdings_bad_cell_skips_lot_and_warns(monkeypatch, caplog, cell, column):
    vals = {"shares": "10", "purchase_price": "50"}
    vals[column] = cell
    text = (HOLD_HEAD + "Member_1_IRA,VTI,100000,50,2020-01-01,buy\n"
            + f"Member_1_IRA,ZZBAD,{vals['shares']},{vals['purchase_price']},2020-01-01,buy\n")
    with caplog.at_level(logging.WARNING, logger="src.data_io"):
        c = _build(monkeypatch, holdings=text)
    lots = c["lots_by_account"]["Member_1_IRA"]
    assert "VTI" in lots and "ZZBAD" not in lots
    assert any("ZZBAD" in m for m in c["config_contract_warnings"])
    assert any("ZZBAD" in r.getMessage() for r in caplog.records)


def test_holdings_parenthesised_shares_are_negative_and_skipped_without_error(monkeypatch):
    text = HOLD_HEAD + 'Member_1_IRA,VTI,100000,50,2020-01-01,buy\nMember_1_IRA,ZZNEG,"(100)",50,2020-01-01,buy\n'
    c = _build(monkeypatch, holdings=text)
    assert "ZZNEG" not in c["lots_by_account"]["Member_1_IRA"]
    assert "VTI" in c["lots_by_account"]["Member_1_IRA"]
