"""Finding N9 (system review 2026-09-07, Wave 6 item W6-10):
classify_cash_transaction()/classify_investment_transaction() (src/ytd_tracking.py)
implicitly assume the standard Monarch export sign convention -- negative
amount = spending/debit, positive amount = income/credit/refund -- but that
convention was never asserted anywhere in tests/. This pins it as a contract
so a future change to the branching can't silently flip it unnoticed.
"""
from src.ytd_tracking import classify_cash_transaction, classify_investment_transaction


def _row(amount: str, category: str = "Groceries") -> dict:
    return {"Amount": amount, "Category": category, "Merchant": "", "Notes": "", "Tags": "", "Original Statement": ""}


def test_a_negative_amount_cash_row_is_treated_as_spending():
    assert classify_cash_transaction(_row("-50.00")) == "spending"


def test_a_positive_amount_cash_row_with_a_non_income_category_is_treated_as_a_refund():
    assert classify_cash_transaction(_row("50.00")) == "spending_refund"


def test_a_positive_amount_cash_row_with_an_income_category_is_treated_as_income():
    kind = classify_cash_transaction(_row("1000.00", category="Paychecks"))
    assert kind not in ("spending", "spending_refund"), (
        "a positive amount against a recognized income category must classify as income, not spending/refund"
    )


def test_investment_transaction_sign_convention_matches_the_cash_convention():
    # No investment-deposit/withdrawal or income-category text -- a bare
    # nonzero amount on an investment-account row is a transfer either way,
    # but the function must not misread the sign itself (e.g. treating a
    # negative investment amount as "neutral"/zero).
    assert classify_investment_transaction(_row("-500.00")) == "transfer"
    assert classify_investment_transaction(_row("500.00")) == "transfer"
    assert classify_investment_transaction(_row("0")) == "neutral"
