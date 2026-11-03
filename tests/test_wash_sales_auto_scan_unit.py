"""Plan 3a.3 gap (b): the possible-wash scan runs after every ledger change and reads Monarch Buy rows and
broker-activity buys as well as holdings lots. Synthetic fixtures only."""
from __future__ import annotations

import pytest

from src import active_plan, sales_confirm, sales_matching, sales_service, sales_tax_year
from src.wash_sales import dedupe_buys

LOTS = [{"account": "Trust", "symbol": "VTI", "purchase_date": "2026-01-10", "shares": "10",
         "purchase_price": "200", "lot_type": "buy", "note": ""}]


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(LOTS)
    return tmp_path / "input"


def _rows(input_dir):
    return sales_service.list_sales(input_dir)["sales"]


def _loss_sale(input_dir, **over):
    row = dict(sale_date="2026-06-10", account="Trust", tax_class="taxable", symbol="VTI", shares=10,
               proceeds=1000.0, fees=0.0, basis=2000.0, purchase_date="2026-01-10")
    row.update(over)
    return sales_service.add_sale(input_dir, row)


def _monarch_buy(input_dir, date="2026-06-20", text="Bought 5 VTI @ 100", account="Spouse_taxable"):
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        repo = store.dataset("ytd_transactions")
        repo.replace_all(repo.rows() + [{"Date": date, "Account": account, "Category": "Buy", "Merchant": "Vanguard",
                                         "Original Statement": text, "Amount": "-500"}])


def _broker_buy(input_dir, run_date="2026-06-01", kind="buy", quantity=3.0, symbol="VTI"):
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        iid = store.broker.add_import(broker="fidelity", account="Joint_taxable")
        store.broker.add_rows(iid, [{"row_key": f"k-{run_date}-{kind}", "broker": "fidelity", "account": "Joint_taxable",
                                     "run_date": run_date, "kind": kind, "sweep": False, "action": "YOU BOUGHT",
                                     "symbol": symbol, "description": "", "quantity": quantity, "price": 100.0,
                                     "amount": -300.0}])


def test_manual_add_of_a_loss_flags_it_without_pressing_the_button(input_dir):
    _monarch_buy(input_dir)
    sale = _loss_sale(input_dir)
    assert sale["wash_flag"] == "possible"
    assert [r["wash_flag"] for r in _rows(input_dir)] == ["possible"]


def test_a_gain_is_not_flagged(input_dir):
    _monarch_buy(input_dir)
    assert _loss_sale(input_dir, proceeds=3000.0)["wash_flag"] == "none"


def test_csv_import_flags_after_commit(input_dir):
    _monarch_buy(input_dir)
    text = ("sale_date,account,tax_class,symbol,shares,proceeds,basis,purchase_date\n"
            "2026-06-10,Trust,taxable,VTI,10,1000,2000,2026-01-10\n")
    assert sales_service.commit_csv(input_dir, text)["written"] == 1
    assert [r["wash_flag"] for r in _rows(input_dir)] == ["possible"]


def test_confirm_flags_and_undo_clears_without_the_button(input_dir):
    _monarch_buy(input_dir, date="2026-06-12")
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        cid = store.sales.add_candidate(source="monarch", sale_date="2026-06-10", account="Trust", symbol="VTI",
                                        shares=10.0, price=100.0, amount=1000.0, monarch_id="m-1")[0]
    out = sales_confirm.confirm(input_dir, cid, allocation={"0": 10.0}, tax_class="taxable", trade_date="2026-06-10")
    flags = {r["sale_id"]: r["wash_flag"] for r in _rows(input_dir)}
    assert [flags[i] for i in out["sale_ids"]] == ["possible"]
    # undo voids the row; a voided row is never scanned, and no live flagged row remains
    sales_confirm.undo(input_dir, cid)
    assert [r for r in _rows(input_dir) if r["status"] == "confirmed" and r["wash_flag"] != "none"] == []


def test_monarch_buy_triggers_a_flag(input_dir):
    sale = _loss_sale(input_dir)
    assert sale["wash_flag"] == "none"
    _monarch_buy(input_dir, date="2026-07-05")   # 25 days later
    sales_tax_year.refresh_wash_flags(input_dir)
    row = _rows(input_dir)[0]
    assert row["wash_flag"] == "possible"
    assert "25 days later" in row["wash_note"] and "Spouse_taxable" in row["wash_note"]


def test_broker_csv_buy_and_reinvestment_trigger_a_flag(input_dir):
    _loss_sale(input_dir)
    _broker_buy(input_dir, run_date="2026-06-01", kind="reinvest")
    sales_tax_year.refresh_wash_flags(input_dir)
    row = _rows(input_dir)[0]
    assert row["wash_flag"] == "possible" and "Joint_taxable" in row["wash_note"]


def test_window_and_symbol_rules_hold_for_new_sources(input_dir):
    _loss_sale(input_dir)
    _monarch_buy(input_dir, date="2026-07-11")                              # 31 days: outside
    _monarch_buy(input_dir, text="Bought 5 VXUS @ 60", date="2026-06-12")   # other symbol
    _broker_buy(input_dir, run_date="2026-05-10")                           # 31 days before: outside
    sales_tax_year.refresh_wash_flags(input_dir)
    assert _rows(input_dir)[0]["wash_flag"] == "none"


def test_scan_failure_never_fails_the_primary_operation(input_dir, monkeypatch):
    def boom(_store):
        raise RuntimeError("scan broke")
    monkeypatch.setattr(sales_tax_year, "refresh_wash_flags_in", boom)
    sale = _loss_sale(input_dir)
    assert sale["wash_flag"] == "none" and sale["status"] == "confirmed"


def test_same_purchase_in_two_sources_counts_once():
    buys = dedupe_buys(
        [{"date": "2026-06-20", "symbol": "VTI", "shares": 5.0, "account": "Spouse_taxable", "source": "holdings"}],
        [{"date": "2026-06-20", "symbol": "VTI", "shares": 5.0, "account": "Spouse_taxable", "source": "broker"}])
    assert len(buys) == 1 and buys[0]["source"] == "holdings"


def test_parse_buy_text_and_rows():
    assert sales_matching.parse_buy_text("Bought 10 VTI @ 10") == {"symbol": "VTI", "shares": 10.0, "price": 10.0}
    assert sales_matching.parse_buy_text("Sold 10 VTI @ 10") is None
    rows = [{"Category": "Buy", "Date": "2026-06-20", "Account": "A", "Original Statement": "Bought 2 VXUS @ 5"},
            {"Category": "Buy", "Date": "2026-06-20", "Account": "A", "Original Statement": "bare"},
            {"Category": "Groceries", "Date": "2026-06-20", "Account": "A", "Original Statement": "Bought 2 VXUS @ 5"}]
    assert sales_matching.buy_rows(rows) == [{"date": "2026-06-20", "account": "A", "symbol": "VXUS", "shares": 2.0, "price": 5.0}]
