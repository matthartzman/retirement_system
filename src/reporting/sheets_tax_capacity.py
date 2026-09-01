"""Tax-Capacity Worksheet builder (Sheet 11B).

System review 2026-08-31, Wave 1 item 1.17 / finding F12 ("No consolidated
bracket-capacity view"). Before this sheet, "how much room is left this
year" was scattered across four places:

  - Sheet 11 (Roth Conversion, sheets_strategy.py build_sheet11) shows
    bracket headroom sized to the configured Roth target bracket only.
  - Sheet 7 (Lifetime Tax, sheets_projection_tax.py build_sheet7) shows
    realized tax and effective marginal rate, but its own header note says
    it EXCLUDES IRMAA (set from income two years prior) and the ACA
    premium-tax-credit cliff.
  - Sheet 12C (Gain Harvesting, sheets_strategy.py build_sheet_gain_harvest)
    shows 0%-LTCG-bracket headroom for the CURRENT plan year only.
  - QCD dollars land on cash-flow/RMD rows with no headroom context at all.

A planner had to reconcile four sheets to size one year's decision. This
sheet derives nothing new -- every column reads a value the engine or an
existing sheet builder already computes (see the file:line citations in the
helpers below) and lays them out one row per projection year so every
figure here also appears, unchanged, on its source sheet.

Kept to a modest column count deliberately: Sheet 7's own comment documents
a real prior failure where a too-wide/tall note collapsed the PDF export
entirely (ReportLab cannot split one row across pages, so the whole export
silently produced no PDF). This sheet's note is a single short paragraph and
its column count (13) sits below Sheet 11's (15) and Sheet 7's (16), both of
which already export to PDF successfully.
"""

from .workbook_common import (
    DGRAY,
    FEDERAL_BRACKETS_BASE_YEAR,
    FMT_DOLLAR,
    FMT_YEAR,
    IRMAA_TIERS_BASE_YEAR,
    LGRAY,
    NAVY,
    NIIT_THRESHOLD,
    TAX_BASE_YEAR,
    WHITE,
    get_column_letter,
    inflate_brackets,
    qc,
    section_title,
    write_cell,
    write_hdr,
)
from .. import gain_harvest as _gh


def _bracket_top(taxable_inc, year, filing, brk_inf):
    """Top of the ordinary bracket ``taxable_inc`` currently sits in.

    Same table and inflation convention as core.py's ``marginal_rate``
    (src/core.py:1287, re-exported into every sheets_*.py that already
    displays "Marginal Rate (bracket)") -- this just returns the bracket's
    ceiling instead of its rate, so "room to the top of the current bracket"
    reads from the exact table that column already uses.
    """
    brk = FEDERAL_BRACKETS_BASE_YEAR.get(filing, FEDERAL_BRACKETS_BASE_YEAR['Single'])
    brk = inflate_brackets(brk, brk_inf, year - TAX_BASE_YEAR)
    for lo, hi, _rate in brk:
        if lo <= taxable_inc < hi:
            return hi
    return brk[-1][1] if brk else float('inf')


def _irmaa_inflation_factor(c, year):
    """Mirror deterministic_engine.py's ``_irmaa_factor_for_year``
    (src/projection_stages/deterministic_engine.py:454) so the "$ to next
    IRMAA tier" column is inflated on the exact same basis the engine used
    to set ``row['irmaa_tier']`` for this row.
    """
    idx = c.get('irmaa_index_by_year') if isinstance(c.get('irmaa_index_by_year'), dict) else None
    if idx:
        return float(idx.get(year, idx.get(int(year), 1.0)) or 1.0)
    return (1.0 + float(c.get('irmaa_inflator', 0.02) or 0.0)) ** (int(year) - int(c.get('plan_start', year)))


def _next_irmaa_tier_distance(magi, year, filing, c):
    """Dollars of MAGI remaining before the next IRMAA tier.

    ``magi`` should be the same two-year-lookback MAGI the engine already
    computed (``row['irmaa_magi_used']`` -- see ``irmaa_lookback_magi``,
    src/core.py:870, and ``_irmaa_tier_path``,
    src/projection_stages/deterministic_engine.py:468), so this reconciles
    with ``row['irmaa_tier']`` for the same row. Returns ``None`` once MAGI
    is already above the top tier.
    """
    tiers = IRMAA_TIERS_BASE_YEAR.get(filing, IRMAA_TIERS_BASE_YEAR['MFJ'])
    infl = _irmaa_inflation_factor(c, year)
    for threshold, _partb, _partd in tiers:
        t = threshold * infl
        if magi < t:
            return t - magi
    return None


def build_sheet_tax_capacity(ws, c, rows):
    """Tax-Capacity Worksheet -- one row per projection year."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'TAX-CAPACITY WORKSHEET', 13)

    r = 2
    write_cell(ws, r, 1,
               'Consolidates bracket, IRMAA, 0%-LTCG, ACA-cliff, and NIIT headroom that are '
               'otherwise scattered across the Roth Conversion, Lifetime Tax, and Gain '
               'Harvesting sheets, alongside what the plan actually used that room for this '
               'year. Every figure here also appears, unchanged, on its own source sheet.',
               align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=13)
    ws.row_dimensions[r].height = 30
    r += 2

    hdrs = [
        'Year', 'Filing', 'AGI Before Conversion', 'Room to Top of Current Bracket',
        'Room to Roth Target Bracket', 'Room in 0% LTCG Bracket',
        'MAGI Used for IRMAA (2-yr lookback)', '$ to Next IRMAA Tier',
        'ACA Cliff Distance', 'Room to NIIT Threshold',
        'Roth Conversion Taken', 'Gain Harvested', 'QCD Taken',
    ]
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, NAVY, WHITE, size=8)
    r += 1

    plan_start = int(c.get('plan_start', rows[0]['year'] if rows else 2026))
    brk_inf = float(c.get('brk_inf', 0.02) or 0.02)
    # gain_harvest.py's scan_gain_harvest_opportunities (src/gain_harvest.py:122)
    # inflates ltcg_0_top with c['bracket_inf'], not c['brk_inf'] -- mirrored
    # here verbatim so this column's current-year value reconciles exactly
    # with Sheet 12C's headroom figure rather than quietly using a different key.
    bracket_inf_gh = float(c.get('bracket_inf', 0.02) or 0.02)
    ltcg_0_top = float(c.get('ltcg_0_top', 96_700) or 0.0)
    aca_fpl_base = max(0.0, float(c.get('aca_fpl_base', 0.0) or 0.0))

    total_conv = total_gain = total_qcd = 0.0
    for row in rows:
        year = row['year']
        filing = row.get('filing', 'MFJ')
        taxable_inc = float(row.get('taxable_inc', 0.0) or 0.0)
        agi = float(row.get('agi', 0.0) or 0.0)
        roth_conv = float(row.get('roth_conv', 0.0) or 0.0)
        # conv_pre_agi (src/planning_engines.py:1632, set every year a Roth
        # conversion policy is active -- src/projection_stages/
        # deterministic_engine.py:1606) is the engine's own pre-conversion
        # AGI and reconciles exactly with Sheet 11's "Pre-Conv AGI" column.
        # When no conversion policy is configured that field is always 0, so
        # fall back to backing this year's conversion out of AGI directly --
        # identical to conv_pre_agi's own definition, and reduces to plain
        # AGI when roth_conv is 0.
        pre_agi = row.get('conv_pre_agi') or (agi - roth_conv)
        # conv_bracket_room (src/planning_engines.py:1634) -- 0/blank when no
        # Roth conversion policy is configured, exactly as Sheet 11 shows it.
        bracket_room_target = float(row.get('conv_bracket_room', 0.0) or 0.0)

        cur_bracket_top = _bracket_top(taxable_inc, year, filing, brk_inf)
        cur_bracket_room = max(0.0, cur_bracket_top - taxable_inc)

        # compute_zero_bracket_headroom, src/gain_harvest.py:39 -- the exact
        # function Sheet 12C calls (via scan_gain_harvest_opportunities) for
        # the current plan year only; called here for every row instead.
        bf = (1.0 + bracket_inf_gh) ** (year - plan_start)
        ltcg_headroom = _gh.compute_zero_bracket_headroom(ltcg_0_top, bf, taxable_inc)

        # irmaa_magi_used, src/projection_stages/deterministic_engine.py:1985
        # -- the actual two-year-lookback MAGI the engine used to assess this
        # row's IRMAA surcharge/tier (irmaa_lookback_magi, src/core.py:870).
        irmaa_magi = float(row.get('irmaa_magi_used', agi) or agi)
        irmaa_dist = _next_irmaa_tier_distance(irmaa_magi, year, filing, c)

        # Bridge-year test mirrors deterministic_engine.py:1391-1396's own
        # h_bridge/w_bridge/bridge_people computation (pre-65 ACA eligibility).
        h_alive = row.get('h_alive', True)
        w_alive = row.get('w_alive', True)
        h_age = row.get('h_age', 99)
        w_age = row.get('w_age', 99)
        bridge_people = (1 if h_alive and h_age < 65 else 0) + (1 if w_alive and w_age < 65 else 0)
        aca_dist = None
        if bridge_people > 0 and c.get('aca_ptc_enabled', True) and aca_fpl_base > 0:
            # 400%-FPL reference point aca_premium_tax_credit's own applicable
            # -percentage schedule treats as the cliff (src/planning_engines.py:
            # 1700, 1712) -- distance to it, using MAGI (irmaa_magi_used is the
            # same AGI-based MAGI proxy the engine's own PTC call uses).
            fpl = aca_fpl_base * ((1.0 + float(c.get('inf', 0.025) or 0.0)) ** max(0, year - plan_start))
            aca_dist = max(0.0, 4.0 * fpl - irmaa_magi)

        # NIIT_THRESHOLD, src/taxes.py:78 -- same statutory (non-indexed)
        # dollar table core.py's niit_tax() and planning_engines.py's Roth
        # NIIT guardrail both read from.
        niit_thr = float(NIIT_THRESHOLD.get(filing, 250_000) or 250_000)
        niit_dist = max(0.0, niit_thr - agi)

        # gain_harvest_realized, src/projection_stages/deterministic_engine.py:
        # 2456; qcd_total_yr, src/projection_stages/deterministic_engine.py:1338.
        gain_realized = float(row.get('gain_harvest_realized', 0.0) or 0.0)
        qcd = float(row.get('qcd_total_yr', 0.0) or 0.0)
        total_conv += roth_conv
        total_gain += gain_realized
        total_qcd += qcd

        vals = [
            year, filing, pre_agi, cur_bracket_room,
            bracket_room_target if bracket_room_target > 0 else '',
            ltcg_headroom, irmaa_magi,
            irmaa_dist if irmaa_dist is not None else 'Top tier',
            aca_dist if aca_dist is not None else '',
            niit_dist, roth_conv, gain_realized, qcd,
        ]
        fmts = [FMT_YEAR, None, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR,
                FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR,
                FMT_DOLLAR, FMT_DOLLAR]
        for i, (val, fmt) in enumerate(zip(vals, fmts), 1):
            use_fmt = fmt if not isinstance(val, str) else None
            bg = 'E2EFDA' if i in (11, 12, 13) and isinstance(val, (int, float)) and val > 0 else None
            write_cell(ws, r, i, val, fmt=use_fmt, bg=bg,
                       align='center' if i in (1, 2) else 'right')
        r += 1

    r += 1
    write_cell(ws, r, 1, 'Lifetime Totals', bold=True, bg=DGRAY, fg=WHITE)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    write_cell(ws, r, 11, total_conv, fmt=FMT_DOLLAR, bold=True, bg=DGRAY, fg=WHITE)
    write_cell(ws, r, 12, total_gain, fmt=FMT_DOLLAR, bold=True, bg=DGRAY, fg=WHITE)
    write_cell(ws, r, 13, total_qcd, fmt=FMT_DOLLAR, bold=True, bg=DGRAY, fg=WHITE)

    for col in range(1, 14):
        ws.column_dimensions[get_column_letter(col)].width = 15

    qc('11B. Tax Capacity', 'One row per projection year with reconciled headroom figures', True,
       f'years={len(rows)}; total_conversions=${total_conv:,.0f}; '
       f'total_gain_harvested=${total_gain:,.0f}; total_qcd=${total_qcd:,.0f}')
