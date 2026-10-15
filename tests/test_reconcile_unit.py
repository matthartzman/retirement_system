"""R2 of the reconciliation page: pairing app numbers with Monarch's, and the preview/apply/undo writes."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src import active_plan, reconcile
from src import monarch_balances_import as mbi
from src import ytd_tracking as ytd

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc)

SETUP = [
    {"Account": "Family Checking", "Role": "Cash / spending", "Current Balance": "13000"},
    {"Account": "Visa Card", "Role": "Credit card", "Current Balance": "900"},
    {"Account": "Home Loan", "Role": "Mortgage", "Current Balance": "283000"},
    {"Account": "Private Note", "Role": "Offline asset", "Current Value": "500000"},
    {"Account": "Paid Annuity", "Role": "Annuity", "Current Value": "50000"},
    {"Account": "Brokerage A", "Role": "Investment", "Mapped Investment Account": "Brokerage A", "Current Value": "1000"},
    {"Account": "Empty Unmatched", "Role": "Cash / spending"},
]
MONARCH = [  # account_key, display name, balance on the latest day
    ("family checking", "Family Checking", 13894.27),
    ("visa card", "Visa Card", -10021.20),
    ("home loan", "Home Loan", -283204.0),
    ("private note", "Private Note", 512847.98),
    ("paid annuity", "Paid Annuity", 50896.0),
    ("brokerage a", "Brokerage A", 105808.52),
    ("house", "114 Main St", 1279500.0),
    ("car one", "2016 Car", 10244.38),
    ("car two", "2023 Car", 42971.50),
    ("mystery", "Mystery Account", 77.0),
    ("zero", "Zero Account", 0.0),
]


def _workspace(tmp_path: Path) -> Path:
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", SETUP)
    with active_plan.workspace_store(base, write=True) as store:
        store.set_value("Other Assets", "Home", "value_as_of_plan_start", "1313000")
        store.set_value("Other Assets", "Autos", "value", "50000")
        store.set_value("Cashflow", "Mortgage", "balance_as_of_plan_start", "293284")
    csv_path = base / "Monarch Extractor" / "output" / "balances.csv"
    csv_path.parent.mkdir(parents=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(mbi.EXPECTED_HEADER)
        for d in ("2026-10-13", "2026-10-14"):
            for key, name, bal in MONARCH:
                w.writerow([d, key, name, bal])
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    return base


def _rows(base, **kw):
    return {r["id"]: r for r in reconcile.build_rows(base / "input", today=TODAY, **kw)["rows"]}


def test_no_balances_yet(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", SETUP)
    assert reconcile.build_rows(base / "input", today=TODAY)["has_balances"] is False


def test_automatic_name_matches_and_differences(tmp_path):
    rows = _rows(_workspace(tmp_path))
    chk = rows["setup:Family Checking"]
    assert (chk["app_value"], chk["monarch_value"], chk["difference"], chk["status"]) == (13000.0, 13894.27, 894.27, "differs")
    assert chk["updatable"] and chk["auto_matched"] and chk["group"] == reconcile.GROUP_CASH
    assert chk["write"] == {"kind": "setup_account", "ref": "Family Checking", "field": "Current Value", "old": "13000", "new": "13894.27"}


def test_liabilities_compare_by_magnitude_and_write_positive(tmp_path):
    rows = _rows(_workspace(tmp_path))
    visa = rows["setup:Visa Card"]
    assert visa["monarch_value"] == 10021.20 and visa["difference"] == 9121.20 and visa["write"]["new"] == "10021.20"
    loan = rows["setup:Home Loan"]
    assert loan["monarch_value"] == 283204.0 and loan["difference"] == 204.0


def test_manual_account_updates_current_value_field(tmp_path):
    note = _rows(_workspace(tmp_path))["setup:Private Note"]
    assert note["group"] == reconcile.GROUP_MANUAL and note["write"]["field"] == "Current Value" and note["write"]["new"] == "512847.98"


def test_investments_are_report_only(tmp_path):
    inv = _rows(_workspace(tmp_path))["setup:Brokerage A"]
    assert inv["status"] == "report_only" and not inv["updatable"] and inv["write"] is None
    assert inv["difference"] is not None and "Holdings" in inv["report_reason"]
    assert inv["group"] == reconcile.GROUP_INVEST


def test_tolerance_decides_match(tmp_path):
    base = _workspace(tmp_path)
    assert _rows(base, tolerance=5000.0)["setup:Family Checking"]["status"] == "match"
    assert _rows(base, tolerance=1.0)["setup:Family Checking"]["status"] == "differs"


def test_blank_unmatched_app_rows_are_hidden_and_unmatched_monarch_listed(tmp_path):
    data = reconcile.build_rows(_workspace(tmp_path) / "input", today=TODAY)
    assert "setup:Empty Unmatched" not in {r["id"] for r in data["rows"]}
    labels = {u["label"] for u in data["unmatched"]}
    assert "Mystery Account" in labels and "114 Main St" in labels
    assert "Zero Account" not in labels                      # zero balances are noise


def test_plan_inputs_need_a_mapping_then_sum_several_accounts(tmp_path):
    base = _workspace(tmp_path)
    assert _rows(base)["plan:autos"]["status"] == "not_in_monarch"
    reconcile.set_mapping(base / "input", "car one", "plan:autos")
    reconcile.set_mapping(base / "input", "car two", "plan:autos")
    reconcile.set_mapping(base / "input", "house", "plan:home")
    reconcile.set_mapping(base / "input", "home loan", "plan:mortgage")
    rows = _rows(base)
    autos = rows["plan:autos"]
    assert autos["monarch_value"] == 53215.88 and len(autos["monarch_accounts"]) == 2
    assert autos["write"] == {"kind": "plan:autos", "ref": "Other Assets|Autos|value", "field": "value", "old": "50000", "new": "53215.88"}
    assert rows["plan:home"]["difference"] == 1279500.0 - 1313000.0
    mort = rows["plan:mortgage"]
    assert mort["monarch_value"] == 283204.0 and mort["app_value"] == 293284.0
    assert "setup:Home Loan" not in rows or rows["setup:Home Loan"]["status"] == "not_in_monarch"   # remapped away


def test_saved_mapping_overrides_name_match_and_ignore_hides(tmp_path):
    base = _workspace(tmp_path)
    reconcile.set_mapping(base / "input", "mystery", "setup:Family Checking")
    chk = _rows(base)["setup:Family Checking"]
    assert chk["monarch_value"] == 13894.27 + 77.0 and not chk["auto_matched"]
    reconcile.set_mapping(base / "input", "mystery", "ignore")
    data = reconcile.build_rows(base / "input", today=TODAY)
    assert data["ignored"] == 1 and "Mystery Account" not in {u["label"] for u in data["unmatched"]}
    reconcile.set_mapping(base / "input", "mystery", None)
    assert "Mystery Account" in {u["label"] for u in reconcile.build_rows(base / "input", today=TODAY)["unmatched"]}


def test_each_matched_account_says_whether_it_was_matched_by_name_and_ignored_ones_are_listed(tmp_path):
    base = _workspace(tmp_path)
    reconcile.set_mapping(base / "input", "car one", "plan:autos")
    rows = _rows(base)
    assert rows["setup:Family Checking"]["monarch_accounts"][0]["auto"] is True
    assert rows["plan:autos"]["monarch_accounts"][0]["auto"] is False
    reconcile.set_mapping(base / "input", "family checking", "ignore")       # switch the by-name match off
    data = reconcile.build_rows(base / "input", today=TODAY)
    assert [i["label"] for i in data["ignored_accounts"]] == ["Family Checking"] and data["ignored"] == 1
    assert next(r for r in data["rows"] if r["id"] == "setup:Family Checking")["status"] == "not_in_monarch"
    reconcile.set_mapping(base / "input", "family checking", None)           # stop ignoring: the name match is back
    assert _rows(base)["setup:Family Checking"]["auto_matched"]


def test_the_as_of_picker_lists_every_stored_date(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", SETUP[:1])
    path = base / "Monarch Extractor" / "output" / "balances.csv"
    path.parent.mkdir(parents=True)
    lines = ["date,account_key,account,balance"] + [f"2025-{m:02d}-01,family checking,Family Checking,{m}" for m in range(1, 13)]
    lines += [f"2026-10-{d:02d},family checking,Family Checking,1" for d in range(1, 15)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    dates = reconcile.build_rows(base / "input", today=TODAY)["dates"]
    assert len(dates) == 26 and dates[-1] == "2025-01-01" and dates[0] == "2026-10-14"


def test_store_errors_surface_as_reconcile_errors(tmp_path):
    with pytest.raises(reconcile.ReconcileError):
        reconcile.build_rows(tmp_path / "nowhere" / "input", today=TODAY)
    base = _workspace(tmp_path)
    with pytest.raises(reconcile.ReconcileError):
        reconcile.undo(base / "input", 999)


def test_mapping_rejects_bad_targets(tmp_path):
    base = _workspace(tmp_path)
    for key, target in (("ghost", "plan:home"), ("mystery", "setup:No Such"), ("mystery", "bogus")):
        with pytest.raises(reconcile.ReconcileError):
            reconcile.set_mapping(base / "input", key, target)


def test_as_of_date_uses_that_days_balance(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    ytd.write_account_setup(base / "input", SETUP[:1])
    path = base / "Monarch Extractor" / "output" / "balances.csv"
    path.parent.mkdir(parents=True)
    path.write_text("date,account_key,account,balance\n2026-10-13,family checking,Family Checking,100\n2026-10-14,family checking,Family Checking,200\n", encoding="utf-8")
    assert mbi.import_balances(base, today=TODAY, now=NOW)["success"]
    assert _rows(base, as_of="2026-10-13")["setup:Family Checking"]["monarch_value"] == 100.0
    assert _rows(base)["setup:Family Checking"]["monarch_value"] == 200.0
    with pytest.raises(reconcile.ReconcileError):
        reconcile.build_rows(base / "input", "10/13/2026")


# ---- preview / apply / undo ---------------------------------------------------------------

def _setup_value(base, name, field):
    return next(r[field] for r in ytd.read_account_setup(base / "input") if r["Account"] == name)


def _plan_value(base, section, sub, label):
    return active_plan.peek_plan_data_for_input_dir(base / "input")[section][sub][label]


def test_preview_changes_nothing_and_lists_old_to_new(tmp_path):
    base = _workspace(tmp_path)
    p = reconcile.preview(base / "input", [{"id": "setup:Family Checking"}, {"id": "setup:Brokerage A"}, {"id": "nope"}], today=TODAY)
    assert [(c["id"], c["old"], c["new"]) for c in p["changes"]] == [("setup:Family Checking", "13000", "13894.27")]
    reasons = {r["id"]: r["reason"] for r in p["rejected"]}
    assert "Holdings" in reasons["setup:Brokerage A"] and reasons["nope"] == "no such row"
    assert _setup_value(base, "Family Checking", "Current Balance") == "13000"


def test_apply_writes_setup_and_plan_inputs_and_logs_each(tmp_path):
    base = _workspace(tmp_path)
    reconcile.set_mapping(base / "input", "house", "plan:home")
    res = reconcile.apply(base / "input", [{"id": "setup:Family Checking"}, {"id": "setup:Visa Card"}, {"id": "plan:home"}], today=TODAY)
    assert len(res["applied"]) == 3 and res["rejected"] == []
    assert _setup_value(base, "Family Checking", "Current Balance") == "13894.27"
    assert _setup_value(base, "Visa Card", "Current Balance") == "10021.20"
    assert _plan_value(base, "Other Assets", "Home", "value_as_of_plan_start") == "1279500.00"
    after = _rows(base)
    assert after["setup:Family Checking"]["status"] == "match" and after["plan:home"]["status"] == "match"
    log = reconcile.change_log(base / "input")
    assert {e["label"] for e in log} == {"Family Checking", "Visa Card", "Home value (plan input)"}
    assert all(e["monarch_date"] == "2026-10-14" and e["undone_at"] is None for e in log)
    other = _setup_value(base, "Private Note", "Current Value")
    assert other == "500000"                                         # untouched rows keep their text


def test_apply_rejects_a_stale_preview(tmp_path):
    base = _workspace(tmp_path)
    res = reconcile.apply(base / "input", [{"id": "setup:Family Checking", "expected_new": "1.00"}], today=TODAY)
    assert res["applied"] == [] and "changed since the preview" in res["rejected"][0]["reason"]
    assert _setup_value(base, "Family Checking", "Current Balance") == "13000"


def test_undo_restores_old_value_once(tmp_path):
    base = _workspace(tmp_path)
    cid = reconcile.apply(base / "input", [{"id": "setup:Family Checking"}], today=TODAY)["applied"][0]["change_id"]
    out = reconcile.undo(base / "input", cid)
    assert out["restored"] == "13000" and _setup_value(base, "Family Checking", "Current Balance") == "13000"
    with pytest.raises(reconcile.ReconcileError, match="already undone"):
        reconcile.undo(base / "input", cid)
    assert reconcile.change_log(base / "input")[0]["undone_at"]


def test_undo_refuses_when_the_value_was_edited_since(tmp_path):
    base = _workspace(tmp_path)
    cid = reconcile.apply(base / "input", [{"id": "setup:Family Checking"}], today=TODAY)["applied"][0]["change_id"]
    rows = ytd.read_account_setup(base / "input")
    for r in rows:
        if r["Account"] == "Family Checking":
            r["Current Value"] = r["Current Balance"] = "99999"
    ytd.write_account_setup(base / "input", rows)
    with pytest.raises(reconcile.ReconcileError, match="was not undone"):
        reconcile.undo(base / "input", cid)
    assert _setup_value(base, "Family Checking", "Current Balance") == "99999"


def test_undo_plan_input(tmp_path):
    base = _workspace(tmp_path)
    reconcile.set_mapping(base / "input", "house", "plan:home")
    cid = reconcile.apply(base / "input", [{"id": "plan:home"}], today=TODAY)["applied"][0]["change_id"]
    reconcile.undo(base / "input", cid)
    assert _plan_value(base, "Other Assets", "Home", "value_as_of_plan_start") == "1313000"
