"""ARC-001: per-year tax-path helpers lifted from the deterministic stage."""
import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.engine_kernels import FEDERAL_BRACKETS_BASE_YEAR
from src.projection_stages import tax_paths as tp


@pytest.fixture(scope="module")
def c():
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return _frozen_config()


def _walk(brackets, factor, taxable):
    tax = 0.0
    for lo, hi, rate in brackets:
        lo, hi = lo * factor, hi * factor
        if taxable <= lo:
            break
        tax += (min(taxable, hi) - lo) * rate
    return tax


def test_ordinary_tax_matches_a_manual_bracket_walk(c):
    year = c["plan_start"] + 3
    factor = tp.bracket_factor_for_year(c, year)
    assert factor >= 1.0
    for filing in ("Single", "MFJ"):
        brackets = FEDERAL_BRACKETS_BASE_YEAR[filing]
        got = tp.ordinary_fed_tax_path(c, 200_000.0, year, filing)
        assert got == pytest.approx(_walk(brackets, factor, 200_000.0), rel=1e-9)


def test_zero_taxable_and_no_dividends_reduce_to_the_ordinary_schedule(c):
    year = c["plan_start"] + 1
    assert tp.ordinary_fed_tax_path(c, 0.0, year, "MFJ") == 0.0
    assert tp.compute_fed_tax_path(c, {}, 150_000.0, year, "MFJ") == pytest.approx(
        tp.ordinary_fed_tax_path(c, 150_000.0, year, "MFJ"))


def test_qualified_dividends_come_from_the_passed_dict(c):
    year = c["plan_start"] + 1
    with_qd = tp.compute_fed_tax_path(c, {year: 40_000.0}, 150_000.0, year, "MFJ")
    without = tp.compute_fed_tax_path(c, {}, 150_000.0, year, "MFJ")
    assert with_qd < without        # 0/15/20% on the dividends beats the ordinary rates


def test_standard_deduction_scales_with_65_plus_count(c):
    year = c["plan_start"]
    base = tp.standard_deduction_path(c, year, "MFJ", None, 0)
    assert tp.standard_deduction_path(c, year, "MFJ", None, 2) > base > 0


def test_ira_elective_delta_is_zero_without_income_and_positive_with_it(c):
    year = c["plan_start"] + 1
    fed_base = tp.compute_fed_tax_path(c, {}, 80_000.0, year, "MFJ")
    args = dict(fed_tax_base=fed_base, state_tax_base=0.0, taxable_inc_base=80_000.0,
                retirement_dist_base=0.0, year=year, filing="MFJ", ss_taxable=0.0, earned_net=0.0,
                investment_inc=0.0, nonqual_ann=0.0, roth_conv=0.0, h_over_65=False)
    zero, f0, s0 = tp.ira_elective_ordinary_tax_delta(c, {}, ira_wd_cumulative=0.0, **args)
    assert (zero, f0, s0) == (0.0, fed_base, 0.0)
    delta, f1, _s1 = tp.ira_elective_ordinary_tax_delta(c, {}, ira_wd_cumulative=20_000.0, **args)
    assert f1 > fed_base and delta > 0
