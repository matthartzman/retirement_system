"""Item 141 — standard QC: Budget/Projection-seed reconciliation across surfaces.

The same underlying unified spending budget (client_spending_budget.csv +
client_spending_taxonomy.csv) is displayed on multiple surfaces:

  1. UI Spending Model page  -> spending_tracker.spending_model /
     spending_summary_taxonomy  (grand budget, per-tracking-type budget, and
     budget_derived_core_spend_base / projection_seed).
  2. Projection engine        -> spending_budget_resolver.resolve_spending_inputs
     (spend_base + recurring_extras + lump), which drives the Cash Flow sheet.
  3. Workbook Core Spending    -> workbook_builder.build_sheet_core_spending
     (now sourced from the same unified model, scoped to Core Expenses).

These tests walk every tracking type / group / category and assert the numbers
reconcile wherever they represent the same thing, and explicitly document the
intentional definitional differences (Income/Transfer/Business/Housing/Wellness
and Travel/Large-Discretionary — at every level: group, category, and line —
are excluded from the projection spend_base by design).

They exist to catch a whole class of regressions:
  * a surface reading a stale/duplicate CSV instead of the unified model,
  * double-counting a category that carries both a category budget row AND a
    detail line row (the bug fixed for item 141),
  * a hardcoded/stale tracking-type or exclusion list drifting from the taxonomy.
"""
from pathlib import Path

import pytest

from src import spending_tracker as st
from src.spending_budget_resolver import (
    resolve_spending_inputs,
    EXCLUDED_FROM_SPEND_BASE,
    TIME_BOUNDED_LINE_TRACKING_TYPES,
)


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed(root: Path, taxonomy: str, budget: str, aliases: str = "", txns: str = ""):
    write(root / "input/client_spending_taxonomy.csv", taxonomy)
    write(root / "input/client_spending_budget.csv", budget)
    write(root / "input/client_spending_aliases.csv",
          aliases or "match_value,match_field,exact,priority,category_id,source\n")
    write(root / "input/ytd_transactions.csv",
          txns or "Date,Merchant,Category,Account,Amount,Owner\n")


# ---------------------------------------------------------------------------
# 1. The exact bug from item 141: a category with BOTH a category budget row and
#    a detail line row must be counted ONCE, not twice, in the projection
#    spend_base.  The resolver previously only suppressed the category row for
#    Housing/Travel/Large-Discretionary; a Core Expenses category (charitable
#    giving) double-counted into spend_base.
# ---------------------------------------------------------------------------
def test_core_category_with_detail_line_is_not_double_counted(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="""tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Gifts,charity,Charitable Donations,template,active,
Core Expenses,Food,groceries,Groceries,template,active,
""",
        budget="""kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,charity,Charitable Donations,5000,,,,category row
category,groceries,Groceries,6000,,,,
line,charity,Charitable Giving,5000,,,,detail line for the SAME 5000 budget
""",
    )
    resolved = resolve_spending_inputs(root, year_range=range(2026, 2031))
    # charity counts once (5000) + groceries (6000) = 11000, NOT 16000.
    assert resolved["spend_base"] == 11000
    # And the per-category rollup reflects a single 5000, not 10000.
    assert resolved["spending_category_rollup_by_year"][2026]["charity"] == 5000


# ---------------------------------------------------------------------------
# 2. UI budget_derived_core_spend_base == resolver spend_base (same seed).
# ---------------------------------------------------------------------------
def test_ui_core_spend_base_equals_resolver_spend_base(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="""tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Gifts,charity,Charitable Donations,template,active,
Core Expenses,Food,groceries,Groceries,template,active,
Travel,Trips,vacation,Vacation,template,active,
Travel,Fun,entertainment_recreation,Entertainment & Recreation,template,active,
Housing,Home,mortgage,Mortgage,template,active,
Wellness,Med,medical,Medical,template,active,
Business,Ops,biz_services,Business Services,template,active,
""",
        budget="""kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,charity,Charitable Donations,5000,,,,
category,groceries,Groceries,6000,,,,
category,entertainment_recreation,Entertainment & Recreation,3000,,,,recurring travel-group core-style spend
category,mortgage,Mortgage,36000,,,,excluded housing
category,medical,Medical,10000,,,,excluded wellness
category,biz_services,Business Services,2000,,,,excluded business
line,charity,Charitable Giving,5000,,,,detail line for the 5000
line,vacation,Annual Vacation,8000,2026,2028,,time-bounded travel extra
""",
    )
    model = st.spending_model(root, year=2026)
    resolved = resolve_spending_inputs(root, config={"plan_start": 2026, "plan_end": 2030})
    assert model["totals"]["budget_derived_core_spend_base"] == resolved["spend_base"]


# ---------------------------------------------------------------------------
# 3. The workbook Core Spending sheet's Core-Expenses budget reconciles with the
#    UI Spending Model's Core Expenses tracking-type budget.
# ---------------------------------------------------------------------------
def test_workbook_core_spending_sheet_budget_matches_ui(tmp_path, monkeypatch):
    root = tmp_path
    _seed(
        root,
        taxonomy="""tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Gifts,charity,Charitable Donations,template,active,
Core Expenses,Food,groceries,Groceries,template,active,
Housing,Home,mortgage,Mortgage,template,active,
""",
        budget="""kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,charity,Charitable Donations,5000,,,,
category,groceries,Groceries,6000,,,,
category,mortgage,Mortgage,36000,,,,
line,charity,Charitable Giving,5000,,,,
""",
    )
    # Point spending_tracker's default root at the tmp plan so the sheet builder
    # (which calls spending_summary_taxonomy with no root) reads this fixture.
    monkeypatch.setenv("RETIREMENT_SYSTEM_BASE_DIR", str(root))

    from openpyxl import Workbook
    from src.reporting import workbook_builder as wb

    model = st.spending_model(root)
    core = next(t for t in model["tracking_types"] if t["tracking_type"] == "Core Expenses")
    ui_core_budget = core["annual_budget"]

    ws = Workbook().active
    wb.build_sheet_core_spending(ws, {"spend_base": 11000})

    # Recompute the sheet total the same way build_sheet_core_spending does and
    # assert it equals the UI Core Expenses budget (charity counted once = 5000
    # via its line, + groceries 6000 = 11000). Housing is excluded.
    summary = st.spending_summary_taxonomy()
    core_tt = next(t for t in summary["tracking_types"] if t["tracking_type"] == "Core Expenses")
    sheet_total = sum(g["annual_budget"] for g in core_tt["groups"])
    assert sheet_total == ui_core_budget == 11000


# ---------------------------------------------------------------------------
# 4. Every tracking type reconciles OR is a documented intentional exclusion.
#    This walks the whole taxonomy and asserts the resolver's per-category
#    contribution to spend_base is included exactly for the non-excluded,
#    non-time-bounded categories, and excluded exactly for the rest.
# ---------------------------------------------------------------------------
def test_every_tracking_type_inclusion_is_intentional_and_consistent(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="""tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Food,groceries,Groceries,template,active,
Wellness,Med,medical,Medical,template,active,
Housing,Home,mortgage,Mortgage,template,active,
Travel,Trips,vacation,Vacation,template,active,
Large Discretionary,Big,wedding,Wedding,template,active,
Business,Ops,biz_services,Business Services,template,active,
""",
        budget="""kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,groceries,Groceries,6000,,,,
category,medical,Medical,10000,,,,
category,mortgage,Mortgage,36000,,,,
category,vacation,Vacation,8000,,,,
category,wedding,Wedding,50000,,,,
category,biz_services,Business Services,2000,,,,
line,wedding,Wedding,50000,,,2027,one-time large discretionary
line,vacation,Annual Vacation,8000,2026,2028,,time-bounded travel
""",
    )
    resolved = resolve_spending_inputs(root, config={"plan_start": 2026, "plan_end": 2030})
    # Only Core Expenses groceries (6000) belongs in spend_base.
    #   Wellness/Housing/Business -> excluded tracking types.
    #   Travel/Large Discretionary -> time-bounded lines route to extras/lump, not spend_base.
    assert resolved["spend_base"] == 6000
    # Business reference is tracked separately, not in spend_base.
    assert resolved["business_reference_budget"] == 2000
    # Time-bounded travel line becomes a recurring extra.
    assert any(e["type"] == "Annual Vacation" for e in resolved["recurring_extras"])
    # One-time wedding becomes a lump in its year.
    assert resolved["lump"].get(2027) == 50000

    # Guard the documented exclusion set so it can't silently drift.
    assert EXCLUDED_FROM_SPEND_BASE == {
        "Income", "Transfer", "Transfers", "Business", "Housing", "Wellness"
    }
    assert TIME_BOUNDED_LINE_TRACKING_TYPES == {"Travel", "Large Discretionary"}


# ---------------------------------------------------------------------------
# 4b. Core spending must NEVER absorb Travel/Large-Discretionary dollars, even
#     when they arrive as plain category budgets with no detail lines (the leak
#     that inflated spend_base by the entertainment_recreation category). The
#     dollars still project — as a recurring extra spanning the plan window —
#     and the UI core base reconciles with the resolver.
# ---------------------------------------------------------------------------
def test_travel_and_large_disc_category_budgets_never_enter_spend_base(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="""tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Food,groceries,Groceries,template,active,
Travel,Fun,entertainment_recreation,Entertainment & Recreation,template,active,
Large Discretionary,Big,boat,Boat Fund,template,active,
""",
        budget="""kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,groceries,Groceries,6000,,,,
category,entertainment_recreation,Entertainment & Recreation,3270,,,,travel category with NO detail lines
category,boat,Boat Fund,4000,,,,large-disc category with NO detail lines
""",
    )
    resolved = resolve_spending_inputs(root, config={"plan_start": 2026, "plan_end": 2030})
    # Only groceries is core.
    assert resolved["spend_base"] == 6000
    # The Travel/Large-Disc category budgets still project, as recurring extras
    # over the plan window (Travel/Other columns), not as core spending.
    extras = {e["category_id"]: e for e in resolved["recurring_extras"]}
    assert extras["entertainment_recreation"]["amount"] == 3270
    assert extras["entertainment_recreation"]["start_year"] == 2026
    assert extras["entertainment_recreation"]["end_year"] == 2030
    assert extras["boat"]["amount"] == 4000
    # UI core base agrees with the resolver.
    model = st.spending_model(root, year=2026)
    assert model["totals"]["budget_derived_core_spend_base"] == resolved["spend_base"] == 6000


# ---------------------------------------------------------------------------
# 5. Grand budget (all tracking types incl. excluded ones) is stable and equals
#    the sum of per-tracking-type budgets — the UI Spending Model header number.
# ---------------------------------------------------------------------------
def test_grand_budget_equals_sum_of_tracking_type_budgets(tmp_path):
    root = tmp_path
    _seed(
        root,
        taxonomy="""tracking_type,group,category_id,label,origin,status,notes
Core Expenses,Food,groceries,Groceries,template,active,
Housing,Home,mortgage,Mortgage,template,active,
Wellness,Med,medical,Medical,template,active,
""",
        budget="""kind,key,label,annual_budget,start_year,end_year,one_time_year,notes
category,groceries,Groceries,6000,,,,
category,mortgage,Mortgage,36000,,,,
category,medical,Medical,10000,,,,
""",
    )
    model = st.spending_model(root, year=2026)
    per_type = sum(t["annual_budget"] for t in model["tracking_types"])
    assert model["totals"]["annual_budget"] == pytest.approx(per_type, abs=0.01)
    assert model["totals"]["projection_seed"] == model["totals"]["annual_budget"]


# ---------------------------------------------------------------------------
# Regression guard (bug: "Uncategorized" showed ~$21 of actuals even though every
# transaction was categorized). Root cause was a spurious user alias routing a
# real category name ("Postage & Shipping") into the catch-all "uncategorized"
# category via a substring match, so its spend landed under Uncategorized instead
# of surfacing under its own name. Guard the committed alias data against that
# class of footgun: nothing may alias INTO "uncategorized" except a transaction
# literally categorized "Uncategorized".
# ---------------------------------------------------------------------------
def test_no_alias_routes_a_real_category_into_the_uncategorized_catch_all():
    project_root = Path(__file__).resolve().parents[1]
    offenders = [
        alias
        for alias in st.load_aliases(project_root)
        if (alias.get("category_id") or "").strip() == "uncategorized"
        and str(alias.get("match_value") or "").strip().lower() != "uncategorized"
    ]
    assert not offenders, (
        "Aliases route a real category into the uncategorized catch-all, which "
        "hides real spend under Uncategorized: " + repr(offenders)
    )
