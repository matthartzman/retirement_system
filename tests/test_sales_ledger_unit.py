"""Pure helpers of the realized-sales ledger (plan step 1.2): holding period, row validation, lot allocation."""
from __future__ import annotations

from datetime import date

import pytest

from src import sales_ledger
from src.sales_ledger import ValidationError, allocate_lots, holding_period, validate_sale_row
from src.stores import sales_repo

SALE_STATUSES, TAX_CLASSES = sales_repo.SALE_STATUSES, sales_repo.TAX_CLASSES


def test_column_values_mirror_the_repo():
    assert sales_ledger.TAX_CLASSES == sales_repo.TAX_CLASSES
    assert sales_ledger.SALE_SOURCES == sales_repo.SALE_SOURCES
    assert sales_ledger.SALE_STATUSES == sales_repo.SALE_STATUSES


# ---------------------------------------------------------------- holding_period
@pytest.mark.parametrize("purchase, sale, expected", [
    ("2025-03-05", "2026-03-05", "short"),   # the anniversary itself is still short
    ("2025-03-05", "2026-03-06", "long"),
    ("2025-03-05", "2026-03-04", "short"),
    ("2025-03-05", "2025-03-05", "short"),   # same day
    ("2024-02-29", "2025-02-28", "short"),   # leap-day purchase: anniversary is Feb 28 (non-leap year)
    ("2024-02-29", "2025-03-01", "long"),
    ("2023-02-28", "2024-02-29", "long"),    # anniversary Feb 28 passed
    ("2023-12-31", "2024-12-31", "short"),
    ("2023-12-31", "2025-01-01", "long"),
    ("2020-02-29", "2024-02-29", "long"),
])
def test_holding_period_calendar_rule(purchase, sale, expected):
    assert holding_period(purchase, sale) == expected


def test_holding_period_leap_day_anniversary_in_leap_year():
    assert holding_period("2023-02-28", "2024-02-28") == "short"
    assert holding_period("2024-02-29", "2028-03-01") == "long"


def test_holding_period_accepts_date_objects():
    assert holding_period(date(2025, 3, 5), date(2026, 3, 6)) == "long"


@pytest.mark.parametrize("purchase", [None, "", "  "])
def test_holding_period_unknown_without_purchase_date(purchase):
    assert holding_period(purchase, "2026-03-06") == "unknown"


def test_holding_period_bad_dates_raise():
    with pytest.raises(ValidationError):
        holding_period("03/05/2025", "2026-03-06")
    with pytest.raises(ValidationError):
        holding_period("2025-03-05", None)


# ---------------------------------------------------------------- validate_sale_row
def _row(**over):
    row = dict(sale_date="2026-06-10", account="Trust", tax_class="taxable", symbol="vti", shares=10,
               proceeds=2000.0, fees=5.0, basis=1500.0, purchase_date="2025-01-02", source="manual")
    row.update(over)
    return row


def test_validate_computes_gain_net_of_fees_and_derives_holding_period():
    out = validate_sale_row(_row())
    assert out["gain"] == pytest.approx(495.0)
    assert out["holding_period"] == "long"
    assert out["symbol"] == "VTI"
    assert out["status"] == "confirmed"
    assert out["fees"] == 5.0


def test_validate_loss_is_negative_gain():
    assert validate_sale_row(_row(proceeds=1000.0))["gain"] == pytest.approx(-505.0)


def test_validate_fees_default_to_zero():
    row = _row()
    del row["fees"]
    assert validate_sale_row(row)["gain"] == pytest.approx(500.0)


@pytest.mark.parametrize("tax_class", [c for c in TAX_CLASSES if c != "taxable"])
def test_validate_non_taxable_class_has_no_gain(tax_class):
    out = validate_sale_row(_row(tax_class=tax_class, purchase_date=None))
    assert out["gain"] is None


def test_validate_ignores_caller_supplied_gain_and_holding_period():
    out = validate_sale_row(_row(gain=999.0, holding_period="short"))
    assert out["gain"] == pytest.approx(495.0)
    assert out["holding_period"] == "long"


def test_validate_taxable_without_purchase_date_is_blocked():
    with pytest.raises(ValidationError, match="purchase_date"):
        validate_sale_row(_row(purchase_date=None))


@pytest.mark.parametrize("field", ["sale_date", "account", "tax_class", "symbol", "shares", "proceeds", "basis", "source"])
def test_validate_required_fields(field):
    row = _row()
    del row[field]
    with pytest.raises(ValidationError):
        validate_sale_row(row)


@pytest.mark.parametrize("over", [
    dict(shares=0), dict(shares=-1), dict(shares="ten"), dict(tax_class="margin"), dict(source="guess"),
    dict(sale_date="2026-13-01"), dict(fees=-1.0), dict(proceeds=True), dict(account="  "), dict(symbol=""),
    dict(purchase_date="2026-07-01"),  # bought after it was sold
    dict(status="deleted"),
])
def test_validate_rejects_bad_values(over):
    with pytest.raises(ValidationError):
        validate_sale_row(_row(**over))


def test_validate_status_values_are_the_repo_columns():
    for status in SALE_STATUSES:
        assert validate_sale_row(_row(status=status))["status"] == status


def test_validate_output_is_accepted_by_repo_insert(tmp_path):
    from src.stores import PlanStore
    out = validate_sale_row(_row())
    out.pop("status")
    with PlanStore.open(tmp_path / "plan.rpx") as store:
        sale_id = store.sales.insert_sale(**out)
        assert store.sales.get_sale(sale_id)["gain"] == pytest.approx(495.0)


# ---------------------------------------------------------------- allocate_lots
LOTS = [{"lot_key": "A", "remaining": 6.0}, {"lot_key": "B", "remaining": 10.0}]


def test_allocate_accepts_exact_split():
    assert allocate_lots(10, LOTS, {"A": 6, "B": 4}) == {"A": 6.0, "B": 4.0}


def test_allocate_drops_zero_entries():
    assert allocate_lots(4, LOTS, {"A": 0, "B": 4}) == {"B": 4.0}


def test_allocate_no_preselection_empty_allocation_rejected():
    with pytest.raises(ValidationError, match="total"):
        allocate_lots(10, LOTS, {})


def test_allocate_over_lot_remaining_rejected():
    with pytest.raises(ValidationError, match="A"):
        allocate_lots(7, LOTS, {"A": 7})


def test_allocate_total_must_equal_shares_sold():
    with pytest.raises(ValidationError, match="total"):
        allocate_lots(10, LOTS, {"A": 3, "B": 4})
    with pytest.raises(ValidationError, match="total"):
        allocate_lots(5, LOTS, {"A": 3, "B": 4})


def test_allocate_unknown_lot_and_negative_rejected():
    with pytest.raises(ValidationError):
        allocate_lots(4, LOTS, {"Z": 4})
    with pytest.raises(ValidationError):
        allocate_lots(4, LOTS, {"A": -2, "B": 6})


def test_allocate_tolerates_float_dust():
    assert allocate_lots(0.3, [{"lot_key": "A", "remaining": 0.3}], {"A": 0.1 + 0.2}) == {"A": pytest.approx(0.3)}


def test_allocate_single_exact_fit_is_not_chosen_for_the_user():
    # one lot equals the sale, yet nothing is allocated unless the caller says so
    with pytest.raises(ValidationError):
        allocate_lots(6, LOTS, {})


def test_allocate_rejects_nonpositive_shares_sold():
    with pytest.raises(ValidationError):
        allocate_lots(0, LOTS, {})
