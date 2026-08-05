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
    run_scenario as _run_scenario,
    section_title,
    write_cell,
    write_hdr,
)


def _entity_label(entity):
    return {'s_corp': 'S-Corp', 'sole_prop': 'Sole Prop', 'w2': 'W2'}.get(
        str(entity or '').strip().lower(), str(entity or '').strip() or 'Sole Prop')


def _proposed_changes(c):
    """Mechanically-derivable engine overrides for not-yet-adopted
    recommendations. Each entry: (label, overrides, note)."""
    changes = []
    if not c.get('ltc_enabled'):
        # Reuses the "OPTIMAL" illustrative face/premium already shown on
        # Sheet 19 Section C so the two sheets never quote different figures.
        changes.append((
            'Adopt Hybrid Life/LTC Policy ($500K face, ~$18,500/yr premium)',
            {'ltc_enabled': True, 'ltc_annual_prem': 18500, 'ltc_face': 500000,
             'ltc_start_year': max(int(c.get('plan_start', 2024)), 2027)},
            'Premium reduces cash flow every year the policy is active; see Sheet 19 for coverage detail.',
        ))
    if str(c.get('entity', '')).strip().lower() != 's_corp' and (c.get('earned', 0) or 0) > 0:
        changes.append((
            f"Elect S-Corporation (currently {_entity_label(c.get('entity'))})",
            {'entity': 's_corp'},
            'Splits earnings into W-2 salary + distribution; payroll tax applies to salary only. See Sheet 9.',
        ))
    return changes


def _report_only_items(c):
    """Recommendations whose flag is read only by report-building code, not
    the projection engine -- listing a run_scenario delta for these would
    always show $0 and wrongly imply no benefit."""
    items = []
    if not c.get('cst_enabled'):
        items.append(('Credit Shelter Trust at First Death',
                       'Estate-tax-only effect, not modeled in annual cash flow -- see Sheet 14 for the state exemption preserved.'))
    if not c.get('qtip_enabled'):
        items.append(('QTIP Trust for Annuity Post-First-Death',
                       'Estate-tax-only effect, not modeled in annual cash flow -- see Sheet 14.'))
    if not (c.get('daf_amount', 0) or 0) > 0:
        items.append(('DAF Contribution in Highest-Income Year',
                       'Deduction and carryforward are modeled on Sheet 12, not in this workbook\'s annual cash flow.'))
    return items


def build_sheet_current_vs_proposed(ws, c, rows):
    """Sheet 37 -- Current vs. Proposed."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'CURRENT VS. PROPOSED', 7)
    r = 3
    write_cell(ws, r, 1,
                "Re-runs this plan with each not-yet-adopted recommendation applied, using the same "
                "projection engine as the rest of this workbook -- not a separate estimate. Only "
                "recommendations that change the annual cash-flow projection are shown below with a "
                "dollar delta; estate/charitable-only recommendations are listed separately with a "
                "pointer to the sheet that models them, since toggling their flag alone doesn't move "
                "these numbers.", align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    r += 2

    base_nw = rows[-1]['total_nw']
    base_tax = sum(row['total_tax'] for row in rows)

    write_hdr(ws, r, 1, 'Engine-Modeled Comparisons', NAVY, WHITE, span=7); r += 1
    hdrs = ['Proposed Change', 'Current Terminal NW', 'Proposed Terminal NW',
            'Δ Terminal NW', 'Current Lifetime Tax', 'Proposed Lifetime Tax', 'Δ Lifetime Tax']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    changes = _proposed_changes(c)
    if not changes:
        write_cell(ws, r, 1, 'No mechanically-comparable recommendations are currently outstanding.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        r += 1
    for label, overrides, note in changes:
        _c2, rows2 = _run_scenario(c, overrides)
        if not rows2:
            continue
        prop_nw = rows2[-1]['total_nw']
        prop_tax = sum(row2['total_tax'] for row2 in rows2)
        delta_nw = prop_nw - base_nw
        delta_tax = prop_tax - base_tax
        bg = 'E2EFDA' if delta_nw > 0 else ('FCE4D6' if delta_nw < 0 else None)
        write_cell(ws, r, 1, label, bold=True)
        write_cell(ws, r, 2, base_nw, fmt=FMT_DOLLAR)
        write_cell(ws, r, 3, prop_nw, fmt=FMT_DOLLAR, bg=bg)
        write_cell(ws, r, 4, delta_nw, fmt=FMT_DOLLAR, bold=True, bg=bg)
        write_cell(ws, r, 5, base_tax, fmt=FMT_DOLLAR)
        write_cell(ws, r, 6, prop_tax, fmt=FMT_DOLLAR)
        write_cell(ws, r, 7, delta_tax, fmt=FMT_DOLLAR)
        r += 1
        write_cell(ws, r, 1, note, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        r += 1

    r += 1
    write_hdr(ws, r, 1, 'Estate/Charitable-Only Recommendations (see referenced sheet)', ORANGE, WHITE, span=7); r += 1
    report_only = _report_only_items(c)
    if not report_only:
        write_cell(ws, r, 1, 'None outstanding.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        r += 1
    for label, note in report_only:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, note, align='left')
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
        r += 1

    qc('37. Current vs Proposed',
       'Engine-modeled comparisons re-run via the shared run_scenario helper', True,
       f'{len(changes)} engine-modeled, {len(report_only)} estate/charitable-only')


__all__ = ['build_sheet_current_vs_proposed']
