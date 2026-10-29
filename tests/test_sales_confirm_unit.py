"""Plan step 2.2: confirming a queued sale against specific holdings lots, undo, dismiss, and the read-only aids."""
from __future__ import annotations

from datetime import date

import pytest

from src import active_plan, sales_confirm
from src.sales_ledger import ValidationError

LOTS = [
    {"account": "Trust", "symbol": "VTI", "purchase_date": "2023-01-10", "shares": "10", "purchase_price": "100", "lot_type": "buy", "note": "first"},
    {"account": "Trust", "symbol": "VTI", "purchase_date": "2025-12-02", "shares": "5.5", "purchase_price": "200", "lot_type": "reinvest", "note": ""},
    {"account": "Trust", "symbol": "VXUS", "purchase_date": "2024-01-02", "shares": "7", "purchase_price": "50", "lot_type": "buy", "note": ""},
    {"account": "IRA", "symbol": "VTI", "purchase_date": "2022-03-01", "shares": "4", "purchase_price": "90", "lot_type": "buy", "note": ""},
]


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(LOTS)
    return tmp_path / "input"


def _holdings(input_dir):
    with active_plan.workspace_store(input_dir.parent) as store:
        return store.dataset("holdings").rows()


def _candidate(input_dir, **over):
    f = dict(source="monarch", sale_date="2026-07-06", account="Trust", symbol="VTI", shares=12.0, price=250.0,
             amount=3000.0, monarch_id="m-1")
    f.update(over)
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        return store.sales.add_candidate(**f)[0]


def _state(input_dir, cid):
    with active_plan.workspace_store(input_dir.parent) as store:
        return next(c for c in store.sales.list_candidates() if c["candidate_id"] == cid)


def _ledger(input_dir, **kw):
    with active_plan.workspace_store(input_dir.parent) as store:
        return store.sales.list_sales(**kw)


# ---- trade date -------------------------------------------------------------------------------------------
def test_prior_business_day_skips_the_weekend():
    assert sales_confirm.prior_business_day("2026-07-07") == "2026-07-06"   # Tue -> Mon
    assert sales_confirm.prior_business_day("2026-07-06") == "2026-07-03"   # Mon -> Fri
    assert sales_confirm.prior_business_day("2026-07-05") == "2026-07-03"   # Sun -> Fri


# ---- panel ------------------------------------------------------------------------------------------------
def test_panel_lists_only_matching_lots_unselected_with_trade_date_prefill(input_dir):
    cid = _candidate(input_dir)
    p = sales_confirm.panel(input_dir, cid)
    assert [l["purchase_date"] for l in p["lots"]] == ["2023-01-10", "2025-12-02"]
    assert p["suggested_trade_date"] == "2026-07-03" and p["settle_date"] == "2026-07-06"
    assert p["year_end_case"] is False and p["allocation"] == {}
    first = p["lots"][0]
    assert first["remaining"] == 10 and first["holding_period"] == "long"
    assert first["implied_gain"] == pytest.approx(10 * (250 - 100))
    assert p["only_exact_fit"] is None


def test_panel_highlights_only_exact_fit_without_selecting_it(input_dir):
    cid = _candidate(input_dir, shares=10.0, amount=2500.0, monarch_id="m-2")
    p = sales_confirm.panel(input_dir, cid)
    assert p["only_exact_fit"] == p["lots"][0]["lot_id"] and p["allocation"] == {}


def test_panel_flags_the_december_trade_january_settle_case(input_dir):
    cid = _candidate(input_dir, sale_date="2027-01-04", monarch_id="m-3")   # Mon Jan 4 -> Fri Jan 1? prior business day
    p = sales_confirm.panel(input_dir, cid)
    assert p["suggested_trade_date"] == "2027-01-01" and p["year_end_case"] is False
    cid2 = _candidate(input_dir, sale_date="2027-01-01", monarch_id="m-4")  # Fri Jan 1 -> Thu Dec 31
    p2 = sales_confirm.panel(input_dir, cid2)
    assert p2["suggested_trade_date"] == "2026-12-31" and p2["year_end_case"] is True


def test_aids_only_fill_a_draft(input_dir):
    cid = _candidate(input_dir)
    aids = sales_confirm.panel(input_dir, cid)["aids"]
    lots = {l["purchase_date"]: l["lot_id"] for l in sales_confirm.panel(input_dir, cid)["lots"]}
    old, new = lots["2023-01-10"], lots["2025-12-02"]
    assert aids["fifo"]["allocation"] == {old: 10.0, new: 2.0}
    assert aids["hifo"]["allocation"] == {new: 5.5, old: 6.5}
    assert aids["lowest_gain"]["allocation"] == {new: 5.5, old: 6.5} or sum(aids["lowest_gain"]["allocation"].values()) == 12
    assert aids["fifo"]["gain"] == pytest.approx(10 * 150 + 2 * 50)
    assert _holdings(input_dir) == LOTS and _ledger(input_dir) == []


def test_lowest_gain_prefers_losses_then_long_term(input_dir):
    lots = [{"lot_id": "a", "remaining": 1, "basis_per_share": 100, "holding_period": "short", "purchase_date": "2026-01-01"},
            {"lot_id": "b", "remaining": 1, "basis_per_share": 100, "holding_period": "long", "purchase_date": "2020-01-01"},
            {"lot_id": "c", "remaining": 1, "basis_per_share": 300, "holding_period": "short", "purchase_date": "2026-02-01"}]
    d = sales_confirm.suggest_allocation("lowest_gain", 2, lots, 200.0)
    assert set(d["allocation"]) == {"c", "b"}   # the loss lot first, then the long-term gain over the short-term one


# ---- confirm ----------------------------------------------------------------------------------------------
def _alloc(input_dir, cid):
    lots = {l["purchase_date"]: l["lot_id"] for l in sales_confirm.panel(input_dir, cid)["lots"]}
    return {lots["2023-01-10"]: 10.0, lots["2025-12-02"]: 2.0}


def test_confirm_writes_rows_reduces_lots_and_marks_candidate(input_dir):
    cid = _candidate(input_dir)
    out = sales_confirm.confirm(input_dir, cid, allocation=_alloc(input_dir, cid), tax_class="taxable",
                                trade_date="2026-07-03")
    rows = _ledger(input_dir)
    assert len(rows) == 2 and [r["sale_id"] for r in rows] == out["sale_ids"]
    assert sum(r["proceeds"] for r in rows) == pytest.approx(3000.0)
    assert rows[0]["proceeds"] == pytest.approx(2500.0) and rows[0]["basis"] == pytest.approx(1000.0)
    assert rows[0]["gain"] == pytest.approx(1500.0) and rows[0]["holding_period"] == "long"
    assert rows[1]["holding_period"] == "short" and rows[1]["basis"] == pytest.approx(400.0)
    assert rows[0]["sale_date"] == "2026-07-03" and rows[0]["settle_date"] == "2026-07-06"
    assert rows[0]["source"] == "monarch" and rows[0]["monarch_id"] == "m-1"
    h = _holdings(input_dir)
    assert [(r["symbol"], r["shares"]) for r in h] == [("VTI", "3.5"), ("VXUS", "7"), ("VTI", "4")]
    c = _state(input_dir, cid)
    assert c["state"] == "confirmed" and c["confirmed_sale_ids"] == out["sale_ids"]


def test_confirm_non_taxable_has_no_gain_but_reduces_lots(input_dir):
    cid = _candidate(input_dir, account="IRA", shares=4.0, amount=1000.0, monarch_id="m-5")
    lot = sales_confirm.panel(input_dir, cid)["lots"][0]["lot_id"]
    sales_confirm.confirm(input_dir, cid, allocation={lot: 4.0}, tax_class="pre_tax", trade_date="2026-07-03")
    (row,) = _ledger(input_dir)
    assert row["gain"] is None and row["tax_class"] == "pre_tax"
    assert all(r["account"] != "IRA" for r in _holdings(input_dir))


@pytest.mark.parametrize("alloc_fn, text", [
    (lambda ids: {}, "must equal"),
    (lambda ids: {ids[0]: 9.0}, "must equal"),
    (lambda ids: {ids[0]: 11.0, ids[1]: 1.0}, "exceeds"),
])
def test_confirm_refuses_bad_allocations_and_changes_nothing(input_dir, alloc_fn, text):
    cid = _candidate(input_dir)
    ids = [l["lot_id"] for l in sales_confirm.panel(input_dir, cid)["lots"]]
    with pytest.raises(ValidationError, match=text):
        sales_confirm.confirm(input_dir, cid, allocation=alloc_fn(ids), tax_class="taxable", trade_date="2026-07-03")
    assert _holdings(input_dir) == LOTS and _ledger(input_dir) == [] and _state(input_dir, cid)["state"] == "unmatched"


def test_confirm_twice_is_refused_and_adds_no_rows(input_dir):
    cid = _candidate(input_dir)
    a = _alloc(input_dir, cid)
    sales_confirm.confirm(input_dir, cid, allocation=a, tax_class="taxable", trade_date="2026-07-03")
    with pytest.raises(ValidationError, match="unmatched"):
        sales_confirm.confirm(input_dir, cid, allocation=a, tax_class="taxable", trade_date="2026-07-03")
    assert len(_ledger(input_dir)) == 2


def test_confirm_taxable_lot_without_purchase_date_is_blocked_atomically(input_dir):
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        store.dataset("holdings").replace_all([{**LOTS[0], "purchase_date": ""}, LOTS[1]])
    cid = _candidate(input_dir)
    ids = [l["lot_id"] for l in sales_confirm.panel(input_dir, cid)["lots"]]
    with pytest.raises(ValidationError, match="purchase_date"):
        sales_confirm.confirm(input_dir, cid, allocation={ids[0]: 10.0, ids[1]: 2.0}, tax_class="taxable", trade_date="2026-07-03")
    assert _ledger(input_dir) == [] and _state(input_dir, cid)["state"] == "unmatched"


def test_holdings_diff_candidate_cannot_be_confirmed(input_dir):
    cid = _candidate(input_dir, source="holdings_diff", monarch_id=None)
    with pytest.raises(ValidationError, match="already removed"):
        sales_confirm.confirm(input_dir, cid, allocation={"0": 12.0}, tax_class="taxable", trade_date="2026-07-03")


def test_bare_candidate_needs_symbol_and_shares_supplied(input_dir):
    cid = _candidate(input_dir, symbol=None, shares=None, price=None, amount=500.0, monarch_id="m-6")
    lot = next(l for l in sales_confirm.panel(input_dir, cid, symbol="VXUS")["lots"])
    with pytest.raises(ValidationError, match="symbol"):
        sales_confirm.confirm(input_dir, cid, allocation={lot["lot_id"]: 7.0}, tax_class="taxable", trade_date="2026-07-03")
    sales_confirm.confirm(input_dir, cid, allocation={lot["lot_id"]: 7.0}, tax_class="taxable", trade_date="2026-07-03",
                          symbol="vxus", shares=7.0)
    (row,) = _ledger(input_dir)
    assert row["symbol"] == "VXUS" and row["proceeds"] == pytest.approx(500.0)


# ---- undo -------------------------------------------------------------------------------------------------
def test_confirm_undo_confirm_restores_identical_holdings_partial_lot_and_is_repeatable(input_dir):
    cid = _candidate(input_dir)
    a = _alloc(input_dir, cid)
    sales_confirm.confirm(input_dir, cid, allocation=a, tax_class="taxable", trade_date="2026-07-03")
    after_confirm = _holdings(input_dir)
    sales_confirm.undo(input_dir, cid)
    assert _holdings(input_dir) == LOTS                      # fully-removed lot back in place, partial lot whole
    assert _state(input_dir, cid)["state"] == "unmatched" and _state(input_dir, cid)["confirmed_sale_ids"] == []
    assert _ledger(input_dir) == [] and all(r["status"] == "voided" for r in _ledger(input_dir, include_voided=True))
    sales_confirm.confirm(input_dir, cid, allocation=a, tax_class="taxable", trade_date="2026-07-03")
    assert _holdings(input_dir) == after_confirm
    assert len(_ledger(input_dir)) == 2 and len(_ledger(input_dir, include_voided=True)) == 4


def test_undo_when_not_confirmed_is_refused(input_dir):
    cid = _candidate(input_dir)
    with pytest.raises(ValidationError, match="confirmed"):
        sales_confirm.undo(input_dir, cid)


def test_undo_is_locked_once_a_1099b_was_applied(input_dir):
    cid = _candidate(input_dir)
    out = sales_confirm.confirm(input_dir, cid, allocation=_alloc(input_dir, cid), tax_class="taxable", trade_date="2026-07-03")
    with active_plan.workspace_store(input_dir.parent, write=True) as store, store._write() as con:
        con.execute("UPDATE realized_sales SET official_proceeds = 1.0 WHERE sale_id = ?", (out["sale_ids"][0],))
    before = _holdings(input_dir)
    with pytest.raises(ValidationError, match="1099-B"):
        sales_confirm.undo(input_dir, cid)
    assert _holdings(input_dir) == before and _state(input_dir, cid)["state"] == "confirmed"


# ---- dismiss ----------------------------------------------------------------------------------------------
def test_dismiss_and_restore_change_only_the_state(input_dir):
    cid, cid2 = _candidate(input_dir), _candidate(input_dir, monarch_id="m-9")
    sales_confirm.dismiss(input_dir, cid, reason="before_ledger_start")
    sales_confirm.dismiss(input_dir, cid2, reason="not_a_sale")
    assert _state(input_dir, cid)["state"] == "dismissed" and _state(input_dir, cid2)["state"] == "not_a_sale"
    assert _holdings(input_dir) == LOTS and _ledger(input_dir) == []
    with pytest.raises(ValidationError, match="unmatched"):
        sales_confirm.dismiss(input_dir, cid, reason="other")
    sales_confirm.restore(input_dir, cid)
    assert _state(input_dir, cid)["state"] == "unmatched"
    with pytest.raises(ValidationError, match="reason"):
        sales_confirm.dismiss(input_dir, cid, reason="whatever")


def test_list_candidates_reports_state_and_counts(input_dir):
    cid = _candidate(input_dir)
    out = sales_confirm.list_candidates(input_dir)
    assert [c["candidate_id"] for c in out["candidates"]] == [cid] and out["counts"]["unmatched"] == 1
