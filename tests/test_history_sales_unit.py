"""Sales that a history-only broker import left out of the ledger: listed, recorded from the replayed buys, dismissed."""
from __future__ import annotations

import pytest

from src import active_plan, history_sales
from src.sales_ledger import ValidationError

ACCT = "Trust - Matt"


def _row(n, date, kind, symbol, qty, price, amount, action="", desc=""):
    return {"row_key": f"k{n}", "broker": "etrade", "account": ACCT, "run_date": date, "settle_date": date, "kind": kind,
            "sweep": False, "action": action or kind.title(), "symbol": symbol, "description": desc, "quantity": qty,
            "price": price, "commission": 0.0, "fees": None, "accrued_interest": None, "amount": amount,
            "cash_balance": None, "candidate_id": None, "lot_ref": None}


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        iid = store.broker.add_import(broker="etrade", account=ACCT, date_from="2025-12-01", date_to="2026-10-30",
                                      summary={"history_only": True})
        store.broker.add_rows(iid, [
            _row(1, "2025-12-30", "buy", "ITOT", 380.0, 150.0, -57000.0),
            _row(2, "2026-03-04", "buy", "ITOT", 270.0, 148.0, -39960.0),
            _row(3, "2026-09-22", "sell", "ITOT", -600.0, 170.0, 102000.0),
            _row(4, "2026-09-24", "buy", "912797VN4", 120000.0, 0.99661155, -119593.39),
            _row(5, "2026-10-27", "sell", "912797VN4", -120000.0, 1.0, 120000.0, action="Redemption",
                 desc="US TSY BILL 26OC27 REDEMPTION OF MATURED BOND"),
            _row(6, "2025-06-01", "sell", "OLD", -10.0, 5.0, 50.0),
        ])
    return tmp_path / "input"


def test_lists_the_history_sale_with_fifo_lots_and_the_bill_as_interest(input_dir):
    items = history_sales.list_unrecorded(input_dir)["items"]
    sale = next(i for i in items if i["kind"] == "sale")
    assert (sale["symbol"], sale["sale_date"], sale["shares"], sale["proceeds"]) == ("ITOT", "2026-09-22", 600.0, 102000.0)
    assert sale["complete"] and [(p["purchase_date"], p["shares"]) for p in sale["pieces"]] == [("2025-12-30", 380.0), ("2026-03-04", 220.0)]
    assert sale["basis"] == pytest.approx(380 * 150 + 220 * 148)
    bill = next(i for i in items if i["kind"] == "interest")
    assert bill["symbol"] == "912797VN4" and bill["proceeds"] == 120000.0
    assert all(i["sale_date"] >= "2026-01-01" for i in items)          # the 2025 sale is not offered


def test_record_writes_one_row_per_lot_and_the_item_leaves_the_list(input_dir):
    key = next(i["key"] for i in history_sales.list_unrecorded(input_dir)["items"] if i["kind"] == "sale")
    out = history_sales.record(input_dir, key, tax_class="taxable")
    assert len(out["sale_ids"]) == 2
    with active_plan.workspace_store(input_dir.parent) as store:
        rows = store.sales.list_sales()
    assert round(sum(r["proceeds"] for r in rows), 2) == 102000.0
    assert {r["holding_period"] for r in rows} == {"short"}
    assert round(sum(r["gain"] for r in rows), 2) == round(102000 - (380 * 150 + 220 * 148), 2)
    assert not [i for i in history_sales.list_unrecorded(input_dir)["items"] if i["kind"] == "sale"]
    with pytest.raises(ValidationError):
        history_sales.record(input_dir, key)                             # already recorded


def test_a_bill_maturity_is_never_recorded_as_a_sale(input_dir):
    key = next(i["key"] for i in history_sales.list_unrecorded(input_dir)["items"] if i["kind"] == "interest")
    with pytest.raises(ValidationError, match="interest"):
        history_sales.record(input_dir, key)


def test_dismiss_hides_an_item(input_dir):
    key = next(i["key"] for i in history_sales.list_unrecorded(input_dir)["items"] if i["kind"] == "sale")
    history_sales.dismiss(input_dir, key)
    assert not [i for i in history_sales.list_unrecorded(input_dir)["items"] if i["kind"] == "sale"]


def test_a_sale_the_files_cannot_cover_is_listed_incomplete_and_not_recordable(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        iid = store.broker.add_import(broker="etrade", account=ACCT, summary={"history_only": True})
        store.broker.add_rows(iid, [_row(1, "2026-05-01", "sell", "ZZZ", -5.0, 10.0, 50.0)])
    d = tmp_path / "input"
    item = history_sales.list_unrecorded(d)["items"][0]
    assert item["complete"] is False
    with pytest.raises(ValidationError, match="Record a sale"):
        history_sales.record(d, item["key"])
