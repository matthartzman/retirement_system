"""Sheet 37 -- Current vs. Proposed comparison report.

Wave 5.4 (system review 2026-08-04, planner finding
no-current-vs-proposed-deliverable): "Comparison report + snapshot diff."

Turns the Executive Summary's recommendation list into an actual verified
comparison. For every recommendation whose adoption can be expressed as a
concrete config override that the deterministic engine reads (not just a
report-time-only calculation), this re-runs the plan with that override via
the same shared run_scenario() every other stress/scenario sheet uses, and
shows the resulting terminal-net-worth and lifetime-tax deltas next to the
current (as-configured) plan -- a real engine re-run, not a separate estimate.

Recommendations that only change report-time-only figures (estate trusts,
charitable-deduction sizing) are listed with a pointer to the sheet that
actually models them instead of a fabricated $0 delta: toggling their config
flag alone has no effect on the projection engine's cash flow (see
data_io.py -- cst_enabled/qtip_enabled/daf_amount are read only by
report-building code, not by projection_stages/deterministic_engine.py), so
showing a run_scenario delta for them would misleadingly imply "no benefit."
"""
from __future__ import annotations

from .workbook_common import (
    DGRAY,
    FMT_DOLLAR,
    LGRAY,
    NAVY,
    ORANGE,
    WHITE,
    qc,
    section_title,
    write_cell,
    write_hdr,
)
# Item 2.16 (finding A11): imported directly from the engine rather than
# through workbook_common's pass-through re-export.
from ..planning_engines import run_scenario as _run_scenario


def _entity_label(entity):
    return {'s_corp': 'S-Corp', 'sole_prop': 'Sole Prop', 'w2': 'W2'}.get(
        str(entity or '').strip().lower(), str(entity or '').strip() or 'Sole Prop')


def _proposed_changes(c):
    """Every mechanically-derivable engine-lever recommendation this sheet
    tracks, active or not. Each entry: (label, overrides, note, is_active,
    how_to_incorporate). #272: previously only listed not-yet-adopted items,
    which meant an active recommendation was invisible here -- a planner
    reviewing this sheet couldn't tell "already done" from "never considered."
    is_active items still get a run_scenario delta (overrides applied to a
    plan already at that setting is a harmless no-op re-run, useful as a
    sanity check that the number matches the current-plan column)."""
    changes = []
    ltc_active = bool(c.get('ltc_enabled'))
    # Reuses the "OPTIMAL" illustrative face/premium already shown on
    # Sheet 19 Section C so the two sheets never quote different figures.
    changes.append((
        'Hybrid Life/LTC Policy ($500K face, ~$18,500/yr premium)',
        {'ltc_enabled': True, 'ltc_annual_prem': 18500, 'ltc_face': 500000,
         'ltc_start_year': max(int(c.get('plan_start', 2024)), 2027)},
        'Premium reduces cash flow every year the policy is active; see Sheet 19 for coverage detail.',
        ltc_active,
        'Already active.' if ltc_active else 'To incorporate: enable "ltc_enabled" and set premium/face/start year on the LTC Stress page, then rebuild.',
    ))
    scorp_active = str(c.get('entity', '')).strip().lower() == 's_corp'
    if scorp_active or (c.get('earned', 0) or 0) > 0:
        changes.append((
            f"S-Corporation election (currently {_entity_label(c.get('entity'))})",
            {'entity': 's_corp'},
            'Splits earnings into W-2 salary + distribution; payroll tax applies to salary only. See Sheet 9.',
            scorp_active,
            'Already active.' if scorp_active else 'To incorporate: set entity=s_corp and a reasonable W-2 salary on the Work Income page, then rebuild.',
        ))
    return changes


def _report_only_items(c):
    """Recommendations whose flag is read only by report-building code, not
    the projection engine -- listing a run_scenario delta for these would
    always show $0 and wrongly imply no benefit. Each entry: (label, note,
    is_active, how_to_incorporate)."""
    items = []
    cst_active = bool(c.get('cst_enabled'))
    items.append(('Credit Shelter Trust at First Death',
                   'Estate-tax-only effect, not modeled in annual cash flow -- see Sheet 14 for the state exemption preserved.',
                   cst_active,
                   'Already active.' if cst_active else 'To incorporate: enable "cst_enabled" on the Estate page, then rebuild.'))
    qtip_active = bool(c.get('qtip_enabled'))
    items.append(('QTIP Trust for Annuity Post-First-Death',
                   'Estate-tax-only effect, not modeled in annual cash flow -- see Sheet 14.',
                   qtip_active,
                   'Already active.' if qtip_active else 'To incorporate: enable "qtip_enabled" on the Estate page, then rebuild.'))
    daf_active = (c.get('daf_amount', 0) or 0) > 0
    items.append(('DAF Contribution in Highest-Income Year',
                   'Deduction and carryforward are modeled on Sheet 12, not in this workbook\'s annual cash flow.',
                   daf_active,
                   'Already active.' if daf_active else 'To incorporate: set a DAF contribution amount/year on Special Strategies > Charitable Giving, then rebuild.'))
    return items


def build_sheet_current_vs_proposed(ws, c, rows):
    """Sheet 37 -- Current vs. Proposed."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'CURRENT VS. PROPOSED', 7)
    r = 3
    write_cell(ws, r, 1,
                "Lists every recommendation this workbook tracks -- both already ACTIVE/incorporated "
                "and PROPOSED/not-yet-incorporated -- using the same projection engine as the rest of "
                "this workbook, not a separate estimate. Only recommendations that change the annual "
                "cash-flow projection get a dollar delta; estate/charitable-only recommendations are "
                "listed separately with a pointer to the sheet that models them, since toggling their "
                "flag alone doesn't move these numbers. The rightmost column gives the specific step to "
                "incorporate a proposed item.", align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    r += 2

    base_nw = rows[-1]['total_nw']
    base_tax = sum(row['total_tax'] for row in rows)

    write_hdr(ws, r, 1, 'Engine-Modeled Comparisons', NAVY, WHITE, span=8); r += 1
    hdrs = ['Recommendation', 'Status', 'Current Terminal NW', 'Proposed Terminal NW',
            'Δ Terminal NW', 'Current Lifetime Tax', 'Proposed Lifetime Tax', 'Δ Lifetime Tax']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    changes = _proposed_changes(c)
    if not changes:
        write_cell(ws, r, 1, 'No mechanically-comparable recommendations are tracked for this plan.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        r += 1
    for label, overrides, note, is_active, how_to in changes:
        _c2, rows2 = _run_scenario(c, overrides)
        if not rows2:
            continue
        prop_nw = rows2[-1]['total_nw']
        prop_tax = sum(row2['total_tax'] for row2 in rows2)
        delta_nw = prop_nw - base_nw
        delta_tax = prop_tax - base_tax
        status_bg = 'E2EFDA' if is_active else 'FFF2CC'
        bg = 'E2EFDA' if delta_nw > 0 else ('FCE4D6' if delta_nw < 0 else None)
        write_cell(ws, r, 1, label, bold=True)
        write_cell(ws, r, 2, 'ACTIVE' if is_active else 'PROPOSED', bold=True, bg=status_bg, align='center')
        write_cell(ws, r, 3, base_nw, fmt=FMT_DOLLAR)
        write_cell(ws, r, 4, prop_nw, fmt=FMT_DOLLAR, bg=bg)
        write_cell(ws, r, 5, delta_nw, fmt=FMT_DOLLAR, bold=True, bg=bg)
        write_cell(ws, r, 6, base_tax, fmt=FMT_DOLLAR)
        write_cell(ws, r, 7, prop_tax, fmt=FMT_DOLLAR)
        write_cell(ws, r, 8, delta_tax, fmt=FMT_DOLLAR)
        r += 1
        write_cell(ws, r, 1, note, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        write_cell(ws, r, 5, how_to, align='left', bold=not is_active)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=8)
        r += 1

    r += 1
    write_hdr(ws, r, 1, 'Estate/Charitable-Only Recommendations (see referenced sheet)', ORANGE, WHITE, span=8); r += 1
    report_only = _report_only_items(c)
    if not report_only:
        write_cell(ws, r, 1, 'None tracked for this plan.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        r += 1
    for label, note, is_active, how_to in report_only:
        status_bg = 'E2EFDA' if is_active else 'FFF2CC'
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, 'ACTIVE' if is_active else 'PROPOSED', bold=True, bg=status_bg, align='center')
        write_cell(ws, r, 3, note, align='left')
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        write_cell(ws, r, 6, how_to, align='left', bold=not is_active)
        ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=8)
        r += 1

    qc('37. Current vs Proposed',
       'Engine-modeled comparisons re-run via the shared run_scenario helper', True,
       f'{len(changes)} engine-modeled, {len(report_only)} estate/charitable-only')


__all__ = ['build_sheet_current_vs_proposed']
