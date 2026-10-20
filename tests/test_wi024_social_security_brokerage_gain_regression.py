"""WI-024 phase 2, step 3 / FIN-001: Social Security taxation sees the brokerage gain.

Provisional income = other income + tax-exempt interest + 50% of benefits. MFJ bases
32,000 / 44,000. Hand case: benefits 40,000, other income 20,000.
  Without gain: provisional 20,000 + 20,000 = 40,000 -> taxable = 50% x (40,000 - 32,000) = 4,000.
  With a 20,000 gain: provisional 60,000 -> taxable = 85% x (60,000 - 44,000) + min(50% x 12,000,
  50% x 40,000) = 13,600 + 6,000 = 19,600 (cap 85% x 40,000 = 34,000 not reached).
  Extra taxable benefit = 15,600, taxed as ordinary income on top of the ordinary stack.
"""
import pytest

from src.core import social_security_taxable_amount
from src.projection_stages.withdrawal_cascade_investment_tax import (
    _InvestmentTaxState, _refresh_investment_taxes)

C = {"ltcg_0_top": 98_900.0, "ltcg_15_top": 613_700.0, "plan_start": 2026, "brk_inf": 0.02}


def _ss_extra(extra_gain):
    return (social_security_taxable_amount(40_000.0, 20_000.0 + extra_gain, "MFJ")
            - social_security_taxable_amount(40_000.0, 20_000.0, "MFJ"))


def _state(**kw):
    base = dict(ltcg_tax=0.0, ltcg_gain=0.0, niit=0.0, available_losses=0.0, agi=44_000.0,
                taxable_inc=20_000.0, filing="MFJ", base_nii_without_ltcg=0.0,
                ss_extra_fn=_ss_extra, fed_tax_fn=lambda t: 0.12 * t)
    base.update(kw)
    return _InvestmentTaxState(**base)


def test_hand_values_of_the_social_security_inclusion():
    assert social_security_taxable_amount(40_000.0, 20_000.0, "MFJ") == pytest.approx(4_000.0)
    assert social_security_taxable_amount(40_000.0, 40_000.0, "MFJ") == pytest.approx(19_600.0)
    assert _ss_extra(20_000.0) == pytest.approx(15_600.0)


def test_cascade_taxes_the_extra_benefit_as_ordinary_income_and_lifts_the_gain_stack():
    st = _state(ltcg_gain=20_000.0)
    delta = _refresh_investment_taxes(dict(C), st, False, 2026)
    assert st.ss_extra == pytest.approx(15_600.0)
    assert st.ss_tax == pytest.approx(0.12 * 15_600.0)          # 1,872.00
    # Gain stack base 20,000 + 15,600 = 35,600, all in the 0% band -> no LTCG tax.
    assert st.ltcg_tax == pytest.approx(0.0)
    assert delta == pytest.approx(1_872.0)


def test_extra_benefit_counts_in_niit_magi():
    # AGI 240,000 + gain 20,000 + extra benefit 15,600 = 275,600; excess 25,600;
    # NII 20,000 -> 3.8% x 20,000 = 760.00 (MAGI no longer binds); without the extra
    # benefit MAGI would be 260,000, excess 10,000 -> 380.00.
    st = _state(ltcg_gain=20_000.0, agi=240_000.0)
    _refresh_investment_taxes(dict(C), st, True, 2026)
    assert st.niit == pytest.approx(760.0)


def test_cascade_fixed_point_converges_with_social_security_feedback():
    need = 50_000.0

    def cost(w):
        st = _state(ltcg_gain=0.5 * w)
        _refresh_investment_taxes(dict(C), st, True, 2026)
        return st.ltcg_tax + st.niit + st.ss_tax

    w, last = need, None
    for i in range(60):
        nxt = need + cost(w)
        step = abs(nxt - w)
        if last is not None and step > 1e-9:
            assert step <= last * 0.95 + 1e-6, (i, step, last)
        w, last = nxt, step
        if step < 0.005:
            break
    assert last < 0.005
