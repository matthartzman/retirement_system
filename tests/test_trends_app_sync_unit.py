"""M5: the reporter reads account type, match and ignore from the Retirement app's Monarch mapping."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

from financial_trends_reporter import account_registry as reg
from financial_trends_reporter import app_sync
from financial_trends_reporter import balance_store as bs
from src import active_plan
from src import monarch_balances_import as mbi
from src import ytd_tracking as ytd

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)
ACCOUNTS = [("roth - matt", "Roth - Matt"), ("venmo", "Venmo"), ("house", "114 Main St"), ("mystery", "Mystery")]


def _write(path: Path, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("w", encoding="utf-8", newline="")
    w = csv.writer(fh)
    w.writerow(header)
    for d in ("2026-10-13", "2026-10-14"):
        for k, n in ACCOUNTS:
            w.writerow([d, k, n, 100.0])
    fh.close()


def _setup(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", [{"Account": "Matt's Roth", "Role": "Investment", "Mapped Investment Account": "Matt's Roth"}])
    _write(base / "Monarch Extractor" / "output" / "balances.csv", mbi.EXPECTED_HEADER)
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    db = tmp_path / "trends.sqlite3"
    _write(tmp_path / "b.csv", bs.EXPECTED_HEADER)
    assert bs.import_balances(db, tmp_path / "b.csv", today=TODAY, now=NOW)["success"]
    return base, db


def _by_key(db):
    return {a["account_key"]: a for a in reg.list_accounts(db)}


def test_sync_sets_match_type_and_ignore_from_the_app(tmp_path):
    base, db = _setup(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("roth - matt", "setup_account", "Matt's Roth", "app")
        store.monarch.set_mapping("venmo", "ignore")
        store.monarch.set_mapping("house", "plan:home", "", "ask")
    out = app_sync.sync_from_app(db, base)
    assert out == {"success": True, "app_account": 1, "type": 2, "ignored": 1}
    accts = _by_key(db)
    assert accts["roth - matt"]["app_account"] == "Matt's Roth" and accts["roth - matt"]["type"] == "Investment"
    assert accts["house"]["type"] == "Real estate"
    assert accts["venmo"]["enabled"] == {"networth": False, "holdings": False, "flows": False}
    assert accts["mystery"]["enabled"]["networth"] is True  # unmapped accounts are untouched


def test_sync_keeps_a_type_the_user_confirmed_and_is_idempotent(tmp_path):
    base, db = _setup(tmp_path)
    reg.set_account(db, "house", type="Other")  # confirmed by hand
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("house", "plan:home", "", "ask")
    assert app_sync.sync_from_app(db, base)["type"] == 0
    assert _by_key(db)["house"]["type"] == "Other"
    assert app_sync.sync_from_app(db, base) == app_sync.sync_from_app(db, base)


def test_sync_never_raises_when_the_plan_cannot_be_read(tmp_path):
    _, db = _setup(tmp_path)
    out = app_sync.sync_from_app(db, tmp_path / "no_such_workspace")
    assert out["success"] is False and "error" in out


def test_un_ignoring_in_the_app_re_enables_the_account(tmp_path):
    base, db = _setup(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("venmo", "ignore")
    app_sync.sync_from_app(db, base)
    assert _by_key(db)["venmo"]["enabled"]["networth"] is False
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("venmo", "setup_account", "Venmo", "ask")
    out = app_sync.sync_from_app(db, base)
    assert out["un_ignored"] == 1 and _by_key(db)["venmo"]["enabled"]["networth"] is True
    # a match removed altogether also frees it
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("venmo", "ignore")
    app_sync.sync_from_app(db, base)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.clear_mapping("venmo")
    assert app_sync.sync_from_app(db, base)["un_ignored"] == 1
    assert _by_key(db)["venmo"]["enabled"]["networth"] is True


def test_sync_does_not_stamp_cash_on_a_mortgage_or_card_matched_to_a_default_cash_role(tmp_path):
    """Regression: matched Accounts & Sources rows default to the 'Cash / spending' role, which used to
    overwrite the name-based Loan / Credit card type with a confirmed 'Cash'."""
    base, db = _setup(tmp_path)
    conn = reg.connect(db)
    with conn:
        conn.executemany(
            "INSERT INTO accounts (account_key, display_name, type, confirmed, active, first_seen, last_seen) "
            "VALUES (?,?,?,?,1,'2026-10-13','2026-10-14')",
            [("mortgage 1.99% 7/34", "Mortgage 1.99% 7/34", "Cash", 1),  # already damaged by the old sync
             ("platinum card", "Platinum Card (...1008)", None, 0),
             ("checking", "Family Checking", None, 0)])
    conn.close()
    ytd.write_account_setup(base / "input", [
        {"Account": "Mortgage 1.99% 7/34", "Role": "Cash / spending"},
        {"Account": "Platinum Card (...1008)", "Role": "Cash / spending"},
        {"Account": "Family Checking", "Role": "Cash / spending"}])
    with active_plan.workspace_store(base, write=True) as store:
        for key, name in (("mortgage 1.99% 7/34", "Mortgage 1.99% 7/34"), ("platinum card", "Platinum Card (...1008)"),
                          ("checking", "Family Checking")):
            store.monarch.set_mapping(key, "setup_account", name, "app")
    app_sync.sync_from_app(db, base)
    accts = _by_key(db)
    assert accts["mortgage 1.99% 7/34"]["type"] == "Loan"
    assert accts["platinum card"]["type"] == "Credit card"
    assert accts["checking"]["type"] == "Cash"


def test_sync_repairs_a_credit_card_stamped_cash(tmp_path):
    base, db = _setup(tmp_path)
    reg.set_account(db, "mystery", type="Cash")  # what an earlier sync stamped from the default role
    conn = reg.connect(db)
    try:
        conn.execute("UPDATE accounts SET display_name='Costco Anywhere Visa Card (...1530)' WHERE account_key='mystery'")
        conn.commit()
    finally:
        conn.close()
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("mystery", "liability:liab_x", "", "app")
    assert app_sync.sync_from_app(db, base)["type"] == 1
    assert _by_key(db)["mystery"]["type"] == "Credit card"
