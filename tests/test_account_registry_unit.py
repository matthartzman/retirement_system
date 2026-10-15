"""Phase 3 of the Monarch balances feed: classifier, registry, toggles and API."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone

import pytest

from financial_trends_reporter import account_registry as reg
from financial_trends_reporter import balance_store as bs
from financial_trends_reporter.main import create_app

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("name,expected", [
    ("Mortgage 1.99% 7/34", "Loan"),
    ("Home Equity Line of Credit $199K 9/28", "Loan"),
    ("BMW Loan 4.64% 12/28", "Loan"),
    ("Platinum Card® (...1008)", "Credit card"),
    ("Costco Anywhere Visa Card by Citi (...1530)", "Credit card"),
    ("BoA Balance Transfer MasterCar (...9507)", "Credit card"),
    ("Joint Annuity - Alex - Apr 2026", "Annuity/Pension"),
    ("Pension - Sam - June 2026", "Annuity/Pension"),
    ("Health Savings Account (HSA)", "HSA"),
    ("HSA - Alex", "HSA"),
    ("IRA - Alex", "Retirement"),
    ("Rollover IRA (IRRL) (...2059)", "Retirement"),
    ("Roth - Sam", "Retirement"),
    ("SEP IRA - Alex", "Retirement"),
    ("401k - Employer - Alex", "Retirement"),
    ("EMPLOYER FUTURE FUND 401(K) PLAN - 092038", "Retirement"),
    ("Trust - Alex", "Investment"),
    ("Brokerage - Alex", "Investment"),
    ("iBond - Sam", "Investment"),
    ("Family Checking and Bill Pay ", "Cash"),
    ("Venmo", "Cash"),
    ("Rainy Day Savings", "Cash"),
    ("2016 KIA Optima EX", "Vehicle"),
    ("114 S Main St Springfield IL 60521", "Real estate"),
    ("Masterworks Dec 25", "Other"),
    ("Private Note Jan 2026", "Other"),
    ("USBank (...3635)", "Other"),  # ambiguous by name: the user confirms it in the UI
])
def test_classify(name, expected):
    assert reg.classify(name) == expected


def test_default_toggles_follow_the_agreed_holdings_definition():
    # Holdings: liquid investments + checking/Venmo; NOT annuity/pension, Other, property, debts.
    holdings = {t for t in reg.TYPES if reg.default_enabled("holdings", t)}
    assert holdings == {"Cash", "Investment", "Retirement", "HSA"}
    assert all(reg.default_enabled("networth", t) for t in reg.TYPES)
    assert {t for t in reg.TYPES if reg.default_enabled("flows", t)} == {"Investment", "Retirement", "HSA"}
    with pytest.raises(ValueError):
        reg.default_enabled("bogus", "Cash")


def _seed(tmp_path):
    db = tmp_path / "b.sqlite3"
    src = tmp_path / "balances.csv"
    rows = [
        ("2026-10-13", "ira - alex", "IRA - Alex", 100.0), ("2026-10-14", "ira - alex", "IRA - Alex", 110.0),
        ("2026-10-13", "venmo", "Venmo", 0.0), ("2026-10-14", "venmo", "Venmo", 5.0),
        ("2026-10-14", "masterworks", "Masterworks", 50.0),
    ]
    with src.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(bs.EXPECTED_HEADER)
        w.writerows(rows)
    assert bs.import_balances(db, src, today=TODAY, now=NOW)["success"]
    return db


def _by_key(accounts):
    return {a["account_key"]: a for a in accounts}


def test_list_classifies_new_accounts_with_latest_balance(tmp_path):
    accts = _by_key(reg.list_accounts(_seed(tmp_path)))
    assert accts["ira - alex"]["type"] == "Retirement" and accts["ira - alex"]["latest_balance"] == 110.0
    assert accts["venmo"]["enabled"] == {"networth": True, "holdings": True, "flows": False}
    assert accts["masterworks"]["enabled"]["holdings"] is False
    assert not any(a["confirmed"] for a in accts.values())


def test_set_account_type_and_mapping_persist_across_reimport(tmp_path):
    db = _seed(tmp_path)
    reg.list_accounts(db)
    updated = reg.set_account(db, "masterworks", type="Investment", app_account="Alt Fund")
    assert updated["type"] == "Investment" and updated["app_account"] == "Alt Fund" and updated["confirmed"]
    assert updated["enabled"]["holdings"] is True  # follows the new type
    assert bs.import_balances(db, tmp_path / "balances.csv", today=TODAY, now=NOW)["success"]
    again = _by_key(reg.list_accounts(db))["masterworks"]
    assert again["type"] == "Investment" and again["app_account"] == "Alt Fund"


def test_many_monarch_accounts_can_map_to_one_app_account(tmp_path):
    db = _seed(tmp_path)
    reg.set_account(db, "ira - alex", app_account="Alex IRA")
    reg.set_account(db, "venmo", app_account="Alex IRA")
    mapped = {a["app_account"] for a in reg.list_accounts(db) if a["account_key"] in {"ira - alex", "venmo"}}
    assert mapped == {"Alex IRA"}


def test_set_account_rejects_bad_input(tmp_path):
    db = _seed(tmp_path)
    with pytest.raises(ValueError):
        reg.set_account(db, "venmo", type="Spaceship")
    with pytest.raises(ValueError):
        reg.set_account(db, "nope", type="Cash")


def test_prefs_override_and_clear(tmp_path):
    db = _seed(tmp_path)
    reg.set_prefs(db, [{"chart": "holdings", "account_key": "masterworks", "enabled": True},
                       {"chart": "networth", "account_key": "venmo", "enabled": False}])
    accts = _by_key(reg.list_accounts(db))
    assert accts["masterworks"]["enabled"]["holdings"] is True and accts["masterworks"]["overridden"]["holdings"]
    assert accts["venmo"]["enabled"]["networth"] is False
    reg.set_prefs(db, [{"chart": "holdings", "account_key": "masterworks", "enabled": None}])
    accts = _by_key(reg.list_accounts(db))
    assert accts["masterworks"]["enabled"]["holdings"] is False and not accts["masterworks"]["overridden"]["holdings"]


def test_prefs_are_all_or_nothing(tmp_path):
    db = _seed(tmp_path)
    with pytest.raises(ValueError):
        reg.set_prefs(db, [{"chart": "holdings", "account_key": "venmo", "enabled": False},
                           {"chart": "holdings", "account_key": "ghost", "enabled": False}])
    assert _by_key(reg.list_accounts(db))["venmo"]["enabled"]["holdings"] is True
    for bad in ({"chart": "x", "account_key": "venmo", "enabled": True},
                {"chart": "holdings", "account_key": "venmo", "enabled": "yes"}):
        with pytest.raises(ValueError):
            reg.set_prefs(db, [bad])


def test_legacy_store_without_confirmed_column_is_migrated(tmp_path):
    import sqlite3

    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE accounts (account_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, type TEXT, app_account TEXT, "
        "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);"
        "INSERT INTO accounts VALUES ('venmo','Venmo',NULL,NULL,'2026-01-01','2026-10-14',1);"
    )
    conn.commit()
    conn.close()
    assert reg.list_accounts(db)[0]["type"] == "Cash"


# ---- API -------------------------------------------------------------------------------

def _client(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "input").mkdir(parents=True)
    log = tmp_path / "data" / "log.jsonl"
    db = tmp_path / "data" / bs.DB_FILENAME
    db.parent.mkdir()
    _seed(tmp_path).replace(db)
    return create_app(workspace, log_path=log).test_client()


def test_accounts_endpoint(tmp_path):
    body = json.loads(_client(tmp_path).get("/api/accounts").get_data(as_text=True))
    assert {a["account_key"] for a in body["accounts"]} == {"ira - alex", "venmo", "masterworks"}
    assert "Retirement" in body["types"] and body["charts"] == ["networth", "holdings", "flows"]
    assert body["freshness"]["last_ok"]["latest_date"] == "2026-10-14"


def test_account_and_prefs_endpoints_roundtrip(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/account", json={"account_key": "masterworks", "type": "Investment", "app_account": "Alt Fund"})
    assert r.status_code == 200 and json.loads(r.get_data(as_text=True))["account"]["type"] == "Investment"
    r = client.post("/api/account-prefs", json={"items": [{"chart": "holdings", "account_key": "venmo", "enabled": False}]})
    assert r.status_code == 200
    accts = {a["account_key"]: a for a in json.loads(client.get("/api/accounts").get_data(as_text=True))["accounts"]}
    assert accts["venmo"]["enabled"]["holdings"] is False and accts["masterworks"]["app_account"] == "Alt Fund"


def test_endpoints_reject_bad_input(tmp_path):
    client = _client(tmp_path)
    assert client.post("/api/account", json={"account_key": "ghost", "type": "Cash"}).status_code == 400
    assert client.post("/api/account", json={"account_key": "venmo", "type": "Nope"}).status_code == 400
    assert client.post("/api/account-prefs", json={"items": "x"}).status_code == 400
    bad = {"items": [{"chart": "bad", "account_key": "venmo", "enabled": True}]}
    assert client.post("/api/account-prefs", json=bad).status_code == 400


def test_new_endpoints_keep_the_cross_origin_block(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/account-prefs", json={"items": []}, headers={"Origin": "http://evil.example", "Host": "127.0.0.1:5057"})
    assert r.status_code == 403


def test_app_accounts_endpoint_never_raises_on_empty_workspace(tmp_path):
    r = _client(tmp_path).get("/api/app-accounts")
    assert r.status_code == 200 and json.loads(r.get_data(as_text=True))["app_accounts"] == []
