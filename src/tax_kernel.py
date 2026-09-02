from __future__ import annotations

"""Pure tax-calculation kernel: no config mutation, no I/O.

System review 2026-08-31, Wave 2 item 2.1 (findings A2, A6, A9, Q3). The
federal-bracket inflation factor, the IRMAA tier lookup, and the LTCG
bracket-stacking calculation were previously implemented independently in
three places -- ``src.core.ltcg_tax_on_gain``,
``run_deterministic_projection_stage``'s nested ``_ltcg_tax_on_gain_path`` /
``_bracket_factor_for_year`` (in ``src.projection_stages.deterministic_engine``),
and ``src.tlh``'s ``_ltcg_marginal_rate`` plus its caller's own bracket-factor
computation. Wave 1 item 1.12's diagnostic
(tests/test_ltcg_cross_implementation_equivalence_unit.py) proved these
implementations genuinely disagreed in practice -- up to ~$7,869 over a
30-year horizon on realistic fixture inputs. Two independent bugs drove that
divergence, both fixed by consolidating here:

1. **Inflation index.** ``core.ltcg_tax_on_gain`` inflated bracket tops using
   ``irmaa_inflator``; the engine used ``brk_inf``
   (``fed_tax_bracket_inflator``). These are independently settable and do
   diverge in shipped config (0.02 vs 0.028 in one real fixture).
2. **Compounding base year.** ``core.py`` compounded from ``plan_start``; the
   engine compounded from ``taxes.FEDERAL_BRACKETS_VALUE_YEAR`` -- the
   statutory vintage the bracket tables (including the LTCG bracket tops
   themselves, ``ltcg_0_top`` / ``ltcg_15_top``) are actually pinned to. Even
   with matched rates, a plan starting one year after the brackets' value
   year (the normal case) produced a full extra year of compounding baked in
   from year one.
3. (Separately, ``src.tlh``'s own caller read a config key, ``bracket_inf``,
   that ``data_io.py`` never sets -- it always silently fell back to its
   0.02 default regardless of the household's configured
   ``fed_tax_bracket_inflator``.)

**Financial sign-off (2026-09-01):** the unified convention is
``fed_tax_bracket_inflator`` (``brk_inf``), compounded from
``taxes.FEDERAL_BRACKETS_VALUE_YEAR`` -- i.e. the engine's pre-existing
convention, not core.py's. This treats LTCG bracket tops the same way the
ordinary federal brackets are already treated: as statutory-vintage data
inflated forward from the year it was published, using the household's
configured bracket inflator -- not the Medicare IRMAA index, which governs a
conceptually unrelated threshold. See
``documentation/GOLDEN_MASTER_CHANGELOG.md`` for the resulting golden-master
delta.
"""

from . import taxes as _td


def bracket_factor_for_year(c, year):
    """Inflation factor applied to federal ordinary-bracket and LTCG-bracket
    tops for ``year``, compounded from the brackets' own statutory value
    year (``taxes.FEDERAL_BRACKETS_VALUE_YEAR``) using ``c['brk_inf']``
    (``fed_tax_bracket_inflator``).

    ``c['bracket_index_by_year']``, when present, is an explicit per-year
    override map (used by some stress/scenario paths) layered on top of the
    same base-year-to-plan-start compounding.
    """
    base_year = getattr(_td, 'FEDERAL_BRACKETS_VALUE_YEAR', None)
    if base_year is None:
        base_year = int(c.get('plan_start', year))
    rate = float(c.get('brk_inf', 0.02) or 0.0)
    idx = c.get('bracket_index_by_year') if isinstance(c.get('bracket_index_by_year'), dict) else None
    if idx:
        base_to_plan = (1.0 + rate) ** (int(c.get('plan_start', year)) - int(base_year))
        return base_to_plan * float(idx.get(year, idx.get(int(year), 1.0)) or 1.0)
    return (1.0 + rate) ** (int(year) - int(base_year))


def irmaa_factor_for_year(c, year):
    """Inflation factor applied to IRMAA MAGI thresholds for ``year``,
    compounded from ``plan_start`` using ``c['irmaa_inflator']``. Kept
    distinct from ``bracket_factor_for_year``: IRMAA is a Medicare premium
    threshold, not a federal tax bracket, and uses its own index by design.
    """
    idx = c.get('irmaa_index_by_year') if isinstance(c.get('irmaa_index_by_year'), dict) else None
    if idx:
        return float(idx.get(year, idx.get(int(year), 1.0)) or 1.0)
    return (1.0 + float(c.get('irmaa_inflator', 0.02) or 0.0)) ** (int(year) - int(c.get('plan_start', year)))


def irmaa_surcharge(agi, year, n_people, filing, c):
    """Annual Part B + Part D IRMAA surcharge for a household at ``agi``."""
    tiers = _td.IRMAA_TIERS_BASE_YEAR.get(filing, _td.IRMAA_TIERS_BASE_YEAR['MFJ'])
    infl = irmaa_factor_for_year(c, year)
    for threshold, partb, partd in reversed(tiers):
        if agi > threshold * infl:
            return (partb + partd) * n_people * 12
    return 0.0


def irmaa_tier(agi, year, filing, c):
    """1-indexed IRMAA tier (0 = no surcharge) for a household at ``agi``."""
    tiers = _td.IRMAA_TIERS_BASE_YEAR.get(filing, _td.IRMAA_TIERS_BASE_YEAR['MFJ'])
    infl = irmaa_factor_for_year(c, year)
    for i, (threshold, _, _) in enumerate(reversed(tiers)):
        if agi > threshold * infl:
            return len(tiers) - i
    return 0


def ltcg_marginal_rate(ordinary_income, existing_gain, ltcg_0_top, ltcg_15_top,
                        bracket_factor, niit_applies):
    """Marginal LTCG rate on the next dollar of gain, given where ordinary
    income plus existing gain already sits in the stacked 0/15/20% bands.
    """
    base = max(0.0, ordinary_income) + max(0.0, existing_gain)
    top0 = ltcg_0_top * bracket_factor
    top15 = ltcg_15_top * bracket_factor
    if base < top0:
        rate = 0.0
    elif base < top15:
        rate = 0.15
    else:
        rate = 0.20
    return rate + (0.038 if niit_applies else 0.0)


def ltcg_tax_on_gain(c, gain, ordinary_income, year):
    """Total 0%/15%/20% LTCG bracket-stacking tax on ``gain``, stacked on
    top of ``ordinary_income``. The single canonical implementation -- see
    the module docstring for the inflation-index and base-year convention.

    NIIT is intentionally not included here; callers add NIIT centrally.
    """
    if gain <= 0:
        return 0.0
    infl = bracket_factor_for_year(c, year)
    top0 = float(c.get('ltcg_0_top', 0.0) or 0.0) * infl
    top15 = float(c.get('ltcg_15_top', 0.0) or 0.0) * infl
    base = max(0.0, ordinary_income)
    remaining = float(gain or 0.0)
    in0 = min(remaining, max(0.0, top0 - base))
    remaining -= in0
    in15 = min(remaining, max(0.0, top15 - max(base, top0)))
    remaining -= in15
    tax = in15 * 0.15 + max(0.0, remaining) * 0.20
    return max(0.0, tax)
