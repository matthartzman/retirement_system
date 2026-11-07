"""A checking-account row's free-text Notes must not turn spending into an investment transfer.

Notes are where people write "50% of carpet - deposit" or "Cash in Sitges"; matching the
investment-flow words there hid real Home Improvement, Travel and fee spending from every
spending view. Merchant, statement, category and tag text still identify transfers, and an
explicit ``invest-deposit`` / ``invest-withdrawal`` override in Notes still wins.
"""
from src import ytd_tracking as Y


def _row(**kw):
    base = {"Date": "2026-04-08", "Merchant": "Check 1129", "Category": "Home Improvement",
            "Account": "Family Checking", "Original Statement": "Check 1129",
            "Notes": "", "Tags": "", "Amount": "-5631.88"}
    base.update(kw)
    return base


def test_deposit_word_in_notes_stays_spending():
    assert Y.classify_cash_transaction(_row(Notes="50% of carpet - deposit")) == "spending"


def test_cash_in_phrase_in_notes_stays_spending():
    row = _row(Merchant="Banco Santander Sitges", Category="Travel & Vacation",
               **{"Original Statement": "BANCO SANTANDER", "Notes": "Cash in Sitges", "Amount": "-166.26"})
    assert Y.classify_cash_transaction(row) == "spending"


def test_withdrawal_word_in_notes_stays_spending():
    assert Y.classify_cash_transaction(_row(Notes="paid after the withdrawal cleared")) == "spending"


def test_statement_and_merchant_text_still_mark_transfers():
    assert Y.classify_cash_transaction(_row(**{"Original Statement": "ACH TO BROKERAGE"})) == "transfer"
    assert Y.classify_cash_transaction(_row(Merchant="IRA Contribution")) == "transfer"
    assert Y.classify_cash_transaction(_row(Merchant="Fidelity", **{"Original Statement": "WIRE OUT"})) == "transfer"


def test_tag_still_marks_transfer():
    assert Y.classify_cash_transaction(_row(Tags="invest-deposit")) == "transfer"


def test_explicit_override_in_notes_still_marks_transfer():
    assert Y.classify_cash_transaction(_row(Notes="invest-deposit Trust - Matt")) == "transfer"
    assert Y.classify_cash_transaction(_row(Notes="invest-withdrawal", Amount="250")) == "transfer"
