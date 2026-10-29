"""Plan step 2.3: the ``unmatched_sale`` reconciliation hint on the Planner's reconcile side."""
from __future__ import annotations

import re

from src import active_plan, reconcile, reconcile_sale_hints as hints


def _row(label="Brokerage A", difference=-5000.0, balance_date="2026-10-14"):
    return {"id": f"setup:{label}", "label": label, "difference": difference,
            "monarch_accounts": [{"balance_date": balance_date}]}


def _cand(**kw):
    base = {"candidate_id": 1, "state": "unmatched", "account": "Brokerage A", "symbol": "VTI", "shares": 20.0,
            "price": 250.0, "amount": 5000.0, "sale_date": "2026-10-15"}
    return {**base, **kw}


def test_gap_within_five_percent_of_unmatched_sale_gives_a_hint():
    out = hints.sale_hints([_row(difference=-4900.0)], [_cand()], [])
    h = out["by_row"]["setup:Brokerage A"]
    assert h["kind"] == "unmatched_sale"
    assert h["text"] == "Sale of ~20 VTI on 2026-10-15 is waiting to be confirmed."
    assert out["count"] == 1


def test_gap_outside_tolerance_gives_no_hint_but_still_counts():
    out = hints.sale_hints([_row(difference=-3000.0)], [_cand()], [])
    assert out["by_row"] == {} and out["count"] == 1


def test_sale_dated_on_or_before_the_balance_date_is_not_a_hint():
    out = hints.sale_hints([_row()], [_cand(sale_date="2026-10-14")], [])
    assert out["by_row"] == {}


def test_other_accounts_candidate_is_not_a_hint():
    assert hints.sale_hints([_row()], [_cand(account="Other")], [])["by_row"] == {}


def test_candidate_not_unmatched_is_ignored_and_not_counted():
    out = hints.sale_hints([_row()], [_cand(state="dismissed")], [])
    assert out == {"count": 0, "by_row": {}}


def test_amount_falls_back_to_shares_times_price():
    out = hints.sale_hints([_row()], [_cand(amount=None)], [])
    assert "setup:Brokerage A" in out["by_row"]


def test_confirmed_ledger_sale_also_hints():
    sale = {"status": "confirmed", "account": "Brokerage A", "symbol": "VTI", "shares": 20.0,
            "proceeds": 5000.0, "sale_date": "2026-10-15"}
    out = hints.sale_hints([_row()], [], [sale])
    assert out["by_row"]["setup:Brokerage A"]["text"].startswith("Sale of ~20 VTI on 2026-10-15")
    assert out["count"] == 0


def test_percent_mode_hint_has_no_dollars_shares_or_prices():
    out = hints.sale_hints([_row()], [_cand()], [], percent_mode=True)
    h = out["by_row"]["setup:Brokerage A"]
    assert set(h) == {"kind", "symbol", "sale_date", "text"}
    assert not re.search(r"[\d$]", h["text"].replace("2026-10-15", ""))
    assert "20" not in h["text"] and "5000" not in repr(h) and "250" not in repr(h)


def test_build_rows_carries_the_count_and_hint(tmp_path):
    from tests.test_reconcile_unit import _workspace, TODAY
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.sales.add_candidate(source="monarch", sale_date="2026-10-15", account="Brokerage A", symbol="VTI",
                                  shares=20, price=250, amount=104000.0)
    data = reconcile.build_rows(base / "input", today=TODAY)
    assert data["unmatched_sale_count"] == 1
    row = next(r for r in data["rows"] if r["id"] == "setup:Brokerage A")
    assert row["sale_hint"]["kind"] == "unmatched_sale"
