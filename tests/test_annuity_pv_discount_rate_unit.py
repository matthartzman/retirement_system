"""Annuity PV in net worth: an optional discount rate of its own (annuity_pv_discount_rate).

Blank keeps the historic behaviour (discount at the portfolio return, c['ret']); a value
discounts the remaining guaranteed payments at that rate instead. Only net worth moves:
the portfolio's own growth still runs at c['ret'].
"""
from types import SimpleNamespace

import pytest

from src.parsing import client_sections
from src.projection_stages import portfolio_growth_and_net_worth as stage

YEAR = 2026
PMT = 10_000.0
STREAMS = ('wife_single', 'h_single', 'wife_joint', 'h_joint', 'wife_pension', 'wife_qlac', 'h_qlac')


def _config(**overrides):
    c = {
        'ret': 0.08, 'h_death_yr': 2028, 'w_death_yr': 2028, 'plan_end': 2028,
        'ann_db': {}, 'all_acct_ids': [],
        **{k: {'base': 0, 'init_pmt': 0, 'first_yr': YEAR, 'div_rate': 0, 'add_pct': 0} for k in STREAMS},
    }
    c['h_joint'] = {**c['h_joint'], 'init_pmt': PMT / 12}
    c.update(overrides)
    return c


def _row(c, monkeypatch):
    monkeypatch.setattr(stage._legacy_pe, 'apply_end_of_year_growth',
                        lambda *a, **k: SimpleNamespace(by_account={}, warnings=[]))
    row = {}
    stage.apply_portfolio_growth_and_net_worth(
        c, year=YEAR, h_alive=True, w_alive=True, bal={}, row=row, emit=lambda e: None,
        home_equity=0.0, home_val=0.0, autos_val=0.0, startup=0.0, note_bal=0.0,
        cst_balance=0.0, mort_bal_yr=0.0)
    return row


def _pv(rate):
    return sum(PMT / (1 + rate) ** n for n in range(3))   # 2026..2028, first payment undiscounted


def test_blank_rate_discounts_at_portfolio_return(monkeypatch):
    row = _row(_config(), monkeypatch)
    assert row['h_joint_pv'] == pytest.approx(_pv(0.08))
    assert row['total_nw'] == pytest.approx(_pv(0.08))


def test_own_rate_discounts_annuities_only_at_that_rate(monkeypatch):
    row = _row(_config(ann_pv_rate=0.05), monkeypatch)
    assert row['h_joint_pv'] == pytest.approx(_pv(0.05))
    assert row['total_nw'] == pytest.approx(_pv(0.05))


def test_plan_field_parses_and_blank_means_unset():
    def parse(value):
        data = {'Economic Assumptions': {'': {'annuity_pv_discount_rate': value}}}
        return client_sections.annuity_pv_rate(data)
    assert parse('5.00%') == pytest.approx(0.05)
    assert parse('') is None
    assert client_sections.annuity_pv_rate({}) is None
