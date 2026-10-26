"""Trends Phase 5: the date arithmetic behind /api/spending -- budget proration over the years a
window touches, the full-year budget, and the same window one year earlier."""
from __future__ import annotations

from datetime import date

import pytest

from financial_trends_reporter import spending_window as sw
from tests.test_spending_window_unit import ROWS, _txn, _workspace


def test_window_year_segments_within_one_year_and_across_a_boundary():
    assert sw.window_year_segments(date(2026, 3, 1), date(2026, 3, 31)) == [(2026, 31, 365)]
    assert sw.window_year_segments(date(2025, 12, 15), date(2026, 1, 6)) == [(2025, 17, 365), (2026, 6, 365)]
    assert sw.window_year_segments(date(2026, 1, 2), date(2026, 1, 1)) == []


def test_leap_year_day_counts():
    assert sw.days_in_year(2028) == 366 and sw.days_in_year(2026) == 365 and sw.days_in_year(2100) == 365
    assert sw.window_year_segments(date(2028, 2, 1), date(2028, 3, 1)) == [(2028, 30, 366)]
    assert sw.window_year_segments(date(2027, 1, 1), date(2028, 12, 31)) == [(2027, 365, 365), (2028, 366, 366)]


def test_prorate_within_one_year():
    budgets = {2026: {"Core": 3650.0}}
    assert sw.prorate(date(2026, 3, 1), date(2026, 3, 10), budgets.get) == {"Core": 100.0}


def test_prorate_sums_each_years_budget_across_a_boundary():
    budgets = {2025: {"Core": 3650.0, "Travel": 730.0}, 2026: {"Core": 7300.0}}
    # 17 days of 2025 at $10/day + 6 days of 2026 at $20/day; Travel only budgeted in 2025.
    got = sw.prorate(date(2025, 12, 15), date(2026, 1, 6), lambda y: budgets.get(y, {}))
    assert got == {"Core": 170.0 + 120.0, "Travel": 34.0}


def test_prorate_nested_by_category_and_missing_years():
    budgets = {2026: {"Core": {"Groceries": 365.0}, "Housing": {}}}
    got = sw.prorate(date(2025, 12, 31), date(2026, 1, 1), lambda y: budgets.get(y, {}))
    assert got == {"Core": {"Groceries": 1.0}, "Housing": {}}


def test_full_year_window_equals_the_annual_budget():
    budgets = {2028: {"Core": 1234.56}}
    assert sw.prorate(date(2028, 1, 1), date(2028, 12, 31), budgets.get) == {"Core": 1234.56}


def test_prior_window_and_feb_29():
    assert sw.prior_window(date(2026, 1, 1), date(2026, 10, 26)) == (date(2025, 1, 1), date(2025, 10, 26))
    assert sw.prior_window(date(2028, 2, 29), date(2028, 3, 5)) == (date(2027, 2, 28), date(2027, 3, 5))
    assert sw.prior_window(date(2027, 3, 1), date(2028, 2, 29)) == (date(2026, 3, 1), date(2027, 2, 28))
    # trends_metrics keeps using the same rule (one definition)
    from financial_trends_reporter.trends_metrics import _same_day_prior_year
    assert _same_day_prior_year is sw.same_day_prior_year


def test_payload_prior_is_null_before_data_starts(tmp_path):
    base = _workspace(tmp_path, ROWS)  # first transaction: 2025-11-20
    body = sw.spending_window_payload(base, date(2025, 12, 1), date(2025, 12, 31))
    assert body["prior"] is None  # shifted window starts in 2024, before any data
    body = sw.spending_window_payload(base, date(2026, 1, 1), date(2026, 1, 6))
    assert body["prior"]["window"] == {"from": "2025-01-01", "to": "2025-01-06"}
    assert body["prior"]["by_type"] == {} and body["prior"]["detail"] == {}


def test_payload_budget_full_year_and_prior_on_a_fixture(tmp_path):
    rows = ROWS + [_txn("2025-01-04", "Kroger", "Groceries", -55)]
    base = _workspace(tmp_path, rows)  # Groceries budget $3,650/yr = $10/day
    body = sw.spending_window_payload(base, date(2026, 1, 1), date(2026, 1, 10))
    assert body["window"] == {"from": "2026-01-01", "to": "2026-01-10", "days": 10}
    assert body["budget"]["by_type"] == {"Core Expenses": 100.0}
    assert body["budget"]["by_category"]["Core Expenses"] == {"Groceries": 100.0}
    assert body["full_year_budget"] == {"year": 2026, "by_type": {"Core Expenses": 3650.0},
                                        "by_category": {"Core Expenses": {"Groceries": 3650.0}}}
    assert body["prior"]["by_type"] == {"Core Expenses": 55.0}
    assert body["prior"]["detail"]["Core Expenses"]["Food"]["Groceries"] == {"prior": 55.0, "merchants": {"Kroger": 55.0}}
    assert body["hierarchy"]["Core Expenses"]["Food"]["Groceries"] == {"Kroger": 70.0, "Aldi": 20.0}


def test_full_year_budget_is_the_end_years(tmp_path):
    base = _workspace(tmp_path, ROWS)
    seen = []

    def fake(_base, year):
        seen.append(year)
        return {"by_type": {"Core": 1000.0 * (year - 2020)}, "by_category": {}}

    body = sw.spending_window_payload(base, date(2025, 7, 1), date(2026, 6, 30), budgets=fake)
    assert body["full_year_budget"]["year"] == 2026
    assert body["full_year_budget"]["by_type"] == {"Core": 6000.0}
    assert body["budget"]["by_type"]["Core"] == pytest.approx(5000 * 184 / 365 + 6000 * 181 / 365, abs=0.01)
    assert sorted(set(seen)) == [2025, 2026]


def test_a_year_whose_budget_fails_counts_as_absent(tmp_path, monkeypatch):
    base = _workspace(tmp_path, ROWS)

    def boom(*_a, **_k):
        raise RuntimeError("no taxonomy")

    monkeypatch.setattr(sw.spending_tracker, "spending_summary_taxonomy", boom)
    body = sw.spending_window_payload(base, date(2026, 1, 1), date(2026, 1, 10))
    assert body["budget"] == {"by_type": {}, "by_category": {}}
    assert body["full_year_budget"]["by_type"] == {}
