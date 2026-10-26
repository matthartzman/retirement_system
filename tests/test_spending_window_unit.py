"""Trends Phase 5: ``spending_hierarchy_window`` is ``ytd_spending_hierarchy`` generalised to a
date range, and ``ytd_spending_hierarchy`` is a thin wrapper over it, so the mapping, sign,
refund and "Other merchants" rules live in one place."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src import spending_tracker as st
from tests.plan_fixture import write_plan_dataset

TAXONOMY = ("tracking_type,group,category_id,label,origin,status,notes\n"
            "Core Expenses,Food,groceries,Groceries,template,active,\n"
            "Income,Pay,paychecks,Paychecks,template,active,\n")
ALIASES = ("match_value,match_field,exact,priority,category_id,source\n"
           "Groceries,category,TRUE,50,groceries,test\n"
           "Paychecks,category,TRUE,50,paychecks,test\n")
BUDGET = ("kind,key,label,annual_budget,start_year,end_year,one_time_year,notes\n"
          "category,groceries,Groceries,3650,,,,\n")


def _txn(d, merchant, category, amount):
    return f"{d},{merchant},{category},Checking,{amount:.2f},Member_1\n"


def _workspace(tmp_path: Path, rows, budget: str = BUDGET) -> Path:
    """A workspace with a two-category taxonomy, aliases, a budget and ``rows`` of transactions."""
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    write_plan_dataset(base_dir, "client_spending_taxonomy.csv", TAXONOMY)
    write_plan_dataset(base_dir, "client_spending_aliases.csv", ALIASES)
    write_plan_dataset(base_dir, "client_spending_budget.csv", budget)
    write_plan_dataset(base_dir, "ytd_transactions.csv",
                       "Date,Merchant,Category,Account,Amount,Owner\n" + "".join(rows))
    return base_dir


ROWS = [
    _txn("2025-11-20", "Kroger", "Groceries", -40),
    _txn("2025-12-28", "Kroger", "Groceries", -60),
    _txn("2025-12-30", "Delta", "Zzz Odd Stuff", -25),
    _txn("2026-01-03", "Kroger", "Groceries", -100),
    _txn("2026-01-05", "Aldi", "Groceries", -20),
    _txn("2026-01-09", "Kroger", "Groceries", 30),          # refund
    _txn("2026-01-10", "Employer", "Paychecks", 5000),      # income
    _txn("2026-01-11", "Bank", "Transfer", -700),            # transfer
    _txn("2026-02-14", "Odd Shop", "Zzz Odd Stuff", -15),    # no taxonomy mapping
    _txn("2026-03-01", "Kroger", "Groceries", -10),
]


def _total(node):
    return node if isinstance(node, (int, float)) else sum(_total(v) for v in node.values())


def _find_category(tree, name):
    for groups in tree.values():
        for cats in groups.values():
            if name in cats:
                return cats[name]
    return None


def test_wrapper_equals_window_for_jan1_through_and_full_year(tmp_path):
    base = _workspace(tmp_path, ROWS)
    through = date(2026, 2, 20)
    assert st.ytd_spending_hierarchy(base, 2026, through=through) == \
        st.spending_hierarchy_window(base, date(2026, 1, 1), through)
    assert st.ytd_spending_hierarchy(base, 2026) == \
        st.spending_hierarchy_window(base, date(2026, 1, 1), date(2026, 12, 31))
    assert st.ytd_spending_hierarchy(base, 2025) == \
        st.spending_hierarchy_window(base, date(2025, 1, 1), date(2025, 12, 31))
    # merchants_per_category flows through the wrapper too
    assert st.ytd_spending_hierarchy(base, 2026, merchants_per_category=1) == \
        st.spending_hierarchy_window(base, date(2026, 1, 1), date(2026, 12, 31), merchants_per_category=1)


def test_wrapper_through_outside_the_year_keeps_old_semantics(tmp_path):
    base = _workspace(tmp_path, ROWS)
    # a `through` after Dec 31 never pulls in next year's rows; one before Jan 1 yields nothing
    assert st.ytd_spending_hierarchy(base, 2025, through=date(2026, 6, 1)) == st.ytd_spending_hierarchy(base, 2025)
    assert st.ytd_spending_hierarchy(base, 2026, through=date(2025, 12, 31)) == {}


def test_window_crossing_a_year_boundary_sums_both_years(tmp_path):
    base = _workspace(tmp_path, ROWS)
    tree = st.spending_hierarchy_window(base, date(2025, 12, 15), date(2026, 1, 6))
    groceries = _find_category(tree, "Groceries")
    assert groceries == {"Kroger": 160.0, "Aldi": 20.0}
    assert _find_category(tree, "Zzz Odd Stuff") == {"Delta": 25.0}
    assert round(_total(tree), 2) == 205.0


def test_refunds_net_against_category(tmp_path):
    base = _workspace(tmp_path, ROWS)
    tree = st.spending_hierarchy_window(base, date(2026, 1, 1), date(2026, 1, 9))
    assert _find_category(tree, "Groceries") == {"Kroger": 70.0, "Aldi": 20.0}
    # refunds larger than purchases in the window net to a "Refunds & credits" line
    only_refund = st.spending_hierarchy_window(base, date(2026, 1, 9), date(2026, 1, 9))
    assert only_refund == {"Core Expenses": {"Food": {"Groceries": {"Refunds & credits": -30.0}}}}


def test_transfers_and_income_are_excluded(tmp_path):
    base = _workspace(tmp_path, ROWS)
    tree = st.spending_hierarchy_window(base, date(2026, 1, 10), date(2026, 1, 11))
    assert tree == {}
    assert "Income" not in st.spending_hierarchy_window(base, date(2025, 1, 1), date(2026, 12, 31))


def test_unmapped_spend_lands_under_unmapped(tmp_path):
    base = _workspace(tmp_path, ROWS)
    tree = st.spending_hierarchy_window(base, date(2026, 2, 1), date(2026, 2, 28))
    assert tree == {"Unmapped": {"Unmapped": {"Zzz Odd Stuff": {"Odd Shop": 15.0}}}}


def test_window_with_no_transactions_is_empty(tmp_path):
    base = _workspace(tmp_path, ROWS)
    assert st.spending_hierarchy_window(base, date(2024, 1, 1), date(2024, 6, 30)) == {}
    assert st.spending_hierarchy_window(base, date(2026, 4, 1), date(2026, 4, 30)) == {}
