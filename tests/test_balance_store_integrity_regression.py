"""F-03 / F-02 follow-up: snapshot before destructive imports, held (not silent) partial renames, integer cents that
preserve existing values exactly, and the purge tool for rows dated in the future."""
from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from financial_trends_reporter import balance_store as bs
from financial_trends_reporter.tools import purge_future_balances as purge_tool

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
DAYS = ("2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14")


def _csv(tmp: Path, rows, name="balances.csv") -> Path:
    p = tmp / name
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(bs.EXPECTED_HEADER)
        w.writerows(rows)
    return p


def _seed(tmp: Path):
    db = tmp / "data" / "b.sqlite3"
    rows = [(d, "acct0", "Acct 0", 1000.0 + i) for i, d in enumerate(DAYS)] + [(d, "acct1", "Acct 1", 200.5) for d in DAYS]
    assert bs.import_balances(db, _csv(tmp, rows), today=TODAY, now=NOW)["success"]
    return db


def test_lossless_rename_still_merges_and_is_snapshotted_first(tmp_path):
    db = _seed(tmp_path)
    rows = [(d, "acct0 renamed", "Acct 0 R", 1000.0 + i) for i, d in enumerate(DAYS)] + [(d, "acct1", "Acct 1", 200.5) for d in DAYS]
    res = bs.import_balances(db, _csv(tmp_path, rows, "n.csv"), today=TODAY, now=NOW)
    assert res["success"] and "snapshot" in res and Path(res["snapshot"]).is_file()
    snap = sqlite3.connect(res["snapshot"])  # the snapshot still has the old key's history
    assert snap.execute("SELECT COUNT(*) FROM balances WHERE account_key='acct0'").fetchone()[0] == 5
    snap.close()
    with bs.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM balances WHERE account_key='acct0'").fetchone()[0] == 0


def test_partial_rename_is_held_not_merged_until_confirmed(tmp_path):
    db = _seed(tmp_path)
    # the new key repeats only 4 of the old key's 5 days: 80%, which the old heuristic merged (deleting day 5)
    rows = [(d, "acct0 renamed", "Acct 0 R", 1000.0 + i) for i, d in enumerate(DAYS[:4])] \
        + [(DAYS[4], "acct0 renamed", "Acct 0 R", 5555.0)] + [(d, "acct1", "Acct 1", 200.5) for d in DAYS]
    res = bs.import_balances(db, _csv(tmp_path, rows, "n.csv"), today=TODAY, now=NOW)
    assert res["success"] and res["pending_renames"] == [{"old": "acct0", "new": "acct0 renamed", "matched": 4, "of": 5}]
    with bs.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM balances WHERE account_key='acct0'").fetchone()[0] == 5  # nothing deleted
    assert bs.pending_renames(db)[0]["old_key"] == "acct0"
    out = bs.confirm_rename(db, "acct0", "acct0 renamed", now=NOW)
    assert Path(out["snapshot"]).is_file() and not bs.pending_renames(db)
    with bs.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM balances WHERE account_key='acct0'").fetchone()[0] == 0
    with pytest.raises(LookupError):
        bs.confirm_rename(db, "acct0", "acct0 renamed")


def test_rejecting_a_held_rename_keeps_both_accounts(tmp_path):
    db = _seed(tmp_path)
    rows = [(d, "acct0 renamed", "R", 1000.0 + i) for i, d in enumerate(DAYS[:4])] + [(DAYS[4], "acct0 renamed", "R", 1.0)] \
        + [(d, "acct1", "Acct 1", 200.5) for d in DAYS]
    bs.import_balances(db, _csv(tmp_path, rows, "n.csv"), today=TODAY, now=NOW)
    bs.reject_rename(db, "acct0", "acct0 renamed")
    assert bs.pending_renames(db) == []
    with bs.connect(db) as conn:
        assert {r[0] for r in conn.execute("SELECT account_key FROM accounts")} == {"acct0", "acct0 renamed", "acct1"}


def test_mirror_import_that_drops_an_account_snapshots_first(tmp_path):
    db = _seed(tmp_path)
    rows = [(d, "acct1", "Acct 1", 200.5) for d in DAYS]
    res = bs.import_balance_rows(db, rows, "plan", now=NOW, mirror=True)
    assert res["success"] and Path(res["snapshot"]).is_file()
    snap = sqlite3.connect(res["snapshot"])
    assert snap.execute("SELECT COUNT(*) FROM balances WHERE account_key='acct0'").fetchone()[0] == 5
    snap.close()


def test_snapshots_are_pruned_to_the_newest_few(tmp_path):
    db = _seed(tmp_path)
    for i in range(8):
        with bs.connect(db) as conn:
            bs.snapshot_db(conn, keep=3, now=datetime(2026, 10, 14, 12, 0, i, tzinfo=timezone.utc))
    assert len(list((db.parent / bs.SNAPSHOT_DIR).glob("*.sqlite3"))) == 3


# ---- integer cents ----
REAL_LOOKING = [1234567.89, 98765432.10, 0.01, 0.0, -1234.5, 250000.0, 4.35, 1.005, 100.005, 33333.33, 1e9 + 0.07]


def test_cents_round_trip_exactly_for_real_looking_values():
    for v in REAL_LOOKING:
        c = bs.to_cents(v)
        if c is not None:
            assert c / 100.0 == v, v  # cents -> REAL gives back the identical float
    assert bs.to_cents(1234567.89) == 123456789 and bs.to_cents(-1234.5) == -123450 and bs.to_cents(0.0) == 0
    assert bs.to_cents(100.005) is None and bs.to_cents(1.005) is None  # sub-cent detail is never rounded away


def test_migration_adds_cents_and_leaves_every_existing_value_bit_identical(tmp_path):
    db = tmp_path / "old.sqlite3"
    con = sqlite3.connect(db)  # the pre-migration schema: no balance_cents column
    con.executescript("""CREATE TABLE balances (date TEXT NOT NULL, account_key TEXT NOT NULL, balance REAL NOT NULL,
                         PRIMARY KEY (date, account_key));""")
    con.executemany("INSERT INTO balances VALUES (?,?,?)", [("2026-10-14", f"k{i}", v) for i, v in enumerate(REAL_LOOKING)])
    con.commit()
    before = {r[0]: r[1] for r in con.execute("SELECT account_key, balance FROM balances")}
    con.close()
    conn = bs.connect(db)
    try:
        after = {r["account_key"]: (r["balance"], r["balance_cents"]) for r in conn.execute("SELECT * FROM balances")}
    finally:
        conn.close()
    for i, v in enumerate(REAL_LOOKING):
        stored, cents = after[f"k{i}"]
        assert stored == before[f"k{i}"] == v and repr(stored) == repr(v)  # not one bit changed
        assert cents == bs.to_cents(v)
    again = bs.connect(db)  # idempotent
    assert again.execute("SELECT COUNT(*) FROM balances WHERE balance_cents IS NOT NULL").fetchone()[0] == sum(
        bs.to_cents(v) is not None for v in REAL_LOOKING)
    again.close()


def test_new_imports_store_cents_alongside_the_real_value(tmp_path):
    db = _seed(tmp_path)
    with bs.connect(db) as conn:
        row = conn.execute("SELECT balance, balance_cents FROM balances WHERE account_key='acct1' LIMIT 1").fetchone()
    assert row["balance"] == 200.5 and row["balance_cents"] == 20050


# ---- purge of future-dated rows ----
def _poison(db):
    with bs.connect(db) as conn:
        conn.execute("INSERT INTO balances (date, account_key, balance, balance_cents) VALUES ('2099-01-01','acct0',1.0,100)")
        conn.execute("INSERT INTO balances (date, account_key, balance, balance_cents) VALUES ('2099-01-01','ghost',9.0,900)")
        conn.execute("INSERT INTO accounts (account_key, display_name, first_seen, last_seen, active) VALUES ('ghost','Ghost','2099-01-01','2099-01-01',1)")
        conn.execute("UPDATE accounts SET active=0 WHERE account_key IN ('acct0','acct1')")
        conn.commit()


def test_purge_future_rows_dry_run_changes_nothing_and_apply_restores_the_accounts(tmp_path):
    db = _seed(tmp_path)
    _poison(db)
    preview = bs.purge_future_rows(db, today=TODAY)
    assert preview["rows"] == 2 and preview["dates"] == ["2099-01-01"] and not preview["applied"]
    with bs.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM balances WHERE date > '2026-10-15'").fetchone()[0] == 2
    done = bs.purge_future_rows(db, today=TODAY, apply=True, now=NOW)
    assert done["applied"] and Path(done["snapshot"]).is_file()
    with bs.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM balances WHERE date > '2026-10-15'").fetchone()[0] == 0
        assert {r[0] for r in conn.execute("SELECT account_key FROM accounts")} == {"acct0", "acct1"}  # ghost is gone
        assert [r[0] for r in conn.execute("SELECT active FROM accounts ORDER BY 1")] == [1, 1]
        assert conn.execute("SELECT status FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()[0] == "purged"
    # today and tomorrow are never touched
    with bs.connect(db) as conn:
        conn.execute("INSERT INTO balances (date, account_key, balance) VALUES ('2026-10-15','acct1',1.0)")
        conn.commit()
    assert bs.purge_future_rows(db, today=TODAY, apply=True)["rows"] == 0


def test_purge_tool_is_a_dry_run_unless_apply(tmp_path, capsys):
    db = _seed(tmp_path)
    _poison(db)
    assert purge_tool.main(["--db", str(db), "--today", "2026-10-14"]) == 0
    assert "would remove 2 row(s)" in capsys.readouterr().out
    with bs.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM balances WHERE date > '2026-10-15'").fetchone()[0] == 2
    assert purge_tool.main(["--db", str(db), "--today", "2026-10-14", "--apply"]) == 0
    assert "removed 2 row(s)" in capsys.readouterr().out
