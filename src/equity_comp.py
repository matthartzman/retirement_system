"""Equity-compensation tax-event modeling for the projection engine.

Pure functions that turn the parsed ``equity_comp`` grant list (see
``data_io.parse_advanced_modules``) into per-year tax events the deterministic
engine consumes when the ``equity_compensation`` module is enabled:

    ordinary_income   RSU settlement, NSO exercise spread, ESPP discount
    amt_preference    ISO exercise bargain element (an AMT preference item)
    ltcg_gain         long-term gain realized on an ISO/RSU sale
    cash_proceeds     cash landing in a taxable account from a sale/settlement

Only the structured grant fields are used (grant_type, shares, fmv_today,
exercise_price/strike, fmv_growth_rate, planned_exercise_year,
planned_sale_year), so the model is deterministic and free-text vest schedules
never drive the numbers. Modeling conventions:

    RSU / RSA   settled-and-sold in ``planned_sale_year``: full FMV is ordinary
                income and cash proceeds that year.
    NSO / NQSO  exercised-and-sold in ``planned_exercise_year``: the (FMV - strike)
                spread is ordinary income and net cash that year.
    ISO         exercised-and-held in ``planned_exercise_year`` (AMT preference,
                no ordinary income or cash), then sold in ``planned_sale_year`` as
                a long-term gain (FMV_sale - strike) with net cash proceeds.
    ESPP        sold in ``planned_sale_year``: a 15% purchase discount is ordinary
                income and full FMV is cash proceeds.

These are report/engine modeling assumptions, not tax advice; the equity sheet
(2K) documents the per-type treatment.
"""

ESPP_DISCOUNT = 0.15


def _fmv(grant, year, base_year):
    growth = float(grant.get('fmv_growth_rate', 0.0) or 0.0)
    return float(grant.get('fmv_today', 0.0) or 0.0) * ((1.0 + growth) ** max(0, int(year) - int(base_year)))


def _empty():
    return {'ordinary_income': 0.0, 'amt_preference': 0.0, 'ltcg_gain': 0.0, 'cash_proceeds': 0.0}


def equity_comp_year_events(grants, year, base_year):
    """Aggregate every grant's tax events for ``year`` into one dict."""
    out = _empty()
    for g in (grants or []):
        gtype = str(g.get('grant_type', '')).strip().upper()
        shares = float(g.get('shares', 0.0) or 0.0)
        strike = float(g.get('strike', 0.0) or 0.0)
        ex_year = int(g.get('planned_exercise_year', 0) or 0)
        sale_year = int(g.get('planned_sale_year', 0) or 0)
        if shares <= 0:
            continue

        if gtype in ('RSU', 'RSA'):
            if sale_year and year == sale_year:
                fmv = _fmv(g, year, base_year)
                out['ordinary_income'] += shares * fmv
                out['cash_proceeds'] += shares * fmv
        elif gtype in ('NSO', 'NQSO'):
            if ex_year and year == ex_year:
                fmv = _fmv(g, year, base_year)
                spread = max(0.0, fmv - strike) * shares
                out['ordinary_income'] += spread
                out['cash_proceeds'] += spread
        elif gtype == 'ISO':
            if ex_year and year == ex_year:
                fmv = _fmv(g, year, base_year)
                out['amt_preference'] += max(0.0, fmv - strike) * shares
            if sale_year and year == sale_year:
                fmv = _fmv(g, year, base_year)
                out['ltcg_gain'] += max(0.0, fmv - strike) * shares
                out['cash_proceeds'] += max(0.0, fmv - strike) * shares
        elif gtype == 'ESPP':
            if sale_year and year == sale_year:
                fmv = _fmv(g, year, base_year)
                out['ordinary_income'] += ESPP_DISCOUNT * fmv * shares
                out['cash_proceeds'] += shares * fmv
    return out


def equity_comp_active(grants):
    """True if any grant has a modeled event (guards the engine's gated block)."""
    for g in (grants or []):
        if float(g.get('shares', 0.0) or 0.0) > 0 and (
                int(g.get('planned_exercise_year', 0) or 0) or int(g.get('planned_sale_year', 0) or 0)):
            return True
    return False
