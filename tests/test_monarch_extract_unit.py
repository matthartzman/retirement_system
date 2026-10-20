"""WI-011 / QA-004: behavioural tests for the Monarch extractor's data logic.

monarch_extract.py lives in a folder with a space, so it is loaded by path.
Everything runs against tmp_path: no network, no browser, no writes beside the
script. Fixture values are synthetic.
"""
from __future__ import annotations

import copy
import csv
import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "Monarch Extractor" / "monarch_extract.py"


def _load():
    spec = importlib.util.spec_from_file_location("monarch_extract_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def me(tmp_path, monkeypatch):
    mod = _load()
    out = tmp_path / "output"
    monkeypatch.setattr(mod, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(mod, "OUTPUT_DIR", out)
    monkeypatch.setattr(mod, "HISTORY_FILE", out / "transactions.csv")
    monkeypatch.setattr(mod, "NEW_FILE", out / "new_transactions.csv")
    monkeypatch.setattr(mod, "CHANGED_FILE", out / "changed_transactions.csv")
    monkeypatch.setattr(mod, "DUPLICATES_FILE", out / "duplicates_removed.csv")
    monkeypatch.setattr(mod, "STATE_DB", out / "monarch_state.sqlite3")
    mod.init_database()
    return mod


def _row(**over):
    base = {"Id": "t1", "Date": "2026-01-02", "Merchant": "Shop", "Amount": "-10.00",
            "Account": "Checking", "Category": "Food", "Notes": "n"}
    base.update(over)
    return base


def _tx(me, **over):
    return me.normalize_transaction(_row(**over), 2)


def _outbox(me):
    con = sqlite3.connect(me.STATE_DB)
    try:
        return con.execute(
            "SELECT transaction_id, change_type, delivery_status FROM outbox ORDER BY created_at, event_id"
        ).fetchall()
    finally:
        con.close()


def test_dirs_are_created_lazily(tmp_path):
    mod = _load()
    mod.RAW_DIR = tmp_path / "r"
    mod.OUTPUT_DIR = tmp_path / "o"
    assert not mod.RAW_DIR.exists() and not mod.OUTPUT_DIR.exists()
    mod.ensure_dirs()
    assert mod.RAW_DIR.is_dir() and mod.OUTPUT_DIR.is_dir()


# ---- fingerprinting -------------------------------------------------------

def test_fingerprint_stable_and_key_order_independent(me):
    a = _tx(me)
    b = copy.deepcopy(a)
    b["source_columns"] = dict(reversed(list(a["source_columns"].items())))
    assert me.transaction_fingerprint(a) == me.transaction_fingerprint(b)


@pytest.mark.parametrize("field,value", [
    ("id", "t2"), ("date", "2026-01-03"), ("merchant", "Other"),
    ("amount", "-11.00"), ("account", "Savings"), ("category", "Fun"),
])
def test_fingerprint_changes_with_each_input_field(me, field, value):
    base = _tx(me)
    mutated = dict(base)
    mutated[field] = value
    assert me.transaction_fingerprint(base) != me.transaction_fingerprint(mutated)


def test_fingerprint_changes_with_source_columns(me):
    base = _tx(me)
    mutated = copy.deepcopy(base)
    mutated["source_columns"]["notes"] = "different"
    assert me.transaction_fingerprint(base) != me.transaction_fingerprint(mutated)


def test_fingerprint_ignores_row_key(me):
    base = _tx(me)
    other = dict(base, row_key="something-else")
    assert me.transaction_fingerprint(base) == me.transaction_fingerprint(other)


def test_fingerprint_mutation_check_inputs_are_all_load_bearing(me):
    """Mutation-style check: simulate a fingerprint that drops each input in
    turn and show it would miss a change the real function detects."""
    base = _tx(me)
    real = me.transaction_fingerprint
    for dropped in ("id", "date", "merchant", "amount", "account", "category", "source_columns"):
        def mutant(tx, _d=dropped):
            tx = dict(tx)
            tx.pop(_d, None)
            return real(tx)
        changed = copy.deepcopy(base)
        if dropped == "source_columns":
            changed["source_columns"]["notes"] = "zzz"
        else:
            changed[dropped] = "zzz"
        assert real(base) != real(changed), dropped
        assert mutant(base) == mutant(changed), dropped


# ---- normalisation / id-less rows ----------------------------------------

@pytest.mark.parametrize("row,expected", [
    ({"Id": " abc "}, "abc"),
    ({"id": "abc"}, "abc"),
    ({"Id": ""}, ""),
    ({"Merchant": "X"}, ""),
])
def test_monarch_transaction_id_table(me, row, expected):
    assert me.monarch_transaction_id(row) == expected


def test_idless_rows_get_run_local_key_and_no_events(me):
    txs = [me.normalize_transaction(_row(Id=""), 2), me.normalize_transaction(_row(Id=""), 3)]
    assert [t["row_key"] for t in txs] == ["missing-monarch-id-row-2", "missing-monarch-id-row-3"]
    _, new, changed = me.compare_and_record(txs, "x.csv", "Last 30 days")
    assert (new, changed) == (0, 0)
    assert _outbox(me) == []


# ---- once-only events -----------------------------------------------------

def test_repeated_export_creates_no_new_events(me):
    txs = [_tx(me), _tx(me, Id="t2")]
    assert me.compare_and_record(txs, "a.csv", "p")[1:] == (2, 0)
    assert me.compare_and_record(txs, "a.csv", "p")[1:] == (0, 0)
    assert len(_outbox(me)) == 2


def test_changed_amount_creates_exactly_one_changed_event(me):
    me.compare_and_record([_tx(me)], "a.csv", "p")
    _, new, changed = me.compare_and_record([_tx(me, Amount="-99.00")], "b.csv", "p")
    assert (new, changed) == (0, 1)
    assert sorted(r[1] for r in _outbox(me)) == ["changed", "new"]
    assert me.compare_and_record([_tx(me, Amount="-99.00")], "c.csv", "p")[1:] == (0, 0)
    assert len(_outbox(me)) == 2


def test_pending_events_span_runs(me):
    me.compare_and_record([_tx(me)], "a", "p")
    me.compare_and_record([_tx(me, Id="t2")], "b", "p")
    ids = sorted(e["transaction"]["id"] for e in me.get_all_pending_events())
    assert ids == ["t1", "t2"]


# ---- mark delivered -------------------------------------------------------

def test_mark_run_delivered_clears_only_that_run(me):
    run1, *_ = me.compare_and_record([_tx(me)], "a", "p")
    run2, *_ = me.compare_and_record([_tx(me, Id="t2")], "b", "p")
    me.mark_run_delivered(run1)
    status = {r[0]: r[2] for r in _outbox(me)}
    assert status == {"t1": "delivered", "t2": "pending"}
    assert [e["transaction"]["id"] for e in me.get_all_pending_events()] == ["t2"]
    con = sqlite3.connect(me.STATE_DB)
    try:
        assert con.execute("SELECT status FROM runs WHERE run_id=?", (run1,)).fetchone()[0] == "delivered"
        assert con.execute("SELECT status FROM runs WHERE run_id=?", (run2,)).fetchone()[0] == "ready"
    finally:
        con.close()


@pytest.mark.parametrize("which", ["unknown", "twice"])
def test_mark_run_delivered_errors(me, which):
    run, *_ = me.compare_and_record([_tx(me)], "a", "p")
    if which == "twice":
        me.mark_run_delivered(run)
        target = run
    else:
        target = "no-such-run"
    with pytest.raises(RuntimeError, match="No pending events"):
        me.mark_run_delivered(target)


# ---- history CSV: round trip and atomic write -----------------------------

def test_history_round_trip(me):
    txs = {t["id"]: t for t in (_tx(me), _tx(me, Id="t2", Date="2026-02-01"))}
    me.save_history_csv(txs)
    loaded = me.load_history_csv()
    assert set(loaded) == {"t1", "t2"}
    assert loaded["t1"]["amount"] == "-10.00"
    assert list(me.OUTPUT_DIR.glob("*.tmp")) == []


def test_history_write_is_atomic_on_failure(me, monkeypatch):
    me.save_history_csv({"t1": _tx(me)})
    before = me.HISTORY_FILE.read_bytes()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(me.csv.DictWriter, "writerow", boom)
    with pytest.raises(OSError):
        me.save_history_csv({"t1": _tx(me), "t2": _tx(me, Id="t2")})
    assert me.HISTORY_FILE.read_bytes() == before
    assert list(me.OUTPUT_DIR.glob("*.tmp")) == []


def test_read_csv_normalizes_and_keeps_idless(me, tmp_path):
    path = tmp_path / "raw.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Id", "Date", "Merchant", "Amount"])
        w.writeheader()
        w.writerow({"Id": "a", "Date": "2026-01-01", "Merchant": "M", "Amount": "1"})
        w.writerow({"Id": "", "Date": "2026-01-02", "Merchant": "N", "Amount": "2"})
    rows = me.read_csv(path)
    assert [r["id"] for r in rows] == ["a", ""]
    assert rows[1]["row_key"] == "missing-monarch-id-row-3"
