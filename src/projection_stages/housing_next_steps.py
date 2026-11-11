"""Next-housing-step helpers lifted out of run_deterministic_projection_stage (ARC-001).

Pure functions of the plan config ``c``; behaviour is identical to the closures
they replace (verified by golden-master and phase-golden equality).
"""
from __future__ import annotations


def mortgage_payment_and_balance(principal, annual_rate, year_index, term_years=30):
    """Return annual P&I payment and end-of-year balance for a fixed mortgage."""
    principal = max(0.0, float(principal or 0.0))
    if principal <= 0.0:
        return 0.0, 0.0
    term_years = max(1, int(term_years or 30))
    total_pmts = term_years * 12
    made_pmts = max(0, min(total_pmts, int(year_index) * 12))
    remaining_pmts_start = max(0, total_pmts - made_pmts)
    if remaining_pmts_start <= 0:
        return 0.0, 0.0
    monthly_rate = max(0.0, float(annual_rate or 0.0)) / 12.0
    if monthly_rate > 1e-9:
        monthly_pmt = principal * monthly_rate / (1 - (1 + monthly_rate) ** (-total_pmts))
        bal_start = principal * ((1 + monthly_rate) ** total_pmts - (1 + monthly_rate) ** made_pmts) / ((1 + monthly_rate) ** total_pmts - 1)
    else:
        monthly_pmt = principal / total_pmts
        bal_start = max(0.0, principal - monthly_pmt * made_pmts)
    bal = bal_start
    principal_paid = 0.0
    for _ in range(min(12, remaining_pmts_start)):
        interest = bal * monthly_rate
        principal_component = max(0.0, min(bal, monthly_pmt - interest))
        bal = max(0.0, bal - principal_component)
        principal_paid += principal_component
    return monthly_pmt * min(12, remaining_pmts_start), bal

def next_housing_for_year(c, infl_ratio, year):
    """Compute cash-flow and net-worth impacts from Housing next-step rows.

    Purchase down payments are not ordinary spending; they are exposed as
    `other_cash_need` so the workbook cash bridge can reconcile them
    separately from annual spending.  Rent and ongoing purchase operating
    costs are Housing spending.
    """
    out = {
        'rent': 0.0, 'mortgage_payment': 0.0, 'real_estate_tax': 0.0,
        'insurance': 0.0, 'utilities': 0.0, 'maintenance': 0.0, 'hoa': 0.0,
        'purchase_cash': 0.0, 'home_value': 0.0, 'mortgage_balance': 0.0,
        'equity': 0.0, 'active_labels': [],
    }
    for step in c.get('next_housing_steps', []) or []:
        try:
            start = int(step.get('start_year') or 0)
        except Exception:
            start = 0
        if not start or year < start:
            continue
        try:
            end = int(step.get('end_year') or 0)
        except Exception:
            end = 0
        if end and year > end:
            continue
        # A step marked for sale (see apply_next_housing_sale below) stops
        # contributing ongoing cash flow/value from its sale year onward,
        # same as if it had been sold -- regardless of whether its own
        # `end_year` was also set to `sale_year - 1` (the well-formed
        # case). This is a safety net, not the primary mechanism: a
        # caller that sets `sale_year` without also setting `end_year`
        # still gets correct behavior instead of double-counting a home
        # that has already been sold.
        try:
            sale_yr = int(step.get('sale_year') or 0)
        except Exception:
            sale_yr = 0
        if sale_yr and year >= sale_yr:
            continue
        typ = str(step.get('type') or 'purchase').strip().lower()
        base = start
        infl = infl_ratio(year, base)
        label = step.get('id') or 'next_housing'
        out['active_labels'].append(str(label))
        if typ == 'rent':
            out['rent'] += float(step.get('monthly_rent', 0.0) or 0.0) * 12.0 * infl
            # Rent steps use explicit renters-insurance and rental-utility
            # inputs.  Current-home utilities/homeowners insurance do not
            # carry over after sale.
            out['insurance'] += float(step.get('insurance_annual', 0.0) or 0.0) * infl
            out['utilities'] += float(step.get('utilities_annual', 0.0) or 0.0) * infl
            continue
        price = float(step.get('purchase_price', 0.0) or 0.0)
        if price <= 0.0:
            # Even without a purchase price, carry operating costs if present.
            out['insurance'] += float(step.get('insurance_annual', 0.0) or 0.0) * infl
            out['utilities'] += float(step.get('utilities_annual', 0.0) or 0.0) * infl
            out['maintenance'] += float(step.get('maintenance_annual', 0.0) or 0.0) * infl
            continue
        down_pct = max(0.0, min(1.0, float(step.get('down_payment_pct', 0.20) or 0.20)))
        loan = max(0.0, price * (1.0 - down_pct))
        if year == start:
            out['purchase_cash'] += price * down_pct
        year_index = max(0, year - start)
        pmt, bal_end = mortgage_payment_and_balance(loan, float(step.get('mortgage_rate_pct', 0.0) or 0.0), year_index)
        home_value = price * ((1.0 + float(c.get('home_appr', 0.0) or 0.0)) ** max(0, year - start + 1))
        out['mortgage_payment'] += pmt
        out['mortgage_balance'] += bal_end
        out['home_value'] += home_value
        out['equity'] += max(0.0, home_value - bal_end)
        out['real_estate_tax'] += price * float(step.get('real_estate_tax_pct', 0.0) or 0.0) * infl
        out['insurance'] += float(step.get('insurance_annual', 0.0) or 0.0) * infl
        out['utilities'] += float(step.get('utilities_annual', 0.0) or 0.0) * infl
        out['maintenance'] += float(step.get('maintenance_annual', 0.0) or 0.0) * infl
        out['hoa'] += price * float(step.get('hoa_pct', 0.0) or 0.0) * infl
    return out

def next_housing_sale_inputs(c, step, sale_year):
    """Gross value and mortgage payoff for selling a next_housing_steps
    purchase step in `sale_year`, valued as of the end of the PRIOR
    year -- the same convention apply_home_sale uses for the original
    home (a sale year's gross proceeds come from last year's ending
    value; the sale year itself doesn't add another year of
    appreciation). Mirrors the per-step formula in
    `next_housing_for_year` above (kept as a small separate
    computation, not a shared helper, so that function's already-tested
    aggregate-across-steps behavior is untouched). Returns None for a
    rent step or a purchase step with no positive price -- nothing to
    sell.
    """
    if str(step.get('type') or 'purchase').strip().lower() != 'purchase':
        return None
    price = float(step.get('purchase_price', 0.0) or 0.0)
    try:
        start = int(step.get('start_year') or 0)
    except Exception:
        start = 0
    if price <= 0.0 or not start:
        return None
    valuation_year = sale_year - 1
    home_value = price * ((1.0 + float(c.get('home_appr', 0.0) or 0.0)) ** max(0, valuation_year - start + 1))
    down_pct = max(0.0, min(1.0, float(step.get('down_payment_pct', 0.20) or 0.20)))
    loan = max(0.0, price * (1.0 - down_pct))
    year_index = max(0, valuation_year - start)
    _pmt, mort_bal = mortgage_payment_and_balance(loan, float(step.get('mortgage_rate_pct', 0.0) or 0.0), year_index)
    return home_value, mort_bal
