"""Checking & Savings accounts: cash accounts shown as a name, a balance and the date it was last updated.

Storage is unchanged: each account is one ``CASH`` lot in the holdings (so the engine reads it as before) plus an
Accounts & Sources row (role "Cash / spending") that names the lot. The account import (``reconcile``) updates the
balance and its date; this page adds and removes accounts and shows where each balance comes from. No symbol, purchase
date, shares, price or lot type is shown: the lot fields are filled in here.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from . import active_plan, platform_runtime, reconcile, ytd_tracking as ytd


class CashAccountError(ValueError):
    """A request the page cannot honor (blank or duplicate name, unknown account, bad balance)."""


def _key(text: Any) -> str:
    return str(text or "").strip().casefold()


def account_id(name: str) -> str:
    """The holdings account id for a display name: ``Family Checking`` -> ``Family_Checking``."""
    return re.sub(r"\s+", "_", name.strip())


def _setup_row(setup: list[dict[str, str]], acct_id: str) -> dict[str, str] | None:
    return next((r for r in setup if _key(r.get("Mapped Investment Account")) == _key(acct_id)
                 and (r.get("Role") or reconcile.CASH_ROLE) == reconcile.CASH_ROLE), None)


def list_accounts(input_dir: str | Path) -> dict[str, Any]:
    """``{accounts: [{account, name, balance, as_of, import_account}], import_accounts: [...]}``."""
    with active_plan.workspace_store(Path(input_dir).parent) as store:
        lots = reconcile._cash_only_lots(store.holdings.rows())
        setup = store.dataset("ytd_account_setup").rows()
        repo = store.monarch
        latest = repo.latest_date()
        monarch = repo.accounts_as_of(latest) if latest else []
        mapping = repo.mapping()
    out = []
    for lot in sorted(lots.values(), key=lambda l: _key(l["account"])):
        row = _setup_row(setup, lot["account"])
        name = (row or {}).get("Account") or str(lot["account"]).replace("_", " ")
        fed = [m["account"] for m in monarch
               if (mapping.get(m["account_key"]) or {}).get("ref", "").casefold() == _key(name)
               or (m["account_key"] not in mapping and _key(m["account"]) == _key(name))]
        out.append({"account": lot["account"], "name": name, "balance": str(lot.get("shares") or "").strip(),
                    "as_of": str(lot.get("purchase_date") or "").strip(), "import_account": fed[0] if fed else None})
    return {"accounts": out, "has_import": bool(monarch),
            "import_accounts": [{"account_key": m["account_key"], "account": m["account"]} for m in monarch]}


def add_account(input_dir: str | Path, name: str, balance: Any, as_of: str | None = None,
                import_account_key: str | None = None) -> dict[str, Any]:
    name = " ".join(str(name or "").split())
    if not name:
        raise CashAccountError("Give the account a name.")
    try:
        amount = round(float(str(balance).replace(",", "").replace("$", "") or 0), 2)
    except ValueError as exc:
        raise CashAccountError("The balance must be a number.") from exc
    when = as_of or platform_runtime.today().isoformat()
    try:
        date.fromisoformat(when)
    except ValueError as exc:
        raise CashAccountError("The date must look like 2026-11-02.") from exc
    acct = account_id(name)
    with active_plan.workspace_store(Path(input_dir).parent, write=True) as store:
        with store.transaction():
            holdings = store.holdings
            rows = holdings.rows()
            if any(_key(r.get("account")) == _key(acct) for r in rows):
                raise CashAccountError(f"{name!r} already exists in the holdings or as a cash account.")
            setup = [ytd.normalize_account_setup(r) for r in store.dataset("ytd_account_setup").rows()]
            if any(_key(r["Account"]) == _key(name) for r in setup):
                raise CashAccountError(f"{name!r} is already an account in Accounts & Sources.")
            rows.append({"account": acct, "symbol": "CASH", "purchase_date": when, "shares": f"{amount:.2f}",
                         "purchase_price": "1", "lot_type": "buy"})
            holdings.replace_all(rows, header=holdings.extra_columns())
            setup.append(ytd.normalize_account_setup({
                "Account": name, "Role": reconcile.CASH_ROLE, "Mapped Investment Account": acct,
                "Prior Year End Date": f"{platform_runtime.today().year - 1}-12-31", "Prior Year End Balance": "0",
                "Current Value": f"{amount:.2f}", "Current Balance": f"{amount:.2f}"}))
            store.dataset("ytd_account_setup").replace_all(setup)
            if import_account_key:
                known = {a["account_key"] for a in store.monarch.accounts_as_of(store.monarch.latest_date() or "9999-12-31")}
                if import_account_key not in known:
                    raise CashAccountError("That imported account is not in the latest import.")
                store.monarch.set_mapping(import_account_key, reconcile.MAP_SETUP, name, "auto")
    return {"account": acct, "name": name}


def delete_account(input_dir: str | Path, account: str) -> dict[str, Any]:
    with active_plan.workspace_store(Path(input_dir).parent, write=True) as store:
        with store.transaction():
            holdings = store.holdings
            rows = holdings.rows()
            if _key(account) not in reconcile._cash_only_lots(rows):
                raise CashAccountError(f"{account!r} is not a cash account.")
            holdings.replace_all([r for r in rows if _key(r.get("account")) != _key(account)], header=holdings.extra_columns())
            setup = [ytd.normalize_account_setup(r) for r in store.dataset("ytd_account_setup").rows()]
            gone = _setup_row(setup, account)
            if gone is not None:
                store.dataset("ytd_account_setup").replace_all([r for r in setup if r is not gone])
                for key, m in list(store.monarch.mapping().items()):
                    if m.get("kind") == reconcile.MAP_SETUP and _key(m.get("ref")) == _key(gone["Account"]):
                        store.monarch.clear_mapping(key)
    return {"account": account}
