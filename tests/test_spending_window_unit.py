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


# Task 6: every hierarchy leaf is backed by ``spending_transactions_window`` -- both walk the same
# shared iterator and share the same top-N ranking, so a merchant line always equals its rows.
ROWS_INVARIANT = [
    _txn("2025-11-28", "Kroger", "Groceries", -11.11),       # before the window
    _txn("2025-12-02", "Kroger", "Groceries", -40.10),
    _txn("2025-12-05", "Aldi", "Groceries", -20.20),
    _txn("2025-12-07", "Publix", "Groceries", -30.30),
    _txn("2025-12-09", "Costco", "Groceries", -0.10),
    _txn("2025-12-10", "Costco", "Groceries", -0.20),
    _txn("2025-12-12", "Safeway", "Groceries", -15.15),
    _txn("2025-12-14", "Trader Joes", "Groceries", -9.99),
    _txn("2025-12-15", "Whole Foods", "Groceries", -9.99),
    _txn("2025-12-20", "Target", "Groceries", -20.00),
    _txn("2025-12-29", "", "Groceries", -12.34),               # "(no merchant)"
    _txn("2025-12-30", "Delta", "Zzz Odd Stuff", -25.00),      # no taxonomy mapping
    _txn("2026-01-03", "Kroger", "Groceries", -100.07),
    _txn("2026-01-04", "Target", "Groceries", 50.00),          # Target nets to a -30 refund
    _txn("2026-01-05", "Sprouts", "Groceries", -5.55),
    _txn("2026-01-08", "Odd Shop", "Zzz Odd Stuff", -15.25),
    _txn("2026-01-10", "Employer", "Paychecks", 5000),         # income
    _txn("2026-01-11", "Bank", "Transfer", -700),              # transfer
    _txn("2026-01-20", "Aldi", "Groceries", -0.30),
    _txn("2026-02-01", "Kroger", "Groceries", -10),            # after the window
]
KNOWN_LINE = ("Core Expenses", "Food", "Groceries", "Kroger")


def test_every_merchant_line_equals_its_transactions(tmp_path):
    base = _workspace(tmp_path, ROWS_INVARIANT)
    start, end = date(2025, 12, 1), date(2026, 1, 31)
    tree = st.spending_hierarchy_window(base, start, end)
    seen = 0
    for tt, groups in tree.items():
        for grp, cats in groups.items():
            for cat, lines in cats.items():
                for line, amount in lines.items():
                    got = st.spending_transactions_window(base, start, end, tt, grp, cat, line)
                    assert got["total"] == amount, (tt, grp, cat, line)
                    seen += 1
    assert {"Other merchants", "Refunds & credits", "(no merchant)"} <= {
        l for g in tree.values() for c in g.values() for ls in c.values() for l in ls}
    assert "Unmapped" in tree and seen >= 9
    # hand-worked: Trader Joes 9.99 + Whole Foods 9.99 + Sprouts 5.55 + Costco 0.10 + 0.20
    other = st.spending_transactions_window(base, start, end, "Core Expenses", "Food", "Groceries", "Other merchants")
    assert other["total"] == 25.83
    assert sorted(t["merchant"] for t in other["transactions"]) == \
        ["Costco", "Costco", "Sprouts", "Trader Joes", "Whole Foods"]
    refunds = st.spending_transactions_window(base, start, end, "Core Expenses", "Food", "Groceries", "Refunds & credits")
    assert refunds["total"] == -30.0
    assert [t["amount"] for t in refunds["transactions"]] == [-50.0, 20.0]


def test_transactions_sorted_newest_first_with_fields(tmp_path):
    got = st.spending_transactions_window(_workspace(tmp_path, ROWS_INVARIANT), date(2025, 12, 1), date(2026, 1, 31),
                                          *KNOWN_LINE)
    dates = [t["date"] for t in got["transactions"]]
    assert len(dates) >= 2 and dates == sorted(dates, reverse=True)
    assert all(set(t) == {"date", "account", "merchant", "amount", "notes"} for t in got["transactions"])
    assert got["transactions"][0] == {"date": "2026-01-03", "account": "Checking", "merchant": "Kroger",
                                      "amount": 100.07, "notes": ""}
    assert got["total"] == 140.17


def test_unknown_line_returns_empty(tmp_path):            # Review Focus 3
    got = st.spending_transactions_window(_workspace(tmp_path, ROWS), date(2026, 1, 1), date(2026, 12, 31),
                                          "Core", "Food", "Groceries", "Nobody")
    assert got == {"transactions": [], "total": 0.0}
