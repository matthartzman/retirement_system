"""Holdings-import diff: lots that disappeared or shrank are candidate sales (ledger plan 5.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.import_preview import detect_sold_lots, preview_holdings_import

HEADER = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"


def _csv(*rows: str) -> str:
    return HEADER + "".join(r + "\n" for r in rows)


def _rows(text: str) -> list[dict[str, str]]:
    from src.import_preview import _csv_dict_rows
    return _csv_dict_rows(text)[0]


CURRENT = _csv(
    "Brokerage,VTI,2024-01-10,10,200,buy,",
    "Brokerage,VTI,2025-06-01,5,250,buy,",
    "Brokerage,BND,2024-03-03,20,70,buy,",
)


def test_removed_lot_is_one_candidate():
    incoming = _csv("Brokerage,VTI,2025-06-01,5,250,buy,", "Brokerage,BND,2024-03-03,20,70,buy,")
    out = detect_sold_lots(_rows(CURRENT), _rows(incoming))
    assert [(c["account"], c["symbol"], c["purchase_date"], c["shares"], c["kind"]) for c in out["candidates"]] == [
        ("Brokerage", "VTI", "2024-01-10", 10.0, "disappeared")]
    assert out["candidates"][0]["purchase_price"] == 200.0
    assert out["possible_transfers"] == [] and out["possible_corporate_actions"] == []


def test_partial_reduction_reports_shares_sold():
    incoming = _csv("Brokerage,VTI,2024-01-10,6,200,buy,", "Brokerage,VTI,2025-06-01,5,250,buy,",
                    "Brokerage,BND,2024-03-03,20,70,buy,")
    out = detect_sold_lots(_rows(CURRENT), _rows(incoming))
    [c] = out["candidates"]
    assert (c["symbol"], c["shares"], c["kind"], c["remaining_shares"]) == ("VTI", 4.0, "reduced", 6.0)


def test_increase_or_no_change_is_not_a_sale():
    incoming = _csv("Brokerage,VTI,2024-01-10,12,200,buy,", "Brokerage,VTI,2025-06-01,5,250,buy,",
                    "Brokerage,BND,2024-03-03,20,70,buy,")
    assert detect_sold_lots(_rows(CURRENT), _rows(incoming))["candidates"] == []


def test_identical_files_infer_nothing():
    assert detect_sold_lots(_rows(CURRENT), _rows(CURRENT))["candidates"] == []


def test_lot_moved_to_another_account_is_a_transfer_not_a_sale():
    incoming = _csv("Brokerage,VTI,2025-06-01,5,250,buy,", "Brokerage,BND,2024-03-03,20,70,buy,",
                    "Spouse IRA,VTI,2024-01-10,10,200,buy,")
    out = detect_sold_lots(_rows(CURRENT), _rows(incoming))
    assert out["candidates"] == []
    [t] = out["possible_transfers"]
    assert (t["symbol"], t["from_account"], t["to_account"], t["shares"]) == ("VTI", "Brokerage", "Spouse IRA", 10.0)


def test_split_is_a_corporate_action_not_a_sale():
    # 10 sh @ 200 becomes 20 sh @ 100: same date, same total basis
    incoming = _csv("Brokerage,VTI,2024-01-10,20,100,buy,", "Brokerage,VTI,2025-06-01,5,250,buy,",
                    "Brokerage,BND,2024-03-03,20,70,buy,")
    out = detect_sold_lots(_rows(CURRENT), _rows(incoming))
    assert out["candidates"] == []
    [a] = out["possible_corporate_actions"]
    assert (a["symbol"], a["account"], a["purchase_date"], a["old_shares"], a["new_shares"]) == (
        "VTI", "Brokerage", "2024-01-10", 10.0, 20.0)


def test_same_date_different_basis_is_still_a_sale():
    incoming = _csv("Brokerage,VTI,2024-01-10,20,150,buy,", "Brokerage,VTI,2025-06-01,5,250,buy,",
                    "Brokerage,BND,2024-03-03,20,70,buy,")
    out = detect_sold_lots(_rows(CURRENT), _rows(incoming))
    assert [c["symbol"] for c in out["candidates"]] == ["VTI"]


def test_matching_ignores_case_formatting_and_rounding():
    cur = _csv("brokerage,vti,01/10/2024,\"1,000\",$200.00,buy,")
    inc = _csv("Brokerage,VTI,2024-01-10,1000.0000001,200,buy,")
    assert detect_sold_lots(_rows(cur), _rows(inc))["candidates"] == []


def test_unparseable_rows_are_ignored():
    cur = _csv("Brokerage,VTI,2024-01-10,abc,200,buy,", ",CASH,,1,1,cash,")
    assert detect_sold_lots(_rows(cur), []) ["candidates"] == []


def test_preview_replace_mode_reports_candidates(tmp_path: Path):
    incoming = _csv("Brokerage,VTI,2025-06-01,5,250,buy,", "Brokerage,BND,2024-03-03,20,70,buy,")
    p = preview_holdings_import(CURRENT, incoming, project_root=tmp_path, mode="replace")
    assert p["potential_sales"]["count"] == 1
    assert p["potential_sales"]["candidates"][0]["symbol"] == "VTI"
    assert any("look sold" in w for w in p["warnings"])


@pytest.mark.parametrize("mode", ["merge", "append", "add"])
def test_preview_merge_modes_infer_nothing(tmp_path: Path, mode: str):
    incoming = _csv("Brokerage,BND,2024-03-03,20,70,buy,")
    p = preview_holdings_import(CURRENT, incoming, project_root=tmp_path, mode=mode)
    assert p["potential_sales"] == {"count": 0, "candidates": [], "possible_transfers": [], "possible_corporate_actions": []}
    assert not any("look sold" in w for w in p["warnings"])
