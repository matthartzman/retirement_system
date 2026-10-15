"""Phase 2 of the Monarch balances feed: the guarded SQLite import."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone

from financial_trends_reporter import balance_store as bs

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)


def _csv(tmp_path, rows, name="balances.csv", header=None):
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header or bs.EXPECTED_HEADER)
        w.writerows(rows)
    return path


def _rows(n_accounts=3, days=("2026-10-13", "2026-10-14")):
    return [(d, f"acct{i}", f"Acct {i}", 100.0 * (i + 1)) for i in range(n_accounts) for d in days]


def _count(db, table):
    conn = bs.connect(db)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_import_is_idempotent(tmp_path):
    db = tmp_path / "b.sqlite3"
    src = _csv(tmp_path, _rows())
    first = bs.import_balances(db, src, today=TODAY, now=NOW)
    second = bs.import_balances(db, src, today=TODAY, now=NOW)
    assert first["success"] and second["success"]
    assert first["rows"] == 6 and first["accounts"] == 3
    assert _count(db, "balances") == 6 and _count(db, "accounts") == 3


def test_reimport_refreshes_changed_history(tmp_path):
    db = tmp_path / "b.sqlite3"
    bs.import_balances(db, _csv(tmp_path, _rows()), today=TODAY, now=NOW)
    changed = _rows()
    changed[0] = (changed[0][0], changed[0][1], changed[0][2], 999.0)
    bs.import_balances(db, _csv(tmp_path, changed, "b2.csv"), today=TODAY, now=NOW)
    conn = bs.connect(db)
    try:
        assert conn.execute("SELECT balance FROM balances WHERE date='2026-10-13' AND account_key='acct0'").fetchone()[0] == 999.0
    finally:
        conn.close()


def test_first_last_seen_and_active_flag(tmp_path):
    db = tmp_path / "b.sqlite3"
    rows = _rows() + [("2026-09-01", "closed", "Closed Acct", 5.0)]
    bs.import_balances(db, _csv(tmp_path, rows), today=TODAY, now=NOW)
    conn = bs.connect(db)
    try:
        closed = conn.execute("SELECT * FROM accounts WHERE account_key='closed'").fetchone()
        live = conn.execute("SELECT * FROM accounts WHERE account_key='acct0'").fetchone()
    finally:
        conn.close()
    assert (closed["first_seen"], closed["last_seen"], closed["active"]) == ("2026-09-01", "2026-09-01", 0)
    assert (live["first_seen"], live["last_seen"], live["active"]) == ("2026-10-13", "2026-10-14", 1)


def test_bad_header_is_rejected_and_nothing_written(tmp_path):
    db = tmp_path / "b.sqlite3"
    result = bs.import_balances(db, _csv(tmp_path, _rows(), header=["Date", "Balance", "Account", "x"]), today=TODAY, now=NOW)
    assert not result["success"] and result["status"] == "rejected"
    assert _count(db, "balances") == 0
    assert _count(db, "import_runs") == 1


def test_bad_value_is_rejected(tmp_path):
    db = tmp_path / "b.sqlite3"
    result = bs.import_balances(db, _csv(tmp_path, [("2026-10-14", "a", "A", "abc")]), today=TODAY, now=NOW)
    assert not result["success"] and _count(db, "balances") == 0


def test_stale_export_is_rejected(tmp_path):
    db = tmp_path / "b.sqlite3"
    result = bs.import_balances(db, _csv(tmp_path, _rows(days=("2026-10-10",))), today=TODAY, now=NOW)
    assert not result["success"] and "stale" in result["error"]


def test_account_count_drop_is_rejected_but_small_drop_allowed(tmp_path):
    db = tmp_path / "b.sqlite3"
    assert bs.import_balances(db, _csv(tmp_path, _rows(10)), today=TODAY, now=NOW)["success"]
    big = bs.import_balances(db, _csv(tmp_path, _rows(7), "b2.csv"), today=TODAY, now=NOW)
    assert not big["success"] and "fell from 10 to 7" in big["error"]
    assert bs.import_balances(db, _csv(tmp_path, _rows(9), "b3.csv"), today=TODAY, now=NOW)["success"]


def test_missing_file_is_rejected(tmp_path):
    result = bs.import_balances(tmp_path / "b.sqlite3", tmp_path / "nope.csv", today=TODAY, now=NOW)
    assert not result["success"]


def test_freshness_reports_last_good_run(tmp_path):
    db = tmp_path / "b.sqlite3"
    bs.import_balances(db, _csv(tmp_path, _rows()), today=TODAY, now=NOW)
    bs.import_balances(db, tmp_path / "nope.csv", today=TODAY, now=NOW)
    f = bs.freshness(db)
    assert f["last_run"]["status"] == "rejected" and f["last_ok"]["latest_date"] == "2026-10-14"


def test_trends_job_stores_balances_beside_its_log(tmp_path):
    """The job's best-effort import must write next to the log it was given, never the real data dir."""
    from financial_trends_reporter import trends_job

    log = tmp_path / "data" / "log.jsonl"
    log.parent.mkdir()
    out = tmp_path / "Monarch Extractor" / "output"
    out.mkdir(parents=True)
    _csv(out, _rows())
    # compute_snapshot needs a real workspace; the import step alone is what is under test.
    result = bs.import_balances(log.with_name(bs.DB_FILENAME), bs.default_source_path(tmp_path), today=TODAY, now=NOW)
    assert result["success"]
    assert (tmp_path / "data" / bs.DB_FILENAME).exists()
    assert trends_job.DB_FILENAME == bs.DB_FILENAME
