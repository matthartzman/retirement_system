"""advanced_modules.py — advanced planning-module input parsing.

Extracted from src/data_io.py as part of system review 2026-08-31, finding
A5 / Wave 3 item 3.13 ("split parse_client into src/parsing/ siblings; move
validation out"). src/data_io.py re-exports parse_advanced_modules for
backward compatibility with existing callers.

Imports the small scalar-coercion helpers (_b, _n, _y) and the life-policy
type set back from src.data_io rather than duplicating them: those helpers
are still shared primitives used throughout parse_client and are themselves
slated for their own future extraction (see the item 3.13 tracking note in
src/parsing/__init__.py). This works because src.data_io defines them before
importing this module (see the "===== BEGIN data_parser.py =====" section),
the same partial-circular-import pattern already used elsewhere in that
module (e.g. its lazy imports of .portfolio_analytics/.config_backend).
"""
from __future__ import annotations

from ..data_io import _LIFE_POLICY_TYPES, _b, _n, _y


def parse_advanced_modules(data):
    """Parse the advanced planning-module input sections into structured config.

    Reads the already-loaded sectioned ``data`` dict (``{section: {subsection:
    {label: value}}}``) and returns a dict of module keys that ``parse_client``
    merges into the engine config ``c``. Every module key is always present
    (empty containers when a section is absent) so the workbook's optional-
    function gating and the report-sheet builders can rely on the keys existing.

    Phase 1 scope: these modules are report-only. They do not feed the
    projection engine. Cross-module engine integration (equity-comp AMT into
    Sheet 7, business value into Sheet 14 estate liquidity, disability
    re-projection) is deliberately deferred to a later phase.
    """
    # ── Education funding (529 accounts + goals) ─────────────────────────────
    edu_accounts, edu_goals, edu_policy = [], [], {}
    for sub, vals in data.get('Education Funding', {}).items():
        if not sub or sub == '529 Accounts':
            continue
        low = sub.lower()
        if low == 'policy':
            edu_policy = {
                'allow_secure_2_roth_rollover': _b(vals.get('allow_secure_2_roth_rollover', 'FALSE')),
                'state_deduction_limit_annual': _n(vals.get('state_deduction_limit_annual', '0'), 0),
            }
        elif 'goal' in low:
            edu_goals.append({
                'name': sub,
                'beneficiary': vals.get('beneficiary', ''),
                'start_year': _y(vals.get('start_year', '0'), 0),
                'end_year': _y(vals.get('end_year', '0'), 0),
                'annual_cost_today': _n(vals.get('annual_cost_today', '0'), 0),
                'cost_inflation_rate': _n(vals.get('cost_inflation_rate', '0.05'), 0.05),
            })
        else:
            # 529 account. Support both the demo schema
            # (balance_today / monthly_contribution) and the UI-generated schema
            # (current_balance / annual_contribution).
            monthly = vals.get('monthly_contribution', '')
            if str(monthly).strip():
                annual_contribution = _n(monthly, 0) * 12
            else:
                annual_contribution = _n(vals.get('annual_contribution', '0'), 0)
            edu_accounts.append({
                'name': sub,
                'owner': vals.get('owner', ''),
                'beneficiary': vals.get('beneficiary', ''),
                'balance_today': _n(vals.get('balance_today', vals.get('current_balance', '0')), 0),
                'annual_contribution': annual_contribution,
                'contribution_start_year': _y(vals.get('contribution_start_year', '0'), 0),
                'contribution_end_year': _y(vals.get('contribution_end_year', '0'), 0),
                'growth_rate': _n(vals.get('growth_rate', '0.06'), 0.06),
                'state_deduction_eligible': _b(vals.get('state_deduction_eligible', 'FALSE')),
            })

    # ── Insurance In Force: life / disability / P&C classification ───────────
    life_policies = []
    disability = {'policies': [], 'simulate_year': 0}
    pc = {'policies': [], 'umbrella_target_multiple': 0.0}
    for sub, vals in data.get('Insurance In Force', {}).items():
        if not sub:
            continue
        labels = set(vals.keys())
        ptype = str(vals.get('policy_type', '')).strip().lower()
        low = sub.lower()
        # Summary count rows (subsection carries only a policy_count) are skipped.
        if labels <= {'policy_count'}:
            continue
        if low == 'pc_targets':
            pc['umbrella_target_multiple'] = _n(vals.get('umbrella_target_multiple_of_nw', '0'), 0)
            continue
        if low == 'di_scenario':
            disability['simulate_year'] = _y(vals.get('simulate_disability_year', '0'), 0)
            continue
        if low.startswith('di_') or 'monthly_benefit' in labels or 'benefit_period_years' in labels:
            disability['policies'].append({
                'name': sub,
                'insured': vals.get('insured', ''),
                'coverage_type': vals.get('type', ''),
                'monthly_benefit': _n(vals.get('monthly_benefit', '0'), 0),
                'elimination_days': _y(vals.get('elimination_days', '0'), 0),
                'benefit_period_years': _y(vals.get('benefit_period_years', '0'), 0),
                'premium_annual': _n(vals.get('premium_annual', '0'), 0),
                'premium_pre_tax': _b(vals.get('premium_pre_tax', 'FALSE')),
            })
            continue
        if low.startswith('pc_') or 'coverage_limit' in labels or ptype in ('ho', 'auto', 'umbrella'):
            pc['policies'].append({
                'name': sub,
                'policy_type': vals.get('policy_type', ''),
                'coverage_limit': _n(vals.get('coverage_limit', '0'), 0),
                'deductible': _n(vals.get('deductible', '0'), 0),
                'annual_premium': _n(vals.get('annual_premium', '0'), 0),
            })
            continue
        if 'face_amount' in labels or ptype in _LIFE_POLICY_TYPES:
            life_policies.append({
                'name': sub,
                'owner': vals.get('owner', ''),
                'insured': vals.get('insured', ''),
                'beneficiary': vals.get('beneficiary', ''),
                'policy_type': vals.get('policy_type', ''),
                'face_amount': _n(vals.get('face_amount', '0'), 0),
                'cash_value_today': _n(vals.get('cash_value_today', '0'), 0),
                'annual_premium': _n(vals.get('annual_premium', '0'), 0),
                'term_end_year': _y(vals.get('term_end_year', '0'), 0),
                'premium_end_year': _y(vals.get('premium_end_year', '0'), 0),
                'cash_value_growth_rate': _n(vals.get('cash_value_growth_rate', '0'), 0),
                'owned_by_ilit': _b(vals.get('owned_by_ilit', 'FALSE')),
                'notes': vals.get('notes', ''),
            })

    # ── Equity compensation (RSU / ISO / NSO / ESPP) ─────────────────────────
    equity_comp = []
    for sub, vals in data.get('Equity Compensation', {}).items():
        if not sub:
            continue
        equity_comp.append({
            'name': sub,
            'recipient': vals.get('recipient', ''),
            'grant_type': str(vals.get('grant_type', '')).strip().upper(),
            'shares': _n(vals.get('shares_outstanding', '0'), 0),
            'fmv_today': _n(vals.get('fmv_per_share_today', '0'), 0),
            'strike': _n(vals.get('exercise_price', '0'), 0),
            'grant_date': vals.get('grant_date', ''),
            'vest_schedule': vals.get('vest_schedule', ''),
            'planned_exercise_year': _y(vals.get('planned_exercise_year', '0'), 0),
            'planned_sale_year': _y(vals.get('planned_sale_year', '0'), 0),
            'fmv_growth_rate': _n(vals.get('fmv_growth_rate', '0'), 0),
        })

    # ── Special-needs planning (SNT / ABLE) from the Estate Planning section ─
    ep = data.get('Estate Planning', {})
    special_needs = {}
    if any(str(k).startswith('SN_') for k in ep.keys()):
        b = ep.get('SN_Beneficiary', {})
        t = ep.get('SN_Trust', {})
        a = ep.get('SN_ABLE', {})
        g = ep.get('SN_GovBenefits', {})
        special_needs = {
            'beneficiary': {
                'name': b.get('name', ''),
                'dob': b.get('dob', ''),
                'lifetime_to_age': _y(b.get('lifetime_to_age', '0'), 0),
                'annual_support_today': _n(b.get('annual_support_today', '0'), 0),
                'inflation_rate': _n(b.get('inflation_rate', '0.025'), 0.025),
            },
            'snt': {
                'balance_today': _n(t.get('balance_today', '0'), 0),
                'funding_schedule': _n(t.get('funding_schedule', '0'), 0),
                'growth_rate': _n(t.get('growth_rate', '0.05'), 0.05),
                'is_third_party': _b(t.get('is_third_party', 'TRUE')),
            },
            'able': {
                'balance_today': _n(a.get('balance_today', '0'), 0),
                'monthly_contribution': _n(a.get('monthly_contribution', '0'), 0),
                'annual_contribution_limit': _n(a.get('annual_contribution_limit', '0'), 0),
            },
            'gov_benefits': {
                'ssi_monthly': _n(g.get('ssi_monthly', '0'), 0),
                'ssdi_monthly': _n(g.get('ssdi_monthly', '0'), 0),
                'medicaid_enrolled': _b(g.get('medicaid_enrolled', 'FALSE')),
            },
        }

    # ── Business succession (dedicated client_business.csv — Phase 2) ────────
    business_succession = []
    for sub, vals in data.get('Business Succession', {}).items():
        if not sub or sub == 'Policy':
            continue
        business_succession.append({
            'name': sub,
            'entity_name': vals.get('entity_name', sub),
            'owner': vals.get('owner', ''),
            'ownership_pct': _n(vals.get('ownership_pct', '0'), 0),
            'valuation_today': _n(vals.get('valuation_today', '0'), 0),
            'valuation_growth_rate': _n(vals.get('valuation_growth_rate', '0'), 0),
            'buy_sell_type': vals.get('buy_sell_type', ''),
            'funding_vehicle': vals.get('funding_vehicle', ''),
            'funding_amount': _n(vals.get('funding_amount', '0'), 0),
            'key_person_coverage': _n(vals.get('key_person_coverage', '0'), 0),
            'successor': vals.get('successor', ''),
            'transfer_year': _y(vals.get('transfer_year', '0'), 0),
        })

    # ── Item 4.7 (P8): per-account beneficiary and titling ───────────────────
    # Subsection = account_registry id (e.g. "Member_1_IRA"), modeled on the
    # Insurance In Force section above (subsection = policy name). Titling
    # drives _account_basis_step_fraction/_survivor_bonus_step_fraction in
    # planning_engines.py instead of one household-wide property_regime; an
    # account with no row here falls back to that household default
    # unchanged. beneficiary_titling_audit() (also planning_engines.py) reads
    # this dict to flag review prompts on the Estate & Legacy sheet.
    account_titling = {}
    for sub, vals in data.get('Account Titling', {}).items():
        if not sub:
            continue
        # Item 3.3 (F4): per-account beneficiary tax modeling. beneficiary_class
        # defaults to '' (treated as DESIGNATED -- the current 10-year-rule
        # behavior) unless the advisor names one of the SECURE Act eligible-
        # designated-beneficiary categories (see after_tax.py's
        # EDB_BENEFICIARY_CLASSES). beneficiary_age/state/baseline_income all
        # default to 0/'' -- no age-based EDB stretch, no state tax, no
        # baseline-income bracket-stacking -- so an account with no row here,
        # or one that predates these fields, keeps today's federal-only,
        # zero-baseline, 10-year-rule behavior exactly.
        account_titling[sub] = {
            'primary_beneficiary': vals.get('primary_beneficiary', ''),
            'contingent_beneficiary': vals.get('contingent_beneficiary', ''),
            'titling': str(vals.get('titling', '') or '').strip().upper(),
            'trust_see_through': _b(vals.get('trust_see_through', 'FALSE')),
            'beneficiary_class': str(vals.get('beneficiary_class', '') or '').strip().upper(),
            'beneficiary_age': int(_n(vals.get('beneficiary_age', '0'), 0) or 0),
            'beneficiary_state': str(vals.get('beneficiary_state', '') or '').strip().upper(),
            'beneficiary_baseline_income': max(0.0, _n(vals.get('beneficiary_baseline_income', '0'), 0)),
        }

    # ── Item 4.8 (P11): gifting schedule with lifetime-exemption tracking ────
    # Subsection = gift entry name (e.g. "Gift 1"). Each entry gifts
    # annual_amount_per_donee * donee_count per active year, drawn directly
    # from funding_account (a new balance-mutating path outside the normal
    # withdrawal cascade -- see run_deterministic_projection_stage). Only the
    # amount per donee ABOVE gift_excl (the annual exclusion) consumes
    # lifetime federal exemption; is_appreciated_asset is disclosure-only
    # (this engine never models the donee's own finances/basis).
    gifting_schedule = []
    for sub, vals in data.get('Gifting Schedule', {}).items():
        if not sub:
            continue
        gifting_schedule.append({
            'name': sub,
            'donor': str(vals.get('donor', 'joint') or 'joint').strip().lower(),
            'funding_account': vals.get('funding_account', ''),
            'annual_amount_per_donee': _n(vals.get('annual_amount_per_donee', '0'), 0),
            'donee_count': int(_n(vals.get('donee_count', '1'), 1) or 1),
            'start_year': _y(vals.get('start_year', '0'), 0),
            'end_year': _y(vals.get('end_year', '0'), 0),
            'is_appreciated_asset': _b(vals.get('is_appreciated_asset', 'FALSE')),
        })

    return {
        'edu_funding': {'accounts': edu_accounts, 'goals': edu_goals, 'policy': edu_policy},
        'life_policies': life_policies,
        'disability': disability,
        'pc_umbrella': pc,
        'equity_comp': equity_comp,
        'special_needs': special_needs,
        'business_succession': business_succession,
        'account_titling': account_titling,
        'gifting_schedule': gifting_schedule,
    }
