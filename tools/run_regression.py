#!/usr/bin/env python3
"""
Regression test suite for the Retirement Planner desktop app.

Run from the project root:
    python tools/run_regression.py

Each check represents a fix that was previously regressed or is critical
infrastructure. A failure here means something that once worked has broken.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    status = PASS if ok else FAIL
    print(f"  {status}  {name}" + (f"  - {detail}" if detail else ""))


def heading(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(8, 78 - len(title)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def file_text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def js_syntax_ok(rel: str) -> bool:
    r = subprocess.run(["node", "--check", str(ROOT / rel)], capture_output=True)
    return r.returncode == 0


def py_syntax_ok(rel: str) -> bool:
    try:
        ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        return True
    except SyntaxError:
        return False


def contains(text: str, *patterns: str) -> bool:
    return all(p in text for p in patterns)


def _norm_code(s: str) -> str:
    """Collapse whitespace, unify quote style, and drop trailing commas.

    Many guards below assert that a snippet of source code *exists*, pinning its
    exact character shape. Running the frontend through a prettier-style
    formatter (single->double quotes, spaces around operators, multi-line
    arrays/objects with trailing commas) rewrites that shape without changing
    behavior, which used to break these guards en masse. Normalizing both the
    haystack and the needle keeps the guards meaningful (the code must still be
    present) without going stale on every reformat.
    """
    s = re.sub(r"\s+", "", s).replace('"', "'")
    return s.replace(",]", "]").replace(",}", "}")


def has_code(text: str, *snippets: str) -> bool:
    """Like ``contains`` but tolerant of formatting differences -- use for
    'this exact code shape exists' guards; use ``in``/``contains`` for guards on
    identifiers or string literals where formatting can't vary."""
    norm = _norm_code(text)
    return all(_norm_code(p) in norm for p in snippets)


# ---------------------------------------------------------------------------
# 1. Syntax checks
# ---------------------------------------------------------------------------
heading("Syntax checks")

for js_file in [
    "frontend/js/dashboard.js",
    "frontend/js/spending_dashboard.js",
]:
    check(f"JS syntax: {js_file}", js_syntax_ok(js_file))

for py_file in [
    "src/desktop_api.py",
    "src/desktop_app.py",
    "src/server/plan_routes.py",
    "src/detailed_results.py",
    "src/ytd_tracking.py",
    "src/data_io.py",
    "src/reporting/sheets_projection.py",
    "src/projection_stages/deterministic_engine.py",
]:
    if (ROOT / py_file).exists():
        check(f"PY syntax: {py_file}", py_syntax_ok(py_file))
    else:
        check(f"PY syntax: {py_file}", False, "file not found")

# ---------------------------------------------------------------------------
# 2. Boot sequence (dashboard.js)
# ---------------------------------------------------------------------------
heading("Boot sequence")
dash = file_text("frontend/js/dashboard.js")
nav = file_text("frontend/js/navigation.js")
reports_ui = file_text("frontend/js/reports_ui.js")
# Detail-table/chart rendering (detailCurrencyK, niceTickRange,
# renderDetailTableForCols, detailChartColor, etc.) was extracted out of
# dashboard.js into reports_ui.js; checks below search both so a further
# move between the two doesn't reintroduce a stale-location false failure.
dash_reports = dash + reports_ui

check("Boot: wireStepNavigation() called", "wireStepNavigation();" in dash)
check("Boot: setAppControls(false) called", "setAppControls(false);" in dash)
check("Boot: renderMain() called at boot", re.search(r"setAppControls\(false\).*?renderMain\(\)", dash, re.DOTALL) is not None)
check("Boot: checkAppStatus(true) called", "checkAppStatus(true)" in dash)
check("Boot: setInterval checkAppStatus", "setInterval" in dash and "checkAppStatus" in dash)
check("Boot: appReady variable used", "appReady" in dash)

# ---------------------------------------------------------------------------
# 3. Exit/shutdown functions
# ---------------------------------------------------------------------------
heading("Exit & shutdown")
check("Exit: openExitModal defined", "function openExitModal()" in dash)
check("Exit: closeExitModal defined", "function closeExitModal()" in dash)
check("Exit: shutdownAndClose defined", "async function shutdownAndClose()" in dash)
check("Exit: saveAndExit defined", "async function saveAndExit()" in dash)
check("Exit: discardAndExit defined", "async function discardAndExit()" in dash)
check("Exit: exitApp defined", "async function exitApp()" in dash)
check("Exit: beforeunload handler present", "beforeunload" in dash)

# ---------------------------------------------------------------------------
# 4. Download & build functions
# ---------------------------------------------------------------------------
heading("Download & build")
check("Download: downloadFile defined", "function downloadFile(url)" in dash)
check("Download: downloadWithBuild defined", "async function downloadWithBuild(" in dash)
check("Download: runBuild defined", "async function runBuild(" in dash)
check("Download: buildWithDesktopProgress defined", "async function buildWithDesktopProgress(" in dash)

# ---------------------------------------------------------------------------
# 5. Housing screen
# ---------------------------------------------------------------------------
heading("Housing screen")
check("Housing: renderNextHousingStepSection defined", "function renderNextHousingStepSection(" in dash)
check("Housing: PURCHASE_FIRST has state/city_type/population_size",
      has_code(dash, "PURCHASE_FIRST=['state','city_type','population_size']"))
check("Housing: RENT_FIRST has only state",
      has_code(dash, "RENT_FIRST=['state']"))
check("Housing: RENT_REST has no city_type/population_size/hoa",
      has_code(dash, "RENT_REST=['start_year','end_year','monthly_rent','insurance_annual','utilities_annual']"))
check("Housing: Estimate button references 3BR/2BA/40x40",
      "40\u00d740 ft backyard" in dash or "40x40 ft backyard" in dash)
check("Housing: city_type/population_size excluded from current home",
      "_CURRENT_HOME_EXCL" in dash and "city_type" in dash and "population_size" in dash)
check("Housing: estimateHousingFromState sends city_type+population",
      has_code(dash, "city_type:cityTypeVal", "population_size:parseInt"))
check("Housing: renderSpendingHousing defined", "function renderSpendingHousing()" in dash)

# ---------------------------------------------------------------------------
# 6. Model-Managed section (spending_dashboard.js)
# ---------------------------------------------------------------------------
heading("Spending dashboard")
spend = file_text("frontend/js/spending_dashboard.js")
check("Spending: renderModelManaged defined", "function renderModelManaged(" in spend)
check("Spending: MM_LABELS dynamic map defined (replaces fixed HOUSING/HEALTHCARE lists)", "MM_LABELS" in spend and "housing:'Housing'" in spend)
check("Spending: renderModelManaged uses MM_LABELS loop", "MM_LABELS" in spend and "typeKey" in spend)
check("Spending: renderBusinessSection defined", "function renderBusinessSection(" in spend)
check("Spending: renderUnmappedWarning defined", "function renderUnmappedWarning(" in spend)
check("Spending: renderSpendingDashboard defined", "function renderSpendingDashboard()" in spend)
check("Spending: renderSpendingBars defined", "function renderSpendingBars(" in spend)
check("Spending: renderSpendingMonthly defined", "function renderSpendingMonthly(" in spend)
check("Spending: loadSpendingDashboard defined", "function loadSpendingDashboard(" in spend)
check("Spending: /api/spending/dashboard endpoint used",
      "'/api/spending/dashboard'" in spend)

# ---------------------------------------------------------------------------
# 7. Detailed Results / Retirement Plan Workbook
# ---------------------------------------------------------------------------
heading("Retirement Plan Workbook (Detailed Results)")
check("WorkbookPage: title renamed in STEPS",
      has_code(dash, "title:'Results'"))
check("WorkbookPage: resultDisplayName defined", "function resultDisplayName(" in dash_reports)
check("WorkbookPage: loadDetailedResults defined", "function loadDetailedResults(" in dash or "loadDetailedResults" in dash)
check("WorkbookPage: setDetailedResultSheet defined", "function setDetailedResultSheet(" in dash)
check("WorkbookPage: all visible sheets returned (no 1A-1F filter)",
      "_REDUNDANT_PREFIXES" not in file_text("src/detailed_results.py"))

# ---------------------------------------------------------------------------
# 8. YTD / Mapped Account
# ---------------------------------------------------------------------------
heading("YTD tracking")
ytd_text = file_text("src/ytd_tracking.py")
check("YTD: annuity_pension_accounts defined", "def annuity_pension_accounts(" in ytd_text)
check("YTD: annuity_pension_account_values defined", "def annuity_pension_account_values(" in ytd_text)
check("YTD: ytd_summary returns annuity_pension_accounts",
      '"annuity_pension_accounts"' in ytd_text or "'annuity_pension_accounts'" in ytd_text)

# ---------------------------------------------------------------------------
# 9. Cash Flow sheet headings
# ---------------------------------------------------------------------------
heading("Cash Flow sheet")
sheets_text = file_text("src/reporting/sheets_projection_cashflow.py")
check("CashFlow: 'Housing' column header", "'Housing'" in sheets_text or '"Housing"' in sheets_text)
check("CashFlow: 'Wellness' column header", "'Wellness'" in sheets_text or '"Wellness"' in sheets_text)
check("CashFlow: 'Travel' column header (renamed from Vacations)", "'Travel'" in sheets_text or '"Travel"' in sheets_text)

# ---------------------------------------------------------------------------
# 10. Detailed Results backend prefixes
# ---------------------------------------------------------------------------
heading("Detailed Results backend")
dr_text = file_text("src/detailed_results.py")
check("DR: _visible_worksheets defined", "def _visible_worksheets(" in dr_text)
check("DR: all visible sheets returned (no prefix filter)", "_REDUNDANT_PREFIXES" not in dr_text)

# ---------------------------------------------------------------------------
# 10b. Column group collapse/expand UI
# ---------------------------------------------------------------------------
check("ColGroups: renderDetailTableForCols defined", "function renderDetailTableForCols(" in dash_reports)
check("ColGroups: renderDetailedResultTable marks collapsible column-group headers", "detail-col-group-th" in dash_reports)
check("ColGroups: setDetailColGroupOpen defined", "setDetailColGroupOpen" in dash)

# ---------------------------------------------------------------------------
# 11. Desktop API
# ---------------------------------------------------------------------------
heading("Desktop API")
api_text = file_text("src/desktop_api.py")
check("DesktopAPI: show_save_dialog defined", "def show_save_dialog(" in api_text)
check("DesktopAPI: show_open_dialog defined", "def show_open_dialog(" in api_text)
check("DesktopAPI: binary download handler", "os.startfile" in api_text or "subprocess" in api_text)

# ---------------------------------------------------------------------------
# 12. valueKind: year fields not currency
# ---------------------------------------------------------------------------
heading("Field type logic")
check("valueKind: _year suffix returns number before currency check",
      has_code(dash, "l.endsWith('_year'))return 'number'"))

# ---------------------------------------------------------------------------
# 13. humanLabel overrides
# ---------------------------------------------------------------------------
heading("humanLabel overrides")
check("humanLabel: HOA Annual Fee", has_code(dash, "'HOA Annual Fee'"))
check("humanLabel: Area Type", has_code(dash, "'Area Type'"))
check("humanLabel: Commission % for selling_cost_pct", has_code(dash, "'Commission %'"))

# ---------------------------------------------------------------------------
# 14. Plan file save / load routes
# ---------------------------------------------------------------------------
heading("Plan file routes")
pr_text = file_text("src/server/plan_routes.py")
check("PlanRoutes: /api/plan/save-as defined", '"/api/plan/save-as"' in pr_text)
check("PlanRoutes: /api/plan/load-file defined", '"/api/plan/load-file"' in pr_text)
check("PlanRoutes: plan_save_as WAL checkpoint", "wal_checkpoint" in pr_text)
check("PlanRoutes: plan_load_file checks file exists", "not src.exists()" in pr_text)

# ---------------------------------------------------------------------------
# 15. pywebview bridge
# ---------------------------------------------------------------------------
heading("PyWebView bridge")
bridge = file_text("frontend/js/pywebview_bridge.js")
check("Bridge: intercepts /api/ fetch calls", "/api/" in bridge)
check("Bridge: sets __is_desktop_app__", "__is_desktop_app__" in bridge)
check("Bridge: callBridge defined", "callBridge" in bridge)

# ---------------------------------------------------------------------------
# 16. Section 5 Workbook -- WP-A through WP-D regression checks
# ---------------------------------------------------------------------------
heading("Section 5: Retirement Plan Workbook -- WP-A/B/C/D")

# WP-A: detailCurrencyK sub-$1K values return plain dollar amount, not $0K
check(
    "WP-A: detailCurrencyK returns plain dollar for sub-$500 values (not $0K)",
    has_code(dash_reports, "Math.round(abs/1000)===0)return (neg?'-':'')+'$'+Math.round(abs)"),
)

# WP-B: niceTickRange function exists
check(
    "WP-B: niceTickRange function defined",
    "function niceTickRange(" in dash_reports,
)

# WP-B: niceTickRange returns an array
check(
    "WP-B: niceTickRange returns array via Array.from",
    "function niceTickRange(" in dash_reports and "Array.from" in dash_reports,
)

# WP-B: Bar/line chart y-axis ticks use niceTickRange (not hardcoded list)
check(
    "WP-B: stacked bar chart uses niceTickRange for y-axis ticks",
    has_code(dash_reports, "niceVals=niceTickRange(max)"),
)

# WP-C: y-axis label reads chart.y_label with fallback (not hardcoded string)
check(
    "WP-C: y-axis label uses chart.y_label with inferred fallback",
    has_code(dash_reports, "chart.y_label||detailInferYLabel(max)"),
)

# WP-C: Y-axis formatter branches on % / plain number / currency thresholds
check(
    "WP-C: y-axis formatter percent branch for max <= 1.5",
    has_code(dash_reports, "max<=1.5?(rawVal*100).toFixed(0)+'%'"),
)
check(
    "WP-C: y-axis formatter plain number branch for max <= 150",
    has_code(dash_reports, "max<=150?String(Math.round(rawVal))"),
)

# WP-D: Unknown chart types render .chart-type-note div (not a crash)
check(
    "WP-D: unknown chart type renders chart-type-note div",
    "chart-type-note" in dash_reports and "Chart type not yet supported" in dash_reports,
)

# WP-D: Column group first-group fix -- every group (including the first)
# renders with the same initial "collapsed" class; none is special-cased open.
check(
    "WP-D: column group headers all start collapsed, no first-group special case",
    'class="detail-col-group-th collapsed" data-group="${gi}"' in dash_reports,
)

# WP-D: setDetailColGroupOpen calls setTimeout(renderMain, 0) after state update
check(
    "WP-D: setDetailColGroupOpen defers renderMain via setTimeout",
    "setDetailColGroupOpen" in dash_reports and has_code(dash_reports, "setTimeout(renderMain,0)"),
)

# WP-D: renderDetailTableForCols adds title attribute to <td> elements
check(
    "WP-D: renderDetailTableForCols writes title= tooltip on each td",
    'title="${esc(String(' in dash_reports,
)

# WP-D: CVD-safe palette -- detailChartColor starts with #000000 (Wong palette)
check(
    "WP-D: detailChartColor uses Wong 8-color palette starting with #000000",
    has_code(dash_reports, "'#000000','#E69F00','#56B4E9','#009E73'"),
)

# ---------------------------------------------------------------------------
# Section 17 - Outstanding items sprint (P1/P2/P3)
# ---------------------------------------------------------------------------
check("P1-A8: spendingData=null after saveYtdTransactions success", has_code(dash, "spendingData=null"))
check("P1-A9: applySpendingForecast stale-data block present", "ytdTransactionsChanged||ytdAccountsChanged" in dash or "ytdTransactionsChanged || ytdAccountsChanged" in dash)
check("P1-B1: guarded setStep defined in navigation module", "function setStep(ctx,id)" in nav and "wireStepNavigation" in nav)
check("P1-B1: autosave steps list includes ytd_transactions", "'ytd_transactions'" in nav and "AUTOSAVE_STEPS" in nav)
check("P2-C1: down_payment valueKind override returns percent", has_code(dash, "norm(r.label)==='down_payment'") or has_code(dash, "norm(r?.label)==='down_payment'"))
check("P2-C1: humanLabel down_payment no trailing percent sign", "Down Payment '" not in dash)
check("P2-B2: /api/build/status endpoint defined", "/api/build/status" in file_text("src/server/workbook_routes.py") or "/api/build/status" in file_text("src/server/base_routes.py"))
check("P2-B2: startup lastBuildOk restore calls /api/build/status", has_code(dash, "api('/api/build/status')"))
check("P2-D19: bottom action row has Save Changes + Download Workbook", "Save Changes" in dash and "Download Workbook" in dash)
check("P2-B6: workbookNavOpened localStorage guard", "workbookNavOpened" in dash)
check("P3-B7: saveWorkbookViewState defined", "saveWorkbookViewState" in dash)
check("P3-B7: restoreWorkbookViewState defined", "restoreWorkbookViewState" in dash)
check("P3-B8: data-group attribute on detail-col-group-th headers", 'data-group="${gi}"' in dash_reports)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
heading("Summary")
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)
print(f"  {passed}/{total} passed  |  {failed} failed\n")

if failed:
    print("FAILED checks:")
    for name, ok, detail in results:
        if not ok:
            print(f"  x  {name}" + (f"  - {detail}" if detail else ""))
    import sys; sys.exit(1)
else:
    print("All regression checks passed.")
    import sys; sys.exit(0)
