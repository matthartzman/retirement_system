"""allocation_optimizer_inputs.py — Allocation Optimizer input parsing.

Extracted from src/data_io.py's parse_client() as part of ticket 312 (design
doc docs/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
section 4, "Allocation Optimizer inputs"). src/data_io.py re-exports
parse_allocation_optimizer_inputs for backward compatibility with existing
callers.

This is the largest and densest of the five sections in that design doc: it
reads four sections/tables (``Model Constants > Allocation``, ``Asset Class
Assumptions``, ``Asset Allocation Policy``, ``Asset Class Optimizer
Controls``, ``Asset Correlations``) and includes a per-asset-class loop that
merges three CSV tables together with a local closure (``_section_vals``) and
canonicalizes class names via ``allocation_policy.canonical_asset_class``.
The loop and its closure are relocated here VERBATIM -- this is a pure code
move, not a refactor -- to avoid introducing any transcription risk in the
per-class merge logic the design doc specifically flagged.

Two output keys are conditional/derived rather than unconditionally set:

* ``allocation_source_target_class`` is only populated (via ``setdefault``)
  when the per-class loop finds an alternate-asset-class mapping whose
  ``selection_action`` is ``consider_alternate_first`` -- absent from the
  returned dict entirely otherwise, matching the pre-extraction behavior of
  ``c.setdefault('allocation_source_target_class', {})[...]`` (key never
  created unless that branch runs).
* ``cash_target_pct`` defaults from ``Model Constants > Allocation >
  cash_target_pct`` but is overridden by ``allocation_target_pct['Cash']``
  when present -- both branches live inside this function since the second
  reads a value set earlier in the same block.

``allocation_coverage`` (a nested dict of boolean coverage flags) is also
derived here, from ``c.get('allocation_source_target_class')`` -- which, per
the note above, is read via ``.get(...)`` inside this same function using a
local variable already set earlier in this block, so pulling the whole
1746-1969 span into one function preserves that intra-block dependency
exactly as it existed inside parse_client().

Imports the small scalar-coercion helpers (_v, _b, _n) back from src.data_io,
and the allocation_policy / optimization modules (aliased ``_ap`` / ``_ao``
to match the names used at the parse_client() call site) directly from
``src`` rather than through src.data_io, since those are plain sibling
modules with no circular-import concern. This mirrors the partial-circular-
import pattern already used by src/parsing/daf.py for the _v/_b/_n helpers.
"""
from __future__ import annotations

from .. import allocation_policy as _ap
from .. import optimization as _ao
from ..data_io import _b, _n, _v


def parse_allocation_optimizer_inputs(data):
    """Parse the "Allocation Optimizer Inputs" section.

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and returns the ~27 Allocation
    Optimizer input fields that parse_client merges into the engine config
    ``c``. No other already-computed scalar is needed -- signature is
    ``(data)`` only, matching the design doc's recommended interface.
    """
    c = {}

    # 1. Risk tolerance (1-10, 0 = auto-derive from age + withdrawal rate)
    c['risk_tolerance'] = _n(_v(data, 'Model Constants', 'Allocation',
                                'risk_tolerance', '0'), 0)
    # 2. Asset class assumptions (use selected capital-market horizon/preset
    # unless overridden). Returns/volatility are user-editable; full pairwise
    # correlations are editable in advanced/expert mode.
    c['asset_class_overrides'] = {}
    c['asset_class_enabled'] = {}
    c['asset_class_selection_action'] = {}
    c['asset_class_alternate_first'] = {}
    c['allocation_target_pct'] = {}
    c['allocation_optimizer_override_pct'] = {}
    c['allocation_target_notes'] = {}
    c['allocation_target_sum'] = 0.0
    c['allocation_selection_mode'] = 'user_target'
    c['allocation_optimizer_comment'] = getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', '')
    c['capital_market_config'] = {}
    c['asset_correlation_overrides'] = {}
    _aco = data.get('Asset Class Assumptions', {})
    # Client-owned asset allocation policy lives separately from system-owned
    # capital-market assumptions. Expected return/volatility and correlations
    # come from Asset Class Assumptions / Asset Correlations in system_config.csv
    # or reference files; include/min/max allocation controls come from
    # client_policy.csv under Asset Allocation Policy.
    _aap = data.get('Asset Allocation Policy', {})
    _opt_controls = data.get('Asset Class Optimizer Controls', {})
    _aap_global = _aap.get('Global', {}) if isinstance(_aap, dict) else {}
    _aap_global = _aap_global if isinstance(_aap_global, dict) else {}
    c['allocation_selection_mode'] = _ap.normalize_allocation_mode(
        _aap_global.get('allocation_selection_mode',
                        _aap_global.get('allocation_mode',
                                        _aap_global.get('use_allocation_optimizer', 'user_target')))
    )
    # Time-segmented real-loss-probability floors (holding_period.py /
    # real_loss_curves.py). Off by default so existing plans are byte-stable;
    # when enabled, the optimizer/max-Sharpe recommendation modes nudge
    # near-term liquid balance toward Cash and durable long-horizon balance
    # toward growth classes, using this household's own withdrawal-derived
    # holding-period profile rather than a flat risk-tolerance split alone.
    c['holding_period_allocation_enabled'] = _b(_aap_global.get('holding_period_allocation_enabled', 'NO'))
    c['holding_period_floor_strength'] = _n(_aap_global.get('holding_period_floor_strength', '1.0'), 1.0)
    # Tuning knobs for allocation_selection_mode=real_loss_aware's per-bucket
    # solver (_real_loss_aware_weights): risk_aversion is the same
    # mean-variance risk-aversion coefficient optimize_equity_sleeve already
    # uses; real_loss_aware_weight scales the added real-loss-probability
    # penalty term relative to variance. Defaults match the values already
    # baked into optimize_equity_sleeve's objective (risk_aversion=3.0) and a
    # neutral 1:1 weighting of the two penalty terms.
    c['real_loss_aware_risk_aversion'] = _n(_aap_global.get('real_loss_aware_risk_aversion', '3.0'), 3.0)
    c['real_loss_aware_weight'] = _n(_aap_global.get('real_loss_aware_weight', '1.0'), 1.0)
    _global = _aco.get('Global', {}) if isinstance(_aco, dict) else {}
    if isinstance(_global, dict):
        c['capital_market_config'] = {
            'assumption_mode': (_global.get('capital_market_assumption_mode') or _global.get('assumption_mode') or 'PRESET'),
            'horizon_years': _n(_global.get('capital_market_assumption_horizon_years', _global.get('horizon_years', '30')), 30),
            # 'manual' (default): use horizon_years above as configured. 'auto_from_withdrawals':
            # derive the effective horizon from this household's own projected withdrawal
            # schedule instead (see data_io._resolve_auto_horizon_and_reapply). Off by default
            # so existing plans are byte-stable unless a plan explicitly opts in.
            'horizon_source': str(_global.get('capital_market_assumption_horizon_source') or _global.get('horizon_source') or 'manual').strip().lower(),
            'preset': (_global.get('capital_market_assumption_preset') or _global.get('preset') or 'BASELINE'),
            'use_custom_capital_market_file': _b(_global.get('use_custom_capital_market_file', 'NO')),
            'custom_capital_market_file': (_global.get('custom_capital_market_file') or 'capital_market_assumptions.csv'),
            'correlation_assumption_mode': (_global.get('correlation_assumption_mode') or 'PRESET'),
            'correlation_preset': (_global.get('correlation_preset') or 'MODERATE'),
            'use_custom_correlations_file': _b(_global.get('use_custom_correlations_file', 'NO')),
            'custom_correlations_file': (_global.get('custom_correlations_file') or 'asset_correlations.csv'),
        }
    raw_class_names = set(getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}).keys())
    if isinstance(_aco, dict):
        raw_class_names.update(k for k in _aco.keys() if k != 'Global')
    if isinstance(_aap, dict):
        raw_class_names.update(k for k in _aap.keys() if k != 'Global')
    if isinstance(_opt_controls, dict):
        raw_class_names.update(k for k in _opt_controls.keys() if k != 'Global')
    class_names = sorted({_ap.canonical_asset_class(k) for k in raw_class_names})
    for cls_name in class_names:
        # Gold/precious-metal sleeves are intentionally excluded from the v7.8
        # recommendation model and from future allocation consideration.
        if cls_name not in getattr(_ao, 'ASSET_CLASSES', {}):
            continue
        def _section_vals(src, canonical):
            if not isinstance(src, dict):
                return {}
            for key, vals in src.items():
                if key == 'Global':
                    continue
                if _ap.canonical_asset_class(key) == canonical and isinstance(vals, dict):
                    return vals
            return {}
        cap_vals = _section_vals(_aco, cls_name)
        policy_vals = _section_vals(_aap, cls_name)
        opt_vals = _section_vals(_opt_controls, cls_name)
        cap_vals = cap_vals if isinstance(cap_vals, dict) else {}
        policy_vals = policy_vals if isinstance(policy_vals, dict) else {}
        default_target = getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}).get(cls_name, 0.0)
        raw_target = policy_vals.get('target_pct', '')
        target_pct = _n(raw_target, default_target)
        c['allocation_target_pct'][cls_name] = max(0.0, target_pct)
        c['allocation_target_notes'][cls_name] = getattr(_ap, 'ASSET_CLASS_NOTES', {}).get(cls_name, '')
        c['asset_class_overrides'][cls_name] = {
            'ret': _n(cap_vals.get('expected_return', ''), -1),
            'vol': _n(cap_vals.get('volatility', ''), -1),
            'target_pct': max(0.0, target_pct),
            'min_target': -1,
            'max_target': -1,
        }
        raw_override = opt_vals.get('optimizer_override_pct', '')
        c['allocation_optimizer_override_pct'][cls_name] = max(0.0, _n(raw_override, 0.0)) if str(raw_override).strip() else 0.0

        raw_action = opt_vals.get('selection_action', '')
        if str(raw_action).strip():
            action = _ap.normalize_selection_action(raw_action)
        else:
            action = getattr(_ap, 'DEFAULT_SELECTION_ACTIONS', {}).get(cls_name, getattr(_ap, 'SELECTION_INCLUDE', 'include'))
        c['asset_class_enabled'][cls_name] = action != getattr(_ap, 'SELECTION_EXCLUDE', 'exclude')
        raw_alt = opt_vals.get('alternate_asset_class', '')
        alt_text = str(raw_alt or '').strip()
        alt_cls = _ap.canonical_asset_class(alt_text) if alt_text else ''
        if alt_cls == cls_name:
            alt_cls = ''
        # If the alternate is another asset class, the optimizer redirects target
        # weight to that class. If it is an existing plan asset/source (e.g.
        # Social Security, Pension, Home Equity, Note Receivable), store the
        # source-to-target mapping so compute_allocation_coverage can count that
        # existing asset toward the selected class target.
        if alt_cls and alt_cls not in getattr(_ao, 'ASSET_CLASSES', {}):
            alt_cls = _ap.normalize_existing_asset_source(alt_cls)
            if action == getattr(_ap, 'SELECTION_ALTERNATE_FIRST', 'consider_alternate_first'):
                c.setdefault('allocation_source_target_class', {})[alt_cls] = cls_name
        c['asset_class_selection_action'][cls_name] = action
        c['asset_class_alternate_first'][cls_name] = alt_cls
    c['allocation_target_sum'] = sum(c['allocation_target_pct'].values())
    c['allocation_optimizer_override_sum'] = sum(c['allocation_optimizer_override_pct'].values())
    _corrs = data.get('Asset Correlations', {})
    if isinstance(_corrs, dict):
        for pair_name, vals in _corrs.items():
            if not isinstance(vals, dict):
                continue
            if '|' not in str(pair_name):
                continue
            _pair_parts = [_ap.canonical_asset_class(p.strip()) for p in str(pair_name).split('|', 1)]
            if any(part not in getattr(_ao, 'ASSET_CLASSES', {}) for part in _pair_parts):
                continue
            corr_val = vals.get('correlation', vals.get('corr', ''))
            if str(corr_val).strip():
                c['asset_correlation_overrides']['|'.join(_pair_parts)] = corr_val
    # 3. SS/pension bond PV — computed automatically from existing fields
    # (no new input needed — computed in allocation_optimizer.compute_optimal_allocation)
    # 4. Human capital stability factor (0-1, 0.8=stable W-2, 0.5=variable/SE)
    c['human_capital_stability'] = _n(_v(data, 'Model Constants', 'Allocation',
                                          'human_capital_stability', '0.80'), 0.80)
    # 5. Concentration flags (% of total wealth already in these categories)
    c['concentration_employer_stock'] = _n(_v(data, 'Model Constants', 'Allocation',
                                               'concentration_employer_stock', '0'), 0)
    c['concentration_real_estate'] = _n(_v(data, 'Model Constants', 'Allocation',
                                            'concentration_real_estate', '0'), 0)
    c['concentration_business'] = _n(_v(data, 'Model Constants', 'Allocation',
                                         'concentration_business', '0'), 0)
    # 6. Glide path: 'target_date' or 'static'
    c['glide_path'] = (_v(data, 'Model Constants', 'Allocation',
                          'glide_path', 'target_date') or 'target_date').strip().lower()
    # 7. Inflation-sensitive spending (fraction of total spending)
    c['inflation_sensitive_spending_pct'] = _n(_v(data, 'Model Constants', 'Allocation',
                                                   'inflation_sensitive_spending_pct', '0.15'), 0.15)
    # Cash buffer target (% of portfolio to keep in cash as market-timing buffer).
    # The guided UI exposes this in the first asset-allocation table as the
    # Cash target_pct row.
    c['cash_target_pct'] = _n(_v(data, 'Model Constants', 'Allocation',
                                  'cash_target_pct', '0.05'), 0.05)
    if c.get('allocation_target_pct', {}).get('Cash') is not None:
        try:
            c['cash_target_pct'] = float(c['allocation_target_pct'].get('Cash') or c['cash_target_pct'])
        except Exception:
            pass

    # Allocation coverage policy is generated from the first allocation table.
    # No separate count-* Plan Data switches are read.
    c['allocation_coverage'] = {
        'social_security_satisfies_fixed_income_target': False,
        'pension_satisfies_fixed_income_target': False,
        'annuities_satisfy_fixed_income_target': False,
        'note_receivable_satisfies_fixed_income_target': False,
        'include_home_equity_in_allocation_view': _b(_v(data, 'Model Constants', 'Allocation', 'include_home_equity_in_allocation_view', 'YES')),
        'home_equity_satisfies_reit_target': False,
        'liquid_reit_target_pct_when_home_not_counted': _n(_v(data, 'Model Constants', 'Allocation', 'liquid_reit_target_pct_when_home_not_counted', '5%'), 0.05),
    }
    _source_targets = c.get('allocation_source_target_class') or {}
    if _source_targets:
        _known = {'Social Security', 'Pension', 'Annuities', 'Note Receivable', 'Guaranteed income + note receivable', 'Home Equity'}
        if any(src in _known for src in _source_targets):
            # When the first allocation table is used, it becomes authoritative
            # for the old coverage-source-to-target flags.
            c['allocation_coverage']['social_security_satisfies_fixed_income_target'] = False
            c['allocation_coverage']['pension_satisfies_fixed_income_target'] = False
            c['allocation_coverage']['annuities_satisfy_fixed_income_target'] = False
            c['allocation_coverage']['note_receivable_satisfies_fixed_income_target'] = False
            c['allocation_coverage']['home_equity_satisfies_reit_target'] = False
        for _src, _target in _source_targets.items():
            _target = _ap.canonical_asset_class(_target)
            _is_fi = _target in getattr(_ap, 'FIXED_INCOME_CLASSES', set()) or _target in {'Bonds', 'Bonds/Fixed Income'}
            _is_re = _target in getattr(_ap, 'REAL_ESTATE_CLASSES', set()) or _target in {'REITs', 'REITs/Real Estate'}
            if _src == 'Guaranteed income + note receivable' and _is_fi:
                c['allocation_coverage']['social_security_satisfies_fixed_income_target'] = True
                c['allocation_coverage']['pension_satisfies_fixed_income_target'] = True
                c['allocation_coverage']['annuities_satisfy_fixed_income_target'] = True
                c['allocation_coverage']['note_receivable_satisfies_fixed_income_target'] = True
            elif _src == 'Social Security' and _is_fi:
                c['allocation_coverage']['social_security_satisfies_fixed_income_target'] = True
            elif _src == 'Pension' and _is_fi:
                c['allocation_coverage']['pension_satisfies_fixed_income_target'] = True
            elif _src == 'Annuities' and _is_fi:
                c['allocation_coverage']['annuities_satisfy_fixed_income_target'] = True
            elif _src == 'Note Receivable' and _is_fi:
                c['allocation_coverage']['note_receivable_satisfies_fixed_income_target'] = True
            elif _src == 'Home Equity' and _is_re:
                c['allocation_coverage']['include_home_equity_in_allocation_view'] = True
                c['allocation_coverage']['home_equity_satisfies_reit_target'] = True
    # Which account types should primarily accumulate cash (comma-separated)
    _cash_acct_pref = _v(data, 'Model Constants', 'Allocation',
                          'cash_accumulation_accounts', 'taxable') or 'taxable'
    c['cash_accumulation_tax_types'] = [s.strip() for s in _cash_acct_pref.split(',')]

    return c
