"""Morgan Stanley spells ACH withdrawals "WITHDRAWL"; they must still count as
investment withdrawals even when Monarch categorises them "Transfer"."""
from src.ytd_tracking import classify_investment_transaction


def _row(statement, amount, category="Transfer"):
    return {"Merchant": statement.title(), "Original Statement": statement,
            "Category": category, "Amount": amount}


def test_misspelled_ach_withdrawl_is_an_investment_withdrawal():
    assert classify_investment_transaction(_row("ACH WITHDRAWL  REFID:1;", "-60000.00")) == "investment_withdrawal"


def test_correctly_spelled_withdrawal_still_works():
    assert classify_investment_transaction(_row("ACH WITHDRAWAL REFID:1;", "-60000.00")) == "investment_withdrawal"


def test_internal_margin_sweeps_remain_transfers():
    assert classify_investment_transaction(_row("TRNSFR CASH TO MARGIN", "-60270.38")) == "transfer"


def _tagged(statement, amount, tag, category="Transfer"):
    r = _row(statement, amount, category)
    r["Tags"] = tag
    return r


def test_invest_withdrawal_tag_forces_a_withdrawal_even_with_unrecognised_text():
    assert classify_investment_transaction(_tagged("TRANSFER (OUTGOING)", "-355000.00", "invest-withdrawal")) == "investment_withdrawal"
    assert classify_investment_transaction(_tagged("RETURN EXCESS CONTR ADJ", "-1372.00", "Invest-Withdrawal")) == "investment_withdrawal"


def test_invest_deposit_tag_forces_a_deposit():
    assert classify_investment_transaction(_tagged("IAFRI JAN 16 UTC 20268212.0", "8212.00", "invest-deposit")) == "investment_deposit"


def test_untagged_hsa_correction_rows_stay_out_of_the_flows():
    assert classify_investment_transaction(_row("NORMAL DISTR PARTIAL ED1 /WEB (CASH)", "-1372.00")) == "transfer"
    assert classify_investment_transaction(_row("ADJ NORMAL DIST ADJ PROCESSED TAX", "1372.00")) == "transfer"


def test_wire_out_merchant_counts_as_a_withdrawal_without_a_tag():
    assert classify_investment_transaction(_row("WIRE OUT - TO BANK", "-860000.00")) == "investment_withdrawal"


def test_moves_into_an_annuity_are_not_investment_flows_even_when_tagged():
    # Liquid Investments and Cash shows the balance drop; Investment Net Flows must not.
    for text in ("WIRE OUT - IRA/401K TO ANNUITY", "Wire Out - IRA to Annuity"):
        assert classify_investment_transaction(_row(text, "-804000.00")) == "transfer"
        assert classify_investment_transaction(_tagged(text, "-804000.00", "invest-withdrawal")) == "transfer"
