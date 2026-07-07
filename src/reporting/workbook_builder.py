from .workbook_common import *
from .workbook_common import optimize_workbook_layout
from .enterprise_pdf import build_enterprise_pdf
from .sheets_summary_builder import build_sheet1, build_sheet2
from .sheets_summary import build_sheet3, build_sheet4
from .sheets_projection_facade import build_sheet5, build_sheet6, build_sheet7, build_sheet8
from .sheets_strategy import build_sheet9, build_sheet10, build_sheet11, build_sheet12, build_sheet13, build_sheet14
from .sheets_stress import build_sheet15, build_sheet16, build_sheet17, build_sheet18, build_sheet19, build_sheet20
from .sheets_qc_reference import validate_all, build_sheet21, build_sheet22, build_sheet23, build_sheet24, account_reconciliation_rows, build_sheet25
from .dashboard import post_save_patch, build_html_dashboard
from ..governance import advisor_readiness, source_citations, tax_law_dashboard, stress_narratives, workbook_consistency_warnings
from ..after_tax import estimate_after_tax_terminal_net_worth
from ..build_snapshot import SNAPSHOT_FILENAME, write_build_snapshot
from ..report_package import REPORT_PACKAGE_FILENAME, write_report_package
from ..results_model import RESULTS_MODEL_FILENAME, write_result_explorer_model


def _build_plan_input_fingerprint(base_dir, config_meta):
    """Return a stable fingerprint of the exact Plan Data files seen by this build."""
    import hashlib as _hashlib
    import json as _json
    from pathlib import Path as _Path

    plan_names = [
        "client_data.csv", "client_household.csv", "client_income.csv", "client_spending.csv",
        "client_assets.csv", "client_policy.csv", "client_insurance_estate.csv",
        "client_optional_functions.csv", "asset_class_optimizer_controls.csv",
        "client_holdings.csv", "target_allocation.csv",
        "client_data.json", "client_data.yaml", "client_household.json", "client_income.json",
        "client_spending.json", "client_assets.json", "client_policy.json",
        "client_insurance_estate.json", "client_optional_functions.json",
        "asset_class_optimizer_controls.json", "client_household.yaml", "client_income.yaml",
        "client_spending.yaml", "client_assets.yaml", "client_policy.yaml",
        "client_insurance_estate.yaml", "client_optional_functions.yaml",
        "asset_class_optimizer_controls.yaml",
    ]
    root = _Path(base_dir)
    meta_path = _Path(str((config_meta or {}).get("path") or root / "input" / "client_data.csv"))
    if not meta_path.is_absolute():
        meta_path = root / meta_path
    plan_dir = meta_path.parent if meta_path.suffix else root / "input"
    files = []
    h = _hashlib.sha256()
    for name in plan_names:
        path = plan_dir / name
        if not path.exists() or not path.is_file():
            continue
        data = path.read_bytes()
        rel = f"{plan_dir.name}/{name}"
        digest = _hashlib.sha256(data).hexdigest()
        files.append({"file": rel, "sha256": digest, "bytes": len(data)})
        h.update(rel.encode("utf-8")); h.update(b"\0"); h.update(digest.encode("ascii")); h.update(b"\0")
    bootstrap = (config_meta or {}).get("bootstrap_csv")
    if bootstrap:
        bp = _Path(str(bootstrap))
        if not bp.is_absolute():
            bp = root / bp
        if bp.exists() and bp.is_file():
            data = bp.read_bytes()
            rel = bp.name
            digest = _hashlib.sha256(data).hexdigest()
            files.append({"file": rel, "sha256": digest, "bytes": len(data)})
            h.update(rel.encode("utf-8")); h.update(b"\0"); h.update(digest.encode("ascii")); h.update(b"\0")
    return {"sha256": h.hexdigest(), "plan_dir": str(plan_dir), "files": files}


def _build_spending_heard(c):
    return {
        "annual_spending_base_year": c.get("spend_base"),
        "core_spending_growth_mode": c.get("core_spending_growth_mode"),
        "core_spending_manual_growth_rate": c.get("core_spending_manual_growth_rate"),
        "core_spending_effective_growth_rate": c.get("spend_inf"),
        "inflation_general": c.get("inf"),
        "spending_freeze_year": c.get("spending_freeze_yr"),
    }


def _build_roth_heard(c):
    return {
        "roth_policy": c.get("roth_policy"),
        "roth_policy_requested": c.get("roth_policy_requested"),
        "roth_policy_lock": c.get("roth_policy_lock"),
        "roth_bracket_strategy": c.get("roth_bracket_strategy"),
        "roth_target_rate": c.get("roth_target_rate"),
        "roth_irmaa_cap": c.get("roth_irmaa_cap"),
        "irmaa_guardrail_mode": c.get("irmaa_guardrail_mode"),
        "roth_irmaa_target_tier": c.get("roth_irmaa_target_tier"),
        "roth_headroom_usage_pct": c.get("roth_headroom_usage_pct"),
        "roth_irmaa_headroom_usage_pct": c.get("roth_irmaa_headroom_usage_pct"),
        "roth_fixed_amount": c.get("roth_fixed_amount"),
        "roth_max_conversion_years": c.get("roth_max_conversion_years"),
        "selected_roth_strategy": (c.get("roth_optimization") or {}).get("selected_label"),
    }


def build_sheet_spending_summary(ws, c):
    """Taxonomy-aware Spending Summary — 4-level collapsible outline.

    Hierarchy (outline levels):
      Level 0  — Tracking Type header row  (always visible, bold, dark BG)
      Level 1  — Group header row          (expand level 1 to show groups)
      Level 2  — Category detail row       (expand level 2 to show categories)

    Uses spending_tracker.spending_summary_taxonomy() which resolves category
    IDs via keyword mapping rules, then falls back to the legacy flat map.
    """
    import datetime
    from ..spending_tracker import spending_summary_taxonomy

    ws.sheet_view.showGridLines = False
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.freeze_panes = 'B5'

    current_year = datetime.date.today().year

    try:
        data = spending_summary_taxonomy(year=current_year)
    except Exception as exc:
        data = {
            'success': False, 'tracking_types': [],
            'grand_actual': 0, 'grand_annualized': 0, 'grand_budget': 0,
            'days_elapsed': 0,
        }

    tracking_types = data.get('tracking_types', [])
    days_elapsed   = data.get('days_elapsed', 0)
    grand_actual   = data.get('grand_actual', 0)
    grand_ann      = data.get('grand_annualized', 0)
    grand_budget   = data.get('grand_budget', 0)
    unmapped       = data.get('unmapped_categories', [])
    ann_factor     = data.get('annualization_factor', 1.0)

    # ── Title ─────────────────────────────────────────────────────────────────
    section_title(
        ws, 1,
        f'SPENDING SUMMARY — {current_year} YTD  ({days_elapsed} days elapsed)',
        6, bg=RED,
    )

    # ── Summary metrics ───────────────────────────────────────────────────────
    r = 2
    for lbl, val, fmt in [
        (f'YTD total spending — actual ({days_elapsed} days)', grand_actual, FMT_DOLLAR),
        ('Annualized at current pace',                          grand_ann,   FMT_DOLLAR),
        ('Total annual budget (categories with budgets set)',   grand_budget, FMT_DOLLAR),
    ]:
        write_cell(ws, r, 1, lbl, bold=True, bg='EAF2F8', border=False)
        write_cell(ws, r, 2, val, fmt=fmt, bold=True, bg='EAF2F8', align='right', border=False)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=1)
        r += 1

    r += 1  # blank

    # ── Column headers ────────────────────────────────────────────────────────
    HDR_BG = DGRAY
    write_hdr(ws, r, 1, 'Tracking Type / Group / Category', HDR_BG, WHITE, span=1)
    write_hdr(ws, r, 2, 'YTD Actual',   HDR_BG, WHITE)
    write_hdr(ws, r, 3, 'Annualized',   HDR_BG, WHITE)
    write_hdr(ws, r, 4, 'Budget',       HDR_BG, WHITE)
    write_hdr(ws, r, 5, 'vs Budget',    HDR_BG, WHITE)
    write_hdr(ws, r, 6, '% of Total',   HDR_BG, WHITE)
    r += 1

    # ── Colour palette ────────────────────────────────────────────────────────
    TYPE_BG = 'D6E4F0'   # tracking-type row  (level 0 — always visible)
    GRP_BG  = 'EAF2F8'   # group row           (level 1)
    CAT_BG  = None       # category row        (level 2)

    # ── Tracking type loop ────────────────────────────────────────────────────
    for tt_data in tracking_types:
        tt_name    = tt_data['tracking_type']
        tt_actual  = tt_data['actual']
        tt_ann     = tt_data['annualized']
        tt_budget  = tt_data['budget']
        groups     = tt_data.get('groups', [])

        if not groups and tt_actual == 0:
            continue  # skip empty types

        # Tracking Type header (outline level 0 — always visible)
        pct_of_total = (tt_actual / grand_actual) if grand_actual > 0 else 0
        variance     = (tt_ann - tt_budget) if tt_budget else 0

        write_cell(ws, r, 1, tt_name,    bold=True, bg=TYPE_BG)
        write_cell(ws, r, 2, tt_actual,  bold=True, bg=TYPE_BG, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 3, tt_ann,     bold=True, bg=TYPE_BG, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 4, tt_budget if tt_budget else '',
                   bold=True, bg=TYPE_BG,
                   fmt=FMT_DOLLAR if tt_budget else None, align='right')
        write_cell(ws, r, 5, variance if tt_budget else '',
                   bold=True, bg=TYPE_BG,
                   fmt=FMT_DOLLAR if tt_budget else None, align='right',
                   fg=('C00000' if tt_budget and variance > 0 else '000000'))
        write_cell(ws, r, 6, pct_of_total, bold=True, bg=TYPE_BG, fmt=FMT_PCT, align='right')
        r += 1

        # Groups (outline level 1 — hidden by default, expand tracking type to reveal)
        for grp_data in groups:
            grp_name   = grp_data['group']
            grp_actual = grp_data['actual']
            grp_ann    = grp_data['annualized']
            grp_budget = grp_data['budget']
            cats       = grp_data.get('categories', [])

            grp_pct      = (grp_actual / grand_actual) if grand_actual > 0 else 0
            grp_variance = (grp_ann - grp_budget) if grp_budget else 0

            write_cell(ws, r, 1, f'  {grp_name}', bold=True, bg=GRP_BG)
            write_cell(ws, r, 2, grp_actual,  bold=True, bg=GRP_BG, fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 3, grp_ann,     bold=True, bg=GRP_BG, fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 4, grp_budget if grp_budget else '',
                       bold=True, bg=GRP_BG,
                       fmt=FMT_DOLLAR if grp_budget else None, align='right')
            write_cell(ws, r, 5, grp_variance if grp_budget else '',
                       bold=True, bg=GRP_BG,
                       fmt=FMT_DOLLAR if grp_budget else None, align='right',
                       fg=('C00000' if grp_budget and grp_variance > 0 else '000000'))
            write_cell(ws, r, 6, grp_pct, bold=True, bg=GRP_BG, fmt=FMT_PCT, align='right')
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1

            # Categories (outline level 2 — hidden by default)
            for cat in cats:
                cat_label  = cat.get('label') or cat.get('id', '')
                cat_actual = cat['actual']
                cat_ann    = cat['annualized']
                cat_budget = cat.get('budget', 0)
                cat_pct    = (cat_actual / grand_actual) if grand_actual > 0 else 0
                cat_var    = (cat_ann - cat_budget) if cat_budget else 0

                write_cell(ws, r, 1, f'    {cat_label}', bg=CAT_BG)
                write_cell(ws, r, 2, cat_actual,  fmt=FMT_DOLLAR, align='right', bg=CAT_BG)
                write_cell(ws, r, 3, cat_ann,     fmt=FMT_DOLLAR, align='right', bg=CAT_BG)
                write_cell(ws, r, 4, cat_budget if cat_budget else '',
                           fmt=FMT_DOLLAR if cat_budget else None, align='right', bg=CAT_BG)
                write_cell(ws, r, 5, cat_var if cat_budget else '',
                           fmt=FMT_DOLLAR if cat_budget else None, align='right', bg=CAT_BG,
                           fg=('C00000' if cat_budget and cat_var > 0 else '000000'))
                write_cell(ws, r, 6, cat_pct, fmt=FMT_PCT, align='right', bg=CAT_BG)
                ws.row_dimensions[r].outlineLevel = 2
                ws.row_dimensions[r].hidden = True
                r += 1

    # ── Grand total row ───────────────────────────────────────────────────────
    r += 1
    write_cell(ws, r, 1, 'TOTAL SPENDING', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, grand_actual,  bold=True, bg=LGRAY, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 3, grand_ann,     bold=True, bg=LGRAY, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 4, grand_budget if grand_budget else '',
               bold=True, bg=LGRAY,
               fmt=FMT_DOLLAR if grand_budget else None, align='right')
    overall_var = (grand_ann - grand_budget) if grand_budget else 0
    write_cell(ws, r, 5, overall_var if grand_budget else '',
               bold=True, bg=LGRAY,
               fmt=FMT_DOLLAR if grand_budget else None, align='right',
               fg=('C00000' if grand_budget and overall_var > 0 else '000000'))
    write_cell(ws, r, 6, 1.0 if grand_actual > 0 else 0,
               bold=True, bg=LGRAY, fmt=FMT_PCT, align='right')
    r += 2

    # ── Unmapped categories note ──────────────────────────────────────────────
    if unmapped:
        section_title(ws, r, 'UNMAPPED TRANSACTION CATEGORIES (defaulted to Core Expenses / Other)', 6, bg=ORANGE)
        r += 1
        write_cell(ws, r, 1,
                   'These bank category names were not matched by any keyword rule and have no '
                   'canonical Spending Category assignment. Add an Advanced Auto-Mapping Rule on the Spending Categories page.',
                   fg='595959', border=False)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1
        for cat_name in sorted(unmapped):
            write_cell(ws, r, 1, f'  {cat_name}', bg=CAT_BG)
            for col in range(2, 7):
                write_cell(ws, r, col, '', bg=CAT_BG)
            r += 1

    # ── No data fallback ──────────────────────────────────────────────────────
    if not tracking_types or grand_actual == 0:
        write_cell(ws, r, 1,
                   'No transaction data found. Upload a transaction CSV on the '
                   'Income & Expense Transactions tab, then rebuild the workbook.',
                   fg='595959', border=False)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)

    # ── Column widths ─────────────────────────────────────────────────────────
    ws.column_dimensions['A'].width = 44
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 10

    qc('Spending Summary',
       f'Taxonomy-aware spending summary, {len(tracking_types)} tracking types', True,
       f'${grand_actual:,.0f} actual  |  ${grand_ann:,.0f} annualized  |  {len(unmapped)} unmapped')


def build_sheet_core_spending(ws, c):
    """Core Spending Breakdown — Core-Expenses budget & YTD by group.

    RECONCILIATION (item 141): this sheet used to read the legacy
    spending_category_map.csv / spending_budget.csv (percentage-based) via
    group_actuals()/budget_by_group().  Those files are a separate, stale data
    source from the unified spending model that drives the UI Spending Model
    page, the Cash Flow projection (spend_base), and the Spending Summary sheet.
    That mismatch is exactly the "budget numbers differ per screen" bug reported.

    It now sources the SAME unified taxonomy model (spending_summary_taxonomy)
    that the UI and the Spending Summary sheet use, scoped to the Core Expenses
    tracking type.  The Budget column here is the unified per-group annual budget
    / projection seed, so it reconciles exactly with the UI and with the Core
    Expenses portion of the Cash Flow spend_base.  YTD Actual / Annualized are the
    transaction-derived actuals for the same categories — a different but
    intentional lens (what was actually spent vs. what is budgeted).

    Housing / Wellness / Travel / Large Discretionary are shown in a reference
    section: they are tracked as their own Cash Flow columns and are intentionally
    excluded from Core Spending to prevent double-counting.
    """
    import datetime
    from ..spending_tracker import spending_summary_taxonomy

    ws.sheet_view.showGridLines = False
    ws.sheet_properties.outlinePr.summaryBelow = False   # group header above detail
    ws.freeze_panes = 'B5'

    current_year = datetime.date.today().year
    core_assumption = float(c.get('spend_base', 0) or 0)

    try:
        summary = spending_summary_taxonomy(year=current_year)
    except Exception:
        summary = {'tracking_types': [], 'days_elapsed': 0, 'annualization_factor': 1.0}

    days_elapsed = summary.get('days_elapsed', 0)
    ann_factor   = summary.get('annualization_factor', 1.0)
    tracking_types = summary.get('tracking_types', [])

    # Core Expenses is "core spending" in the unified model.
    core_tt = next((t for t in tracking_types if t.get('tracking_type') == 'Core Expenses'), None)

    # Reshape unified Core Expenses groups into the row shape this sheet renders.
    groups = []
    total_actual = 0.0
    total_ann = 0.0
    for g in (core_tt.get('groups', []) if core_tt else []):
        groups.append({
            'group': g.get('group', ''),
            'actual': g.get('ytd_actual', g.get('actual', 0)) or 0,
            'annualized': g.get('annualized_actual', g.get('annualized', 0)) or 0,
            'budget': g.get('annual_budget', g.get('budget', 0)) or 0,
            'categories': [
                {'category': cat.get('label') or cat.get('id', ''),
                 'actual': cat.get('ytd_actual', cat.get('actual', 0)) or 0,
                 'budget': cat.get('annual_budget', cat.get('budget', 0)) or 0}
                for cat in g.get('categories', [])
            ],
        })
        total_actual += g.get('ytd_actual', g.get('actual', 0)) or 0
        total_ann += g.get('annualized_actual', g.get('annualized', 0)) or 0

    # Per-group budget from the unified model (reconciles with UI + Cash Flow).
    budget_groups = {g['group']: {'budget_amount': g['budget']} for g in groups}

    # Reference section: tracking types tracked separately in the Cash Flow model.
    EXCLUDED_TTS = ['Housing', 'Wellness', 'Travel', 'Large Discretionary']
    model_managed = {}
    for t in tracking_types:
        tt = t.get('tracking_type')
        if tt not in EXCLUDED_TTS:
            continue
        cats = {}
        for g in t.get('groups', []):
            for cat in g.get('categories', []):
                amt = cat.get('ytd_actual', cat.get('actual', 0)) or 0
                if amt:
                    cats[cat.get('label') or cat.get('id', '')] = amt
        # Even with no YTD actuals, surface the budgeted total so the reference is meaningful.
        if not cats:
            budget_total = t.get('annual_budget', t.get('budget', 0)) or 0
            if budget_total:
                cats[f'{tt} (annual budget)'] = budget_total
        if cats:
            model_managed[tt.lower().replace(' ', '_')] = cats

    # ── Title ──────────────────────────────────────────────────────────────────
    section_title(ws, 1, f'CORE SPENDING BREAKDOWN — {current_year} YTD  ({days_elapsed} days elapsed)', 5, bg=RED)

    # ── Summary metrics ────────────────────────────────────────────────────────
    r = 2
    summary_rows = [
        ('Model core spending assumption (annual)',        core_assumption,    FMT_DOLLAR),
        (f'YTD core spending — actual ({days_elapsed} days)', total_actual,   FMT_DOLLAR),
        ('Annualized at current pace',                     total_ann,         FMT_DOLLAR),
    ]
    if core_assumption > 0 and total_ann > 0:
        variance = total_ann - core_assumption
        pct_of_model = total_ann / core_assumption
        summary_rows.append((
            f'Annualized vs model ({pct_of_model:.0%}  {"OVER" if variance > 0 else "under"} budget)',
            variance,
            FMT_DOLLAR,
        ))
    for lbl, val, fmt in summary_rows:
        write_cell(ws, r, 1, lbl, bold=True, bg='EAF2F8', border=False)
        write_cell(ws, r, 2, val, fmt=fmt, bold=True, bg='EAF2F8',
                   align='right', border=False,
                   fg=('C00000' if lbl.startswith('Annualized vs') and val > 0 else '000000'))
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=1)
        r += 1

    r += 1  # blank separator

    # ── Column headers ─────────────────────────────────────────────────────────
    HDR_BG = DGRAY
    write_hdr(ws, r, 1, 'Spending Group / Category', HDR_BG, WHITE, span=1)
    write_hdr(ws, r, 2, 'YTD Actual',                HDR_BG, WHITE)
    write_hdr(ws, r, 3, 'Annualized',                HDR_BG, WHITE)
    write_hdr(ws, r, 4, '% of Core',                 HDR_BG, WHITE)
    write_hdr(ws, r, 5, 'Budget',                    HDR_BG, WHITE)
    r += 1

    # ── Group rows + collapsible category detail ───────────────────────────────
    GRP_BG  = 'F0F4FA'
    CAT_BG  = None

    for grp in groups:
        grp_name    = grp['group']
        grp_actual  = grp['actual']
        grp_ann     = grp['annualized']
        grp_pct     = (grp_actual / total_actual) if total_actual > 0 else 0
        budget_info = budget_groups.get(grp_name, {})
        grp_budget  = budget_info.get('budget_amount', 0)

        # Group summary row
        write_cell(ws, r, 1, grp_name,   bold=True, bg=GRP_BG)
        write_cell(ws, r, 2, grp_actual, bold=True, bg=GRP_BG, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 3, grp_ann,    bold=True, bg=GRP_BG, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 4, grp_pct,    bold=True, bg=GRP_BG, fmt=FMT_PCT,    align='right')
        write_cell(ws, r, 5, grp_budget if grp_budget else '',
                   bold=True, bg=GRP_BG, fmt=FMT_DOLLAR if grp_budget else None, align='right')
        r += 1

        # Category detail rows (collapsed by default)
        for cat in grp.get('categories', []):
            cat_name   = cat['category']
            cat_actual = cat['actual']
            cat_ann    = round(cat_actual * ann_factor, 2)
            cat_pct    = (cat_actual / total_actual) if total_actual > 0 else 0

            cat_budget = cat.get('budget', 0) or 0
            write_cell(ws, r, 1, f'    {cat_name}', bg=CAT_BG)
            write_cell(ws, r, 2, cat_actual, fmt=FMT_DOLLAR, align='right', bg=CAT_BG)
            write_cell(ws, r, 3, cat_ann,    fmt=FMT_DOLLAR, align='right', bg=CAT_BG)
            write_cell(ws, r, 4, cat_pct,    fmt=FMT_PCT,    align='right', bg=CAT_BG)
            write_cell(ws, r, 5, cat_budget if cat_budget else '',
                       fmt=FMT_DOLLAR if cat_budget else None, align='right', bg=CAT_BG)
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1

    # ── Total row ──────────────────────────────────────────────────────────────
    r += 1
    write_cell(ws, r, 1, 'TOTAL CORE SPENDING', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, total_actual, bold=True, bg=LGRAY, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 3, total_ann,    bold=True, bg=LGRAY, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 4, 1.0 if total_actual > 0 else 0,
               bold=True, bg=LGRAY, fmt=FMT_PCT, align='right')
    total_budget = sum(
        (budget_groups.get(g['group'], {}).get('budget_amount', 0) or 0) for g in groups
    )
    write_cell(ws, r, 5, total_budget if total_budget else '',
               bold=True, bg=LGRAY,
               fmt=FMT_DOLLAR if total_budget else None, align='right')
    r += 2

    # ── Model-managed exclusions (reference only, no double-counting) ──────────
    EXCL_LABELS = {
        'housing':    'Housing (mortgage, property tax, home improvement, rent)',
        'wellness': 'Wellness (premiums, Medicare, out-of-pocket)',
        'travel':     'Travel & Vacations',
        'large_discretionary': 'Large Discretionary Expenses (weddings, home projects, etc.)',
    }
    if model_managed:
        section_title(ws, r,
                      'EXCLUDED — Tracked Separately by the Retirement Projection Model',
                      5, bg=ORANGE)
        r += 1
        write_cell(ws, r, 1,
                   'These categories appear in your transaction data but are already modelled '
                   'in the Cash Flow projection. They are excluded here to prevent double-counting.',
                   fg='595959', border=False)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1

        for tracking_type, cats in model_managed.items():
            if not cats:
                continue
            lbl         = EXCL_LABELS.get(tracking_type, tracking_type.replace('_', ' ').title())
            excl_total  = sum(cats.values())
            write_cell(ws, r, 1, lbl,        bold=True, bg='FFF3E0')
            write_cell(ws, r, 2, excl_total, bold=True, bg='FFF3E0', fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 3, '',         bg='FFF3E0')
            write_cell(ws, r, 4, '',         bg='FFF3E0')
            write_cell(ws, r, 5, '',         bg='FFF3E0')
            r += 1
            for cat_name, amt in sorted(cats.items(), key=lambda x: -x[1]):
                write_cell(ws, r, 1, f'    {cat_name}', bg=CAT_BG)
                write_cell(ws, r, 2, amt, fmt=FMT_DOLLAR, align='right', bg=CAT_BG)
                write_cell(ws, r, 3, '',  bg=CAT_BG)
                write_cell(ws, r, 4, '',  bg=CAT_BG)
                write_cell(ws, r, 5, '',  bg=CAT_BG)
                ws.row_dimensions[r].outlineLevel = 1
                ws.row_dimensions[r].hidden = True
                r += 1

    # ── No data fallback ───────────────────────────────────────────────────────
    if not groups and not model_managed:
        write_cell(ws, r, 1,
                   'No transaction data loaded. Upload a transaction CSV on the '
                   'Income & Expense Transactions tab, then rebuild the workbook.',
                   fg='595959', border=False)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)

    # ── Column widths ──────────────────────────────────────────────────────────
    ws.column_dimensions['A'].width = 42
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 14

    qc('Core Spending', f'YTD core spending breakdown, {len(groups)} groups', True,
       f'${total_actual:,.0f} actual  |  ${total_ann:,.0f} annualized')


def build_sheet26_workbook_warnings(ws, c, rows):
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'WORKBOOK WARNINGS — Consistency, Staleness, and Advisor Review', 8, bg=ORANGE)
    warnings = workbook_consistency_warnings(c, rows)
    r = 3
    write_hdr(ws, r, 1, 'Severity', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Code', DGRAY, WHITE)
    write_hdr(ws, r, 3, 'Message', DGRAY, WHITE, span=3)
    write_hdr(ws, r, 6, 'Recommended Action', DGRAY, WHITE, span=3)
    r += 1
    if not warnings:
        write_cell(ws, r, 1, 'OK', bold=True, bg='E2EFDA')
        write_cell(ws, r, 2, 'NO_CONSISTENCY_WARNINGS')
        write_cell(ws, r, 3, 'No workbook consistency warnings were detected from the canonical result contract.')
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        write_cell(ws, r, 6, 'Review tax freshness, pricing, and assumption signoff separately.')
        ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=8)
    else:
        for w in warnings:
            sev = str(w.get('severity','WARN'))
            write_cell(ws, r, 1, sev, bold=True, bg='FFF2CC' if sev == 'WARN' else 'FCE4D6')
            write_cell(ws, r, 2, w.get('code',''))
            write_cell(ws, r, 3, w.get('message',''))
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
            write_cell(ws, r, 6, w.get('action',''))
            ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=8)
            r += 1
    for col, width in {'A':12,'B':30,'C':36,'D':12,'E':12,'F':42,'G':12,'H':12}.items():
        ws.column_dimensions[col].width = width



def build_sheet27_planning_levers(ws, c, rows, mc_data):
    """Interactive planning levers / sensitivity dashboard.

    This is a screening worksheet, not a replacement for rebuilding the model.
    Input cells let the user test practical levers and formulas estimate
    directional impact on terminal net worth and Monte Carlo success.
    """
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A11'
    ws.sheet_properties.tabColor = SECTION_COLOR.get('2')
    section_title(ws, 1, '2H. PLANNING LEVERS / SENSITIVITY DASHBOARD', 9, bg=SECTION_COLOR.get('2'))
    write_cell(ws, 3, 1, 'Use this worksheet to screen changes before changing actual Plan Data and rebuilding. Yellow cells are editable test assumptions; results are directional estimates only.', fg='666666')
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=10)

    terminal = float((rows[-1].get('total_nw') if rows else 0.0) or 0.0)
    mc_success = float((mc_data or {}).get('success_rate', 0.0) or 0.0)
    spend = float(c.get('spend_base', c.get('annual_spending_base_year', 200000)) or 200000)
    earned = float(c.get('earned', c.get('annual_earned_income', 0.0)) or 0.0)
    years = max(1, int(float(c.get('plan_end', 2056) or 2056)) - int(float(c.get('plan_start', 2026) or 2026)) + 1)

    write_hdr(ws, 5, 1, 'Current model anchor', DGRAY, WHITE, span=2)
    anchors = [
        ('Terminal net worth', terminal, FMT_DOLLAR),
        ('Monte Carlo success', mc_success, FMT_PCT),
        ('Core annual spending', spend, FMT_DOLLAR),
        ('Earned income assumption', earned, FMT_DOLLAR),
        ('Remaining plan years', years, FMT_INT),
    ]
    r = 6
    for label, value, fmt in anchors:
        write_cell(ws, r, 1, label, bold=True, bg='EDE7F6')
        write_cell(ws, r, 2, value, fmt=fmt)
        r += 1

    header_row = 12
    headers = ['Focus', 'Lever', 'Source Section', 'Test Amount', 'Unit', 'Estimated Δ TNW', 'Estimated Δ Success', 'TNW Rank', 'Success Rank', 'Guidance']
    for idx, header in enumerate(headers, start=1):
        write_hdr(ws, header_row, idx, header, DGRAY, WHITE)
    specs = [
        ('TNW', 'Reduce recurring/core spending', 'Spending Categories', 10000, '$/year', '=D{r}*$B$10*0.55', '=MIN(0.30,MAX(-0.30,(D{r}/MAX(1,$B$8))*0.25))', 'Improves both TNW and success by lowering annual withdrawals.'),
        ('TNW', 'Work longer / retire later', 'Retirement Timing', 1, 'years', '=D{r}*($B$9*0.45+$B$8*0.25)', '=MIN(0.30,MAX(-0.30,D{r}*0.08))', 'Usually the strongest lever because it adds income and delays withdrawals.'),
        ('TNW', 'Cut or delay large discretionary spending', 'Large Discretionary', 25000, '$ one-time', '=D{r}', '=MIN(0.30,MAX(-0.30,(D{r}/MAX(1,$B$8))*0.04))', 'Directly preserves liquidity and compounding capital.'),
        ('TNW', 'Preserve annual S-Corp tax advantage', 'Entity & Charitable', 29000, '$/year', '=D{r}*MIN(5,$B$10)*0.9', '=MIN(0.30,MAX(-0.30,(D{r}/MAX(1,$B$8))*0.03))', 'Use the S-Corp vs LLC optimizer result if the actual benefit differs.'),
        ('TNW', 'Roth/tax optimization savings', 'Roth Conversion', 50000, '$ total', '=D{r}', '=0', 'Improves after-tax legacy; confirm near-term liquidity does not fall.'),
        ('TNW', 'Improve return without raising volatility', 'Asset Allocation', 25, 'bps/year', '=$B$6*(D{r}/10000)*$B$10*0.35', '=MIN(0.30,MAX(-0.30,(D{r}/25)*0.01))', 'Only positive if volatility does not rise enough to reduce success.'),
        ('Success', 'Dedicated liquidity reserve', 'Cash Reserves', 50000, '$ reserve', '=0', '=MIN(0.30,MAX(-0.30,(D{r}/MAX(1,$B$8))*0.08))', 'Reduces forced selling after poor early returns.'),
        ('Success', 'Home-equity backstop', 'Housing', 250000, '$ available', '=0', '=MIN(0.30,MAX(-0.30,(D{r}/MAX(1,$B$8))*0.06))', 'Improves success only if there is a real access plan.'),
        ('Success', 'Dynamic spending guardrail', 'Spending Categories', 10, '% cut in bad markets', '=$B$8*(D{r}/100)*$B$10*0.25', '=MIN(0.30,MAX(-0.30,D{r}*0.006))', 'Flexing discretionary spending after poor markets is often high impact.'),
        ('Success', 'LTC / catastrophic-care protection', 'Insurance & LTC Policies', 250000, '$ coverage', '=-D{r}*0.05', '=MIN(0.30,MAX(-0.30,(D{r}/MAX(1,$B$8))*0.04))', 'May lower expected TNW slightly, but protects downside paths.'),
    ]
    first = header_row + 1
    last = first + len(specs) - 1
    for i, (focus, lever, source_section, default, unit, tnw_formula, success_formula, guidance) in enumerate(specs, start=first):
        write_cell(ws, i, 1, focus)
        write_cell(ws, i, 2, lever, bold=True)
        write_cell(ws, i, 3, source_section)
        ccell = write_cell(ws, i, 4, default, fmt=FMT_DOLLAR if '$' in unit else FMT_INT)
        input_style(ws, ccell)
        write_cell(ws, i, 5, unit)
        write_cell(ws, i, 6, tnw_formula.format(r=i), fmt=FMT_DOLLAR)
        write_cell(ws, i, 7, success_formula.format(r=i), fmt=FMT_PCT)
        write_cell(ws, i, 8, f'=RANK.EQ(F{i},$F${first}:$F${last},0)', fmt=FMT_INT)
        write_cell(ws, i, 9, f'=RANK.EQ(G{i},$G${first}:$G${last},0)', fmt=FMT_INT)
        note = write_cell(ws, i, 10, guidance)
        note.alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[i].height = 34

    r = last + 3
    section_title(ws, r, 'HOW TO USE', 10, bg=SECTION_COLOR.get('2'))
    for j, text in enumerate([
        '1. Change a yellow test amount to screen sensitivity.',
        '2. If the lever looks material, change the actual Plan Data or Optimizer input in the UI.',
        '3. Rebuild outputs and compare measured Δ TNW and Δ success in Build Impact.',
        '4. Do not accept TNW improvements that materially reduce probability of success unless that risk tradeoff is intentional.',
    ], start=r+1):
        write_cell(ws, j, 1, text, border=False)
        ws.merge_cells(start_row=j, start_column=1, end_row=j, end_column=10)

    widths = {'A':12,'B':28,'C':20,'D':12,'E':20,'F':15,'G':15,'H':10,'I':12,'J':46}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    qc('27. Planning Levers', 'Interactive lever sensitivity dashboard created', True, f'{len(specs)} levers')



def build_workbook_section_divider(ws, area):
    """Create a read-only navigation divider sheet for one of the five top-level workbook areas."""
    section_name = area.get('section', 'Section')
    color = SECTION_COLOR.get(area.get('code'), NAVY)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = color
    section_title(ws, 1, section_name.upper(), 8, bg=color)
    write_cell(ws, 3, 1, area.get('description', ''), bold=True)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=8)
    write_hdr(ws, 5, 1, 'Workbook area', DGRAY, WHITE, span=2)
    write_hdr(ws, 5, 3, 'Included sheets', DGRAY, WHITE, span=5)
    write_cell(ws, 6, 1, section_name, bold=True, bg='EAF2F8')
    ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=2)
    r = 6
    for sheet_name in area.get('sheets', []):
        cell = ws.cell(row=r, column=3, value=sheet_name)
        cell.font = body_font(color='0563C1')
        cell.hyperlink = f"#'{sheet_name}'!A1"
        cell.border = thin_border()
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=7)
        r += 1
    if r == 6:
        write_cell(ws, r, 3, 'No sheets assigned.')
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=7)
        r += 1
    note_cell = write_cell(ws, r + 1, 1, 'This workbook is an output/reporting surface. Edit plan data in the app database; use CSV only for import/export utilities.', fg='666666')
    note_cell.font = Font(name='Arial', italic=True, color='666666', size=10)
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=8)
    for col, width in {'A':18,'B':18,'C':28,'D':18,'E':18,'F':18,'G':18,'H':18}.items():
        ws.column_dimensions[col].width = width
    for row_idx in range(1, r + 3):
        ws.row_dimensions[row_idx].height = 20



# ─────────────────────────────────────────────────────────────────────────────
# User-facing workbook tab refactor helpers
# ─────────────────────────────────────────────────────────────────────────────

FINAL_SHEET_RENAMES = {
    '1. Executive Summary': '1A. Executive Summary',
    '5. Net Worth Projection': '1B. Net Worth',
    '6. Cash Flow Projection': '1C. Cash Flow',
    '3. Balance Sheet': '1D. Balance Sheet',
    '8. Charts Dashboard': '1E. Charts',
    '7. Lifetime Tax': '1F. Lifetime Taxes',
    '11. Roth Conversion': '2A. Roth Conversion',
    '4. Asset Allocation': '2B. Asset Allocation',
    '13. State Residency': '2C. State Residency',
    '10. Social Security': '2D. Social Security',
    '12. Charitable Giving': '2F. Charitable Giving',
    '14. Estate Plan': '2G. Estate & Legacy Planning',
    '27. Planning Levers': '2H. Planning Levers',
    '15. Market-Luck Stress Test': '3A. Monte Carlo',
    '18. Survivor Stress Test': '3B. Survivor',
    '19. Life Insurance': '3C. LTC + Life Insurance',
    '28. Core Spending': '1G. Core Spending',
    '29. Spending Summary': '1H. Spending Summary',
    '2. Assumptions': '4B. Assumptions',
    '25. Account Reconciliation': '4C. Account Reconciliation',
    '21. Quality Control': '4D. Quality Control',
    '20. RMD Audit': '4E. RMD Audit',
    '23. Methodology': '4F. Methodology',
    '22. Glossary': '4G. Glossary',
}

SHEET_NUM_LABEL_REPLACEMENTS = {
    'Sheet 13 & 14': '2C. State Residency & 2G. Estate & Legacy Planning',
    'Sheet 17) shows': '3C. LTC + Life Insurance shows',
    'Sheet 3': '1D. Balance Sheet',
    'Sheet 4': '2B. Asset Allocation',
    'Sheet 5': '1B. Net Worth',
    'Sheet 6': '1C. Cash Flow',
    'Sheet 7': '1F. Lifetime Taxes',
    'Sheet 8': '1E. Charts',
    'Sheet 9': '2E. S-Corp vs LLC',
    'Sheet 10': '2D. Social Security',
    'Sheet 11': '2A. Roth Conversion',
    'Sheet 12': '2F. Charitable Giving',
    'Sheet 13': '2C. State Residency',
    'Sheet 14': '2G. Estate & Legacy Planning',
    'Sheet 15': '3A. Monte Carlo',
    'Sheet 16': 'Scenario Analysis',
    'Sheet 17': '3C. LTC + Life Insurance',
    'Sheet 18': '3B. Survivor',
    'Sheet 19': '3C. LTC + Life Insurance',
    'Sheet 20': '4E. RMD Audit',
    'Sheet 21': '4D. Quality Control',
    'Sheet 22': '4G. Glossary',
    'Sheet 23': '4F. Methodology',
    'Sheet 24': '2B. Asset Allocation',
    'Sheet 25': '4C. Account Reconciliation',
    'Sheet 26': 'Workbook Warnings',
}

CSV_LABEL_REPLACEMENTS = {
    'Plan Data CSV': 'database-backed Plan Data',
    'stored in database-backed Plan Data': 'stored in database-backed Plan Data',
    'CSV Current': 'Current database setting',
    'CSV:': 'App setting:',
    'set in CSV': 'configured in the app',
    'set in client data CSV': 'configured in the app',
    'client_assets.csv': 'Plan Data import/export',
    'client_holdings.csv': 'holdings data',
    'All CSV scenarios': 'All configured scenarios',
    'CSV scenarios': 'configured scenarios',
    'CSV policy rows': 'configured policy rows',
    'CSV Forced Actions': 'configured Forced Actions',
    'reasonable salary $60K on $290K income': 'reasonable salary $60K on $290K income',
    'Required ($60,000 set in CSV)': 'Required ($60,000 configured in the app)',
    'Set enabled:TRUE in [DAF][Settings] of CSV': 'Enable DAF in Plan Data / System',
    'add enabled:TRUE to CSV': 'enable in Plan Data / System',
    'per CSV': 'per configured',
    'CSV settings:': 'Configured settings:',
    'expert CSV assumptions': 'expert import assumptions',
}


def _used_row(ws):
    for row in range(ws.max_row, 0, -1):
        if any(ws.cell(row=row, column=col).value not in (None, '') for col in range(1, ws.max_column + 1)):
            return row
    return 1


def _copy_cell(src_cell, dst_cell):
    dst_cell.value = src_cell.value
    if src_cell.has_style:
        dst_cell._style = copy(src_cell._style)
    if src_cell.number_format:
        dst_cell.number_format = src_cell.number_format
    if src_cell.alignment:
        dst_cell.alignment = copy(src_cell.alignment)
    if src_cell.protection:
        dst_cell.protection = copy(src_cell.protection)
    if src_cell.hyperlink:
        dst_cell._hyperlink = copy(src_cell.hyperlink)
    if src_cell.comment:
        dst_cell.comment = copy(src_cell.comment)


def _copy_rows(src_ws, dst_ws, start_row, end_row, dst_start_row, max_col=None):
    max_col = max_col or src_ws.max_column
    for r in range(start_row, end_row + 1):
        dst_ws.row_dimensions[dst_start_row + r - start_row].height = src_ws.row_dimensions[r].height
        for ccol in range(1, max_col + 1):
            _copy_cell(src_ws.cell(row=r, column=ccol), dst_ws.cell(row=dst_start_row + r - start_row, column=ccol))
    for merged in list(src_ws.merged_cells.ranges):
        if merged.min_row >= start_row and merged.max_row <= end_row:
            dst_ws.merge_cells(
                start_row=dst_start_row + merged.min_row - start_row,
                start_column=merged.min_col,
                end_row=dst_start_row + merged.max_row - start_row,
                end_column=merged.max_col,
            )
    for col_letter, dim in src_ws.column_dimensions.items():
        dst_ws.column_dimensions[col_letter].width = dim.width


def _find_row_containing(ws, text):
    needle = str(text).lower()
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None and needle in str(cell.value).lower():
                return cell.row
    return None


def _delete_sheet_if_present(wb, name):
    if name in wb.sheetnames:
        wb.remove(wb[name])


def _hide_sheet_if_present(wb, name):
    if name in wb.sheetnames:
        wb[name].sheet_state = 'hidden'
        wb[name].sheet_properties.tabColor = SECTION_COLOR.get('H')


def _replace_text_refs(wb):
    text_replacements = dict(FINAL_SHEET_RENAMES)
    text_replacements.update(SHEET_NUM_LABEL_REPLACEMENTS)
    text_replacements.update(CSV_LABEL_REPLACEMENTS)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if not isinstance(val, str):
                    continue
                new_val = val
                for old, new in text_replacements.items():
                    new_val = new_val.replace(old, new)
                if new_val != val:
                    cell.value = new_val


def _build_plan_data_sheet(wb, c):
    """Create a clean System/Plan Data output sheet.

    Plan scope and system settings should not be duplicated inside Executive
    Summary. This sheet provides a read-only snapshot of the saved plan data
    used for the build and the workbook scope.
    """
    src_name = '1. Executive Summary' if '1. Executive Summary' in wb.sheetnames else '1A. Executive Summary'
    _delete_sheet_if_present(wb, '4A. Plan Scope')
    _delete_sheet_if_present(wb, '4A. Plan Data')
    ws = wb.create_sheet('4A. Plan Data')
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = SECTION_COLOR.get('4')
    section_title(ws, 1, '4A. Plan Data — PLAN DATA SNAPSHOT', 6, bg=SECTION_COLOR.get('4'))
    write_cell(ws, 3, 1, 'The workbook is a generated output. Edit plan data in the database-backed app; CSV remains an import/export utility for large tables only.', fg='666666')
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=6)

    r = 5
    write_hdr(ws, r, 1, 'Plan data item', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Value', DGRAY, WHITE)
    write_hdr(ws, r, 3, 'Notes', DGRAY, WHITE, span=4)
    r += 1
    labels = ['Plan Prepared', 'Clients', 'Residence State', 'Plan Horizon', 'Statutory Version', 'Workbook Pricing Source']
    src = wb[src_name] if src_name in wb.sheetnames else None
    for label in labels:
        value = ''
        if src is not None:
            row = _find_row_containing(src, label)
            if row:
                value = src.cell(row=row, column=2).value
        write_cell(ws, r, 1, label)
        write_cell(ws, r, 2, value)
        write_cell(ws, r, 3, 'Source: saved plan snapshot used for this workbook build')
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
        r += 1

    r += 1
    write_hdr(ws, r, 1, 'Section', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Sheet', DGRAY, WHITE)
    write_hdr(ws, r, 3, 'Purpose', DGRAY, WHITE, span=4)
    r += 1
    purposes = {
        '1A. Executive Summary': 'plan-level findings, recommendations, and strategy narrative',
        '1B. Net Worth': 'net-worth projection report',
        '1C. Cash Flow': 'annual cash-flow report',
        '1D. Balance Sheet': 'current household balance sheet',
        '1E. Charts': 'visual report dashboard',
        '1F. Lifetime Taxes': 'tax projection report',
        '2A. Roth Conversion': 'Roth conversion optimizer',
        '2B. Asset Allocation': 'asset allocation and rebalancing optimizer',
        '2C. State Residency': 'state residency optimizer',
        '2D. Social Security': 'Social Security claiming optimizer',
        '2E. S-Corp vs LLC': 'entity strategy optimizer',
        '2F. Charitable Giving': 'charitable giving optimizer',
        '2G. Estate & Legacy Planning': 'estate and legacy optimizer',
        '2H. Planning Levers': 'interactive sensitivity dashboard for TNW and probability-of-success levers',
        '3A. Monte Carlo': 'probability-of-success and market stress testing',
        '3B. Survivor': 'survivor stress test',
        '3C. LTC + Life Insurance': 'combined protection stress test',
        '4A. Plan Data': 'database-backed plan snapshot and workbook scope',
        '4B. Assumptions': 'model assumptions and tax-law inputs',
        '4C. Account Reconciliation': 'account-level reconciliation and data checks',
        '4D. Quality Control': 'validation checks and workbook warnings',
        '4E. RMD Audit': 'required minimum distribution audit',
        '4F. Methodology': 'model methodology and rerun notes',
        '4G. Glossary': 'terms and definitions',
    }
    for area in WORKBOOK_SECTION_LAYOUT:
        for sheet_name in area.get('sheets', []):
            write_cell(ws, r, 1, area.get('section'))
            write_cell(ws, r, 2, sheet_name)
            write_cell(ws, r, 3, purposes.get(sheet_name, ''))
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
            r += 1
    for col, width in {'A':18,'B':24,'C':28,'D':10,'E':10,'F':10}.items():
        ws.column_dimensions[col].width = width


def _build_feature_toggle_sheet(wb, c):
    _delete_sheet_if_present(wb, '4D. System Setting')
    return


def _extract_scorp_sheet(wb):
    if '9. Retirement Strategy' not in wb.sheetnames:
        return
    src = wb['9. Retirement Strategy']
    _delete_sheet_if_present(wb, '2E. S-Corp vs LLC')
    ws = wb.create_sheet('2E. S-Corp vs LLC')
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = SECTION_COLOR.get('2')
    start = _find_row_containing(src, 'S-CORPORATION vs. LLC') or 25
    end = min(_used_row(src), start + 15)
    _copy_rows(src, ws, start, end, 1, max_col=src.max_column)
    if ws['A1'].value:
        ws['A1'].value = 'S-CORP vs LLC — ENTITY COMPARISON'
    for col in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col)].width = src.column_dimensions[get_column_letter(col)].width or 16


def _merge_strategy_into_executive_summary(wb):
    if '1. Executive Summary' not in wb.sheetnames or '9. Retirement Strategy' not in wb.sheetnames:
        return
    dst = wb['1. Executive Summary']
    src = wb['9. Retirement Strategy']
    # Merge retirement strategy/IPS/risk narrative into Executive Summary, but
    # move the entity comparison to the dedicated S-Corp vs LLC optimizer sheet.
    src_end = (_find_row_containing(src, 'S-CORPORATION vs. LLC') or 25) - 2
    src_end = max(1, min(src_end, _used_row(src)))
    dst_start = _used_row(dst) + 3
    _copy_rows(src, dst, 1, src_end, dst_start, max_col=src.max_column)


def _merge_asset_location_into_allocation(wb):
    if '4. Asset Allocation' not in wb.sheetnames or '24. Asset Location' not in wb.sheetnames:
        return
    dst = wb['4. Asset Allocation']
    src = wb['24. Asset Location']
    dst_start = _used_row(dst) + 3
    _copy_rows(src, dst, 1, _used_row(src), dst_start, max_col=src.max_column)


def _merge_ltc_into_life_insurance(wb):
    if '19. Life Insurance' not in wb.sheetnames or '17. LTC Stress Test' not in wb.sheetnames:
        return
    dst = wb['19. Life Insurance']
    src = wb['17. LTC Stress Test']
    dst['A1'].value = 'COMBINED LTC + LIFE INSURANCE ANALYSIS'
    dst_start = _used_row(dst) + 3
    _copy_rows(src, dst, 1, _used_row(src), dst_start, max_col=src.max_column)


def _rename_final_sheets(wb):
    for old, new in FINAL_SHEET_RENAMES.items():
        if old in wb.sheetnames:
            _delete_sheet_if_present(wb, new)
            wb[old].title = new


def apply_final_workbook_structure(wb, c):
    """Merge, relabel, and hide legacy build sheets into the final workbook tab model."""
    _build_plan_data_sheet(wb, c)
    _extract_scorp_sheet(wb)
    _merge_strategy_into_executive_summary(wb)
    _merge_asset_location_into_allocation(wb)
    _merge_ltc_into_life_insurance(wb)
    _delete_sheet_if_present(wb, '4D. System Setting')
    _rename_final_sheets(wb)
    _replace_text_refs(wb)

    if '4D. Quality Control' in wb.sheetnames and '26. Workbook Warnings' in wb.sheetnames:
        qc_ws = wb['4D. Quality Control']
        warn_ws = wb['26. Workbook Warnings']
        dst_start = _used_row(qc_ws) + 3
        _copy_rows(warn_ws, qc_ws, 1, _used_row(warn_ws), dst_start, max_col=warn_ws.max_column)
        qc_ws.cell(row=dst_start, column=1).value = 'WORKBOOK WARNINGS — Consistency, Staleness, and Advisor Review'
        qc_ws.cell(row=dst_start, column=1).font = body_font(bold=True, color='FFFFFF')
        qc_ws.cell(row=dst_start, column=1).fill = PatternFill('solid', fgColor=SECTION_COLOR.get('4'))
        _delete_sheet_if_present(wb, '26. Workbook Warnings')
    for legacy in ['9. Retirement Strategy', '17. LTC Stress Test', '24. Asset Location']:
        _delete_sheet_if_present(wb, legacy)
    for hidden in ['16. Scenario Analysis']:
        _hide_sheet_if_present(wb, hidden)

def _active_plan_data_section_count(data):
    """Count non-system planning sections present in the active backend."""
    system_sections = {
        "Market Pricing",
        "Plan Settings",
        "Asset Class Assumptions",
        "Asset Correlations",
        "System",
        "Rebalancing",
    }
    return sum(1 for sec, subs in (data or {}).items() if sec not in system_sections and bool(subs))


def _ensure_active_plan_data_loaded(data, config_meta):
    """Fail before expensive workbook work when the active backend has no plan.

    Newer UI builds use the saved server working copy/SQLite backend, so the
    old existence check for input/client_data.csv was too narrow. A package can
    be database-backed, split-file backed, or CSV-backed; the invariant is that
    load_active_config() must produce at least one real planning section.
    """
    if _active_plan_data_section_count(data) > 0:
        return
    backend = str((config_meta or {}).get("backend") or "active backend")
    path = str((config_meta or {}).get("path") or "")
    raise FileNotFoundError(
        "No active Plan Data was available to the build. Load or save Plan Data, "
        "then build again. The build checked the active " + backend +
        (f" source at {path}." if path else ".")
    )

def main():
    import os as _os
    base_dir = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

    _os.makedirs(_os.path.join(base_dir, 'output'), exist_ok=True)

    print('Loading active configuration...')
    data, config_meta = load_active_config()
    _ensure_active_plan_data_loaded(data, config_meta)
    workspace_id = sanitize_id(config_meta.get('workspace_id', 'local'))
    client_id = sanitize_id(config_meta.get('client_id', workspace_id))
    output_path_dir = workspace_output_dir(workspace_id)
    _os.makedirs(output_path_dir, exist_ok=True)
    out_path  = _os.path.join(str(output_path_dir), 'retirement_plan.xlsx')
    html_path = _os.path.join(str(output_path_dir), 'retirement_dashboard.html')

    print(f"Using config backend: {config_meta.get('backend')} ({config_meta.get('path')})")
    print('Local plan: single-user desktop mode')
    print(f'Output directory: {output_path_dir}')
    print(f"Live market pricing enabled: {pricing_diagnostics().get('live_enabled')}")

    url_template = ''

    print('Parsing client data and normalizing engine contract...')
    c = prepare_config_from_sectioned_data(data, url_template, optimize_roth=True)
    try:
        from ..ytd_projection_blend import compute_current_year_overrides
        c.update(compute_current_year_overrides(c, workspace_input_dir(workspace_id), today=datetime.date.today()))
        if c.get('ytd_blend_applied', {}).get('flows_blended'):
            print(f"  Current year ({c['ytd_blend_applied']['current_year']}) blends YTD actuals through {c['ytd_blend_applied'].get('ytd_end')} with projected remainder.")
    except Exception as exc:
        print(f'Warning: YTD actuals blend for the current year failed (falling back to full-year projection): {exc}')
    _ropt = c.get('roth_optimization', {}) or {}
    if _ropt:
        print(f"  Selected Roth strategy: {_ropt.get('selected_label', c.get('roth_policy'))}")
    print(f'  Config contract: {c.get("config_contract_version")} from {c.get("config_contract_source")}')
    print(f'  Plan horizon: {c["plan_start"]} – {c["plan_end"]}')
    print(f'  ETF prices: {PRICE_CACHE}')
    write_pricing_diagnostics(_os.path.join(str(output_path_dir), 'pricing_diagnostics.json'), print_report=True)

    print('Running projection, validation, and Monte Carlo...')
    # User-facing builds must always produce artifacts, even when the plan has
    # unfunded cash gaps.  The validation summary is preserved in the workbook
    # and plan_summary.json so the user can review/fix the issue instead of
    # being blocked by a hard release gate.  Keep hard-gate behavior available
    # through run_projection_artifacts(..., enforce_release_gate=True) for tests
    # or CI-style release checks.
    artifacts = run_projection_artifacts(c, run_mc=True, enforce_release_gate=False)
    c = artifacts.config
    rows = artifacts.rows
    mc_data = artifacts.mc_data
    validation_summary = artifacts.validation
    print(f'  {len(rows)} rows; validation FAIL={validation_summary.get("fail_count")} WARN={validation_summary.get("warn_count")}')

    print('Building workbook...')
    wb = Workbook()
    wb.remove(wb.active)

    # ── Create all named sheets ───────────────────────────────────────────────
    # Sheet 3b (Holdings Detail) removed — holdings are in Sheet 3 Balance Sheet inline
    sheets = {}
    for name, _ in V5_LAYOUT:
        ws = wb.create_sheet(name)
        sheets[name] = ws

    print('  Sheet 1 — Executive Summary')
    build_sheet1(sheets['1. Executive Summary'], c, rows, mc_data)
    print('  Sheet 2 — Assumptions')
    build_sheet2(sheets['2. Assumptions'], c, rows)
    print('  Sheet 3 — Balance Sheet')
    build_sheet3(sheets['3. Balance Sheet'], c, rows)
    print('  Sheet 4 — Asset Allocation')
    build_sheet4(sheets['4. Asset Allocation'], c)
    print('  Sheet 5 — Net Worth Projection')
    build_sheet5(sheets['5. Net Worth Projection'], c, rows)
    print('  Sheet 6 — Cash Flow Projection')
    build_sheet6(sheets['6. Cash Flow Projection'], c, rows)
    print('  Sheet 7 — Lifetime Tax')
    build_sheet7(sheets['7. Lifetime Tax'], c, rows)
    print('  Sheet 8 — Charts Dashboard')
    build_sheet8(sheets['8. Charts Dashboard'], c, rows, mc_data)
    print('  Sheet 9 — Retirement Strategy')
    build_sheet9(sheets['9. Retirement Strategy'], c, rows)
    print('  Sheet 10 — Social Security')
    build_sheet10(sheets['10. Social Security'], c, rows)
    print('  Sheet 11 — Roth Conversion')
    build_sheet11(sheets['11. Roth Conversion'], c, rows)
    print('  Sheet 12 — Charitable Giving')
    build_sheet12(sheets['12. Charitable Giving'], c, rows)
    print('  Sheet 13 — State Residency')
    build_sheet13(sheets['13. State Residency'], c, rows)
    print('  Sheet 14 — Estate Plan')
    build_sheet14(sheets['14. Estate Plan'], c, rows)
    print('  Sheet 27 — Planning Levers')
    build_sheet27_planning_levers(sheets['27. Planning Levers'], c, rows, mc_data)
    print('  Sheet 15 — Monte Carlo')
    build_sheet15(sheets['15. Market-Luck Stress Test'], c, rows, mc_data)
    print('  Sheet 16 — Scenario Analysis')
    build_sheet16(sheets['16. Scenario Analysis'], c, rows)
    print('  Sheet 17 — LTC Stress Test')
    build_sheet17(sheets['17. LTC Stress Test'], c, rows)
    print('  Sheet 18 — Survivor Stress Test')
    build_sheet18(sheets['18. Survivor Stress Test'], c, rows)
    print('  Sheet 19 — Life Insurance')
    build_sheet19(sheets['19. Life Insurance'], c)
    print('  Sheet 20 — RMD Audit')
    build_sheet20(sheets['20. RMD Audit'], c, rows)
    print('  Sheet 22 — Glossary')
    build_sheet22(sheets['22. Glossary'])
    print('  Sheet 23 — Methodology')
    build_sheet23(sheets['23. Methodology'], c)
    build_sheet24(sheets['24. Asset Location'], c, rows)
    print('  Sheet 25 — Account Reconciliation')
    build_sheet25(sheets['25. Account Reconciliation'], c, rows)
    print('  Sheet 28 — Core Spending Breakdown')
    build_sheet_core_spending(sheets['28. Core Spending'], c)
    print('  Sheet 29 — Spending Summary (taxonomy)')
    build_sheet_spending_summary(sheets['29. Spending Summary'], c)
    if '26. Workbook Warnings' in sheets:
        print('  Sheet 26 — Workbook Warnings')
        build_sheet26_workbook_warnings(sheets['26. Workbook Warnings'], c, rows)

    # QC last
    print('  Sheet 21 — Quality Control')
    qc('21. Quality Control', 'QC sheet itself has checks', True, f'{len(QC_CHECKS)} checks')
    build_sheet21(sheets['21. Quality Control'], QC_CHECKS, rows, c)

    # ── Final user-facing workbook layout ───────────────────────────────────
    # Build-time sheets use legacy stable names.  After all formulas/charts/QC
    # have been built, merge/rename/reorder into the user-facing numbered
    # section tabs requested by the workbook UI refactor.
    apply_final_workbook_structure(wb, c)

    # ── Numbered section navigation, tab colours, and sheet order ─────────────
    # Excel has a flat sheet-tab model, so the workbook mirrors the app's top
    # areas with visible divider tabs and lettered sheets ordered immediately
    # after each divider.  Excel/PDF remain output-only surfaces.
    for area in WORKBOOK_SECTION_LAYOUT:
        section_name = area['section']
        if section_name not in wb.sheetnames:
            wb.create_sheet(section_name)
        build_workbook_section_divider(wb[section_name], area)

    FULL_LAYOUT = []
    for area in WORKBOOK_SECTION_LAYOUT:
        FULL_LAYOUT.append((area['section'], area['code']))
        FULL_LAYOUT.extend((sheet_name, area['code']) for sheet_name in area['sheets']        )

    # Reorder sheets to match the FULL_LAYOUT order
    ordered_names = [name for name, _ in FULL_LAYOUT if name in wb.sheetnames]
    remainder = [s for s in wb.sheetnames if s not in set(ordered_names)]
    final_order = ordered_names + remainder

    for idx, name in enumerate(final_order):
        if name in wb.sheetnames:
            wb.move_sheet(name, offset=idx - wb.sheetnames.index(name))

    # Apply tab colours by section code
    for sheet_name, code in FULL_LAYOUT:
        if sheet_name in wb.sheetnames:
            color = SECTION_COLOR.get(code, NAVY)
            wb[sheet_name].sheet_properties.tabColor = color

    optimize_workbook_layout(wb)

    # Save workbook
    print(f'Saving workbook to {out_path}')
    wb.save(out_path)
    print(f'Workbook saved: {out_path}')

    # Build the printable PDF report (landscape, minimal margins) alongside the
    # workbook so the "Download PDF" button has an artifact to serve. Wrapped in
    # try/except: the .xlsx is the canonical deliverable, so a PDF failure must
    # not fail the whole build. Without this call retirement_plan.pdf is never
    # written and /api/pdf 404s ("run build first").
    pdf_path = _os.path.join(str(output_path_dir), 'retirement_plan.pdf')
    try:
        build_enterprise_pdf(c, rows, mc_data, out_path=pdf_path)
        print(f'PDF report saved: {pdf_path}')
    except Exception as _pdf_err:  # noqa: BLE001 - PDF is best-effort, never fatal
        print(f'WARNING: PDF report generation failed ({_pdf_err}); workbook build continues.')

    # Build offline HTML dashboard from the workbook and projection rows.
    build_html_dashboard(out_path, html_path, rows, c)
    print(f'HTML dashboard saved: {html_path}')

    # Write Results Explorer model
    results_model_path = _os.path.join(str(output_path_dir), RESULTS_MODEL_FILENAME)
    write_result_explorer_model(results_model_path, c, rows, mc_data)
    print(f'Results explorer model written: {results_model_path}')

    # Write plan_summary.json so the build server can verify success and display KPIs.
    # KPI computation and file write are separated: if KPI math fails we still write
    # a minimal file (so the server recognises the build as complete); if the file
    # write itself fails we propagate so the caller gets a real error message.
    import json as _json
    build_id = _os.environ.get('RETIREMENT_SYSTEM_BUILD_ID', '')
    terminal = rows[-1] if rows else {}
    passed = sum(1 for _, _, status, _ in QC_CHECKS if status == 'PASS')
    qc_result = f'QC: {passed} / {len(QC_CHECKS)} PASS'
    summary_data: dict = {
        'build_id': build_id,
        'qc_result': qc_result,
        'h_name': str(c.get('h_name') or 'Member 1'),
        'w_name': str(c.get('w_name') or 'Member 2'),
        'h_nick': str(c.get('h_nick') or c.get('h_name') or 'Member 1'),
        'w_nick': str(c.get('w_nick') or c.get('w_name') or 'Member 2'),
        'terminal_nw': 0.0,
        'terminal_pretax_nw': 0.0,
        'terminal_roth_nw': 0.0,
        'lifetime_tax': 0.0,
        'total_roth_conversions': 0.0,
        'mc_success': 0.0,
        'after_tax_terminal_nw': 0.0,
        'after_tax_terminal_net_worth': 0.0,
        'terminal_deferred_pretax_tax': 0.0,
        'terminal_deferred_taxable_cap_gain_tax': 0.0,
        'terminal_taxable_unrealized_gain_est': 0.0,
        'terminal_taxable_basis_est': 0.0,
        'terminal_deferred_tax_total': 0.0,
        'terminal_estate_tax': 0.0,
        'post_tax_inheritance': 0.0,
        'validation_fail_count': int((validation_summary or {}).get('fail_count', 0) or 0),
        'validation_warn_count': int((validation_summary or {}).get('warn_count', 0) or 0),
        'validation_first_fail': (validation_summary or {}).get('first_fail'),
    }
    try:
        after_tax_kpis = estimate_after_tax_terminal_net_worth(c, terminal)
        lifetime_tax = sum(float(r.get('total_tax', 0.0) or 0.0) for r in rows)
        total_roth_conversions = sum(float(r.get('roth_conv', 0.0) or 0.0) for r in rows)
        mc_success = float((mc_data or {}).get('success_rate', 0.0) or 0.0)
        summary_data.update({
            'terminal_nw': float(terminal.get('total_nw', 0.0) or 0.0),
            'terminal_pretax_nw': float(terminal.get('pretax_nw', 0.0) or 0.0),
            'terminal_roth_nw': float(terminal.get('roth_nw', 0.0) or 0.0),
            'lifetime_tax': lifetime_tax,
            'total_roth_conversions': total_roth_conversions,
            'mc_success': mc_success,
            'after_tax_terminal_nw': float(after_tax_kpis.get('after_tax_terminal_nw', 0.0) or 0.0),
            'after_tax_terminal_net_worth': float(after_tax_kpis.get('after_tax_terminal_net_worth', 0.0) or 0.0),
            'terminal_deferred_pretax_tax': float(after_tax_kpis.get('terminal_deferred_pretax_tax', 0.0) or 0.0),
            'terminal_deferred_taxable_cap_gain_tax': float(after_tax_kpis.get('terminal_deferred_taxable_cap_gain_tax', 0.0) or 0.0),
            'terminal_taxable_unrealized_gain_est': float(after_tax_kpis.get('terminal_taxable_unrealized_gain_est', 0.0) or 0.0),
            'terminal_taxable_basis_est': float(after_tax_kpis.get('terminal_taxable_basis_est', 0.0) or 0.0),
            'terminal_deferred_tax_total': float(after_tax_kpis.get('terminal_deferred_tax_total', 0.0) or 0.0),
            'terminal_estate_tax': float(after_tax_kpis.get('terminal_estate_tax', 0.0) or 0.0),
            'post_tax_inheritance': float(after_tax_kpis.get('post_tax_inheritance', 0.0) or 0.0),
        })
    except Exception as _kpi_exc:
        print(f'Warning: KPI computation for plan summary failed (defaults used): {_kpi_exc}')
    summary_out = _os.path.join(str(output_path_dir), 'plan_summary.json')
    with open(summary_out, 'w', encoding='utf-8') as _sf:
        _json.dump(summary_data, _sf, indent=2)
    print(f'Plan summary written: {summary_out}')

    snapshot = write_build_snapshot(
        output_path_dir,
        build_id=build_id,
        plan_input_fingerprint=_build_plan_input_fingerprint(base_dir, config_meta),
        summary=summary_data,
        system_config_path=_os.path.join(base_dir, 'system_config.csv'),
        pricing_diagnostics_path=_os.path.join(str(output_path_dir), 'pricing_diagnostics.json'),
        sqlite_db_path=(config_meta or {}).get('sqlite_db') or (config_meta or {}).get('path'),
    )
    print(f'Build snapshot written: {_os.path.join(str(output_path_dir), SNAPSHOT_FILENAME)} ({snapshot.get("artifact_count", 0)} artifacts)')

    package = write_report_package(
        output_path_dir,
        build_id=build_id,
        summary=summary_data,
        build_snapshot=snapshot,
    )
    print(f'Report package written: {_os.path.join(str(output_path_dir), REPORT_PACKAGE_FILENAME)} ({package.get("artifact_count", 0)} artifacts)')

    print('Build complete.')
    return out_path


if __name__ == '__main__':
    main()
