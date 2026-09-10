"""roth_conversion_policy.py — Roth Conversion Policy parameter parsing.

Extracted from src/data_io.py's parse_client() per ticket 312 / the design
doc docs/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md
(section 3, "Roth Conversion Policy"). Follows the same pattern as the
sibling modules (src/parsing/daf.py, note_receivable.py, insurance.py,
estate_planning.py): a pure function reading only the sectioned ``data``
dict, returning the fields parse_client merges into the engine config ``c``.

Imports the shared scalar/enum-coercion helpers (``_v``, ``_n``, ``_td``,
``normalize_roth_policy``, ``is_explicit_user_roth_policy``,
``strategy_for_roth_policy``, ``normalize_irmaa_guardrail_mode``,
``percent_to_float``, ``DEFAULT_ROTH_TAX_DISCOUNT_RATE``) back from
src.data_io rather than duplicating them, the same partial-circular-import
pattern already used by the other extracted parsing submodules.

IMPORTANT: ``roth_policy_lock`` is a CONDITIONAL key. It is only present in
the returned dict when ``is_explicit_user_roth_policy(roth_policy)`` is
true, matching the original inline code (``c['roth_policy_lock'] =
'USER_SELECTED'`` was only ever assigned inside that same ``if`` branch, so
the key was simply never set otherwise). Downstream code
(``workbook_builder.py``) reads it via ``c.get("roth_policy_lock")``, which
defaults to ``None`` for an absent key — so this function must NOT
default it to ``None`` in the return dict, since ``dict.update()`` would
then set the key (present, value ``None``) where the original left it
absent entirely. Do not "fix" this to always include the key.
"""
from __future__ import annotations

from ..data_io import (
    DEFAULT_ROTH_TAX_DISCOUNT_RATE,
    _n,
    _v,
    is_explicit_user_roth_policy,
    normalize_irmaa_guardrail_mode,
    normalize_roth_policy,
    percent_to_float,
    strategy_for_roth_policy,
)
from .. import taxes as _td


def parse_roth_conversion_policy(data):
    """Parse the "Withdrawal Policy > Roth Conversion" input section.

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and returns the Roth Conversion Policy
    fields that parse_client merges into the engine config ``c``.

    optimize_terminal_tax: evaluate multiple conversion policies and choose the
                           weighted after-tax terminal NW / lifetime-tax optimum
    fill_to_bracket:       fill to top of target bracket, capped by IRMAA
    fill_to_irmaa:         fill to IRMAA tier threshold only (no bracket cap)
    fixed_dollar:          convert a fixed dollar amount per year
    none:                  no voluntary conversions (forced-only via Forced Actions)
    """
    out = {}

    out['roth_policy'] = normalize_roth_policy(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                           'roth_conversion_policy', 'optimize_terminal_tax'), 'optimize_terminal_tax').strip().lower()
    if out['roth_policy'] not in _td.ROTH_POLICIES:
        out['roth_policy'] = 'optimize_terminal_tax'
    if is_explicit_user_roth_policy(out['roth_policy']):
        out['roth_policy_lock'] = 'USER_SELECTED'
    _roth_bracket_strategy = str(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()
    if _roth_bracket_strategy not in ('NONE', 'FILL_CURRENT_BRACKET', 'FILL_TARGET_BRACKET', 'PARTIAL_TARGET_BRACKET', 'IRMAA_GUARDED', 'SURVIVOR_TAX_AWARE', 'RMD_REDUCTION', 'LEGACY_TARGETED', 'OPTIMIZER_CHOOSES', 'FIXED_DOLLAR', 'PHASE_VARYING'):
        _roth_bracket_strategy = 'OPTIMIZER_CHOOSES'
    if is_explicit_user_roth_policy(out['roth_policy']) and _roth_bracket_strategy == 'OPTIMIZER_CHOOSES':
        _roth_bracket_strategy = strategy_for_roth_policy(out['roth_policy'], _roth_bracket_strategy)
    out['roth_bracket_strategy'] = _roth_bracket_strategy
    out['roth_target_rate'] = percent_to_float(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_target_bracket_rate', '0.22'), 0.22)
    out['roth_phase_rate_1'] = percent_to_float(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_phase_first_bracket_rate', '24.00%'), 0.24)
    out['roth_phase_rate_2'] = percent_to_float(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_phase_second_bracket_rate', '22.00%'), 0.22)
    out['roth_phase_rate_3'] = percent_to_float(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_phase_third_bracket_rate', '12.00%'), 0.12)
    try:
        out['roth_phase_count'] = int(_n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_phase_count', '3'), 3))
    except Exception:
        out['roth_phase_count'] = 3
    if out['roth_phase_count'] not in (2, 3):
        out['roth_phase_count'] = 3
    _roth_irmaa_target_tier = str(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_irmaa_target_tier', 'TIER_2') or 'TIER_2').strip().upper().replace(' ', '_')
    if _roth_irmaa_target_tier not in ('TIER_1', 'TIER_2', 'TIER_3', 'TIER_4', 'TIER_5'):
        _roth_irmaa_target_tier = 'TIER_2'
    out['roth_irmaa_target_tier'] = _roth_irmaa_target_tier
    try:
        _idx = int(_roth_irmaa_target_tier.split('_')[-1]) - 1
        out['roth_irmaa_target_threshold_mfj'] = float(_td.IRMAA_TIERS_BASE_YEAR.get('MFJ', [])[max(0, _idx)][0])
    except Exception:
        out['roth_irmaa_target_threshold_mfj'] = 268000.0
    out['roth_fixed_amount'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_fixed_annual_amount', '50000'), 50000)
    out['roth_max_annual_conversion_pct_of_traditional_ira'] = min(1.0, max(0.0, _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'max_annual_conversion_pct_of_traditional_ira', '20%'), 0.20)))
    try:
        out['roth_max_conversion_years'] = int(_n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'max_conversion_years', '10'), 10))
    except Exception:
        out['roth_max_conversion_years'] = 10
    _roth_objective_mode = str(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_objective_mode', 'BALANCED_RETIREMENT') or 'BALANCED_RETIREMENT').strip().upper()
    if _roth_objective_mode not in ('BALANCED_RETIREMENT', 'MINIMIZE_LIFETIME_TAX', 'MAXIMIZE_TERMINAL_NET_WORTH', 'LEGACY_OPTIMIZED', 'ESTATE_TAX_AWARE', 'CUSTOM_WEIGHTED'):
        _roth_objective_mode = 'BALANCED_RETIREMENT'
    out['roth_objective_mode'] = _roth_objective_mode
    out['roth_headroom_usage_pct'] = min(1.0, max(0.0, _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_headroom_usage_pct', '95%'), 0.95)))
    out['roth_irmaa_headroom_usage_pct'] = min(1.0, max(0.0, _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_irmaa_headroom_usage_pct', '95%'), 0.95)))
    out['irmaa_guardrail_mode'] = normalize_irmaa_guardrail_mode(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'irmaa_guardrail_mode', 'AVOID_NEXT_TIER'), 'AVOID_NEXT_TIER')
    if out['irmaa_guardrail_mode'] not in ('IGNORE', 'WARN_ONLY', 'AVOID_NEXT_TIER', 'AVOID_TIER_2_OR_ABOVE', 'CUSTOM_MAGI_CAP'):
        out['irmaa_guardrail_mode'] = 'AVOID_NEXT_TIER'
    # The single controlling setting is IRMAA Guardrail Behavior.
    if out['roth_policy'] == 'fill_to_irmaa':
        out['roth_irmaa_cap'] = True
    else:
        out['roth_irmaa_cap'] = out['irmaa_guardrail_mode'] not in ('IGNORE', 'WARN_ONLY')
    _estate_mode = str(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'estate_tax_objective_mode', 'BALANCED') or 'BALANCED').strip().upper()
    if _estate_mode not in ('OFF', 'MONITOR_ONLY', 'BALANCED', 'STRONG'):
        _estate_mode = 'BALANCED'
    out['estate_tax_objective_mode'] = _estate_mode
    out['roth_optimize_terminal_weight'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_optimize_terminal_weight', '1.0'), 1.0)
    out['roth_optimize_tax_weight'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_optimize_lifetime_tax_weight', '0.25'), 0.25)
    out['roth_optimize_terminal_tax_rate'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_optimize_terminal_pretax_tax_rate', '0.24'), 0.24)
    # Legacy-aware Roth conversion objective controls. These inputs let the
    # optimizer value tax-rate diversification, future ordinary-tax risk,
    # survivor tax compression, and the tax burden inherited with pre-tax IRA
    # balances. They are objective weights only; the projection cash-flow/tax
    # mechanics still use the standard tax assumptions.
    _legacy_mode = str(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'legacy_objective_mode', 'BALANCED') or 'BALANCED').strip().upper()
    if _legacy_mode not in ('OFF', 'LOW', 'BALANCED', 'STRONG'):
        _legacy_mode = 'BALANCED'
    out['roth_legacy_objective_mode'] = _legacy_mode
    out['roth_future_tax_rate_stress_pct'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'future_tax_rate_stress_pct', '10%'), 0.10)
    out['roth_future_tax_risk_weight'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'future_tax_risk_weight', '0.35'), 0.35)
    out['roth_inheritance_tax_burden_weight'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'inheritance_tax_burden_weight', '0.25'), 0.25)
    out['roth_heir_ordinary_tax_rate_assumption'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'heir_ordinary_tax_rate_assumption_pct', '24%'), 0.24)
    # Item 4.3: assumed beneficiary filing status. Drives the derived effective
    # SECURE Act 10-year-rule ordinary tax rate on inherited pre-tax balances
    # (used unless heir_ordinary_tax_rate_assumption_pct is set to a non-default
    # value). Single is the common adult-child-beneficiary case.
    _heir_filing = str(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'heir_filing_status', 'Single') or 'Single').strip()
    out['roth_heir_filing_status'] = _heir_filing if _heir_filing in ('Single', 'MFJ', 'HOH', 'MFS') else 'Single'
    out['roth_pre_tax_bequest_penalty_pct'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'pre_tax_bequest_penalty_pct', '15%'), 0.15)
    out['roth_bequest_preference_bonus_pct'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_bequest_preference_bonus_pct', '5%'), 0.05)
    out['roth_survivor_tax_risk_weight'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'survivor_tax_risk_weight', '0.25'), 0.25)
    out['roth_tax_discount_rate'] = _n(_v(data, 'Withdrawal Policy', 'Roth Conversion',
                                   'roth_tax_discount_rate', str(DEFAULT_ROTH_TAX_DISCOUNT_RATE)),
                                   DEFAULT_ROTH_TAX_DISCOUNT_RATE)

    return out
