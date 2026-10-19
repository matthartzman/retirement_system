"""363 p: the OBBBA senior bonus applies on top of itemized deductions too, not only the standard one."""
import os

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")


def test_itemizing_year_keeps_the_senior_bonus():
    from src.core import standard_deduction
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        rows = project(c)
    row = next(r for r in rows if r["year"] == 2028)          # MFJ, both 65+, itemizes (itemized + bonus > standard + bonus)
    bonus = row["senior_bonus_deduction"]
    assert bonus > 0
    std = standard_deduction(2028, "MFJ", c["brk_inf"], 2) + bonus
    taken = row["agi"] - row["taxable_inc"]
    # Hand check (2026-10 measure): before the fix 2028 taxable was 229,085 (deduction == std + bonus);
    # itemizing + bonus gives 228,854 -- 231 more deduction, 231 x 24% = 55 less federal tax (39,578 -> 39,523).
    assert taken > std + 100
