from __future__ import annotations

from typing import Any


def compute_cashflow_breakdown(row: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Canonical cash-flow breakdown (single source of truth) + gross cash flow.

    Purely additive, read-only snapshot of the income / portfolio-draw /
    spending / tax itemization that every downstream cash-flow consumer
    (sheets_projection_cashflow build_sheet6, sheets_projection_charts
    build_sheet8, results_model _cashflow_page + _chart_page) reads
    verbatim, so they can never re-derive divergent numbers again. Every
    value here already exists on `row` (set by earlier stages this same
    year) by the time this runs -- this function computes nothing new and
    mutates nothing; it only re-shapes already-finalized fields.

    Takes the whole (already largely built) `row` dict rather than an
    enumerated list of scalars: unlike compute_effective_marginal_rate /
    compute_spend_by_tier, this stage's job IS "reflect nearly everything
    computed so far" -- it reads ~35 distinct row keys with no local
    (non-row) state involved, so naming each as a separate parameter would
    be pure busywork with no audit benefit (every one of them is already
    `row['x']`, not a bespoke local). Passing `row` here does not resurrect
    the general "row soup" problem those two extractions avoided: this is
    a read-only reporting snapshot, not a stage with a large mutation
    surface -- it never sets anything on `row` itself.

    Reconciliation guarantees, all verified exact ($0 residual) for the
    live household in tests/test_cashflow_breakdown_single_source_of_truth.py:
      sum(income)                          == Σ Income (build_sheet6)
      sum(expense excl. other_cash_need)   == row['total_spend']  (engine spend need)
      sum(tax)                             == row['total_tax']    (exact, by construction)
      sum(income)+sum(draws) - (sum(expense)+sum(tax)) == surplus - unfunded_gap
    The tax dict decomposes total_tax into non-overlapping components:
    federal+state+niit+irmaa+payroll+home_sale+ltcg+tlh_credit+other,
    where ltcg is the portfolio LTCG *beyond* the home-sale portion,
    tlh_credit is the (negative) tax-loss-harvest ordinary-income credit,
    and `other` is the reconciling remainder (equity-comp LTCG/AMT etc.)
    so the itemization sums to row['total_tax'] exactly regardless of
    which optional modules ran. Housing is exposed at component grain
    (mortgage/rent/housing_operating, whose sum == housing_total_yr) so a
    consumer can show one rolled-up "Housing" figure or the 3-way split
    without any key double-counting sum(expense.values()).

    Also folds in the Optimization-refactor Phase 1 item 2 gross external
    cash flow (for ELTR / tax-NPV reporting), reusing the just-built
    income/draws sub-dicts, which already exclude internal transfers (Roth
    conversion, DAF in-kind, gifting, spousal rollover, CST funding) by
    construction -- see the reconciliation guarantees above.

    Returns (cashflow_breakdown, gross_cash_flow_yr) -- assign to
    row['cashflow_breakdown'] and row['gross_cash_flow_yr'] respectively.
    """
    total_tax = row.get('total_tax', 0.0)
    home_sale_tax = row.get('home_sale_tax', 0.0)
    ltcg_tax = row.get('ltcg_tax', 0.0)
    tlh_credit = row.get('tlh_ordinary_credit', 0.0)
    tax_named = (row.get('fed_tax', 0.0) + row.get('state_tax', 0.0)
                 + row.get('niit', 0.0) + row.get('irmaa', 0.0)
                 + row.get('payroll_tax', 0.0)
                 + ltcg_tax - tlh_credit)
    cashflow_breakdown = {
        'income': {
            'earned': row.get('earned', 0.0),
            'h_ss': row.get('h_ss', 0.0),
            'w_ss': row.get('w_ss', 0.0),
            'pension': row.get('pension', 0.0),
            'wife_single_ann': row.get('wife_single_ann', 0.0),
            'wife_joint_ann': row.get('wife_joint_ann', 0.0),
            'h_single_ann': row.get('h_single_ann', 0.0),
            'h_joint_ann': row.get('h_joint_ann', 0.0),
            'note_pi': row.get('note_princ', 0.0) + row.get('note_int', 0.0),
            'rmd_total': row.get('rmd_total', 0.0),
        },
        'draws': {
            'trust_wd': row.get('h_trust_wd', 0.0) + row.get('w_trust_wd', 0.0),
            'hsa_wd': row.get('hsa_wd', 0.0),
            'roth_wd': row.get('h_roth_wd', 0.0) + row.get('w_roth_wd', 0.0),
            'ira_elective': row.get('h_ira_elective', 0.0) + row.get('w_ira_elective', 0.0),
            'heloc_draw': row.get('heloc_draw', 0.0),
        },
        # Housing is exposed only at component grain (mortgage / rent /
        # housing_operating); their sum == row['housing_total_yr'], which is
        # what build_sheet6 and build_sheet8 display as a single "Housing"
        # figure while _chart_page keeps its 3-way split. No rolled-up
        # 'housing' key is stored, so sum(expense.values()) never
        # double-counts. Every key except 'other_cash_need' sums to
        # row['total_spend']; 'other_cash_need' is the separate purchase-cash
        # component of total_cash_need (= total_spend + total_tax +
        # other_cash_need).
        'expense': {
            'spend_base': row.get('spend_base_yr', 0.0),
            'mortgage': row.get('mortgage', 0.0),
            'rent': row.get('rent_yr', 0.0),
            'housing_operating': row.get('housing_operating_yr', 0.0),
            'wellness': (row.get('wellness_base_yr', 0.0)
                         + row.get('wellness_shock_yr', 0.0)
                         + row.get('ltc_prem_yr', 0.0)),
            'travel': row.get('rec_extra', 0.0),
            'other_lump': row.get('lump', 0.0),
            'business_expenses': row.get('business_expenses_yr', 0.0),
            'heloc_pai': (row.get('heloc_interest', 0.0)
                          + row.get('heloc_repayment_principal', 0.0)),
            'other_cash_need': row.get('other_cash_need_yr', 0.0),
        },
        'tax': {
            'federal': row.get('fed_tax', 0.0),
            'state': row.get('state_tax', 0.0),
            'niit': row.get('niit', 0.0),
            'irmaa': row.get('irmaa', 0.0),
            'payroll': row.get('payroll_tax', 0.0),
            'home_sale': home_sale_tax,
            'ltcg': ltcg_tax - home_sale_tax,
            'tlh_credit': -tlh_credit,
            'other': total_tax - tax_named,
        },
        'surplus': row.get('surplus', 0.0),  # authoritative engine value, not re-derived
        'unfunded_gap': row['unfunded_gap'],
    }
    gross_cash_flow_yr = (
        sum(cashflow_breakdown['income'].values())
        + sum(cashflow_breakdown['draws'].values())
    )
    return cashflow_breakdown, gross_cash_flow_yr
