"""Phase 4 guards: response scan, repo scan tool, logging filter, synced-folder warning. Made-up numbers only."""
import importlib.util
import json
import logging
from pathlib import Path

import pytest

from src import active_plan, onedrive_guard
from src.account_numbers import MaskingFilter, contains_account_number
from src.server import app, plan_routes
from tests.broker_activity_fixtures import FILE_NAME, HEADER, FOOTER

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("scan_tool", ROOT / "tools" / "check_no_account_numbers.py")
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)

ACCT = "Member_1_HSA"
BIG = "987654321"
WIRE = f'09/17/2026,WIRE TO ACCT {BIG} REF (Cash),"",No Description,Cash,"",0,"","","","-100",49.88,""'


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("holdings").replace_all([])
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: tmp_path / "input")
    return app.test_client()


def test_broker_and_sales_responses_hold_no_full_number(client):
    text = "\ufeff\n\n" + HEADER + "\n" + WIRE + "\n" + FOOTER + "\n"
    body = {"broker": "fidelity", "content": text, "file_name": FILE_NAME, "account": ACCT}
    seen = [client.post("/api/sales/broker/preview", json=body).get_data(as_text=True),
            client.post("/api/sales/broker/commit", json=body).get_data(as_text=True)]
    for url in ("/api/sales/broker/imports", "/api/sales/broker/income", "/api/sales", "/api/sales/candidates"):
        seen.append(client.get(url).get_data(as_text=True))
    blob = "\n".join(seen)
    assert json.loads(seen[0])  # real response
    for fake in (BIG, "12345678"):
        assert fake not in blob
    assert not contains_account_number(blob, known_ids=[BIG, "12345678"])


def test_repo_scan_flags_cue_and_listed_numbers_without_echoing():
    assert scan.scan_text("ok line\nsend to ACCT 123456789\n", []) == [(2, "cue-word number")]
    assert scan.scan_text("x 5551230099 y", ["5551230099"]) == [(1, "listed number")]
    assert scan.scan_text("send to ACCT 123456789  # acct-scan: ok", []) == []
    assert scan.scan_text("CUSIP 037833100 amount 1,234,567.89", []) == []


def test_repo_scan_passes_on_this_repo():
    assert scan.main() == 0


def test_logging_filter_masks_numbers():
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "wire to ACCT %s done", ("123456789",), None)
    MaskingFilter().filter(rec)
    assert rec.getMessage() == "wire to ACCT \u20266789 done"


def test_synced_folder_warning():
    assert onedrive_guard.synced_folder_warning(Path("C:/Users/x/OneDrive - Co/plans/plan.rpx"))
    assert onedrive_guard.synced_folder_warning(Path("/home/x/Dropbox/backups"))
    assert onedrive_guard.synced_folder_warning(Path("C:/RetirementPlanning/plan.rpx")) is None
