"""Unit tests for src/account_numbers.py. All numbers are made up."""
from src.account_numbers import contains_account_number, last4, mask_file_name, mask_text

E = "…"


def test_last4():
    assert last4("Z12345678") == "5678"
    assert last4("12") == "12" and last4("") == "" and last4(None) == ""


def test_file_name_masked_to_last4():
    assert mask_file_name("History_for_Account_Z98765432 (2).csv") == f"History_for_Account_Z{E}5432 (2).csv"
    assert mask_file_name("History_for_Account_98765432 (2).csv") == f"History_for_Account_{E}5432 (2).csv"
    assert mask_file_name("report-2026.csv") == "report-2026.csv"  # 4-digit year survives


def test_cue_words():
    assert mask_text("WIRE TO ACCT 123456789 REF") == f"WIRE TO ACCT {E}6789 REF"
    assert mask_text("Account #: 98765432") == f"Account #: {E}5432"
    assert mask_text("from a/c 1234-5678-90") == f"from a/c {E}7890"
    assert mask_text("ACC#44556677") == f"ACC#{E}6677"
    assert mask_text("ROUTING 021000021") == f"ROUTING {E}0021"
    assert mask_text("IBAN 12345678901234") == f"IBAN {E}1234"


def test_transfer_reference_form():
    assert mask_text("XFER XXXX-0042 OUT") == "XFER XXXX-0042 OUT"
    assert mask_text("XFER XXXXX-4821-7 OUT") == f"XFER {E}4821 OUT"


def test_cusip_amounts_and_ids_survive():
    for s in ["BUY 037833100 APPLE", "Payment id 1234567890123", "Check 100245 cleared",
              "SELL 1,234,567.89 shares", "Order confirmation 987654321", "ISIN US0378331005"]:
        assert mask_text(s) == s and not contains_account_number(s)


def test_idempotent():
    once = mask_text("TO ACCT 123456789 AND XXXXX-1234-5")
    assert mask_text(once) == once and not contains_account_number(once)
    f = mask_file_name("a_12345678.csv")
    assert mask_file_name(f) == f


def test_last4_alone_allowed():
    assert mask_text("ACCT 1234") == "ACCT 1234"
    assert mask_text("fidelity:1234") == "fidelity:1234"


def test_known_ids_masked_without_cue():
    assert mask_text("memo 5551230099 sent", known_ids=["555-123-0099"]) == f"memo {E}0099 sent"
    assert mask_text("memo 555-123-0099 sent", known_ids=["5551230099"]) == f"memo {E}0099 sent"
    assert contains_account_number("x 5551230099", known_ids=["5551230099"])


def test_exempt_symbol_cue_collision():
    # a CUSIP that sits next to a cue word is never masked when it is the row's own field
    assert mask_text("ACCT 037833100", exempt=["037833100"]) == "ACCT 037833100"


def test_none_and_empty():
    assert mask_text(None) == "" and mask_text("") == "" and mask_file_name(None) == ""
