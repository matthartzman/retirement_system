"""Owner rollover marks: an outgoing cash row marked as a rollover is left out of the withdrawal totals."""
import pytest

from src import cash_rollover_marks as crm, cash_view


class Meta:
    def __init__(self):
        self.d = {}

    def get_meta(self, key, default=None):
        return self.d.get(key, default)

    def set_meta(self, key, value):
        self.d[key] = value

    def delete_meta(self, key):
        self.d.pop(key, None)


def row(d, cls, amt, status="external_withdrawal", in_kind=False):
    return {"date": d, "class": cls, "amount": amt, "counts": True, "in_kind": in_kind, "pair_status": status}


def led():
    return {"A_IRA": [row("2026-04-07", "transfer_out", -355000.0), row("2026-05-01", "distribution", -40.0),
                      row("2026-06-01", "transfer_in", 90.0, "external_inflow"), row("2026-07-01", "transfer_out", -7.0, "internal")]}


def test_marked_row_becomes_external_rollover_and_leaves_the_withdrawal_totals():
    m, l = Meta(), led()
    crm.set_mark(m, "A_IRA", "2026-04-07", -355000.0, True, ledgers=led())
    crm.apply(m, l)
    assert [r["pair_status"] for r in l["A_IRA"]] == ["external_rollover", "external_withdrawal", "external_inflow", "internal"]
    assert cash_view.withdrawals_by_status(l["A_IRA"], 2026)["external_withdrawal"] == 40.0


def test_unmark_restores_the_row_and_an_empty_set_is_removed():
    m = Meta()
    crm.set_mark(m, "A_IRA", "2026-04-07", -355000.0, True, ledgers=led())
    crm.set_mark(m, "A_IRA", "2026-04-07", -355000.0, False, ledgers=led())
    assert crm.KEY not in m.d
    l = led()
    crm.apply(m, l)
    assert l["A_IRA"][0]["pair_status"] == "external_withdrawal"


def test_only_an_unpaired_cash_outflow_can_be_marked():
    m = Meta()
    for d, amt in (("2026-06-01", 90.0), ("2026-07-01", -7.0)):          # an inflow, an internal pair
        with pytest.raises(crm.MarkError, match="Only an outgoing"):
            crm.set_mark(m, "A_IRA", d, amt, True, ledgers=led())
    with pytest.raises(crm.MarkError, match="no cash row"):
        crm.set_mark(m, "A_IRA", "2026-01-01", -1.0, True, ledgers=led())
    assert not m.d


def test_a_mark_never_overrides_a_pair_made_later():
    m, l = Meta(), led()
    crm.set_mark(m, "A_IRA", "2026-05-01", -40.0, True, ledgers=led())
    l["A_IRA"][1]["pair_status"] = "internal"
    crm.apply(m, l)
    assert l["A_IRA"][1]["pair_status"] == "internal"


def test_key_ignores_account_case_and_sign():
    assert crm.mark_key("A_IRA", "2026-04-07", -5.5) == crm.mark_key("a_ira", "2026-04-07T00:00", 5.5)
