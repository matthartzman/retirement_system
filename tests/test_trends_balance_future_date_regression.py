"""A future-dated balance row is rejected, so it cannot deactivate every other account (security review F-02)."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from financial_trends_reporter import balance_store

TODAY = date(2026, 11, 23)
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
GOOD = [("2026-11-22", "a", "A", 100.0), ("2026-11-22", "b", "B", 200.0), ("2026-11-22", "c", "C", 300.0)]


def _active(db):
    with sqlite3.connect(db) as c:
        return dict(c.execute("SELECT account_key, active FROM accounts").fetchall())


def test_future_dated_row_is_rejected_and_other_accounts_stay_active(tmp_path):
    db = tmp_path / "b.sqlite3"
    assert balance_store.import_balance_rows(db, GOOD, "good", now=NOW)["success"]
    # the fresh-export path (today given) is what a CSV import takes
    import csv
    src = tmp_path / "b.csv"
    with src.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(balance_store.EXPECTED_HEADER)
        w.writerows(GOOD + [("2099-01-01", "d", "D", 1.0)])
    res = balance_store.import_balances(db, src, today=TODAY, now=NOW)
    assert res["status"] == "rejected" and "future" in res["error"]
    assert _active(db) == {"a": 1, "b": 1, "c": 1}
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT status FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()[0] == "rejected"
        assert c.execute("SELECT COUNT(*) FROM balances WHERE date > '2026-12-01'").fetchone()[0] == 0


def test_tomorrow_is_still_accepted(tmp_path):
    db = tmp_path / "b.sqlite3"
    rows = [("2026-11-24", "a", "A", 1.0)]
    import csv
    src = tmp_path / "b.csv"
    with src.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(balance_store.EXPECTED_HEADER)
        w.writerows(rows)
    assert balance_store.import_balances(db, src, today=TODAY, now=NOW)["success"]


def test_mirror_path_rejects_a_far_future_row(tmp_path):
    db = tmp_path / "b.sqlite3"
    assert balance_store.import_balance_rows(db, GOOD, "good", now=NOW)["success"]
    res = balance_store.import_balance_rows(db, GOOD + [("2099-01-01", "d", "D", 1.0)], "mirror", now=NOW, mirror=True)
    assert res["status"] == "rejected"
    assert _active(db) == {"a": 1, "b": 1, "c": 1}
