"""Ticket 305: Monarch auto-update needs true upsert semantics -- replace a
changed transaction, add a new one -- keyed on a stored Monarch id, instead
of the existing append-only content-hash dedup used by manual CSV uploads.

See docs/superpowers/specs/2026-09-02-monarch-autoupdate-reporting-design.md.
"""
from __future__ import annotations

from datetime import date

from src import ytd_tracking as ytd


def _row(monarch_id: str, **overrides) -> dict:
    row = {
        "Date": "2026-03-04",
        "Merchant": "Kroger",
        "Category": "Groceries",
        "Account": "Checking",
        "Original Statement": "POS PURCHASE KROGER",
        "Notes": "",
        "Amount": "-52.10",
        "Tags": "",
        "Owner": "Member_1",
        "Monarch Id": monarch_id,
    }
    row.update(overrides)
    return row


def test_new_monarch_id_is_added(tmp_path):
    result = ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1")])
    assert result["added"] == 1
    assert result["updated"] == 0
    stored = ytd.read_transactions(tmp_path)
    assert len(stored) == 1
    assert stored[0]["Monarch Id"] == "mid-1"


def test_same_id_same_content_is_a_noop(tmp_path):
    ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1")])
    result = ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1")])
    assert result["added"] == 0
    assert result["updated"] == 0
    assert len(ytd.read_transactions(tmp_path)) == 1


def test_same_id_changed_content_replaces_in_place(tmp_path):
    ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1", Category="Groceries")])
    result = ytd.upsert_transactions_by_monarch_id(
        tmp_path, [_row("mid-1", Category="Dining", Amount="-61.40")]
    )
    assert result["added"] == 0
    assert result["updated"] == 1
    stored = ytd.read_transactions(tmp_path)
    assert len(stored) == 1
    assert stored[0]["Category"] == "Dining"
    assert float(stored[0]["Amount"]) == -61.40


def test_new_and_changed_in_the_same_batch(tmp_path):
    ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1"), _row("mid-2", Merchant="Costco")])
    result = ytd.upsert_transactions_by_monarch_id(
        tmp_path,
        [
            _row("mid-1", Category="Dining"),  # changed
            _row("mid-2", Merchant="Costco"),  # unchanged
            _row("mid-3", Merchant="Target"),  # new
        ],
    )
    assert result["added"] == 1
    assert result["updated"] == 1
    stored = {r["Monarch Id"]: r for r in ytd.read_transactions(tmp_path)}
    assert len(stored) == 3
    assert stored["mid-1"]["Category"] == "Dining"
    assert stored["mid-3"]["Merchant"] == "Target"


def test_row_without_monarch_id_falls_back_to_hash_dedup(tmp_path):
    no_id_row = _row("", Date="2026-01-05")
    result = ytd.upsert_transactions_by_monarch_id(tmp_path, [no_id_row])
    assert result["added"] == 1

    # Re-importing the identical id-less row is skipped (existing hash-based
    # dedup), same as manual-upload import_transactions() behavior.
    result = ytd.upsert_transactions_by_monarch_id(tmp_path, [no_id_row])
    assert result["added"] == 0
    assert result["skipped"] == 1
    assert len(ytd.read_transactions(tmp_path)) == 1


def test_manual_hash_dedup_is_unaffected_by_the_monarch_id_column(tmp_path):
    # A manually-entered row (no Monarch Id) written before this feature
    # existed must still hash and dedup identically -- adding "Monarch Id" to
    # TRANSACTION_COLUMNS must not perturb transaction_hash() for such rows.
    row = _row("", Date="2026-02-01")
    del row["Monarch Id"]
    ytd.write_transactions(tmp_path, [row])
    existing = ytd.read_transactions(tmp_path)
    assert ytd.transaction_hash(existing[0]) == ytd.transaction_hash(_row("", Date="2026-02-01"))


def test_invalid_date_rows_are_skipped_not_crashed(tmp_path):
    result = ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1", Date="")])
    assert result["added"] == 0
    assert result["invalid_date_rows"] == 1


def test_import_history_records_monarch_auto_mode_and_updated_count(tmp_path):
    ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1")])
    ytd.upsert_transactions_by_monarch_id(tmp_path, [_row("mid-1", Category="Dining")])
    history = ytd.read_import_history(tmp_path)
    assert history[-1]["Mode"] == "monarch_auto"
    assert history[-1]["Rows Updated"] == "1"
