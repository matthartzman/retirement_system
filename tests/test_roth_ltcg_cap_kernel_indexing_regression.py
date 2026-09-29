"""WI-306 / FIN-014 (system review 2026-09-25-2): the Roth-sizing LTCG
rate-tier guardrail must index the 0%/15% LTCG ceilings with the same
convention tax assessment uses (``tax_kernel.bracket_factor_for_year``,
compounded from ``FEDERAL_BRACKETS_VALUE_YEAR``), not a local
``(1+brk_inf)**(year-plan_start)`` re-implementation that sits about one
year of indexing low for a 2026-start plan.
"""
import inspect

import src.gain_harvest as gh
import src.planning_engines as pe
import src.reporting.sheets_tax_capacity as stc
from src import tax_kernel as tk
from tests.test_roth_ltcg_niit_guardrails import _plan


def test_ltcg_cap_threshold_matches_kernel_ltcg_tax_threshold():
    year = 2031
    # plan_start differs from the brackets' value year (2026) on purpose so the
    # old (year - plan_start) convention would give a visibly different factor.
    c, plan = _plan({'roth_niit_cap': False, 'brk_inf': 0.03, 'plan_start': 2028},
                    year=year, portfolio_qualified=200_000.0)
    assert plan.binding_limit == 'LTCG rate tier'
    top0, top15 = pe._roth_ltcg_thresholds_base(c, 'MFJ')
    factor = tk.bracket_factor_for_year(c, year)
    ceiling = plan.pre_agi + plan.amount
    assert abs(ceiling - top15 * factor) < 1e-6
    # The old plan_start convention gives a different factor (guards against
    # a silent revert): the brackets' value year is not plan_start here.
    assert abs(factor - 1.03 ** (year - 2028)) > 1e-6

    # The kernel's own LTCG stacking crosses 15% -> 20% exactly at the ceiling.
    kc = {**c, 'ltcg_0_top': top0, 'ltcg_15_top': top15}
    assert abs(tk.ltcg_tax_on_gain(kc, 1_000.0, ceiling - 1_000.0, year) - 150.0) < 1e-6
    assert abs(tk.ltcg_tax_on_gain(kc, 1_000.0, ceiling, year) - 200.0) < 1e-6


def test_no_local_plan_start_bracket_indexing_left():
    for mod in (pe, gh, stc):
        assert "bracket_inf'" not in inspect.getsource(mod), mod.__name__
    assert "(year - plan_start)" not in inspect.getsource(pe.plan_roth_conversion)


def test_gain_harvest_scan_uses_kernel_factor():
    c = {'ltcg_0_top': 100_000.0, 'brk_inf': 0.03, 'plan_start': 2026, 'lots': []}
    out = gh.scan_gain_harvest_opportunities(c, 2030, ordinary_income=0.0)
    assert abs(out['headroom'] - 100_000.0 * tk.bracket_factor_for_year(c, 2030)) < 1e-6
