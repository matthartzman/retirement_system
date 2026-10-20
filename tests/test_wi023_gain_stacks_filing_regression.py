"""WI-023: home-sale and AMT/equity-comp gain stacks use the filing status in force
for the projection year (Single in a survivor year), not the plan's seeded status.

Both stacks put a 20,000 gain on 119,811 of taxable income in 2056 (bracket
factor 1.02**30 = 1.811362). Single 0% top = 49,450 x f = 89,572, so the whole
gain is in the 15% band: 20,000 x 15% = 3,000.00. MFJ control: 0% top
98,900 x f = 179,144 > 139,811, so the whole gain is at 0%: 0.00.
"""
import pytest

C = {"ltcg_0_top": 98_900.0, "ltcg_15_top": 613_700.0, "plan_start": 2026,
     "brk_inf": 0.02, "filing_status": "MFJ", "account_registry": []}


def test_home_sale_gain_stack_single_survivor_year_and_mfj_control():
    from src.projection_stages.home_sale import resolve_home_sale_gain_tax
    row = {"_home_sale_taxable_gain_pending": 20_000.0}
    single = resolve_home_sale_gain_tax(C, dict(row), year=2056, taxable_inc=119_811.0, filing="Single")
    mfj = resolve_home_sale_gain_tax(C, dict(row), year=2056, taxable_inc=119_811.0, filing="MFJ")
    assert single.tax == pytest.approx(3_000.0)
    assert mfj.tax == pytest.approx(0.0)


def test_equity_comp_gain_stack_single_survivor_year_and_mfj_control():
    from src.projection_stages.amt_equity_comp_true_up import apply_amt_and_equity_comp_true_up

    def run(filing):
        return apply_amt_and_equity_comp_true_up(
            C, year=2056, filing=filing, equity_on=True,
            equity_events={"ltcg_gain": 20_000.0, "amt_preference": 0.0},
            taxable_inc=119_811.0, fed_tax=0.0, total_tax=0.0, amt_credit_carry=0.0, bal={})

    assert run("Single").equity_comp_ltcg_tax == pytest.approx(3_000.0)
    assert run("MFJ").equity_comp_ltcg_tax == pytest.approx(0.0)
