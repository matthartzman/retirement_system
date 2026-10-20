"""WI-023 / FIN-003: qualified dividends stacked at 0/15/20% in the tax kernel.

Source: documentation/archive/reports/SYSTEM_REVIEW_2026-10-19.md sections 5
(FIN-003) and 9 (WI-023).

Stack order (bottom to top): ordinary taxable income -> qualified dividends ->
realized capital gains. The ordinary schedule excludes the dividends; the
dividends and gains are taxed 0/15/20% by their position in the stack;
qualified dividends stay in net investment income for NIIT.

All expected values are hand-computed from the 2026 federal tables the dataset
marks verified (MFJ): ordinary 10% to 24,800, 12% to 100,800, 22% to 211,400;
0% LTCG band to 98,900; 15% to 613,700; NIIT threshold 250,000 at 3.8%.
Bracket factor for 2026 is 1.0 (FEDERAL_BRACKETS_VALUE_YEAR = 2026).
"""
from __future__ import annotations

import pytest

from src import tax_kernel as tk
from src.core import compute_fed_tax

YEAR = 2026
C26 = {"ltcg_0_top": 98_900.0, "ltcg_15_top": 613_700.0, "plan_start": 2026, "brk_inf": 0.02}


def _ordinary_mfj(ordinary_taxable):
    return compute_fed_tax(ordinary_taxable, YEAR, "MFJ", 0.02)


# ---- split ------------------------------------------------------------------

def test_split_caps_dividends_at_taxable_income():
    assert tk.split_qualified_dividends(110_000, 30_000) == (80_000, 30_000)
    # A deduction larger than ordinary income absorbs ordinary income first:
    # taxable 20k with 30k dividends -> dividends in the stack are 20k, ordinary 0.
    assert tk.split_qualified_dividends(20_000, 30_000) == (0.0, 20_000)
    assert tk.split_qualified_dividends(50_000, 0) == (50_000, 0.0)
    assert tk.split_qualified_dividends(-5, 10) == (0.0, 0.0)


# ---- kernel: dividends AND a realized gain together --------------------------

def test_dividends_plus_realized_gain_stack_together():
    # MFJ 2026: 80,000 ordinary taxable + 30,000 qualified dividends (in the
    # 110,000 taxable income) + 20,000 realized gain stacked above 110,000.
    #   ordinary on 80,000      = 2,480 + 0.12 * (80,000 - 24,800)  =  9,104.00
    #   dividends 80k..110k     : 18,900 at 0% (to 98,900), 11,100 at 15% = 1,665.00
    #   gain      110k..130k    : all in the 15% band                     = 3,000.00
    #   total                                                          = 13,769.00
    dividends_tax = tk.fed_tax_with_qualified(C26, _ordinary_mfj, 110_000, 30_000, YEAR)
    assert dividends_tax == pytest.approx(9_104.0 + 1_665.0)             # 10,769.00
    gain_tax = tk.ltcg_tax_on_gain(C26, 20_000, 110_000, YEAR)           # gain base INCLUDES dividends
    assert gain_tax == pytest.approx(3_000.0)
    assert dividends_tax + gain_tax == pytest.approx(13_769.0)
    # Ordering matters: stacking the gain on ordinary income only (dividends
    # left out of the base) would put 18,900 of it at 0% -- the wrong answer.
    assert tk.ltcg_tax_on_gain(C26, 20_000, 80_000, YEAR) == pytest.approx(165.0)  # 1,100 x 15%


def test_dividends_and_gain_straddle_the_20pct_threshold():
    # Ordinary 600,000; dividends 20,000 (600k..620k); gain 10,000 (620k..630k).
    #   dividends: 13,700 at 15% (to 613,700) + 6,300 at 20% = 2,055 + 1,260 = 3,315
    #   gain     : all above 613,700 -> 10,000 x 20%                         = 2,000
    flat = lambda o: 0.0  # isolate the preferential part
    assert tk.fed_tax_with_qualified(C26, flat, 620_000, 20_000, YEAR) == pytest.approx(3_315.0)
    assert tk.ltcg_tax_on_gain(C26, 10_000, 620_000, YEAR) == pytest.approx(2_000.0)


def test_dividends_fully_inside_zero_band_cost_nothing_extra():
    # 60,000 ordinary + 20,000 dividends = 80,000 taxable, all below 98,900.
    # ordinary on 60,000 = 2,480 + 0.12 * 35,200 = 6,704.00; dividends 0.00.
    assert tk.fed_tax_with_qualified(C26, _ordinary_mfj, 80_000, 20_000, YEAR) == pytest.approx(6_704.0)


def test_no_dividends_reduces_to_ordinary_schedule():
    assert tk.fed_tax_with_qualified(C26, _ordinary_mfj, 80_000, 0.0, YEAR) == pytest.approx(9_104.0)


def test_ltcg_marginal_rate_uses_stack_base_that_includes_dividends():
    # Next gain dollar on a base of 80,000 ordinary + 30,000 dividends = 110,000
    # is above 98,900 -> 15%; the same gain on 80,000 alone would be 0%.
    assert tk.ltcg_marginal_rate(110_000, 0.0, 98_900, 613_700, 1.0, False) == 0.15
    assert tk.ltcg_marginal_rate(80_000, 0.0, 98_900, 613_700, 1.0, False) == 0.0


# ---- cascade call site -------------------------------------------------------

def _state(**kw):
    from src.projection_stages.withdrawal_cascade_investment_tax import _InvestmentTaxState
    base = dict(ltcg_tax=0.0, ltcg_gain=0.0, niit=0.0, available_losses=0.0, agi=0.0,
                taxable_inc=0.0, filing="MFJ", base_nii_without_ltcg=0.0)
    base.update(kw)
    return _InvestmentTaxState(**base)


def test_cascade_stacks_realized_gain_above_dividends():
    from src.projection_stages.withdrawal_cascade_investment_tax import _refresh_investment_taxes
    # taxable_inc = 110,000 already contains the 30,000 dividends (80,000 ordinary).
    # Gain 20,000 sits 110k..130k, all at 15% = 3,000.00 (not 165.00).
    state = _state(ltcg_gain=20_000.0, taxable_inc=110_000.0, agi=140_000.0)
    _refresh_investment_taxes(dict(C26), state, False, YEAR)
    assert state.ltcg_tax == pytest.approx(3_000.0)


def test_cascade_gain_loss_offset_uses_same_stack():
    from src.projection_stages.withdrawal_cascade_investment_tax import _refresh_investment_taxes
    # Net gain = 20,000 - 5,000 loss = 15,000 at 15% = 2,250.00.
    state = _state(ltcg_gain=20_000.0, available_losses=5_000.0, taxable_inc=110_000.0, agi=140_000.0)
    _refresh_investment_taxes(dict(C26), state, False, YEAR)
    assert state.ltcg_tax == pytest.approx(2_250.0)


# ---- NIIT: qualified dividends stay in NII ----------------------------------

def test_niit_case_dividends_are_in_nii_with_realized_gain():
    from src.projection_stages.withdrawal_cascade_investment_tax import _refresh_investment_taxes
    # MFJ, AGI 400,000 (includes 30,000 qualified dividends), realized gain 20,000.
    # NII = 30,000 dividends + 20,000 gain = 50,000; MAGI excess = 400,000 - 250,000
    # = 150,000; NIIT = 3.8% x min(50,000, 150,000) = 1,900.00.
    # If the dividends were dropped from NII it would be 3.8% x 20,000 = 760.00.
    state = _state(ltcg_gain=20_000.0, taxable_inc=330_000.0, agi=400_000.0,
                   base_nii_without_ltcg=30_000.0)
    _refresh_investment_taxes(dict(C26), state, True, YEAR)
    assert state.niit == pytest.approx(1_900.0)
    assert state.niit != pytest.approx(760.0)


def test_niit_case_magi_binds():
    from src.projection_stages.withdrawal_cascade_investment_tax import _refresh_investment_taxes
    # AGI 270,000 -> MAGI excess 20,000 < NII 50,000: 3.8% x 20,000 = 760.00.
    state = _state(ltcg_gain=20_000.0, taxable_inc=200_000.0, agi=270_000.0,
                   base_nii_without_ltcg=30_000.0)
    _refresh_investment_taxes(dict(C26), state, True, YEAR)
    assert state.niit == pytest.approx(760.0)


# ---- engine: LTCG band tops from the 2026 dataset ---------------------------

def test_frozen_plan_ltcg_band_tops_come_from_the_2026_dataset():
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
    # The fixture's Model Constants carry the stale 2025 pair (96,700 / 600,050);
    # the loader treats that pair as unset and uses the verified dataset values.
    assert c["ltcg_0_top"] == 98_900.0
    assert c["ltcg_15_top"] == 613_700.0


def test_engine_row_fed_tax_matches_closed_form_every_year():
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    from src.planning_engines import project
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        rows = project(c)
    checked = 0
    for r in rows:
        qd = float(r.get("portfolio_qualified_dividends") or 0.0)
        taxable = float(r["taxable_inc"])
        if qd <= 0 or taxable <= 0:
            continue
        ordinary, qd_in = tk.split_qualified_dividends(taxable, qd)
        expected = (compute_fed_tax(ordinary, r["year"], r["filing"], c["brk_inf"])
                    + tk.ltcg_tax_on_gain(c, qd_in, ordinary, r["year"], r["filing"]))
        # fed_tax can carry later true-up adjustments (AMT, credits); allow $1.
        assert r["fed_tax"] == pytest.approx(expected, abs=1.0), r["year"]
        checked += 1
    assert checked >= 20


# ---- Roth LTCG cap: dividends are in the stack, tops from the dataset --------

def test_roth_ltcg_cap_counts_dividends_and_uses_dataset_top():
    from tests.test_roth_ltcg_niit_guardrails import _plan
    # 50,000 qualified dividends and nothing else: pre-conversion stack position
    # 50,000. Zero band tops out at 98,900 (2026 MFJ, bracket factor 1.0), so the
    # guardrail allows 98,900 - 50,000 = 48,900 of conversion (usage pct 1.0).
    c, plan = _plan({"roth_niit_cap": False}, portfolio_qualified=50_000.0)
    assert plan.pre_agi == 50_000.0
    assert plan.binding_limit == "LTCG rate tier"
    assert plan.amount == pytest.approx(98_900.0 - 50_000.0)


# ---- survivor (Single) year uses Single band tops ---------------------------

def test_survivor_single_year_stacks_on_single_band_tops():
    # Plan seeded as MFJ (c carries MFJ tops); projection year 2056 is Single.
    # Bracket factor 2056 = 1.02**30 = 1.811362 (brk_inf 0.02, value year 2026).
    # Single tops 49,450 / 545,500 -> 0% top 89,572.3 in 2056 dollars.
    # 74,192 ordinary + 45,619 qualified dividends (taxable 119,811):
    #   0% : 89,572.3 - 74,192 = 15,380.3 ; 15% : 45,619 - 15,380.3 = 30,238.7
    #   tax = 30,238.7 x 0.15 = 4,535.8 (rounded; exact below).
    c = {**C26, "filing_status": "MFJ"}
    f = 1.02 ** 30
    zero_top = 49_450.0 * f
    expected = (45_619.0 - (zero_top - 74_192.0)) * 0.15
    flat = lambda o: 0.0
    single = tk.fed_tax_with_qualified(c, flat, 119_811.0, 45_619.0, 2056, "Single")
    assert single == pytest.approx(expected)
    assert single == pytest.approx(4_535.9, abs=0.2)
    # Realized gain of 10,000 above the dividends is entirely in the 15% band: 1,500.
    assert tk.ltcg_tax_on_gain(c, 10_000.0, 119_811.0, 2056, "Single") == pytest.approx(1_500.0)
    # MFJ control: same year, MFJ tops 98,900 x f = 179,144 -> all dividends at 0%.
    assert tk.fed_tax_with_qualified(c, flat, 119_811.0, 45_619.0, 2056, "MFJ") == pytest.approx(0.0)
    assert tk.fed_tax_with_qualified(c, flat, 119_811.0, 45_619.0, 2056) == pytest.approx(0.0)
