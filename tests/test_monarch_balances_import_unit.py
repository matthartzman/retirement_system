"""R1 of the reconciliation page: plan-file Monarch tables (schema v13) and the guarded balances import."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src import active_plan
from src import monarch_balances_import as mbi
from src import monarch_autoimport_job as job
from src.stores import PlanStore

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)
HEADER = ["date", "account_key", "account", "balance"]


def _workspace(tmp_path: Path) -> Path:
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    return base


def _csv(path: Path, rows, header=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header or HEADER)
        w.writerows(rows)
    return path


def _rows(n=3, days=("2026-10-13", "2026-10-14")):
    return [(d, f"acct{i}", f"Acct {i}", 100.0 * (i + 1)) for i in range(n) for d in days]


def _repo_read(base, fn):
    with active_plan.workspace_store(base) as store:
        return fn(store.monarch)


def test_import_is_idempotent_and_upserts(tmp_path):
    base = _workspace(tmp_path)
    src = _csv(base / "b.csv", _rows())
    a = mbi.import_balances(base, src, today=TODAY, now=NOW)
    b = mbi.import_balances(base, src, today=TODAY, now=NOW)
    assert a["success"] and b["success"] and a["rows"] == 6 and a["accounts"] == 3
    assert _repo_read(base, lambda r: r.count()) == 6
    changed = _rows()
    changed[0] = (changed[0][0], changed[0][1], changed[0][2], 999.0)
    mbi.import_balances(base, _csv(base / "b2.csv", changed), today=TODAY, now=NOW)
    got = {r["account_key"]: r["balance"] for r in _repo_read(base, lambda r: r.accounts_as_of("2026-10-13"))}
    assert got["acct0"] == 999.0


@pytest.mark.parametrize("rows,header,why", [
    ([("2026-10-14", "a", "A", "1")], ["Date", "Balance", "Account", "x"], "header"),
    ([("2026-10-14", "a", "A", "abc")], None, "line 2"),
    ([("not-a-date", "a", "A", "1")], None, "line 2"),
    ([], None, "no rows"),
    ([("2026-10-10", "a", "A", "1")], None, "stale"),
])
def test_bad_files_are_rejected_and_nothing_written(tmp_path, rows, header, why):
    base = _workspace(tmp_path)
    res = mbi.import_balances(base, _csv(base / "b.csv", rows, header), today=TODAY, now=NOW)
    assert not res["success"] and res["status"] == "rejected" and why in res["error"]
    assert _repo_read(base, lambda r: r.count()) == 0
    assert _repo_read(base, lambda r: r.last_import())["status"] == "rejected"


def test_account_count_drop_guard(tmp_path):
    base = _workspace(tmp_path)
    assert mbi.import_balances(base, _csv(base / "a.csv", _rows(10)), today=TODAY, now=NOW)["success"]
    res = mbi.import_balances(base, _csv(base / "b.csv", _rows(7)), today=TODAY, now=NOW)
    assert not res["success"] and "fell from 10 to 7" in res["error"]
    assert mbi.import_balances(base, _csv(base / "c.csv", _rows(9)), today=TODAY, now=NOW)["success"]


def test_missing_file_is_a_quiet_skip_not_a_rejection(tmp_path):
    base = _workspace(tmp_path)
    res = mbi.import_balances(base, today=TODAY, now=NOW)
    assert res == {"success": True, "status": "skipped", "skip_reason": "no balances file"}
    assert not (base / "plan.rpx").exists()


def test_accounts_as_of_carries_forward_and_zeroes_closed(tmp_path):
    base = _workspace(tmp_path)
    rows = [("2026-10-12", "gap", "Gap", 10.0), ("2026-10-14", "gap", "Gap", 30.0),
            ("2026-10-01", "closed", "Closed", 5.0), ("2026-10-14", "live", "Live", 1.0),
            ("2026-10-13", "live", "Live", 1.0), ("2026-10-12", "live", "Live", 1.0)]
    assert mbi.import_balances(base, _csv(base / "b.csv", rows), today=TODAY, now=NOW)["success"]
    on13 = {r["account_key"]: r for r in _repo_read(base, lambda r: r.accounts_as_of("2026-10-13"))}
    assert on13["gap"]["balance"] == 10.0 and on13["gap"]["balance_date"] == "2026-10-12"   # carried forward
    assert on13["closed"]["closed"] and on13["closed"]["balance"] == 0.0
    on14 = {r["account_key"]: r for r in _repo_read(base, lambda r: r.accounts_as_of("2026-10-14"))}
    assert on14["gap"]["balance"] == 30.0 and not on14["live"]["closed"]
    early = {r["account_key"] for r in _repo_read(base, lambda r: r.accounts_as_of("2026-09-30"))}
    assert early == set()                                                                       # nothing existed yet


def test_a_late_syncing_account_is_not_treated_as_closed(tmp_path):
    base = _workspace(tmp_path)
    rows = [("2026-10-13", "late", "Late", 50.0), ("2026-10-14", "live", "Live", 1.0), ("2026-10-13", "live", "Live", 1.0),
            ("2026-10-09", "gone", "Gone", 9.0), ("2026-10-10", "live", "Live", 1.0)]
    assert mbi.import_balances(base, _csv(base / "b.csv", rows), today=TODAY, now=NOW)["success"]
    on14 = {r["account_key"]: r for r in _repo_read(base, lambda r: r.accounts_as_of("2026-10-14"))}
    assert on14["late"]["balance"] == 50.0 and not on14["late"]["closed"]     # one day behind: carried forward
    assert on14["gone"]["closed"] and on14["gone"]["balance"] == 0.0           # stopped five days before the newest date


def test_non_finite_balances_are_rejected_not_crashed(tmp_path):
    base = _workspace(tmp_path)
    for bad in ("nan", "inf", "-inf"):
        res = mbi.import_balances(base, _csv(base / "b.csv", [("2026-10-14", "a", "A", bad)]), today=TODAY, now=NOW)
        assert not res["success"] and "non-finite" in res["error"]
    assert _repo_read(base, lambda r: r.count()) == 0


def test_mapping_and_log_roundtrip(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        m = store.monarch
        m.set_mapping("acct0", "setup_account", "Checking")
        m.set_mapping("acct0", "setup_account", "Checking 2")
        assert m.mapping() == {"acct0": {"kind": "setup_account", "ref": "Checking 2", "policy": "ask"}}
        m.clear_mapping("acct0")
        assert m.mapping() == {}
        i = m.log_change("2026-10-14T00:00:00", "setup_account", "Checking", "Current Balance", "Checking", "100", "120", "2026-10-14")
        assert m.log_entry(i)["undone_at"] is None
        m.mark_undone(i, "2026-10-14T01:00:00")
        assert m.log_entries()[0]["undone_at"] == "2026-10-14T01:00:00"
        with pytest.raises(Exception):
            m.log_entry(9999)


def test_new_plan_files_are_schema_14_and_revisions_do_not_copy_balances(tmp_path):
    base = _workspace(tmp_path)
    mbi.import_balances(base, _csv(base / "b.csv", _rows()), today=TODAY, now=NOW)
    with PlanStore.open(base / "plan.rpx") as store:
        assert store.schema_version == 15
        store.snapshot_revision("test")
        n = store._con.execute("SELECT COUNT(*) FROM revision_datasets WHERE dataset LIKE '%monarch%'").fetchone()[0]
        assert n == 0


def test_job_wrapper_imports_balances_and_never_changes_success(tmp_path, monkeypatch):
    base = _workspace(tmp_path)
    _csv(base / "Monarch Extractor" / "output" / "balances.csv", _rows())
    monkeypatch.setattr(job, "_run_transactions", lambda b, force=False: {"success": True, "skipped": True, "skip_reason": "no_rows"})
    monkeypatch.setattr(job, "import_balances", lambda b, p=None: mbi.import_balances(b, p, today=TODAY, now=NOW))
    res = job.run(base)
    assert res["success"] and res["balances"]["status"] == "ok" and res["balances"]["rows"] == 6

    def boom(b, p=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(job, "import_balances", boom)
    res = job.run(base)
    assert res["success"] and res["balances"]["status"] == "error"
    from src import monarch_autoupdate as mau
    mau.save_policy(base, {"enabled": False})
    assert "balances" not in job.run(base)


def test_policy_defaults_survives_rematch_and_ignore_kind_forces_ignore(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        m = store.monarch
        m.set_mapping("a", "setup_account", "Checking", "auto")
        m.set_mapping("a", "setup_account", "Checking 2")  # re-match without a policy keeps it
        assert m.mapping()["a"]["policy"] == "auto"
        m.set_policy("a", "app")
        assert m.mapping()["a"]["policy"] == "app"
        m.set_mapping("b", "ignore")
        assert m.mapping()["b"]["policy"] == "ignore"
        with pytest.raises(Exception):
            m.set_policy("a", "sometimes")
        with pytest.raises(Exception):
            m.set_policy("nope", "ask")


def test_job_runs_auto_update_after_a_good_balances_import_and_never_fails_the_run(tmp_path, monkeypatch):
    from src import reconcile, ytd_tracking as ytd
    base = _workspace(tmp_path)
    ytd.write_account_setup(base / "input", [{"Account": "Acct 0", "Role": "Cash / spending", "Current Balance": "50"}])
    _csv(base / "Monarch Extractor" / "output" / "balances.csv", _rows())
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.upsert_balances([("2026-10-14", "acct0", "Acct 0", 100.0)])
        store.monarch.set_mapping("acct0", "setup_account", "Acct 0", "auto")
    monkeypatch.setattr(job, "_run_transactions", lambda b, force=False: {"success": True, "skipped": True, "skip_reason": "no_rows"})
    monkeypatch.setattr(job, "import_balances", lambda b, p=None: mbi.import_balances(b, p, today=TODAY, now=NOW))
    res = job.run(base)
    assert res["auto_update"] == {"success": True, "applied": 1, "held": 0}
    assert next(r["Current Balance"] for r in ytd.read_account_setup(base / "input")) in ("100.00", "100")

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(reconcile, "auto_apply", boom)
    res = job.run(base)
    assert res["success"] and res["auto_update"]["success"] is False
