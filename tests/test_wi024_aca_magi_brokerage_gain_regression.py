"""WI-024 phase 2, step 2 / FIN-001: ACA MAGI includes the brokerage gain.

The cascade loses premium tax credit as the realized gain raises ACA MAGI; the loss is
extra cash need in the same fixed point. The credit schedule is stubbed with a linear
phase-out so the hand value is exact: ptc(extra) = max(0, 20,000 - 20% x extra).
A 50,000 gain: loss = 20,000 - (20,000 - 10,000) = 10,000.
"""
import pytest

from src.projection_stages.withdrawal_cascade_investment_tax import (
    _InvestmentTaxState, _refresh_investment_taxes)

C = {"ltcg_0_top": 98_900.0, "ltcg_15_top": 613_700.0, "plan_start": 2026, "brk_inf": 0.02}


def ptc(extra):
    return max(0.0, 20_000.0 - 0.20 * extra)


def _state(**kw):
    base = dict(ltcg_tax=0.0, ltcg_gain=0.0, niit=0.0, available_losses=0.0, agi=60_000.0,
                taxable_inc=30_000.0, filing="MFJ", base_nii_without_ltcg=0.0, aca_ptc_fn=ptc)
    base.update(kw)
    return _InvestmentTaxState(**base)


def test_aca_credit_loss_on_a_50k_gain_closed_form():
    st = _state(ltcg_gain=50_000.0)
    delta = _refresh_investment_taxes(dict(C), st, False, 2026)
    assert st.aca_loss == pytest.approx(10_000.0)
    # LTCG tax on 50,000 stacked on 30,000 taxable: 68,900 at 0%, so 0 here; the whole
    # delta is the lost credit.
    assert delta == pytest.approx(st.ltcg_tax + 10_000.0)


def test_sale_gain_already_in_agi_is_not_double_counted_for_aca():
    st = _state(ltcg_gain=50_000.0, gain_in_agi_already=30_000.0)
    _refresh_investment_taxes(dict(C), st, False, 2026)
    assert st.aca_loss == pytest.approx(0.2 * 20_000.0)  # only 20,000 extra MAGI


def test_aca_loss_is_incremental_between_passes():
    st = _state(ltcg_gain=50_000.0)
    d1 = _refresh_investment_taxes(dict(C), st, False, 2026)
    d2 = _refresh_investment_taxes(dict(C), st, False, 2026)
    assert d1 > 0 and d2 == pytest.approx(0.0)


def test_cascade_fixed_point_converges_with_aca_feedback():
    need = 100_000.0

    def cost(w):
        st = _state(ltcg_gain=0.5 * w)
        _refresh_investment_taxes(dict(C), st, True, 2026)
        return st.ltcg_tax + st.niit + st.aca_loss

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
