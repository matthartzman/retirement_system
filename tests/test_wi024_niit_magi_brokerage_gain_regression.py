"""WI-024 phase 2, step 1 / FIN-001: NIIT MAGI includes the brokerage gain.

Closed form (MFJ, NIIT threshold 250,000, 3.8%): AGI 230,000 before the sale plus
a 100,000 realized gain -> MAGI 330,000; MAGI excess 80,000; NII 100,000;
NIIT = 3.8% x min(100,000, 80,000) = 3,040.00.
Gain already counted in AGI (home/rental sale) is not added twice.
"""
import pytest

from src.projection_stages.withdrawal_cascade_investment_tax import (
    _InvestmentTaxState, _refresh_investment_taxes)

C = {"ltcg_0_top": 98_900.0, "ltcg_15_top": 613_700.0, "plan_start": 2026, "brk_inf": 0.02}


def _state(**kw):
    base = dict(ltcg_tax=0.0, ltcg_gain=0.0, niit=0.0, available_losses=0.0, agi=230_000.0,
                taxable_inc=130_000.0, filing="MFJ", base_nii_without_ltcg=0.0)
    base.update(kw)
    return _InvestmentTaxState(**base)


def test_niit_230k_agi_plus_100k_gain():
    st = _state(ltcg_gain=100_000.0)
    _refresh_investment_taxes(dict(C), st, True, 2026)
    assert st.niit == pytest.approx(3_040.0)


def test_sale_gain_already_in_agi_is_not_double_counted():
    # 100,000 gain of which 60,000 is a home-sale gain already inside AGI (so AGI
    # 230,000 already contains it): extra MAGI = 40,000; excess 20,000; NII 100,000
    # -> 3.8% x min(100,000, 20,000) = 760.00.
    st = _state(ltcg_gain=100_000.0, gain_in_agi_already=60_000.0)
    _refresh_investment_taxes(dict(C), st, True, 2026)
    assert st.niit == pytest.approx(760.0)


def test_loss_offset_reduces_the_gain_added_to_magi():
    # 100,000 gain, 40,000 losses -> net 60,000; MAGI 290,000; excess 40,000;
    # 3.8% x min(60,000, 40,000) = 1,520.00.
    st = _state(ltcg_gain=100_000.0, available_losses=40_000.0)
    _refresh_investment_taxes(dict(C), st, True, 2026)
    assert st.niit == pytest.approx(1_520.0)


def test_cascade_fixed_point_converges_with_magi_feedback():
    """Emulates the cascade loop: paying tax needs more taxable withdrawals
    (half of each dollar withdrawn is gain), which raises the gain, MAGI, NIIT and
    LTCG tax, which raises the withdrawal. The map must contract and settle."""
    need = 200_000.0

    def total_tax(withdrawal):
        st = _state(ltcg_gain=0.5 * withdrawal)
        _refresh_investment_taxes(dict(C), st, True, 2026)
        return st.ltcg_tax + st.niit

    w = need
    last_step = None
    for i in range(40):
        w_next = need + total_tax(w)
        step = abs(w_next - w)
        if last_step is not None and step > 1e-9:
            assert step <= last_step * 0.95 + 1e-6, (i, step, last_step)  # contraction
        w, last_step = w_next, step
        if step < 0.005:
            break
    assert last_step < 0.005
    assert i < 20
