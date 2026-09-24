import pytest
from openpyxl import load_workbook

pytestmark = pytest.mark.slow


def test_workbook_uses_numbered_sections_and_lettered_children(built_workbook_path):
    assert built_workbook_path.exists(), 'Generated workbook is missing'
    wb = load_workbook(built_workbook_path, read_only=False, data_only=False)
    visible = [ws.title for ws in wb.worksheets if ws.sheet_state == 'visible']
    expected = [
        '1. Reports',
        '1A. Executive Summary',
        '1B. Net Worth',
        '1C. Cash Flow',
        '1D. Balance Sheet',
        '1E. Charts',
        '1F. Lifetime Taxes',
        # #221: Core Spending merged into Spending Summary -- no separate
        # sheet/letter for it anymore, so Spending Summary is densely 1G
        # (not the old static 1H).
        '1G. Spending Summary',
        '1H. Current vs. Proposed',
        # W11 addendum (2026-09-22): recatalogued WORKSHEET (was REFERENCE) --
        # an interactive lever-screening tool, not a static echo -- so it now
        # letters and sorts in Reports instead of System, densely last.
        '1I. Planning Levers',
        '2. Optimizers',
        '2A. Roth Conversion',
        # HSA Drawdown always sits right after Roth Conversion (shares its
        # objective, per sheets_strategy.py) -- always-on like Tax Capacity
        # below, not module-gated, so it is never absent.
        '2B. HSA Drawdown',
        '2C. Asset Allocation',
        # #329 §1.2/§3.3 (W9): Withdrawal Sequencing (retirement_strategy)
        # restored from hidden -- built and gated identically before and
        # after, only the lettered nav visibility changed. Sits right after
        # Asset Allocation, matching #329 §3.3's UI ordering.
        '2D. Withdrawal Sequencing',
        # W3 (#329 O10, F1): COMPARISON modules (State Residency, S-Corp vs
        # LLC) moved to their own '3. Comparisons' group, out of Optimizers
        # -- so Social Security now follows Withdrawal Sequencing.
        '2E. Social Security',
        # #329 §1.2 (W9): Asset Location (asset_location) restored from
        # hidden too, workbook-only (not in #329 §3.3's UI list, unlike
        # Withdrawal Sequencing/Scenario Analysis).
        '2F. Asset Location',
        '2G. Charitable Giving',
        '2H. Estate & Legacy Planning',
        # housing-estimate-realism-and-dollar-convention-design.md Slice 3:
        # new optional sheet, lands densely at the end of the plan-optimizer
        # block (highest letter_rank ahead of the "This year's actions" pair).
        '2I. Housing Comparison',
        # W3 (#329 §3.2 F3): action optimizers stay inside Optimizers, but
        # ordered last as a "This year's actions" divider row in the section
        # summary tab -- see build_workbook_section_divider.
        '2J. Tax-Loss Harvesting',
        '2K. Gain Harvesting',
        '3. Comparisons',
        '3A. State Residency',
        '3B. S-Corp vs LLC',
        # #329 §1.2/§3.3 (W9): Scenario Analysis (what_if_analysis) restored
        # from hidden -- "the UI elevates it to a screen while the workbook
        # hides the sheet" is no longer true on the workbook side either.
        # letter_rank 2 lands it as 3C, matching the catalog entry's own
        # `tab="3C. Scenario Analysis"`, set in anticipation of this.
        '3C. Scenario Analysis',
        '4. Risks',
        '4A. Monte Carlo',
        '4B. Survivor',
        # W3 (#329 O10): LTC Stress Test is split back out of the merged Life
        # Insurance sheet into its own tab under 4.1 stress tests.
        '4C. LTC Stress Test',
        # #329 §1.2/§3.3 (W9): Divorce/QDRO would sit here (rank 2.5, between
        # LTC Stress Test and Life Insurance Need) if enabled -- this fixture
        # does not force-enable it (off by default), matching the "newer
        # default-off modules are intentionally NOT force-enabled" comment
        # on RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES above, so letters
        # compress and Life Insurance Need stays 4D.
        # 4.2 protection decisions. Only Life Insurance Need is on in this
        # fixture's plan (existing_life_insurance/disability_income_insurance/
        # property_casualty_umbrella are off), so it is the only one present.
        '4D. Life Insurance Need',
        '5. Reference',
        '5A. Plan Data',
        '5B. Assumptions',
        '5C. Account Reconciliation',
        '5D. Quality Control',
        '5E. RMD Audit',
        '5F. Methodology',
        '5G. Glossary',
        # REFERENCE-kind, filed in System rather than Reports -- restates
        # figures computed elsewhere for the same audit purpose as Plan
        # Data/Assumptions/Methodology/Glossary, the other four REFERENCE
        # sheets. Planning Levers moved out to Reports (see 1I above, W11
        # addendum 2026-09-22), so Tax Capacity now lands densely last as 5H.
        '5H. Tax Capacity',
    ]
    assert visible[: len(expected)] == expected
    assert '5A. Plan Data' in visible
    assert 'Reports' not in visible
    assert 'Risk' not in visible
    assert 'Optimizers' not in visible
    assert 'System Configuration' not in visible


def test_summary_tabs_reference_child_tabs(built_workbook_path):
    wb = load_workbook(built_workbook_path, read_only=False, data_only=False)
    summary_expected = {
        '1. Reports': ['1A. Executive Summary', '1B. Net Worth', '1C. Cash Flow', '1D. Balance Sheet', '1E. Charts'],
        '2. Optimizers': ['2A. Roth Conversion', '2B. HSA Drawdown', '2C. Asset Allocation', '2D. Withdrawal Sequencing', '2E. Social Security', '2H. Estate & Legacy Planning'],
        '3. Comparisons': ['3A. State Residency', '3B. S-Corp vs LLC', '3C. Scenario Analysis'],
        '4. Risks': ['4A. Monte Carlo', '4B. Survivor', '4C. LTC Stress Test', '4D. Life Insurance Need'],
        '5. Reference': ['5A. Plan Data', '5B. Assumptions', '5C. Account Reconciliation', '5D. Quality Control', '5E. RMD Audit', '5F. Methodology', '5G. Glossary'],
    }
    for sheet, children in summary_expected.items():
        ws = wb[sheet]
        values = [cell.value for row in ws.iter_rows(min_row=1, max_row=20, min_col=1, max_col=8) for cell in row]
        for child in children:
            assert child in values


def test_strategy_scorp_ltc_and_asset_location_merges_are_present(built_workbook_path):
    wb = load_workbook(built_workbook_path, read_only=False, data_only=False)
    exec_text = ' '.join(str(c.value or '') for row in wb['1A. Executive Summary'].iter_rows() for c in row)
    scorp_text = ' '.join(str(c.value or '') for row in wb['3B. S-Corp vs LLC'].iter_rows() for c in row)
    allocation_text = ' '.join(str(c.value or '') for row in wb['2C. Asset Allocation'].iter_rows() for c in row)
    ltc_text = ' '.join(str(c.value or '') for row in wb['4C. LTC Stress Test'].iter_rows() for c in row)
    assert 'WITHDRAWAL SEQUENCE STRATEGY' in exec_text
    assert 'S-CORP vs LLC' in scorp_text and 'LLC / Sole-Prop' in scorp_text
    assert 'ASSET-LOCATION OPTIMIZER' in allocation_text
    assert 'LONG-TERM-CARE STRESS TEST' in ltc_text
