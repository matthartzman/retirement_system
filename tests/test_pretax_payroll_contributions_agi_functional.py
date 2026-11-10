"""Pre-tax 401(k) deferrals and HSA contributions leave AGI and come out of cash.

The engine deposited the year's 401(k) deferral and HSA contribution into the
accounts but neither reduced AGI nor was paid for: wages counted in full as
taxable income and in full as spendable cash, so the deposits appeared from
nothing and every contribution year was taxed as if it had not been made.

A traditional 401(k) deferral comes out of W-2 wages (S-corp salary) or net
self-employment income; an HSA contribution is an above-the-line deduction
(Form 8889, including a >2% S-corp shareholder's W-2-routed one). Both lower
AGI and state income, neither lowers FICA/SE tax, and both are cash the
household no longer has to spend. A DAF contribution is different: it is an
itemized deduction below AGI and is already handled by the deduction stack.
"""
from __future__ import annotations

import copy
import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from tests.synthetic_plans import PLAN_START, _no_voluntary_roth, base_plan


def _config(*, k401_mo: float, hsa: bool, entity: str = 's_corp') -> dict:
    c = build_plan_from_json(copy.deepcopy(base_plan()), "")
    c = ensure_engine_config(c, source="pretax_contributions_test")
    _no_voluntary_roth(c)
    c['entity'] = entity
    c['scorp_salary'] = 60_000.0
    c['k401_mo'] = k401_mo
    c['k401_lim'] = 32_500.0
    c['earn_start'] = PLAN_START
    c['earn_end'] = PLAN_START + 1
    c['hsa_requires_hdhp'] = False
    c['hsa_contrib_base'] = 8_000.0
    c['hsa_catchup'] = 0.0
    c['hsa_last_contrib'] = PLAN_START + 1 if hsa else PLAN_START - 1
    return c


def _first_row(c: dict) -> dict:
    rows = project(c)
    rows = rows.rows if hasattr(rows, 'rows') else rows
    return next(r for r in rows if r['year'] == PLAN_START)


@pytest.fixture(scope='module')
def rows():
    return {
        'none': _first_row(_config(k401_mo=0.0, hsa=False)),
        'both': _first_row(_config(k401_mo=2_000.0, hsa=True)),
    }


def test_contributions_are_made(rows):
    assert rows['both']['k401_contrib'] == pytest.approx(24_000.0)
    assert rows['both']['hsa_contrib'] > 0.0


def test_401k_and_hsa_contributions_reduce_agi(rows):
    contrib = rows['both']['k401_contrib'] + rows['both']['hsa_contrib']
    extra_ira = rows['both']['ira_wd'] - rows['none']['ira_wd']
    assert rows['none']['agi'] - rows['both']['agi'] + extra_ira == pytest.approx(contrib, abs=1.0)
    assert rows['both']['pretax_payroll_deductions'] == pytest.approx(contrib)


def test_contributions_do_not_change_payroll_tax(rows):
    assert rows['both']['payroll_tax'] == pytest.approx(rows['none']['payroll_tax'])


def test_contributions_reduce_state_tax(rows):
    assert rows['both']['state_tax'] < rows['none']['state_tax']


def test_contributions_come_out_of_take_home_cash(rows):
    contrib = rows['both']['k401_contrib'] + rows['both']['hsa_contrib']
    assert rows['none']['income_funding'] - rows['both']['income_funding'] == pytest.approx(contrib, abs=0.01)
    bd = rows['both']['cashflow_breakdown']
    assert bd['income']['pretax_contributions'] == pytest.approx(-contrib)


def test_breakdown_key_absent_without_contributions(rows):
    assert 'pretax_contributions' not in rows['none']['cashflow_breakdown']['income']


def test_401k_deferral_cannot_exceed_scorp_salary():
    c = _config(k401_mo=2_000.0, hsa=False)
    c['scorp_salary'] = 10_000.0
    row = _first_row(c)
    assert row['k401_contrib'] == pytest.approx(10_000.0)


def test_roth_sizer_bracket_room_uses_agi_earned_income():
    from tests.test_roth_conversion_ira_draw_reserve_unit import _plan
    # Under 65, so the AGI-phased senior bonus deduction does not move the room too.
    kw = dict(earned_base=200_000.0, note_princ_yr=1_000_000.0, h_age=60.0, w_age=60.0)
    gross = _plan(**kw)
    net = _plan(earned_taxable=169_150.0, **kw)
    assert net.bracket_room - gross.bracket_room == pytest.approx(30_850.0, abs=1.0)


def test_sole_prop_deferral_also_reduces_agi():
    none = _first_row(_config(k401_mo=0.0, hsa=False, entity='sole_prop'))
    k401 = _first_row(_config(k401_mo=2_000.0, hsa=False, entity='sole_prop'))
    # Less take-home cash can mean a small extra IRA draw, which is income again.
    extra_ira = k401['ira_wd'] - none['ira_wd']
    assert none['agi'] - k401['agi'] + extra_ira == pytest.approx(24_000.0, abs=1.0)
    assert k401['payroll_tax'] == pytest.approx(none['payroll_tax'])
