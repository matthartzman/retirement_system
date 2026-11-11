"""ARC-001: gain-stacking helpers lifted from the year loop of the deterministic stage."""
import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.core import state_for_year
from src.engine_kernels import social_security_taxable_amount, state_income_tax
from src.projection_stages import gain_stacking as gs
from src.projection_stages.other_asset_sale_tax import NO_GAINS, OtherAssetSaleGains


@pytest.fixture(scope="module")
def c():
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return _frozen_config()


def test_state_tax_at_is_the_state_income_tax_call(c):
    year = c["plan_start"] + 2
    got = gs.state_tax_at(c, year, "MFJ", 30_000.0, 60_000.0, 20_000.0, 5_000.0, 0.0, 0.0, True)
    want = state_income_tax(state_for_year(c, year), 60_000.0, 20_000.0, 5_000.0, 30_000.0, 0.0, 0.0, year, True,
                            filing="MFJ", brk_inf=c["brk_inf"], rate_override=c.get("state_rate_override"))
    assert got == pytest.approx(want)


def test_ss_extra_from_gain_is_the_marginal_taxable_benefit():
    ss_total, non_ss = 36_000.0, 40_000.0
    got = gs.ss_extra_from_gain(ss_total, non_ss, 25_000.0, 0.0, "MFJ")
    want = (social_security_taxable_amount(ss_total, non_ss + 25_000.0, "MFJ")
            - social_security_taxable_amount(ss_total, non_ss, "MFJ"))
    assert got == pytest.approx(want)
    assert gs.ss_extra_from_gain(ss_total, non_ss, 0.0, 0.0, "MFJ") == 0.0
    assert got >= 0.0


def test_aca_ptc_is_zero_without_bridge_people(c):
    assert gs.aca_ptc_with_gain(c, c["plan_start"], 10_000.0, 50_000.0, 0.0, 0.0, 0.0, 0) == 0.0


def test_stacked_tax_with_no_gain_is_zero_and_with_gain_is_positive(c):
    year = c["plan_start"] + 1

    def fed(t, y, f):
        return max(0.0, t - 20_000.0) * 0.1

    def state(inv):
        return 0.0

    none = gs.other_asset_stacked_tax(c, year, "MFJ", fed, state, 80_000.0, 90_000.0, NO_GAINS, 0.0, 0.0, 1_000.0, 0.0, 0.0)
    some = gs.other_asset_stacked_tax(c, year, "MFJ", fed, state, 80_000.0, 90_000.0, OtherAssetSaleGains(0.0, 0.0, 50_000.0, []), 0.0, 0.0, 1_000.0, 0.0, 0.0)
    assert none.total == pytest.approx(0.0)
    assert some.total > 0.0
