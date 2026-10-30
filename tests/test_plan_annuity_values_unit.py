"""Annuity/pension accounts valued from the plan's PV, not Monarch's hand-typed balance.

Design: documentation/future/superpowers/plans/2026-10-29-annuity-plan-values-design.md
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone

from financial_trends_reporter import balance_series as bser
from financial_trends_reporter import balance_store as bs
from financial_trends_reporter import plan_annuity_values as pav

TODAY = date(2026, 1, 10)
NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
PV = {"H Joint PV": 840_200.0, "W Joint PV": 351_033.0, "H Single PV": 95_096.0,
      "W Single PV": 87_122.0, "Pension PV": 71_992.0}


def _acct(key, name):
    return {"account_key": key, "display_name": name}


def test_each_mapped_account_takes_its_streams_pv():
    accounts = [_acct("mj", "Joint Annuity - Matt - 85 yo"), _acct("pp", "Pension - Pat - 85yo"),
                _acct("ira", "IRA - Matt")]
    aliases = {"Joint Annuity - Matt - 85 yo": "Annuity Joint - Matt", "Pension - Pat - 85yo": "Pension - Pat",
               "IRA - Matt": "IRA - Matt"}
    stream_of = {"Annuity Joint - Matt": "Member 1 Joint Annuity", "Pension - Pat": "Member 2 Pension"}
    assert pav.match_values(accounts, aliases, stream_of, PV) == {"mj": 840_200.0, "pp": 71_992.0}


def test_two_accounts_on_one_stream_keep_monarch():
    accounts = [_acct("a", "Joint A"), _acct("b", "Joint B"), _acct("s", "Single")]
    aliases = {"Joint A": "J1", "Joint B": "J2", "Single": "S"}
    stream_of = {"J1": "Member 1 Joint Annuity", "J2": "Member 1 Joint Annuity", "S": "Member 2 Single Annuity"}
    assert pav.match_values(accounts, aliases, stream_of, PV) == {"s": 87_122.0}


def test_no_build_or_unknown_stream_means_no_override():
    accounts = [_acct("a", "Joint A"), _acct("q", "QLAC")]
    aliases = {"Joint A": "J", "QLAC": "Q"}
    stream_of = {"J": "Member 1 Joint Annuity", "Q": "Member 1 QLAC"}
    assert pav.match_values(accounts, aliases, stream_of, {}) == {}
    assert pav.match_values(accounts, aliases, stream_of, PV) == {"a": 840_200.0}


def test_first_row_pv_reads_the_plan_start_row():
    doc = {"tables": {"net_worth": {"rows": [
        {"year": 2027, "values": {"H Joint PV": 1.0}},
        {"year": 2026, "values": {"H Joint PV": 840_200.0, "W Joint PV": "n/a", "TOTAL NW": 5.0}},
    ]}}}
    assert pav.first_row_pv(doc) == {"H Joint PV": 840_200.0}
    assert pav.first_row_pv({"missing": True}) == {}


def _seed(tmp_path):
    db, src = tmp_path / "b.sqlite3", tmp_path / "balances.csv"
    rows = [("2026-01-09", "ira", "IRA", 100.0), ("2026-01-10", "ira", "IRA", 110.0),
            ("2026-01-09", "annuity", "Annuity - X", 1000.0), ("2026-01-10", "annuity", "Annuity - X", 1000.0),
            ("2026-01-10", "late", "Late annuity", 50.0)]
    with src.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(bs.EXPECTED_HEADER)
        w.writerows(rows)
    assert bs.import_balances(db, src, today=TODAY, now=NOW)["success"]
    return db


def test_summary_and_chart_use_the_plan_value(tmp_path):
    db = _seed(tmp_path)
    plan = {"annuity": 700.0, "late": 40.0}
    s = bser.snapshot_summary(db, plan_values=plan)
    assert s["net_worth"] == 110 + 700 + 40
    row = next(r for r in s["by_account"] if r["account"] == "Annuity - X")
    assert row["value"] == 700.0 and row["source"] == "plan"
    assert "source" not in next(r for r in s["by_account"] if r["account"] == "IRA")

    p = bser.balances_payload(db, plan_values=plan)
    assert p["series"]["annuity"] == [700.0, 700.0]
    assert p["series"]["late"] == [0.0, 40.0]            # the account's own window is kept
    assert [pt["value"] for pt in p["points"]["networth"]] == [100 + 700, 110 + 700 + 40]


def test_without_plan_values_nothing_changes(tmp_path):
    db = _seed(tmp_path)
    assert bser.snapshot_summary(db)["net_worth"] == 110 + 1000 + 50
