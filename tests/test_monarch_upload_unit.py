"""Monarch CSV upload (multi-user Phase 4, item 1): Monarch's own browser exports in, the existing import shapes out.

Synthetic data only. Account numbers are built from repeated digits at run time so no file holds one.
"""
from __future__ import annotations

import base64
import csv
import importlib.util
import io
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src import active_plan
from src import monarch_upload as mu
from src import ytd_tracking as ytd

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)
LONG_NUMBER = "4" * 9  # a synthetic 9-digit number; never a real one
TX_HEADER = ["Date", "Merchant", "Category", "Account", "Original Statement", "Notes", "Amount", "Tags", "Id"]


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "Monarch Extractor" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _csv_text(header, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _tx_rows():
    return [
        ["2026-10-01", "Grocer", "Groceries", "Joint Checking (...4821)", "GROCER 01", "", "-52.10", "", "tx-1"],
        ["2026-10-02", "Coffee", "Coffee Shops", "Joint Checking (...4821)", "COFFEE", "note", "-4.50", "a,b", "tx-2"],
        ["2026-10-03", "Payroll", "Paychecks", "Joint Checking (...4821)", "PAY", "", "2500.00", "", "tx-3"],
        ["2026-10-03", "No id", "Misc", "Joint Checking (...4821)", "", "", "-1.00", "", ""],
    ]


def _bal_text(accounts=("Joint Checking (...4821)", "Brokerage " + LONG_NUMBER), days=("2026-10-13", "10/14/2026")):
    return _csv_text(["Date", "Balance", "Account"],
                     [[d, f"${1000 * (i + 1):,}.00", a] for d in days for i, a in enumerate(accounts)])


def _workspace(tmp_path: Path) -> Path:
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    return base


def _body(kind: str, text: str, encoding: str = "utf-8", **extra) -> dict:
    return {"kind": kind, "filename": f"{kind}.csv", "content_base64": base64.b64encode(text.encode(encoding)).decode(),
            **extra}


# ---------------------------------------------------------------- parity with the extractor's normalisers

def test_transaction_normaliser_matches_the_extractor():
    me = _load("monarch_extract_parity", "monarch_extract.py")
    text = _csv_text(TX_HEADER + ["Extra Col!"], [r + ["x"] for r in _tx_rows()])
    ours = mu.normalize_transactions_text(text)
    theirs = [me.normalize_transaction(row, n) for n, row in enumerate(csv.DictReader(io.StringIO(text)), start=2)]
    assert [(t["id"], t["date"], t["merchant"], t["amount"], t["account"], t["category"], t["source_columns"])
            for t in ours] == [(t["id"], t["date"], t["merchant"], t["amount"], t["account"], t["category"],
                                t["source_columns"]) for t in theirs]


def test_balances_normaliser_matches_the_extractor(tmp_path):
    mb = _load("monarch_balances_parity", "monarch_balances.py")
    text = _bal_text()
    raw = tmp_path / "raw.csv"
    raw.write_text(text, encoding="utf-8")
    theirs = [(r["date"], r["account_key"], r["account"], r["balance"]) for r in mb.normalize_balances_csv(raw)]
    assert mu.normalize_balances_text(text) == theirs


# ---------------------------------------------------------------- decoding and shape checks

@pytest.mark.parametrize("body,needle", [
    ({}, "kind"),
    ({"kind": "holdings", "content_base64": "eA=="}, "kind"),
    ({"kind": "transactions"}, "content_base64"),
    ({"kind": "transactions", "content_base64": "not base64!!"}, "base64"),
    ({"kind": "transactions", "content_base64": ""}, "empty"),
])
def test_bad_bodies_are_refused(body, needle):
    with pytest.raises(mu.UploadError) as exc:
        mu.decode_upload(body)
    assert needle in str(exc.value)


def test_size_cap(monkeypatch):
    monkeypatch.setattr(mu, "MAX_BYTES", 10)
    with pytest.raises(mu.UploadError, match="too large"):
        mu.decode_upload(_body("transactions", "Date,Amount\n" + "x" * 20))


def test_row_cap(monkeypatch):
    monkeypatch.setattr(mu, "MAX_ROWS", 2)
    with pytest.raises(mu.UploadError, match="rows"):
        mu.normalize_transactions_text(_csv_text(TX_HEADER, _tx_rows()))


def test_windows_1252_is_accepted():
    kind, text, dry = mu.decode_upload(_body("transactions", _csv_text(TX_HEADER, [_tx_rows()[0][:1] + ["Café"] +
                                                                                 _tx_rows()[0][2:]]), "cp1252"))
    assert kind == "transactions" and "Café" in text and dry is False


def test_transactions_need_the_monarch_id_column():
    with pytest.raises(mu.UploadError, match="Id"):
        mu.normalize_transactions_text(_csv_text(TX_HEADER[:-1], [r[:-1] for r in _tx_rows()]))


def test_a_balances_file_sent_as_transactions_is_refused():
    with pytest.raises(mu.UploadError, match="balances"):
        mu.normalize_transactions_text(_bal_text())


def test_bad_balances_are_refused_with_masked_messages():
    text = _csv_text(["Date", "Balance", "Account"], [["2026-10-14", "abc", "Brokerage " + LONG_NUMBER]])
    with pytest.raises(mu.UploadError) as exc:
        mu.normalize_balances_text(text)
    assert "line 2" in str(exc.value)
    same_name = _csv_text(["Date", "Balance", "Account"], [["2026-10-14", "1", "Brokerage " + LONG_NUMBER],
                                                           ["2026-10-14", "2", "Brokerage " + LONG_NUMBER]])
    with pytest.raises(mu.UploadError) as exc:
        mu.normalize_balances_text(same_name)
    assert LONG_NUMBER not in str(exc.value) and LONG_NUMBER[-4:] in str(exc.value)


@pytest.mark.parametrize("raw,masked", [
    ("Brokerage " + LONG_NUMBER, "Brokerage …" + LONG_NUMBER[-4:]),
    ("Joint Checking (...4821)", "Joint Checking (...4821)"),
    ("Mortgage 1.99% 7/34", "Mortgage 1.99% 7/34"),
    ("ACCT " + "7" * 8, "ACCT …" + "7" * 4),  # acct-scan: ok
])
def test_mask_names(raw, masked):
    assert mu.mask_names(raw) == masked


# ---------------------------------------------------------------- import into a workspace

def _stored_transactions(base: Path) -> list[dict]:
    return ytd.read_transactions(base / "input")


def test_transactions_upload_upserts_and_is_idempotent(tmp_path):
    base = _workspace(tmp_path)
    body = _body("transactions", _csv_text(TX_HEADER, _tx_rows()))
    first, status = mu.handle_upload(base, body)
    assert status == 200 and first["success"], first
    assert (first["rows_read"], first["rows_without_id"], first["added"]) == (4, 1, 3)
    assert first["date_range"] == ["2026-10-01", "2026-10-03"]
    again, _ = mu.handle_upload(base, body)
    assert again["added"] == 0 and again["updated"] == 0
    stored = _stored_transactions(base)
    assert sorted(r.get("Monarch Id") for r in stored) == ["tx-1", "tx-2", "tx-3"]
    changed = _tx_rows()
    changed[0][2] = "Restaurants"
    third, _ = mu.handle_upload(base, _body("transactions", _csv_text(TX_HEADER, changed)))
    assert third["updated"] == 1


def test_duplicate_ids_in_one_file_keep_the_last(tmp_path):
    base = _workspace(tmp_path)
    rows = _tx_rows()[:2] + [["2026-10-02", "Coffee", "Coffee Shops", "Joint Checking (...4821)", "", "", "-9.99", "", "tx-2"]]
    out, _ = mu.handle_upload(base, _body("transactions", _csv_text(TX_HEADER, rows)))
    assert out["duplicates_in_file"] == 1 and out["added"] == 2
    amount = {r["Monarch Id"]: r["Amount"] for r in _stored_transactions(base)}["tx-2"]
    assert float(str(amount).replace("$", "")) == pytest.approx(-9.99)


def test_dry_run_writes_nothing(tmp_path):
    base = _workspace(tmp_path)
    out, status = mu.handle_upload(base, _body("transactions", _csv_text(TX_HEADER, _tx_rows()), dry_run=True))
    assert status == 200 and out["dry_run"] is True and out["rows_read"] == 4
    assert _stored_transactions(base) == []
    out, status = mu.handle_upload(base, _body("balances", _bal_text(), dry_run=True), today=TODAY, now=NOW)
    assert status == 200 and out["rows"] == 4
    assert not (base / "plan.rpx").exists() or _repo_count(base) == 0


def _repo_count(base: Path) -> int:
    with active_plan.workspace_store(base) as store:
        return store.monarch.count()


def test_balances_upload_goes_through_the_import_guards(tmp_path):
    base = _workspace(tmp_path)
    out, status = mu.handle_upload(base, _body("balances", _bal_text()), today=TODAY, now=NOW)
    assert status == 200 and out["status"] == "ok" and out["accounts"] == 2 and out["rows"] == 4, out
    with active_plan.workspace_store(base) as store:
        assert store.monarch.count() == 4
    stale, status = mu.handle_upload(base, _body("balances", _bal_text(days=("2026-09-01",))), today=TODAY, now=NOW)
    assert status == 400 and stale["status"] == "rejected" and "stale" in stale["error"]


def test_responses_never_carry_a_long_number(tmp_path):
    base = _workspace(tmp_path)
    out, _ = mu.handle_upload(base, _body("balances", _bal_text()), today=TODAY, now=NOW)
    assert LONG_NUMBER not in repr(out)
    assert "Brokerage …" + LONG_NUMBER[-4:] in out["account_names"]
    tx = _tx_rows()
    tx[0][3] = "Brokerage " + LONG_NUMBER
    out, _ = mu.handle_upload(base, _body("transactions", _csv_text(TX_HEADER, tx)))
    assert LONG_NUMBER not in repr(out)


def test_mapping_seed_copy_is_applied_after_balances_and_keeps_edits(tmp_path):
    base = _workspace(tmp_path)
    ytd.write_account_setup(base / "input", [{"Account": "House Checking", "Role": "Cash", "Current Balance": "1"}])
    seed = base / mu.MAPPING_SEED_RELPATH
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text(_csv_text(["Monarch", "App Location", "App Field", "Status", "Primary Source"], [
        ["Joint Checking (...4821)", "Other Assets and Liabilities", "House Checking", "Active", "Monarch"],
        ["Brokerage " + LONG_NUMBER, "", "IGNORE", "Active", "App"],
    ]), encoding="utf-8")
    out, _ = mu.handle_upload(base, _body("balances", _bal_text()), today=TODAY, now=NOW)
    assert out["mapping_seed"] == {"saved": 1, "pending": 0, "ignored": 1, "kept": 0, "not_in_monarch": 0, "skipped": 0}
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("joint checking (...4821)", "ignore", "", "app")  # the user's own edit
    out, _ = mu.handle_upload(base, _body("balances", _bal_text()), today=TODAY, now=NOW)
    assert out["mapping_seed"]["kept"] == 2
    with active_plan.workspace_store(base) as store:
        assert store.monarch.mapping()["joint checking (...4821)"]["kind"] == "ignore"
