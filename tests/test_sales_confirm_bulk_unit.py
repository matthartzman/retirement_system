"""Plan step 2.2 follow-up: the bulk review list (src/sales_confirm_bulk.py) and its /api/sales/candidates/bulk routes."""
from __future__ import annotations

import pytest

from src import active_plan, sales_confirm, sales_confirm_bulk as bulk
from src.sales_ledger import ValidationError
from src.server import app, plan_routes

LOTS = [
    {"account": "Trust", "symbol": "VTI", "purchase_date": "2023-01-10", "shares": "10", "purchase_price": "100", "lot_type": "buy", "note": "first"},
    {"account": "Trust", "symbol": "VTI", "purchase_date": "2025-12-02", "shares": "5.5", "purchase_price": "200", "lot_type": "reinvest", "note": ""},
    {"account": "Trust", "symbol": "VXUS", "purchase_date": "2024-01-02", "shares": "7", "purchase_price": "50", "lot_type": "buy", "note": ""},
]


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all(LOTS)
    return tmp_path / "input"


def _cand(input_dir, **over):
    f = dict(source="monarch", sale_date="2026-07-06", account="Trust", symbol="VTI", shares=4.0, price=250.0,
             amount=1000.0, monarch_id="m-1")
    f.update(over)
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        return store.sales.add_candidate(**f)[0]


def _holdings(input_dir):
    with active_plan.workspace_store(input_dir.parent) as store:
        return store.dataset("holdings").rows()


def _states(input_dir):
    with active_plan.workspace_store(input_dir.parent) as store:
        return {c["candidate_id"]: c["state"] for c in store.sales.list_candidates()}


def _live(input_dir):
    with active_plan.workspace_store(input_dir.parent) as store:
        return store.sales.list_sales()


def _item(cid, alloc, **over):
    return {"candidate_id": cid, "allocation": alloc, "tax_class": "taxable", "trade_date": "2026-07-03", **over}


def test_review_drafts_fifo_per_item_and_flags_bad_ids(input_dir):
    a = _cand(input_dir, shares=4.0, monarch_id="a")
    b = _cand(input_dir, shares=99.0, amount=24750.0, monarch_id="b")   # more than the lots hold
    out = bulk.review(input_dir, [a, b, 12345])
    ia, ib, ic = out["items"]
    assert ia["ok"] and ia["method"] == "fifo" and ia["allocation"] == {"0": 4.0} and "hifo" in ia["aids"]
    assert ib["ok"] and ib["allocation"] == {} and ib["method"] is None   # FIFO cannot cover it: no draft
    assert not ic["ok"] and "no sale candidate" in ic["error"]
    assert _states(input_dir) == {a: "unmatched", b: "unmatched"}


def test_validate_changes_nothing_and_sees_lot_interplay(input_dir):
    a = _cand(input_dir, shares=8.0, amount=2000.0, monarch_id="a")
    b = _cand(input_dir, shares=8.0, amount=2000.0, monarch_id="b")
    before = _holdings(input_dir)
    out = bulk.validate(input_dir, [_item(a, {"0": 8}), _item(b, {"0": 8})])   # lot 0 holds 10: second is over
    assert [r["ok"] for r in out["results"]] == [True, False]
    assert "over" in out["results"][1]["error"].lower() or "remaining" in out["results"][1]["error"].lower()
    assert _holdings(input_dir) == before and _live(input_dir) == []
    assert set(_states(input_dir).values()) == {"unmatched"}


def test_confirm_many_isolates_a_failing_item(input_dir):
    a = _cand(input_dir, shares=4.0, amount=1000.0, monarch_id="a")
    b = _cand(input_dir, shares=3.0, amount=750.0, monarch_id="b")
    c = _cand(input_dir, shares=2.0, symbol="VXUS", amount=300.0, monarch_id="c")
    out = bulk.confirm(input_dir, [_item(a, {"0": 4}), _item(b, {"0": 2}), _item(c, {"2": 2})])   # b allocates 2 of 3
    assert [r["ok"] for r in out["results"]] == [True, False, True]
    assert "must equal" in out["results"][1]["error"]
    assert out["confirmed"] == [a, c] and out["succeeded"] == 2 and out["failed"] == 1
    assert _states(input_dir) == {a: "confirmed", b: "unmatched", c: "confirmed"}
    assert [r["shares"] for r in _holdings(input_dir)] == ["6", "5.5", "5"]
    assert len(_live(input_dir)) == 2


def test_confirm_many_second_item_gets_what_the_first_left(input_dir):
    a = _cand(input_dir, shares=8.0, amount=2000.0, monarch_id="a")
    b = _cand(input_dir, shares=2.0, amount=500.0, monarch_id="b")
    out = bulk.confirm(input_dir, [_item(a, {"0": 8}), _item(b, {"0": 2})])
    assert out["failed"] == 0
    assert [r["shares"] for r in _holdings(input_dir)] == ["5.5", "7"]   # lot 0 emptied by the two sales


def test_lot_ids_stay_the_ones_the_review_showed_after_an_earlier_sale_empties_a_lot(input_dir):
    a = _cand(input_dir, shares=10.0, amount=2500.0, monarch_id="a")   # empties lot 0, so the 2025 lot becomes row 0
    b = _cand(input_dir, shares=3.0, amount=750.0, monarch_id="b")
    out = bulk.confirm(input_dir, [_item(a, {"0": 10}), _item(b, {"1": 3})])   # "1" is the 2025 lot in the review
    assert out["failed"] == 0
    assert [(r["purchase_date"], r["shares"]) for r in _holdings(input_dir)] == [("2025-12-02", "2.5"), ("2024-01-02", "7")]
    assert sorted(s["purchase_date"] for s in _live(input_dir)) == ["2023-01-10", "2025-12-02"]


def test_an_id_for_a_lot_emptied_earlier_in_the_batch_fails_that_item_only(input_dir):
    a = _cand(input_dir, shares=10.0, amount=2500.0, monarch_id="a")
    b = _cand(input_dir, shares=1.0, amount=250.0, monarch_id="b")
    c = _cand(input_dir, shares=1.0, amount=250.0, monarch_id="c")
    out = bulk.confirm(input_dir, [_item(a, {"0": 10}), _item(b, {"0": 1}), _item(c, {"1": 1})])
    assert [r["ok"] for r in out["results"]] == [True, False, True]


def test_batch_undo_restores_lots_and_requeues(input_dir):
    original = _holdings(input_dir)
    a = _cand(input_dir, shares=10.0, amount=2500.0, monarch_id="a")   # takes lot 0 whole: the row is removed
    b = _cand(input_dir, shares=3.0, amount=750.0, monarch_id="b")
    done = bulk.confirm(input_dir, [_item(a, {"0": 10}), _item(b, {"1": 3})])
    assert done["confirmed"] == [a, b] and _holdings(input_dir) != original
    out = bulk.undo(input_dir, done["confirmed"])
    assert out["failed"] == 0
    assert _holdings(input_dir) == original
    assert _states(input_dir) == {a: "unmatched", b: "unmatched"}
    assert _live(input_dir) == []


def test_batch_undo_reports_a_sale_that_is_not_confirmed(input_dir):
    a = _cand(input_dir, monarch_id="a")
    b = _cand(input_dir, monarch_id="b")
    bulk.confirm(input_dir, [_item(a, {"0": 4})])
    out = bulk.undo(input_dir, [a, b])
    assert {r["candidate_id"]: r["ok"] for r in out["results"]} == {a: True, b: False}


def test_bulk_dismiss_and_restore(input_dir):
    a, b = _cand(input_dir, monarch_id="a"), _cand(input_dir, monarch_id="b")
    bulk.confirm(input_dir, [_item(b, {"0": 4})])
    out = bulk.dismiss(input_dir, [a, b], reason="not_a_sale")
    assert out["dismissed"] == [a] and out["failed"] == 1   # b is confirmed, so it is refused
    assert _states(input_dir) == {a: "not_a_sale", b: "confirmed"}
    assert bulk.restore(input_dir, out["dismissed"])["failed"] == 0
    assert _states(input_dir)[a] == "unmatched"
    with pytest.raises(ValidationError):
        bulk.dismiss(input_dir, [a], reason="bogus")


@pytest.mark.parametrize("ids", [[], None, "x", [1, 1], ["a"], list(range(bulk.MAX_ITEMS + 1))])
def test_bad_id_lists_are_refused(input_dir, ids):
    with pytest.raises(ValidationError):
        bulk.review(input_dir, ids)


def test_bad_item_shapes_are_refused_or_reported(input_dir):
    a = _cand(input_dir)
    with pytest.raises(ValidationError):
        bulk.confirm(input_dir, "nope")
    with pytest.raises(ValidationError):
        bulk.confirm(input_dir, [{"allocation": {}}])
    out = bulk.confirm(input_dir, [_item(a, {"0": "abc"})])
    assert not out["results"][0]["ok"] and "number" in out["results"][0]["error"]


@pytest.fixture()
def client(input_dir, monkeypatch):
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: input_dir)
    return app.test_client()


def test_routes_round_trip(input_dir, client):
    a, b = _cand(input_dir, monarch_id="a"), _cand(input_dir, monarch_id="b", shares=3.0, amount=750.0)
    rv = client.post("/api/sales/candidates/bulk/review", json={"candidate_ids": [a, b]}).get_json()
    assert rv["success"] and [i["allocation"] for i in rv["items"]] == [{"0": 4.0}, {"0": 3.0}]
    items = [_item(a, {"0": 4}), _item(b, {"0": 1})]
    val = client.post("/api/sales/candidates/bulk/validate", json={"items": items}).get_json()
    assert val["success"] and (val["succeeded"], val["failed"]) == (1, 1)
    done = client.post("/api/sales/candidates/bulk/confirm", json={"items": items}).get_json()
    assert done["confirmed"] == [a]
    assert client.post("/api/sales/candidates/bulk/undo", json={"candidate_ids": done["confirmed"]}).get_json()["succeeded"] == 1
    dis = client.post("/api/sales/candidates/bulk/dismiss", json={"candidate_ids": [a, b], "reason": "other"}).get_json()
    assert dis["dismissed"] == [a, b]
    assert client.post("/api/sales/candidates/bulk/restore", json={"candidate_ids": [a, b]}).get_json()["succeeded"] == 2
    assert client.post("/api/sales/candidates/bulk/confirm", json={"items": []}).status_code == 400
    assert client.post("/api/sales/candidates/bulk/dismiss", json={"candidate_ids": [a]}).status_code == 400


def test_single_sale_functions_still_work_after_the_in_store_split(input_dir):
    a = _cand(input_dir)
    sales_confirm.confirm(input_dir, a, allocation={"0": 4}, tax_class="taxable", trade_date="2026-07-03")
    sales_confirm.undo(input_dir, a)
    sales_confirm.dismiss(input_dir, a, reason="other")
    sales_confirm.restore(input_dir, a)
    assert _states(input_dir) == {a: "unmatched"}
