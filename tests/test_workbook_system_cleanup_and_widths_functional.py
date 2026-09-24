import pytest
from openpyxl import load_workbook

from src.reporting.workbook_common import TEMPLATE_LAYOUT, _needed_number_width

pytestmark = pytest.mark.slow


def _visible_wb(workbook_path):
    assert workbook_path.exists(), 'Generated workbook is missing'
    return load_workbook(workbook_path, read_only=False, data_only=False)


def test_system_section_uses_clean_sheet_sequence_without_feature_toggle(built_workbook_path):
    wb = _visible_wb(built_workbook_path)
    visible = [ws.title for ws in wb.worksheets if ws.sheet_state == 'visible']
    expected = [
        '1. Reports','1A. Executive Summary','1B. Net Worth','1C. Cash Flow','1D. Balance Sheet','1E. Charts','1F. Lifetime Taxes',
        # #221: Core Spending merged into Spending Summary -- densely 1G now.
        '1G. Spending Summary',
        '1H. Current vs. Proposed',
        # W11 addendum (2026-09-22): recatalogued WORKSHEET (was REFERENCE) --
        # an interactive lever-screening tool, not a static echo -- so it now
        # letters and sorts in Reports instead of System, densely last. See
        # the System-section comment below for where it used to sit.
        '1I. Planning Levers',
        # W3 (#329 O10, F1): COMPARISON modules (State Residency, S-Corp vs
        # LLC) moved to their own '3. Comparisons' group, out of Optimizers.
        # HSA Drawdown (2B) always sits right after Roth Conversion (shares
        # its objective) and is never module-gated, so it is never absent.
        # #329 §1.2/§3.3 (W9): Withdrawal Sequencing and Asset Location
        # restored from hidden, right after Asset Allocation (investments
        # cluster). Tax-Loss Harvesting/Gain Harvesting sort last within
        # Optimizers as the "This year's actions" pair (§3.2 F3), after
        # Housing Comparison.
        '2. Optimizers','2A. Roth Conversion','2B. HSA Drawdown','2C. Asset Allocation',
        '2D. Withdrawal Sequencing','2E. Social Security','2F. Asset Location',
        '2G. Charitable Giving','2H. Estate & Legacy Planning',
        # housing-estimate-realism-and-dollar-convention-design.md Slice 3:
        # new optional sheet, lands densely at the end of the plan-optimizer
        # block (highest letter_rank ahead of the "This year's actions" pair).
        '2I. Housing Comparison',
        '2J. Tax-Loss Harvesting','2K. Gain Harvesting',
        # #329 §1.2/§3.3 (W9): Scenario Analysis restored from hidden too,
        # 3C -- matching the catalog entry's own `tab="3C. Scenario
        # Analysis"`, set in anticipation of this.
        '3. Comparisons','3A. State Residency','3B. S-Corp vs LLC','3C. Scenario Analysis',
        # W3 (#329 O10): LTC Stress Test is split back out of the merged Life
        # Insurance sheet into its own '4.1 stress tests' tab; Life Insurance
        # Need is the only '4.2 protection decision' on in this fixture's
        # plan (existing_life_insurance/disability_income_insurance/
        # property_casualty_umbrella are off). Divorce/QDRO (W9, rank 2.5,
        # between LTC Stress Test and Life Insurance Need) is off by default
        # in this fixture, so it does not appear and letters compress.
        '4. Risks','4A. Monte Carlo','4B. Survivor','4C. LTC Stress Test','4D. Life Insurance Need',
        # W11 addendum (2026-09-22): Planning Levers is recatalogued WORKSHEET
        # and now sits in '1. Reports' as 1I (see above) instead of here.
        # REFERENCE-kind, filed in System rather than Reports; system review
        # 2026-08-31 item 1.17's always-on consolidated headroom view now
        # sorts here, densely last -- 5H now that Planning Levers left System.
        # W3 renumbered System's own group code from '4' to '5' -- '4' is now
        # Risks.
        '5. Reference','5A. Plan Data','5B. Assumptions','5C. Account Reconciliation','5D. Quality Control','5E. RMD Audit','5F. Methodology','5G. Glossary','5H. Tax Capacity',
    ]
    assert visible[:len(expected)] == expected
    assert '4D. Feature Toggle' not in visible
    assert '4A. Plan Scope' not in visible


def test_visible_workbook_has_no_stale_feature_or_plan_scope_labels(built_workbook_path):
    wb = _visible_wb(built_workbook_path)
    banned = ['Feature Toggle', 'Feature Toggles', 'FEATURE TOGGLES', 'Feature / Toggle', 'Plan Scope', 'Charts Dashboard', 'System Configuration']
    hits = []
    for ws in wb.worksheets:
        if ws.sheet_state != 'visible':
            continue
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    for term in banned:
                        if term in cell.value:
                            hits.append((ws.title, cell.coordinate, term, cell.value))
    assert not hits


def _expected_width(stable_sheet, col, heuristic_cap):
    """A column's expected width: the reference formatting workbook's exact
    value if it pins this column, else the heuristic cap.

    #209/#210/#212/#228: TEMPLATE_LAYOUT is keyed by each sheet's STABLE
    (build-time) name, not its final letter -- pass the stable name.
    """
    pinned = TEMPLATE_LAYOUT.get(stable_sheet, {}).get('cols', {}).get(col)
    return pinned if pinned is not None else heuristic_cap


def test_column_width_caps_are_applied_without_header_driven_expansion(built_workbook_path):
    wb = _visible_wb(built_workbook_path)
    # The generated layout pass uses Excel character widths approximating the requested pixel caps,
    # except where the reference formatting workbook (template for column widths and height.xlsx)
    # pins an exact width for that column — those exact values win at generation time.
    max_text_width = round((200 - 5) / 7, 1) + 0.1
    max_dollar_width = round((71 - 5) / 7, 1) + 0.1
    max_int_width = round((40 - 5) / 7, 1) + 0.1
    assert wb['5F. Methodology'].column_dimensions['A'].width <= _expected_width('23. Methodology', 'A', max_text_width)

    # RMD Audit column G holds account balances, which can genuinely need
    # more than the hand-tuned template's pinned width (e.g. a 7-figure IRA
    # balance) -- widen_overflowing_number_columns() then grows it past the
    # cap so Excel shows the real value instead of "#####". Allow the width
    # up to what the sheet's actual largest value needs; anything beyond that
    # would signal header-driven (not data-driven) expansion, which this test
    # still guards against.
    rmd_ws = wb['5E. RMD Audit']
    rmd_g_cap = _expected_width('20. RMD Audit', 'G', max_dollar_width)
    g_cells = [
        cell for row in rmd_ws.iter_rows(min_col=7, max_col=7)
        for cell in row if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    ]
    needed_for_data = max((_needed_number_width(c.value, c.number_format) or 0 for c in g_cells), default=0)
    assert rmd_ws.column_dimensions['G'].width <= max(rmd_g_cap, needed_for_data) + 1.0

    assert wb['5E. RMD Audit'].column_dimensions['C'].width <= _expected_width('20. RMD Audit', 'C', max_int_width)
