"""Phase 2: account numbers are masked at import (broker file name + activity text, Monarch free text). Made-up numbers."""
import pytest

from src import active_plan, broker_import, ytd_tracking
from src.account_numbers import contains_account_number
from tests.broker_activity_fixtures import FILE_NAME, HEADER, FOOTER, history_csv

ACCT = "Member_1_HSA"
WIRE = '09/17/2026,WIRE TO ACCT 987654321 REF (Cash),"",No Description,Cash,"",0,"","","","-100",49.88,""'


@pytest.fixture
def ws(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    with active_plan.workspace_store(base, write=True) as store:
        store.dataset("holdings").replace_all([])
    return base / "input"


def test_broker_import_masks_file_name_and_text_but_keeps_keys(ws):
    text = "﻿\n\n" + HEADER + "\n" + WIRE + "\n" + FOOTER + "\n"
    pv = broker_import.preview(ws, broker="fidelity", text=text, file_name=FILE_NAME, account=ACCT)
    assert "12345678" not in pv["file_name"] and pv["file_name"].endswith("…5678.csv")
    row = pv["will_write"][0]
    assert not contains_account_number(row["action"]) and "…4321" in row["action"]
    broker_import.commit(ws, broker="fidelity", text=text, file_name=FILE_NAME, account=ACCT)
    with active_plan.workspace_store(ws.parent) as store:
        imps = store.broker.list_imports()
        acts = store.broker.activity(account=ACCT)
    assert imps and "987654321" not in repr(acts) and "12345678" not in repr(imps)
    # re-import still dedups (row_key computed before masking)
    again = broker_import.preview(ws, broker="fidelity", text=text, file_name=FILE_NAME, account=ACCT)
    assert again["will_write"] == []


def test_ytd_csv_masks_cue_words_only():
    csv = ("Date,Merchant,Category,Account,Original Statement,Notes,Amount\n"
           "2026-10-01,Transfer,Transfer,Checking,XFER TO ACCT 123456789,Payment id 1234567890123,-50\n")
    rows, errs = ytd_tracking.load_transactions_from_csv_text(csv)
    assert not errs
    assert rows[0]["Original Statement"] == "XFER TO ACCT …6789"
    assert rows[0]["Notes"] == "Payment id 1234567890123"


def test_hash_matches_masked_and_unmasked():
    a = {"Date": "2026-10-01", "Merchant": "X", "Original Statement": "TO ACCT 123456789", "Amount": "-5"}
    b = {**a, "Original Statement": "TO ACCT …6789"}
    assert ytd_tracking.transaction_hash(a) == ytd_tracking.transaction_hash(b)
