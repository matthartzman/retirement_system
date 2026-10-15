"""Phase 1 of the Monarch balances feed: the extractor's normalizer.

monarch_balances.py lives in the "Monarch Extractor" folder (name has a space),
so it is loaded by path. It imports playwright lazily, so no venv is needed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "Monarch Extractor" / "monarch_balances.py"
_spec = importlib.util.spec_from_file_location("monarch_balances", _SCRIPT)
mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mb)


def _write(tmp_path, text, encoding="utf-8"):
    path = tmp_path / "raw.csv"
    path.write_bytes(text.encode(encoding))
    return path


def test_accepts_us_and_iso_dates_and_cosmetic_amounts(tmp_path):
    path = _write(tmp_path, "Date,Balance,Account\n1/10/2024,-359600.74,Mortgage\n2024-01-11,168376.00,Mortgage\n")
    rows = mb.normalize_balances_csv(path)
    assert [(r["date"], r["balance"]) for r in rows] == [("2024-01-10", -359600.74), ("2024-01-11", 168376.0)]


def test_name_cleaning_and_key(tmp_path):
    path = _write(tmp_path, "Date,Balance,Account\n2026-01-01,1,Trust  Under Agreement  \n2026-01-01,2,Platinum Card® (...1008)\n", "utf-8-sig")
    rows = {r["account"]: r for r in mb.normalize_balances_csv(path)}
    assert "Trust Under Agreement" in rows
    assert "Platinum Card® (...1008)" in rows
    assert rows["Trust Under Agreement"]["account_key"] == "trust under agreement"


def test_duplicate_date_account_keeps_last(tmp_path):
    path = _write(tmp_path, "Date,Balance,Account\n2026-01-01,1,A\n2026-01-01,2,a \n")
    rows = mb.normalize_balances_csv(path)
    assert len(rows) == 1 and rows[0]["balance"] == 2.0


@pytest.mark.parametrize("body", [
    "Date,Amount,Account\n2026-01-01,1,A\n",          # wrong header
    "Date,Balance,Account\n",                          # empty
    "Date,Balance,Account\nnot-a-date,1,A\n",          # bad date
    "Date,Balance,Account\n2026-01-01,abc,A\n",        # bad amount
    "Date,Balance,Account\n2026-01-01,1,\n",           # empty account
    "Date,Balance,Account\n2026-01-01,1\n",            # short row
])
def test_bad_exports_are_rejected(tmp_path, body):
    with pytest.raises(ValueError):
        mb.normalize_balances_csv(_write(tmp_path, body))


def test_write_is_atomic_and_round_trips(tmp_path):
    rows = [{"date": "2026-01-01", "account_key": "a", "account": "A", "balance": 1.5}]
    out = tmp_path / "out" / "balances.csv"
    mb.write_balances_csv(rows, out)
    assert out.read_text(encoding="utf-8").splitlines() == ["date,account_key,account,balance", "2026-01-01,a,A,1.5"]
    assert not out.with_name(out.name + ".tmp").exists()
