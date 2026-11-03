"""Phase 3: tools/redact_account_numbers.py (synthetic numbers; counts only; idempotent; row_key untouched)."""
import importlib.util
from pathlib import Path

import pytest

from src import active_plan

_spec = importlib.util.spec_from_file_location("redact_tool", Path(__file__).resolve().parent.parent / "tools" / "redact_account_numbers.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

BIG = "987654321"


@pytest.fixture
def ws(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    with active_plan.workspace_store(base, write=True) as store:
        iid = store.broker.add_import(broker="fidelity", account="A1", file_name="History_for_Account_X12345678.csv")
        store.broker.add_rows(iid, [{"row_key": "k1#0", "broker": "fidelity", "account": "A1", "run_date": "2026-09-17",
                                     "kind": "other", "action": f"WIRE TO ACCT {BIG}", "symbol": "",
                                     "description": "No Description", "amount": -100.0}])
        store.dataset("ytd_transactions").replace_all([
            {"Date": "2026-10-01", "Merchant": "Xfer", "Category": "T", "Account": "C", "Original Statement": f"TO ACCT {BIG}",
             "Notes": "pay 1234567890123", "Amount": "-5"}])
    return base


def test_dry_run_counts_only_and_changes_nothing(ws, capsys):
    res = tool.redact(ws)
    assert res["counts"] == {"broker_imports.file_name": 1, "broker_activity.rows": 1, "ytd_transactions.rows": 1}
    assert not res["applied"]
    with active_plan.workspace_store(ws) as store:
        assert BIG in repr(store.broker.activity(account="A1"))


def test_apply_redacts_keeps_key_and_is_idempotent(ws):
    res = tool.redact(ws, apply=True)
    assert res["applied"] and res["backup"]
    with active_plan.workspace_store(ws) as store:
        acts = store.broker.activity(account="A1")
        assert BIG not in repr(acts) and acts[0]["row_key"] == "k1#0"
        assert "12345678" not in repr(store.broker.list_imports())
        ytd = store.dataset("ytd_transactions").rows()[0]
        assert BIG not in ytd["Original Statement"] and ytd["Notes"] == "pay 1234567890123"
    again = tool.redact(ws, apply=True)
    assert not again["applied"] and sum(again["counts"].values()) == 0
