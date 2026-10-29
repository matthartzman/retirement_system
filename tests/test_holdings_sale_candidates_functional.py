"""Saving a replace-style holdings import queues vanished lots as unmatched sale candidates (ledger plan 5.1)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src import active_plan
from src.server_services import holdings_service

HEADER = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
FULL = HEADER + "Brokerage,VTI,2024-01-10,10,200,buy,\nBrokerage,BND,2024-03-03,20,70,buy,\n"
ONE_GONE = HEADER + "Brokerage,BND,2024-03-03,20,70,buy,\n"


@pytest.fixture()
def plan(tmp_path: Path, monkeypatch):
    path = tmp_path / "plan.rpx"
    monkeypatch.setattr(active_plan, "active_plan_path", lambda: path)
    return path


def _save(content: str, mode: str | None, day: date = date(2026, 10, 28)):
    return holdings_service.save_holdings(content=content, base_dir=Path("."), workspace_id="w", client_id="c",
                                          user_id="u", db_path=Path("x.db"), import_mode=mode, today=day)


def _queue():
    store = active_plan.active_plan_store(readonly=True)
    try:
        return store.sales.list_candidates()
    finally:
        store.close()


def test_replace_import_with_a_lot_removed_queues_one_unconfirmed_candidate(plan):
    _save(FULL, None)
    out = _save(ONE_GONE, "replace")
    assert out["sale_candidates_added"] == 1
    [c] = _queue()
    assert (c["source"], c["state"], c["account"], c["symbol"], c["shares"], c["sale_date"]) == (
        "holdings_diff", "unmatched", "Brokerage", "VTI", 10.0, "2026-10-28")
    assert c["confirmed_sale_ids"] == []


def test_saving_the_same_file_again_adds_nothing(plan):
    _save(FULL, None)
    _save(ONE_GONE, "replace")
    assert _save(ONE_GONE, "replace")["sale_candidates_added"] == 0
    assert len(_queue()) == 1


def test_requeue_is_skipped_while_one_is_still_waiting(plan):
    _save(FULL, None)
    _save(ONE_GONE, "replace")
    _save(FULL, "replace")  # lot comes back
    assert _save(ONE_GONE, "replace")["sale_candidates_added"] == 0
    assert len(_queue()) == 1


def test_plain_save_and_merge_infer_nothing(plan):
    _save(FULL, None)
    assert "sale_candidates_added" not in _save(ONE_GONE, None)
    assert "sale_candidates_added" not in _save(FULL, "merge")
    assert _save(ONE_GONE, "merge").get("sale_candidates_added") is None
    assert _queue() == []


def test_transfer_and_split_are_not_queued(plan):
    _save(FULL, None)
    moved = HEADER + "Brokerage,BND,2024-03-03,20,70,buy,\nSpouse IRA,VTI,2024-01-10,10,200,buy,\n"
    assert _save(moved, "replace")["sale_candidates_added"] == 0
    split = HEADER + "Spouse IRA,VTI,2024-01-10,20,100,buy,\nBrokerage,BND,2024-03-03,20,70,buy,\n"
    assert _save(split, "replace")["sale_candidates_added"] == 0
    assert _queue() == []
