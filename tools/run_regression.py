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
      "PURCHASE_FIRST=['state','city_type','population_size']" in dash)
check("Housing: RENT_FIRST has only state",
      "RENT_FIRST=['state']" in dash)
check("Housing: RENT_REST has no city_type/population_size/hoa",
      "RENT_REST=['start_year','end_year','monthly_rent','insurance_annual','utilities_annual']" in dash)
check("Housing: Estimate button references 3BR/2BA/40x40",
      "40\u00d740 ft backyard" in dash or "40x40 ft backyard" in dash)
check("Housing: city_type/population_size excluded from current home",
      "_CURRENT_HOME_EXCL" in dash and "city_type" in dash and "population_size" in dash)
check("Housing: estimateHousingFromState sends city_type+population",
      "city_type:cityTypeVal" in dash and "population_size:parseInt" in dash)
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
      "title:'Retirement Plan Workbook'" in dash)
check("WorkbookPage: resultDisplayName defined", "function resultDisplayName(" in dash)
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
sheets_text = file_text("src/reporting/sheets_projection.py")
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
# 10b. Column group <details> UI
# ---------------------------------------------------------------------------
check("ColGroups: renderDetailTableForCols defined", "function renderDetailTableForCols(" in dash)
check("ColGroups: renderDetailedResultTable uses <details>", "detail-col-group-section" in dash)
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
      "l.endsWith('_year'))return 'number'" in dash)

# ---------------------------------------------------------------------------
# 13. humanLabel overrides
# ---------------------------------------------------------------------------
heading("humanLabel overrides")
check("humanLabel: HOA Annual Fee", "'HOA Annual Fee'" in dash)
check("humanLabel: Area Type", "'Area Type'" in dash)
check("humanLabel: Commission % for selling_cost_pct", "'Commission %'" in dash)

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
    "Math.round(abs/1000)===0)return (neg?'-':'')+'$'+Math.round(abs)" in dash,
)

# WP-B: niceTickRange function exists
check(
    "WP-B: niceTickRange function defined",
    "function niceTickRange(" in dash,
)

# WP-B: niceTickRange returns an array
check(
    "WP-B: niceTickRange returns array via Array.from",
    "function niceTickRange(" in dash and "Array.from" in dash,
)

# WP-B: Bar/line chart y-axis ticks use niceTickRange (not hardcoded list)
check(
    "WP-B: stacked bar chart uses niceTickRange for y-axis ticks",
    "niceVals=niceTickRange(max)" in dash,
)

# WP-C: y-axis label reads chart.y_label with fallback (not hardcoded string)
check(
    "WP-C: y-axis label uses chart.y_label with inferred fallback",
    "chart.y_label||detailInferYLabel(max)" in dash,
)

# WP-C: Y-axis formatter branches on % / plain number / currency thresholds
check(
    "WP-C: y-axis formatter percent branch for max <= 1.5",
    "max<=1.5?(rawVal*100).toFixed(0)+'%'" in dash,
)
check(
    "WP-C: y-axis formatter plain number branch for max <= 150",
    "max<=150?String(Math.round(rawVal))" in dash,
)

# WP-D: Unknown chart types render .chart-type-note div (not a crash)
check(
    "WP-D: unknown chart type renders chart-type-note div",
    "chart-type-note" in dash and "Chart type not yet supported" in dash,
)

# WP-D: Column group first-group fix -- isOpen uses !== false (not gi===0)
check(
    "WP-D: column group isOpen guard uses !== false",
    "detailedColumnGroupsOpen[key]!==false" in dash,
)

# WP-D: setDetailColGroupOpen calls setTimeout(renderMain, 0) after state update
check(
    "WP-D: setDetailColGroupOpen defers renderMain via setTimeout",
    "setDetailColGroupOpen" in dash and "setTimeout(renderMain,0)" in dash,
)

# WP-D: renderDetailTableForCols adds title attribute to <td> elements
check(
    "WP-D: renderDetailTableForCols writes title= tooltip on each td",
    'title="${esc(String(' in dash,
)

# WP-D: CVD-safe palette -- detailChartColor starts with #000000 (Wong palette)
check(
    "WP-D: detailChartColor uses Wong 8-color palette starting with #000000",
    "'#000000','#E69F00','#56B4E9','#009E73'" in dash,
)

# ---------------------------------------------------------------------------
# Section 17 - Outstanding items sprint (P1/P2/P3)
# ---------------------------------------------------------------------------
check("P1-A8: spendingData=null after saveYtdTransactions success", "spendingData=null" in dash)
check("P1-A9: applySpendingForecast stale-data block present", "ytdTransactionsChanged||ytdAccountsChanged" in dash or "ytdTransactionsChanged || ytdAccountsChanged" in dash)
check("P1-B1: guarded setStep defined in navigation module", "function setStep(ctx,id)" in nav and "wireStepNavigation" in nav)
check("P1-B1: autosave steps list includes ytd_transactions", "'ytd_transactions'" in nav and "AUTOSAVE_STEPS" in nav)
check("P2-C1: down_payment valueKind override returns percent", "norm(r.label)==='down_payment'" in dash or "norm(r?.label)==='down_payment'" in dash)
check("P2-C1: humanLabel down_payment no trailing percent sign", "Down Payment '" not in dash)
check("P2-B2: /api/build/status endpoint defined", "/api/build/status" in file_text("src/server/workbook_routes.py") or "/api/build/status" in file_text("src/server/base_routes.py"))
check("P2-B2: startup lastBuildOk restore calls /api/build/status", "api('/api/build/status')" in dash)
check("P2-D19: bottom action row has Save Changes + Download Workbook", "Save Changes" in dash and "Download Workbook" in dash)
check("P2-B6: workbookNavOpened localStorage guard", "workbookNavOpened" in dash)
check("P3-B7: saveWorkbookViewState defined", "saveWorkbookViewState" in dash)
check("P3-B7: restoreWorkbookViewState defined", "restoreWorkbookViewState" in dash)
check("P3-B8: data-group-key attribute on detail-col-group-section", "data-group-key" in dash)

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
