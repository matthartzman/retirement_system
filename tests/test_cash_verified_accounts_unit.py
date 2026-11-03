"""Verified-account gate for the pair-status floor (year-end Phase 4, owner decisions 2026-11-03): only accounts the owner has
verified against a closed year, with no unmatched rows this year, may have reported withdrawals reach the engine."""
from datetime import date

import pytest

from src import cash_tax_floor, cash_view, cash_verified_accounts as cva, cash_year_close as cyc


class Meta:
    def __init__(self):
        self.d = {}

    def get_meta(self, key, default=None):
        return self.d.get(key, default)

    def set_meta(self, key, value):
        self.d[key] = value

    def delete_meta(self, key):
        self.d.pop(key, None)


def row(d, typ, amt, status="external_withdrawal"):
    return {"date": d, "class": typ, "amount": amt, "counts": True, "in_kind": False, "pair_status": status, "pair_id": None, "partner_account": None}


LED = {"A_IRA": [row("2026-03-01", "distribution", -300.0), row("2027-02-01", "distribution", -50.0)],
       "B_Roth": [row("2026-04-01", "distribution", -10.0)]}


@pytest.fixture
def meta(monkeypatch):
    for mod in (cyc, cash_view, cva):
        monkeypatch.setattr(mod, "today", lambda: date(2027, 3, 1))
    m = Meta()
    cyc.close_year(m, 2026, ledgers={"A_IRA": LED["A_IRA"]})              # 2026 closed with A_IRA only
    return m


def test_cannot_verify_an_account_no_closed_year_covers(meta):
    with pytest.raises(cva.VerifyError, match="closed year"):
        cva.set_verified(meta, "B_Roth", True, ledgers=LED)
    assert not cva.is_verified(meta, "B_Roth")


def test_verify_and_unverify_round_trip_ignoring_case(meta):
    cva.set_verified(meta, "A_IRA", True, ledgers=LED)
    assert cva.is_verified(meta, "a_ira") and cva.is_verified(meta, "A_IRA")
    cva.set_verified(meta, "A_IRA", False, ledgers=LED)
    assert not cva.is_verified(meta, "A_IRA")


def test_eligibility_needs_verification_and_no_unmatched_rows_this_year(meta):
    led = {**LED, "A_IRA": LED["A_IRA"] + [row("2027-02-10", "transfer_out", -5.0, "unmatched")]}
    cva.set_verified(meta, "A_IRA", True, ledgers=LED)
    e = cva.eligibility(meta, 2027, led)
    assert e["A_IRA"]["verified"] and not e["A_IRA"]["eligible"] and "unmatched" in e["A_IRA"]["reason"]
    assert not e["B_Roth"]["verified"] and "not verified" in e["B_Roth"]["reason"]
    ok = cva.eligibility(meta, 2027, LED)
    assert ok["A_IRA"] == {"verified": True, "eligible": True, "reason": ""}
    # an unmatched row in an earlier year does not block this year
    old = {**LED, "A_IRA": LED["A_IRA"] + [row("2025-02-10", "transfer_out", -5.0, "unmatched")]}
    assert cva.eligibility(meta, 2027, old)["A_IRA"]["eligible"]


def test_floor_feed_drops_accounts_that_are_not_eligible(meta, monkeypatch):
    cva.set_verified(meta, "A_IRA", True, ledgers=LED)
    reported = {"A_IRA": 50.0, "B_Roth": 10.0}
    kept, skipped = cva.gate(meta, 2027, LED, reported)
    assert kept == {"A_IRA": 50.0} and list(skipped) == ["B_Roth"] and "not verified" in skipped["B_Roth"]
    assert cva.gate(meta, 2027, LED, {}) == ({}, {})


def test_floor_feed_uses_the_gate_and_records_what_it_skipped(meta, monkeypatch):
    cva.set_verified(meta, "A_IRA", True, ledgers=LED)
    monkeypatch.setattr(cash_tax_floor, "reported_draws", lambda s, y: {"A_IRA": 50.0})
    monkeypatch.setattr(cash_tax_floor, "reported_hsa_draws", lambda s, y: {"H_HSA": 7.0})
    monkeypatch.setattr(cash_tax_floor, "reported_roth_draws", lambda s, y: {"B_Roth": 10.0})
    cfg = {"cash_pair_status_tax": True, "plan_start": 2027}
    cash_tax_floor.apply_gate(cfg, meta, LED)
    assert cfg["cash_pair_floor_draws"] == {"A_IRA": 50.0}
    assert cfg["cash_pair_floor_hsa_draws"] == {} and cfg["cash_pair_floor_roth_draws"] == {}
    assert set(cfg["cash_pair_floor_skipped"]) == {"H_HSA", "B_Roth"}
