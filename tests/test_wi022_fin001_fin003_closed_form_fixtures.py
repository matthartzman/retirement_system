"""WI-022 closed-form fixtures for FIN-003 (qualified-dividend stacking) and
FIN-001 (brokerage gains in MAGI-keyed rules).

Source: documentation/archive/reports/SYSTEM_REVIEW_2026-10-19.md sections 5
(FIN-001, FIN-003) and 9 (WI-022); owner decisions in
SYSTEM_REVIEW_2026-10-19_WAVE0_DECISIONS.md (FIN-001 two phases).

Two kinds of test live here:

* PASSING tests pin the hand-computed closed form with the primitives that
  already exist (``tax_kernel.ltcg_tax_on_gain``, ``core.niit_tax``,
  ``compute_fed_tax``). They show the target numbers are reachable.
* XFAIL tests (``strict=False``) call the engine seam that WI-023 / WI-024
  will change. They fail today and document the target; they must not break
  the suite, and they flip to XPASS when the fix lands (then drop the mark).

No engine, golden or pin is changed by WI-022.

All hand calculations use the 2026 federal tables the dataset marks verified
(reference_src/tax_law_v10.json, MFJ): ordinary 10% to 24,800, 12% to
100,800, 22% to 211,400; 0% LTCG band to 98,900; 15% to 613,700; NIIT
threshold 250,000 at 3.8%. Bracket factor for 2026 is 1.0.
"""
from __future__ import annotations

import pytest

from src import tax_kernel as tk
from src.core import compute_fed_tax, niit_tax

YEAR = 2026
C26 = {"ltcg_0_top": 98_900.0, "ltcg_15_top": 613_700.0, "plan_start": 2026, "brk_inf": 0.02}

# ---- Hand-computed closed forms (MFJ, 2026) --------------------------------
# Case A: 80k ordinary taxable income + 30k qualified dividends + 20k realized gain.
ORD_80K_TAX = 2_480.0 + 0.12 * (80_000 - 24_800)          # 9,104.00
QD_IN_ZERO_BAND = 98_900 - 80_000                         # 18,900 of the 30k at 0%
QD_AT_15 = 30_000 - QD_IN_ZERO_BAND                       # 11,100
PREF_QD = QD_AT_15 * 0.15                                 # 1,665.00
PREF_GAIN = 20_000 * 0.15                                 # 3,000.00 (stacked above 110k)
TARGET_FED_A = ORD_80K_TAX + PREF_QD + PREF_GAIN          # 13,769.00
# Today the 30k dividends sit in the ordinary stack: ordinary tax on 110k.
TODAY_ORD_110K_TAX = 2_480.0 + 0.12 * 76_000 + 0.22 * (110_000 - 100_800)  # 13,624.00
OVERSTATEMENT_QD = TODAY_ORD_110K_TAX - (ORD_80K_TAX + PREF_QD)            # 2,855.00


def test_hand_arithmetic_is_self_consistent():
    assert ORD_80K_TAX == pytest.approx(9_104.0)
    assert PREF_QD == pytest.approx(1_665.0)
    assert PREF_GAIN == pytest.approx(3_000.0)
    assert TARGET_FED_A == pytest.approx(13_769.0)
    assert TODAY_ORD_110K_TAX == pytest.approx(13_624.0)
    assert OVERSTATEMENT_QD == pytest.approx(2_855.0)


# ---- FIN-003: passing primitives -------------------------------------------

def test_ordinary_schedule_matches_hand_value_for_80k():
    assert compute_fed_tax(80_000, YEAR, "MFJ", 0.02) == pytest.approx(ORD_80K_TAX)


def test_dividends_alone_fill_zero_band_then_15pct():
    # 30k qualified dividends stacked on 80k ordinary: 18.9k at 0%, 11.1k at 15%.
    assert tk.ltcg_tax_on_gain(C26, 30_000, 80_000, YEAR) == pytest.approx(PREF_QD)


def test_gain_stacks_above_dividends_at_15pct():
    # The realized 20k gain sits above 80k + 30k = 110k, entirely in the 15% band.
    assert tk.ltcg_tax_on_gain(C26, 20_000, 110_000, YEAR) == pytest.approx(PREF_GAIN)


def test_dividends_plus_gain_together_equal_sum_of_parts():
    # Dividends and gain stacked as one preferential block above 80k ordinary.
    assert tk.ltcg_tax_on_gain(C26, 50_000, 80_000, YEAR) == pytest.approx(PREF_QD + PREF_GAIN)
    assert tk.ltcg_tax_on_gain(C26, 50_000, 80_000, YEAR) == pytest.approx(4_665.0)


def test_twenty_percent_applies_only_above_15pct_top():
    # 20% only above 613,700: 10k of gain above the top of the 15% band.
    assert tk.ltcg_tax_on_gain(C26, 10_000, 613_700, YEAR) == pytest.approx(2_000.0)
    assert tk.ltcg_tax_on_gain(C26, 10_000, 603_700, YEAR) == pytest.approx(1_500.0)


def test_qualified_dividends_stay_in_nii_for_niit():
    # AGI 400k MFJ includes 30k qualified dividends and nothing else investment.
    # NII = 30k, MAGI excess = 150k -> 3.8% x min(30k, 150k) = 1,140.
    assert niit_tax(30_000, 400_000, "MFJ") == pytest.approx(1_140.0)
    assert niit_tax(0, 400_000, "MFJ") == 0.0  # if dividends were left out of NII


# ---- FIN-003: engine target (WI-023 implemented; xfail removed) ------------

@pytest.fixture(scope="module")
def frozen_rows():
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    from src.planning_engines import project

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        rows = project(c)
    return c, rows


def test_engine_federal_tax_taxes_qualified_dividends_at_preferential_rates(frozen_rows):
    c, rows = frozen_rows
    row = rows[0]
    qd = float(row["portfolio_qualified_dividends"])
    taxable = float(row["taxable_inc"])
    assert qd > 0 and taxable > qd
    # fed_tax on the row is the ordinary-schedule tax; the gain tax is carried
    # separately in ltcg_tax, so the expected value covers ordinary + QD only.
    expected = (compute_fed_tax(taxable - qd, row["year"], row["filing"], c["brk_inf"])
                + tk.ltcg_tax_on_gain(c, qd, taxable - qd, row["year"]))
    assert row["fed_tax"] == pytest.approx(expected, abs=1.0)


# ---- FIN-001 phase 2: NIIT (xfail until WI-024) ----------------------------

NIIT_CASE = 0.038 * min(100_000, 330_000 - 250_000)   # 3,040.00


def test_niit_closed_form_230k_agi_plus_100k_gain():
    assert NIIT_CASE == pytest.approx(3_040.0)
    # Formula with MAGI that includes the gain (the target convention).
    assert niit_tax(100_000, 230_000 + 100_000, "MFJ") == pytest.approx(3_040.0)
    # Today's cascade passes the first-pass AGI (gain excluded): no NIIT at all.
    assert niit_tax(100_000, 230_000, "MFJ") == 0.0


def test_cascade_niit_uses_magi_that_includes_brokerage_gain():
    from src.projection_stages.withdrawal_cascade_investment_tax import (
        _InvestmentTaxState, _refresh_investment_taxes)

    c = dict(C26)
    state = _InvestmentTaxState(
        ltcg_tax=0.0, ltcg_gain=100_000.0, niit=0.0, available_losses=0.0,
        agi=230_000.0, taxable_inc=130_000.0, filing="MFJ", base_nii_without_ltcg=0.0)
    _refresh_investment_taxes(c, state, True, YEAR)
    assert state.niit == pytest.approx(3_040.0)


# ---- FIN-001 phase 1: IRMAA MAGI (xfail until WI-024 phase 1) ---------------

def test_irmaa_magi_includes_brokerage_gain_realized_in_year(frozen_rows):
    _c, rows = frozen_rows
    checked = 0
    for r in rows:
        gain = float(r.get("ltcg_gain") or 0.0)
        used = min(float(r.get("cap_loss_used") or 0.0), gain)
        sale = float(r.get("sale_cap_gain_in_agi") or 0.0)
        brokerage_net = max(0.0, gain - used - sale)
        if brokerage_net < 1_000.0:
            continue
        checked += 1
        # irmaa_magi_current >= AGI (ordinary AGI + any sale gain already in it) + brokerage net gain.
        assert float(r["irmaa_magi_current"]) >= float(r["agi"]) + brokerage_net - 1.0, r["year"]
    assert checked >= 2
