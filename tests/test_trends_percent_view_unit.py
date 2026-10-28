"""Pure-function tests for the percent-view scaling and detail stripping."""
import copy
import sqlite3

from financial_trends_reporter import balance_series
from financial_trends_reporter.percent_view import (
    NON_MONEY_KEYS, find_money_leaks, is_non_money, scale_basis, scale_payload, strip_detail,
)


def test_scale_divides_money_keeps_allowlist_and_does_not_mutate():
    src = {"net_worth": {"total": 2_000_000}, "days": 30, "pre_tax_rate": 0.24, "series": {"a": [1_000_000, 500_000]}, "ok": True}
    out = scale_payload(src, 2_000_000)
    assert out == {"net_worth": {"total": 1.0}, "days": 30, "pre_tax_rate": 0.24, "series": {"a": [0.5, 0.25]}, "ok": True}
    assert src["net_worth"]["total"] == 2_000_000


def test_scale_handles_none_bool_nested_lists_and_leaves_input_intact():
    src = {"rows": [{"value": 100, "flag": False, "day": None}, [[50, None]]], "count": 12.5}
    before = copy.deepcopy(src)
    out = scale_payload(src, 100.0)
    assert out == {"rows": [{"value": 1.0, "flag": False, "day": None}, [[0.5, None]]], "count": 12.5}
    assert out["rows"][0]["flag"] is False
    assert src == before


def test_sums_survive_scaling():
    a, b, k = [1200.0, 1300.0], [800.0, -50.0], 7_654_321.0
    sa, sb = scale_payload({"v": a}, k)["v"], scale_payload({"v": b}, k)["v"]
    assert [round((x + y) * k, 2) for x, y in zip(sa, sb)] == [2000.0, 1250.0]


def test_dollar_strings_are_hidden():
    assert scale_payload({"note": "differ by $1,234"}, 10.0) == {"note": "(amount hidden)"}
    assert scale_payload({"note": "2026-10-28"}, 10.0) == {"note": "2026-10-28"}


def test_ratio_suffix_rule_and_unlisted_keys_are_scaled():
    for key in ("pre_tax_rate", "ytd_growth_pct", "x_ratio", "y_fraction", "pct", "rate", "weight", "days", "count"):
        assert is_non_money(key), key
    for key in ("price", "purchase_price", "shares", "quantity", "basis", "total", "something_new"):
        assert not is_non_money(key), key
        assert key not in NON_MONEY_KEYS


def test_basis_none_when_net_worth_not_positive(tmp_path):
    missing = tmp_path / "none.db"
    assert scale_basis(missing, []) is None
    assert scale_basis(missing, [{"net_worth": {"total": -5}}]) is None
    assert scale_basis(missing, [{"net_worth": {"total": 0}}]) is None
    assert scale_basis(missing, [{"as_of_date": "2026-01-01"}]) is None


def test_basis_falls_back_to_last_history_entry(tmp_path):
    history = [{"net_worth": {"total": 10}}, {"net_worth": {"total": 2500.5}}]
    assert scale_basis(tmp_path / "none.db", history) == 2500.5


def test_basis_prefers_store_and_does_not_fall_back_when_store_not_positive(tmp_path, monkeypatch):
    db = tmp_path / "b.db"
    db.write_bytes(b"")
    monkeypatch.setattr(balance_series, "snapshot_summary", lambda p: {"net_worth": 900.0})
    assert scale_basis(db, [{"net_worth": {"total": 5}}]) == 900.0
    monkeypatch.setattr(balance_series, "snapshot_summary", lambda p: {"net_worth": -3.0})
    assert scale_basis(db, [{"net_worth": {"total": 5}}]) is None


def test_basis_empty_store_uses_history(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    # an existing but empty file is not a usable store: fall back to the history, or None
    assert scale_basis(db, [{"net_worth": {"total": -5}}]) is None


def test_scale_with_non_positive_k_raises():
    for k in (0, -1.0):
        try:
            scale_payload({"v": 1}, k)
        except ValueError:
            continue
        raise AssertionError(f"K={k} must raise")


def test_strip_spending_collapses_merchants():
    p = {"hierarchy": {"Expense": {"Home": {"Rent": {"Landlord": 2400.0, "Fee": 10.0}}}},
         "prior": {"detail": {"Expense": {"Home": {"Rent": {"prior": 2300.0, "merchants": {"Landlord": 2300.0}}}}}}}
    before = copy.deepcopy(p)
    out = strip_detail("/api/spending", p)
    assert out["hierarchy"]["Expense"]["Home"]["Rent"] == {"All merchants": 2410.0}
    assert out["prior"]["detail"]["Expense"]["Home"]["Rent"] == {"prior": 2300.0}
    assert p == before


def test_strip_live_snapshot_drops_reconciliation():
    out = strip_detail("/api/live-snapshot", {"reconciliation": {}, "unmapped_monarch": [1], "unmapped_holdings": [2], "liquid": {}})
    assert out == {"liquid": {}}


def test_strip_history_collapses_merchants_in_each_entry():
    entry = {"as_of_date": "2026-10-01", "net_worth": {"total": 5.0},
             "ytd_expense_hierarchy": {"Expense": {"Home": {"Rent": {"Landlord": 100.0, "Fee": 5.0}}}},
             "ytd_expense_prior_detail": {"Expense": {"Home": {"Rent": {"prior": 90.0, "merchants": {"Landlord": 90.0}}}}}}
    out = strip_detail("/api/history", {"history": [entry]})
    got = out["history"][0]
    assert got["ytd_expense_hierarchy"]["Expense"]["Home"]["Rent"] == {"All merchants": 105.0}
    assert got["ytd_expense_prior_detail"]["Expense"]["Home"]["Rent"] == {"prior": 90.0}
    assert got["net_worth"] == {"total": 5.0}
    assert entry["ytd_expense_hierarchy"]["Expense"]["Home"]["Rent"] == {"Landlord": 100.0, "Fee": 5.0}


def test_strip_history_accepts_a_bare_list_and_other_routes_are_unchanged():
    assert strip_detail("/api/history", [{"as_of_date": "x"}]) == [{"as_of_date": "x"}]
    p = {"anything": {"Rent": {"Landlord": 1.0}}}
    assert strip_detail("/api/balances", p) == p


def test_find_money_leaks():
    assert find_money_leaks({"total": 0.4, "days": 400}) == []
    assert find_money_leaks({"total": 1234.0}) == ["total"]
    assert find_money_leaks({"rows": [{"v": 60}], "note": "owes $5", "flag": True}) == ["rows[0].v", "note"]
