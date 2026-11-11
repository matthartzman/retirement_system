"""Cash ledger of one plan investment account (cash tracking Phase 2): a derived view, nothing is stored.

Pure functions. Rows come from ``store.broker.activity(account=...)`` and the kept Monarch cash-movement rows of the
account (``ytd_transactions``); see ``documentation/archive/superpowers/plans/2026-10-31-investment-account-cash-tracking-design-and-plan.md``
sections 4.2 (classes), 4.4 (source precedence) and 4.8 (derived view). Transfer pairing (Phase 3), balances and anchors
(Phase 4) and the screen (Phase 5) are not here: every row leaves ``pair_status`` at ``"unpaired"`` (``cash_pairing``
fills it across accounts) and carries the running ``cash_balance`` of the broker file when it has one.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .ytd_tracking import parse_date

CLASSES = ("income", "trade", "contribution", "fee", "transfer_in", "transfer_out", "distribution", "excess_return",
           "adjustment")
_TRADE_KINDS = frozenset({"buy", "sell", "reinvest"})
_INCOME_KINDS = frozenset({"dividend", "interest", "cap_gain_short", "cap_gain_long", "foreign_tax", "return_of_capital"})
_JOURNAL_PHRASES = ("CASH TO MARGIN", "MARGIN TO CASH")
_ROLLOVER_WORDS = ("ROLLOVER",)
_CORP_ACTION = re.compile(r"REDEMPTION OF MATURE|UNSOLICITED TRADE|\bEXCHANGE\s*$")
_REF_ID = re.compile(r"REFID:\s*(\w+)", re.I)
_DISTRIBUTION_WORDS = ("DISTRIBUTION", "WITHDRAWAL", "RETURN EXCESS")
_FEE_WORDS = ("FEE", "MARGIN INTEREST")
_CONTRIBUTION_WORDS = ("CONTRIBUTION", "CONTR ", "MATCH")
_TRANSFER_WORDS = ("TRANSFER", "ROLLOVER", "FUNDS RECEIVED", "FUNDS TRANSFERRED", "WIRE", "ACH", "DEPOSIT")
_INCOME_WORDS = ("MISC INCOME", "INCOME", "INTEREST", "DIVIDEND")
# Monarch category (lower case) -> class; None takes the direction of the sign.
_MONARCH_CLASS = {"transfer": None, "401k contribution": "contribution", "401k match": "contribution",
                  "financial fees": "fee", "other income": "income", "uncategorized": None}


def _row(*, date: str, source: str, cls: str, amount: float, counts: bool = True, description: str = "", symbol: str = "",
         action: str = "", ref: str = "", cash_balance: float | None = None, in_kind: bool = False,
         needs_review: bool = False, quantity: float | None = None, ref_id: str = "", rollover: bool = False) -> dict[str, Any]:
    return {"date": date, "source": source, "class": cls, "amount": round(float(amount), 2), "counts": counts,
            "description": description, "symbol": symbol, "action": action, "ref": ref, "cash_balance": cash_balance,
            "in_kind": in_kind, "needs_review": needs_review, "quantity": quantity, "ref_id": ref_id,
            "rollover": rollover, "pair_status": "unpaired"}


def _direction(amount: float) -> str:
    return "transfer_in" if amount >= 0 else "transfer_out"


def classify_other(r: Mapping[str, Any]) -> tuple[str, bool, bool, bool]:
    """``(class, counts, in_kind, needs_review)`` of a broker row of kind ``other``."""
    text = f"{r.get('action') or ''} {r.get('description') or ''}".upper()
    amount = float(r.get("amount") or 0.0)
    symbol = (r.get("symbol") or "").strip().upper()
    if any(p in text for p in _JOURNAL_PHRASES) or (r.get("action") or "").strip().upper() == "ADJUSTMENT":
        return "adjustment", False, False, False
    if symbol and symbol != "CASH" and r.get("quantity"):          # securities moved, no cash: the transaction log's
        if _CORP_ACTION.search(text):                              # a maturity, warrant exchange or unsolicited buy is not a transfer
            return "adjustment", False, True, False
        return _direction(float(r["quantity"])), False, True, False
    if amount == 0:                                                # a zero-dollar detail line (Fidelity "TRANSFER - CURR YR"): the dollars sit in its description
        return "adjustment", False, False, False
    if "REDEMPTION" in text and r.get("quantity") and amount != 0:  # units redeemed for cash: sale proceeds, not a transfer
        return "trade", True, False, False
    if "RETURN EXCESS" in text:
        return "excess_return", True, False, False
    if any(w in text for w in _DISTRIBUTION_WORDS):
        if amount > 0 and "WITHDRAWAL" not in text:      # "Partnership Distribution" paid INTO the account is money received, not a withdrawal
            return "income", True, False, False
        return "distribution", True, False, False
    if any(w in text for w in _FEE_WORDS):
        return "fee", True, False, False
    if any(w in text for w in _CONTRIBUTION_WORDS):
        return "contribution", True, False, False
    if any(w in text for w in _TRANSFER_WORDS):
        return _direction(amount), True, False, False
    if any(w in text for w in _INCOME_WORDS):
        return "income", True, False, False
    return _direction(amount), True, False, True                   # unknown: never guessed at, flagged for review


def _broker_row(r: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = r.get("kind")
    if r.get("sweep") and kind in _TRADE_KINDS:
        return None            # sweep legs and the reinvestment into the sweep fund move no cash (Fidelity's balance includes the fund)
    desc = r.get("description") or ""
    m = _REF_ID.search(desc)               # the store keeps only the description, so the reference id is read from it too
    ref_id = str(r.get("ref_id") or (m.group(1) if m else ""))
    qty = r.get("quantity")
    common = dict(date=r["run_date"], source="broker", description=desc, symbol=r.get("symbol") or "",
                  action=r.get("action") or "", ref=ref_id or str(r.get("row_key") or ""), cash_balance=r.get("cash_balance"),
                  ref_id=ref_id, quantity=float(qty) if qty is not None else None)
    amount = float(r.get("amount") or 0.0)
    if kind in _TRADE_KINDS:
        return _row(cls="trade", amount=amount, **common)
    if kind in _INCOME_KINDS:
        return _row(cls="income", amount=amount, **common)
    cls, counts, in_kind, review = classify_other(r)
    rollover = any(w in f"{r.get('action') or ''} {desc}".upper() for w in _ROLLOVER_WORDS)
    return _row(cls=cls, amount=0.0 if in_kind else amount, counts=counts, in_kind=in_kind, needs_review=review,
                rollover=rollover, **common)


def _monarch_row(r: Mapping[str, Any]) -> dict[str, Any] | None:
    category = str(r.get("Category") or "").strip().lower()
    if category not in _MONARCH_CLASS:
        return None
    d = parse_date(r.get("Date"))
    if d is None:
        return None
    amount = float(str(r.get("Amount") or "0").replace(",", "").replace("$", "") or 0)
    cls = _MONARCH_CLASS[category] or _direction(amount)
    return _row(date=d.isoformat(), source="monarch", cls=cls, amount=amount, description=str(r.get("Merchant") or ""),
                ref=f"monarch:{d.isoformat()}:{amount}", needs_review=category == "uncategorized")


def build_ledger(account: str, broker_rows: Iterable[Mapping[str, Any]], imports: Iterable[Mapping[str, Any]],
                 monarch_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Dated ledger rows of ``account``, oldest first.

    ``broker_rows``: its ``broker_activity`` rows; only rows of an ``applied`` import count. ``imports``: its
    ``broker_imports`` rows; the date range of each applied one is covered, the broker file wins there (design 4.4), and
    a Monarch row dated inside a covered range is dropped. ``monarch_rows``: the account's kept Monarch rows."""
    applied = {i["import_id"]: i for i in imports if i.get("status") == "applied" and i.get("account", account) == account}
    covered = [(i["date_from"], i["date_to"]) for i in applied.values() if i.get("date_from") and i.get("date_to")]
    out: list[dict[str, Any]] = []
    for r in broker_rows:
        if r.get("import_id") not in applied:
            continue
        row = _broker_row(r)
        if row:
            out.append(row)
    for r in monarch_rows:
        row = _monarch_row(r)
        if row and not any(a <= row["date"] <= b for a, b in covered):
            out.append(row)
    out.sort(key=lambda x: x["date"])           # stable: broker rows keep the store's order within a day
    return out


def account_ledger(store: Any, account: str, monarch_names: Iterable[str]) -> list[dict[str, Any]]:
    """The ledger read from the store; ``monarch_names`` are the Monarch account names mapped to ``account``."""
    names = {n.strip().lower() for n in monarch_names}
    monarch = [r for r in store.dataset("ytd_transactions").rows() if str(r.get("Account", "")).strip().lower() in names]
    return build_ledger(account, store.broker.activity(account=account), store.broker.list_imports(account=account), monarch)
