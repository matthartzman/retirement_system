"""Direct coverage for spending_tracker.recover_spending_budget_from_seed.

WI-404 (system review 2026-09-25-2, QA-006, carried forward from the prior
review's QA-006): the one function meant to recover a spending budget that a
UI/autosave regression zeroed out had no direct tests. Its contract:

* no seed file, or a seed with no nonzero values -> success False, nothing written;
* force=False fills only missing/zero rows and never overwrites a current
  nonzero budget; force=True lets seed values win;
* persist=True writes the merged budget and keeps a one-time
  ``.pre_recovery_backup`` copy of the pre-recovery budget rows (the budget itself is the plan
  file's ``spending_budget`` table since WP6.3b; the seed and the backup stay files until WP6.3c); persist=False writes nothing.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from src.spending_tracker import _BUDGET_HEADER, recover_spending_budget_from_seed
from tests.plan_fixture import plan_dataset_rows, write_plan_dataset

BUDGET = "client_spending_budget.csv"
SEED = "client_spending_budget.recovery_seed.csv"


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_BUDGET_HEADER, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _BUDGET_HEADER})


def _csv_text(rows: list[dict]) -> str:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=_BUDGET_HEADER, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in _BUDGET_HEADER})
    return buf.getvalue()


def _put_budget(root: Path, rows: list[dict]) -> str:
    """The budget goes into the plan's ``spending_budget`` table; returns its CSV text."""
    text = _csv_text(rows)
    write_plan_dataset(root, BUDGET, text)
    return text


def _budget_rows(root: Path) -> list[dict]:
    return plan_dataset_rows(root, BUDGET)


def _read_amounts(root: Path) -> dict[tuple[str, str], str]:
    return {(r["kind"], r["key"]): r["annual_budget"] for r in _budget_rows(root)}


def _row(kind, key, amount, label=""):
    return {"kind": kind, "key": key, "label": label or key, "annual_budget": amount}


@pytest.fixture
def root(tmp_path):
    # Zeroed-out budget (the autosave-regression shape) plus one nonzero user edit.
    _put_budget(tmp_path, [
        _row("category", "groceries", "0"),
        _row("category", "dining", "4800"),
        _row("group", "grp::Core Expenses::Home", ""),
    ])
    _write(tmp_path / "input" / SEED, [
        _row("category", "groceries", "12000"),
        _row("category", "dining", "6000"),
        _row("group", "grp::Core Expenses::Home", "9000"),
        _row("category", "utilities", "3600"),
        _row("category", "zero_in_seed", "0"),
    ])
    return tmp_path


def test_missing_seed_reports_failure_and_writes_nothing(tmp_path):
    _put_budget(tmp_path, [_row("category", "groceries", "0")])
    before = _budget_rows(tmp_path)
    status = recover_spending_budget_from_seed(tmp_path)
    assert status["success"] is False and status["recovered"] == 0
    assert "seed" in status["error"].lower()
    assert _budget_rows(tmp_path) == before


def test_all_zero_seed_reports_failure(tmp_path):
    _put_budget(tmp_path, [_row("category", "groceries", "0")])
    _write(tmp_path / "input" / SEED, [_row("category", "groceries", "0")])
    status = recover_spending_budget_from_seed(tmp_path)
    assert status["success"] is False and status["recovered"] == 0
    assert not (tmp_path / "input" / (BUDGET + ".pre_recovery_backup")).exists()


def test_fills_only_zero_or_missing_rows_and_keeps_nonzero_edits(root):
    original = _csv_text(_budget_rows(root))
    status = recover_spending_budget_from_seed(root)

    assert status["success"] is True
    # groceries (zero), the Home group (blank) and utilities (missing) -- not
    # dining (nonzero user edit) and not the zero-valued seed row.
    assert status["recovered"] == 3
    assert status["current_total_before"] == 4800
    assert status["seed_total"] == 12000 + 6000 + 9000 + 3600
    assert status["current_total_after"] == 12000 + 4800 + 9000 + 3600

    amounts = _read_amounts(root)
    assert amounts[("category", "groceries")] == "12000"
    assert amounts[("category", "dining")] == "4800"
    assert amounts[("group", "grp::Core Expenses::Home")] == "9000"
    assert amounts[("category", "utilities")] == "3600"
    assert ("category", "zero_in_seed") not in amounts

    backup = root / "input" / (BUDGET + ".pre_recovery_backup")
    assert backup.read_text(encoding="utf-8") == original.replace("\r\n", "\n")


def test_force_lets_seed_overwrite_nonzero_rows(root):
    status = recover_spending_budget_from_seed(root, force=True)
    assert status["success"] is True
    assert _read_amounts(root)[("category", "dining")] == "6000"


def test_persist_false_computes_status_without_writing(root):
    before = _budget_rows(root)
    status = recover_spending_budget_from_seed(root, persist=False)
    assert status["success"] is True and status["recovered"] == 3
    assert status["current_total_after"] == 12000 + 4800 + 9000 + 3600
    assert _budget_rows(root) == before
    assert not (root / "input" / (BUDGET + ".pre_recovery_backup")).exists()


def test_second_run_is_a_no_op_and_keeps_the_first_backup(root):
    original = _csv_text(_budget_rows(root))
    recover_spending_budget_from_seed(root)
    after_first = _budget_rows(root)

    status = recover_spending_budget_from_seed(root)
    assert status["success"] is True and status["recovered"] == 0
    assert _budget_rows(root) == after_first
    # The backup still holds the ORIGINAL pre-recovery file, not the recovered one.
    assert (root / "input" / (BUDGET + ".pre_recovery_backup")).read_text(encoding="utf-8") == original.replace("\r\n", "\n")
