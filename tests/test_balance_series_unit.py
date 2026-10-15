"""Phase 4 of the Monarch balances feed: daily series, chart totals, zero-hiding, source merge."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from financial_trends_reporter import account_registry as reg
from financial_trends_reporter import balance_series as bser
from financial_trends_reporter import balance_store as bs
from financial_trends_reporter.main import create_app

TODAY = date(2026, 1, 10)
NOW = datetime(2026, 1, 10, 4, 0, tzinfo=timezone.utc)


def _rows():
    # a: full range; closed: ends 01-03; gap: missing 01-04..01-05; late: starts 01-08
    rows = []
    for day in range(1, 11):
        d = f"2026-01-{day:02d}"
        rows.append((d, "a", 100.0 + day))
        if day <= 3:
            rows.append((d, "closed", 50.0))
        if day not in (4, 5):
            rows.append((d, "gap", 10.0 * day))
        if day >= 8:
            rows.append((d, "late", 7.0))
    return rows


def test_dense_series_carries_forward_inside_range_and_zeroes_outside():
    dates, s = bser.dense_series(_rows())
    assert dates[0] == "2026-01-01" and dates[-1] == "2026-01-10" and len(dates) == 10
    assert s["closed"] == [50.0, 50.0, 50.0] + [0.0] * 7           # closed account -> 0 afterwards
    assert s["late"] == [0.0] * 7 + [7.0] * 3                       # not yet open -> 0 before
    assert s["gap"][3:5] == [30.0, 30.0]                            # gap carries the last value forward
    assert len(s["a"]) == 10


def test_dense_series_fills_calendar_days_missing_from_every_account():
    dates, s = bser.dense_series([("2026-01-01", "a", 1.0), ("2026-01-04", "a", 4.0)])
    assert dates == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    assert s["a"] == [1.0, 1.0, 1.0, 4.0]


def test_a_late_syncing_account_carries_forward_but_an_old_closure_does_not():
    rows = [("2026-01-01", "a", 1.0), ("2026-01-10", "a", 1.0), ("2026-01-09", "late", 40.0), ("2026-01-02", "gone", 7.0)]
    dates, s = bser.dense_series(rows)
    assert s["late"][-1] == 40.0 and s["late"][-2] == 40.0      # last row one day before the newest date: still live
    assert s["gone"][1] == 7.0 and s["gone"][-1] == 0.0         # stopped eight days before: closed


def test_empty_input():
    assert bser.dense_series([]) == ([], {})


def test_totals_are_the_sum_of_enabled_accounts_and_order_independent():
    dates, s = bser.dense_series(_rows())
    n = len(dates)
    total_all = bser.chart_totals(s, list(s), n)
    for i in range(n):
        assert total_all[i] == pytest.approx(sum(s[k][i] for k in s), abs=0.01)
    rng = random.Random(7)
    for _ in range(25):
        subset = rng.sample(list(s), rng.randint(0, len(s)))
        shuffled = subset[:]
        rng.shuffle(shuffled)
        assert bser.chart_totals(s, subset, n) == bser.chart_totals(s, shuffled, n)
        assert bser.chart_totals(s, subset, n) == [
            round(sum(s[k][i] for k in subset), 2) for i in range(n)
        ]
    assert bser.chart_totals(s, ["ghost"], n) == [0.0] * n       # unknown keys ignored


def test_liabilities_stay_negative_in_net_worth():
    _, s = bser.dense_series([("2026-01-01", "house", 500.0), ("2026-01-01", "mortgage", -200.0)])
    assert bser.chart_totals(s, ["house", "mortgage"], 1) == [300.0]


def _accounts(types=None):
    types = types or {}
    out = []
    for key in ("a", "closed", "gap", "late"):
        t = types.get(key, "Cash")
        out.append({"account_key": key, "display_name": key.title(), "type": t,
                    "enabled": {c: reg.default_enabled(c, t) for c in reg.CHARTS}})
    return out


def test_detail_omits_zero_value_accounts_and_sorts_by_size():
    dates, s = bser.dense_series(_rows())
    day9 = dates.index("2026-01-09")
    keys = [d["account_key"] for d in bser.account_detail(_accounts(), s, day9, "networth")]
    assert "closed" not in keys                                    # zero on that date
    assert keys == ["a", "gap", "late"]                            # 109 > 90(gap carries 10*9) > 7
    day2 = dates.index("2026-01-02")
    assert "late" not in [d["account_key"] for d in bser.account_detail(_accounts(), s, day2, "networth")]


def test_detail_respects_chart_membership():
    dates, s = bser.dense_series(_rows())
    accts = _accounts({"gap": "Annuity/Pension"})
    keys = [d["account_key"] for d in bser.account_detail(accts, s, 8, "holdings")]
    assert "gap" not in keys and "a" in keys


def test_merge_uses_monarch_where_present_and_plan_elsewhere():
    history = [
        {"as_of_date": "2025-12-31", "net_worth": {"total": 111.5}},
        {"as_of_date": "2026-01-02", "net_worth": {"total": 999.0}},     # Monarch covers this date
        {"as_of_date": "2026-01-11", "net_worth": {"total": 222.0}},
        {"as_of_date": "2026-01-12", "net_worth": {}},                   # no figure -> skipped
    ]
    pts = bser.merge_with_log(["2026-01-01", "2026-01-02"], [1.0, 2.0], history, bser._plan_networth)
    assert [(p["date"], p["value"], p["source"]) for p in pts] == [
        ("2025-12-31", 111.5, "plan"), ("2026-01-01", 1.0, "monarch"),
        ("2026-01-02", 2.0, "monarch"), ("2026-01-11", 222.0, "plan"),
    ]


# ---- store-backed ---------------------------------------------------------------------

def _seed(tmp_path):
    db = tmp_path / "b.sqlite3"
    src = tmp_path / "balances.csv"
    rows = [
        ("2026-01-09", "ira", "IRA", 100.0), ("2026-01-10", "ira", "IRA", 110.0),
        ("2026-01-09", "checking", "Checking", 20.0), ("2026-01-10", "checking", "Checking", 25.0),
        ("2026-01-09", "annuity", "Annuity - X", 1000.0), ("2026-01-10", "annuity", "Annuity - X", 1000.0),
        ("2026-01-09", "mortgage", "Mortgage", -300.0), ("2026-01-10", "mortgage", "Mortgage", -299.0),
    ]
    with src.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(bs.EXPECTED_HEADER)
        w.writerows(rows)
    assert bs.import_balances(db, src, today=TODAY, now=NOW)["success"]
    return db


def test_payload_applies_saved_toggles_and_the_holdings_definition(tmp_path):
    db = _seed(tmp_path)
    p = bser.balances_payload(db)
    nw = {pt["date"]: pt["value"] for pt in p["points"]["networth"]}
    h = {pt["date"]: pt["value"] for pt in p["points"]["holdings"]}
    assert nw["2026-01-10"] == 110 + 25 + 1000 - 299
    assert h["2026-01-10"] == 110 + 25                    # annuity and mortgage excluded from Holdings
    reg.set_prefs(db, [{"chart": "holdings", "account_key": "annuity", "enabled": True},
                       {"chart": "networth", "account_key": "mortgage", "enabled": False}])
    p = bser.balances_payload(db)
    assert {pt["date"]: pt["value"] for pt in p["points"]["holdings"]}["2026-01-10"] == 110 + 25 + 1000
    assert {pt["date"]: pt["value"] for pt in p["points"]["networth"]}["2026-01-10"] == 110 + 25 + 1000


def test_snapshot_summary(tmp_path):
    db = _seed(tmp_path)
    s = bser.snapshot_summary(db)
    assert s["latest_date"] == "2026-01-10" and s["net_worth"] == 836.0 and s["holdings"] == 135.0
    assert {r["account"] for r in s["by_account"]} == {"IRA", "Checking", "Annuity - X", "Mortgage"}
    assert bser.snapshot_summary(tmp_path / "missing.sqlite3") is None


def test_balances_endpoint(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "input").mkdir(parents=True)
    data = tmp_path / "data"
    data.mkdir()
    _seed(tmp_path).replace(data / bs.DB_FILENAME)
    log = data / "log.jsonl"
    log.write_text(json.dumps({"as_of_date": "2025-12-31", "net_worth": {"total": 5.0}, "holdings": {"current_value": 4.0}}) + "\n", encoding="utf-8")
    body = json.loads(create_app(workspace, log_path=log).test_client().get("/api/balances").get_data(as_text=True))
    assert body["dates"] == ["2026-01-09", "2026-01-10"]
    assert body["points"]["networth"][0] == {"date": "2025-12-31", "value": 5.0, "source": "plan"}
    assert set(body["series"]) == {"ira", "checking", "annuity", "mortgage"}
    assert body["freshness"]["last_ok"]["latest_date"] == "2026-01-10"


_REAL = Path(__file__).resolve().parent.parent / "financial_trends_reporter" / "data" / bs.DB_FILENAME


@pytest.mark.skipif(not _REAL.exists(), reason="local Monarch balance store not present")
def test_real_store_series_reproduces_every_stored_balance_and_zeroes_closed_accounts():
    rows = bser.load_rows(_REAL)
    dates, s = bser.dense_series(rows)
    index = {d: i for i, d in enumerate(dates)}
    assert all(s[k][index[d]] == pytest.approx(b) for d, k, b in rows)
    last = len(dates) - 1
    by_key = {a["account_key"]: a for a in reg.list_accounts(_REAL)}
    assert all(s[k][last] == 0.0 for k, a in by_key.items() if not a["active"])
