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


# ---- M2: policy and closed accounts
def test_policy_app_is_report_only_and_policy_ignore_hides(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("family checking", "setup_account", "Family Checking", "app")
        store.monarch.set_mapping("private note", "setup_account", "Private Note", "ignore")
    data = reconcile.build_rows(base / "input", today=TODAY)
    rows = {r["id"]: r for r in data["rows"]}
    chk = rows["setup:Family Checking"]
    assert chk["status"] == "report_only" and not chk["updatable"] and chk["policy"] == "app"
    assert chk["report_reason"] == reconcile.REPORT_ONLY_APP and chk["difference"] == 894.27
    assert rows["setup:Private Note"]["status"] == "not_in_monarch"  # the ignored account no longer feeds it
    assert data["ignored"] == 1


def test_policy_app_that_matches_still_reads_as_a_match(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("family checking", "setup_account", "Family Checking", "app")
    data = reconcile.build_rows(base / "input", today=TODAY, tolerance=1000)
    assert {r["id"]: r for r in data["rows"]}["setup:Family Checking"]["status"] == "match"


def test_closed_empty_accounts_are_quiet_and_closed_with_money_is_flagged(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.upsert_balances([("2026-01-01", "old ira", "Old IRA", 0.0), ("2026-01-02", "old ira", "Old IRA", 0.0),
                                       ("2026-01-01", "lost acct", "Lost Acct", 5000.0), ("2026-01-02", "lost acct", "Lost Acct", 5000.0)])
    data = reconcile.build_rows(base / "input", today=TODAY)
    assert [c["label"] for c in data["closed_accounts"]] == ["Old IRA"]
    flagged = {u["label"]: u for u in data["unmatched"]}
    assert "Old IRA" not in flagged
    assert flagged["Lost Acct"]["status"] == "closed_with_balance" and flagged["Lost Acct"]["monarch_value"] == 5000.0


# ---- M2: row-level targets (Other Asset Items with as-of date, notes, liabilities) resolved from seeded matches
def _dyn_workspace(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        for sub, typ, name, val, when in (("Other Asset 1", "Auto", "2016 Kia Optima EX", "$10,554.12", "06/30/2026"),
                                          ("Other Asset 2", "Art", "Art", "$10,000", "06/30/2026")):
            for label, v in (("type", typ), ("name", name), ("value", val), ("as_of_date", when)):
                store.set_value("Other Assets", sub, label, v)
        store.set_value("Note Receivable", "Note 1", "name", "RedMane Note")
        store.set_value("Note Receivable", "Note 1", "face_value", "$320,000")
        store.liabilities.replace_all([{"liability_id": "1", "type": "HELOC", "label": "HELOC", "balance": "199000"}])
        m = store.monarch
        m.upsert_balances([(d, k, n, b) for d in ("2026-10-13", "2026-10-14") for k, n, b in
                           (("kia", "2016 KIA Optima EX", 9800.0), ("art", "Masterworks Art", 12000.0),
                            ("redmane", "RedMane Note Jan 2026", 300000.0), ("heloc", "Home Equity Line", -150000.0))])
        m.set_mapping("kia", "pending", "Other Assets and Liabilities|Auto - 2016 Kia Optima", "auto")
        m.set_mapping("art", "pending", "Other Assets and Liabilities|Art", "ask")
        m.set_mapping("redmane", "pending", "Other Assets and Liabilities|RedMane Note - Face Value", "ask")
        m.set_mapping("heloc", "pending", "Other Assets and Liabilities|Liabilities - HELOC Balance", "ask")
    return base


def test_pending_matches_resolve_to_plan_rows(tmp_path):
    base = _dyn_workspace(tmp_path)
    rows = _rows(base)
    assert rows["other_asset:Other Asset 1"]["monarch_value"] == 9800.0 and rows["other_asset:Other Asset 1"]["policy"] == "auto"
    assert rows["other_asset:Other Asset 2"]["app_value"] == 10000.0
    assert rows["note:Note 1"]["difference"] == -20000.0
    heloc = rows["liability:1"]
    assert heloc["monarch_value"] == 150000.0 and heloc["app_value"] == 199000.0  # liabilities compare by magnitude
    assert heloc["write"]["new"] == "150000.00"


def test_other_asset_update_writes_value_and_as_of_date_and_undo_restores_both(tmp_path):
    base = _dyn_workspace(tmp_path)
    out = reconcile.apply(base / "input", [{"id": "other_asset:Other Asset 1"}, {"id": "note:Note 1"}, {"id": "liability:1"}], today=TODAY)
    assert len(out["applied"]) == 3, out["rejected"]
    with active_plan.workspace_store(base) as store:
        assert store.find_rows("Other Assets", "Other Asset 1", "value")[-1]["value"] == "9800.00"
        assert store.find_rows("Other Assets", "Other Asset 1", "as_of_date")[-1]["value"] == "10/14/2026"  # m/d/yyyy kept
        assert store.find_rows("Note Receivable", "Note 1", "face_value")[-1]["value"] == "300000.00"
        assert store.liabilities.rows()[0]["balance"] == "150000.00"
    for entry in out["applied"]:
        reconcile.undo(base / "input", entry["change_id"])
    with active_plan.workspace_store(base) as store:
        assert store.find_rows("Other Assets", "Other Asset 1", "value")[-1]["value"] == "$10,554.12"
        assert store.find_rows("Other Assets", "Other Asset 1", "as_of_date")[-1]["value"] == "06/30/2026"
        assert store.liabilities.rows()[0]["balance"] == "199000"


def test_change_log_records_whether_a_change_was_manual_or_auto(tmp_path):
    base = _workspace(tmp_path)
    reconcile.apply(base / "input", [{"id": "setup:Family Checking"}], today=TODAY)
    reconcile.apply(base / "input", [{"id": "setup:Private Note"}], today=TODAY, source="auto")
    log = {e["label"]: e["source"] for e in reconcile.change_log(base / "input")}
    assert log == {"Family Checking": "manual", "Private Note": "auto"}


# ---- M3: auto-update with guards
def test_auto_apply_writes_only_auto_rows_that_pass_the_guards_and_logs_them(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        m = store.monarch
        m.set_mapping("family checking", "setup_account", "Family Checking", "auto")   # +$894 on $13,000: fine
        m.set_mapping("private note", "setup_account", "Private Note", "auto")         # +$12,848 on $500,000: under 10%
        m.set_mapping("house", "plan:home", "", "auto")                                 # plan-start input: updated like any other
        m.set_mapping("visa card", "setup_account", "Visa Card", "ask")                 # not auto
    out = reconcile.auto_apply(base / "input", today=TODAY)
    assert {a["id"] for a in out["applied"]} == {"setup:Family Checking", "setup:Private Note", "plan:home"} and out["held"] == []
    assert _setup_value(base, "Family Checking", "Current Value") == "13894.27"
    assert _setup_value(base, "Visa Card", "Current Balance") == "900"
    assert {e["source"] for e in reconcile.change_log(base / "input")} == {"auto"}


def test_big_change_is_held_and_undo_auto_restores_everything(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.set_value("Other Assets", "Autos", "value", "10000")   # Monarch: cars sum 53,215.88 -> +432%, > $5,000
        store.monarch.set_mapping("car one", "plan:autos", "", "auto")
        store.monarch.set_mapping("car two", "plan:autos", "", "auto")
        store.monarch.set_mapping("family checking", "setup_account", "Family Checking", "auto")
    out = reconcile.auto_apply(base / "input", today=TODAY)
    assert [h["id"] for h in out["held"]] == ["plan:autos"] and [a["label"] for a in out["applied"]] == ["Family Checking"]
    undone = reconcile.undo_auto(base / "input")
    assert undone == {"undone": ["Family Checking"], "skipped": []}
    assert _setup_value(base, "Family Checking", "Current Value") == "13000"


# ---- review fixes
def test_pending_name_match_is_exact_first_and_whole_word(tmp_path):
    base = _dyn_workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        for label, v in (("type", "Start-up Equity"), ("name", "Start-up Equity"), ("value", "$66,000"), ("as_of_date", "12/31/2025")):
            store.set_value("Other Assets", "Other Asset 3", label, v)
        store.monarch.upsert_balances([("2026-10-14", "hucu", "hucu.ai", 70000.0)])
        store.monarch.set_mapping("hucu", "pending", "Other Assets and Liabilities|Start-up Equity", "ask")
    rows = _rows(base)
    assert rows["other_asset:Other Asset 3"]["monarch_value"] == 70000.0   # "art" in "start-up" no longer makes it ambiguous
    assert rows["other_asset:Other Asset 2"]["monarch_value"] == 12000.0   # Art still resolves to Art


def test_policy_on_a_name_matched_account_saves_the_match(tmp_path):
    base = _workspace(tmp_path)
    out = reconcile.set_policy(base / "input", "family checking", "auto")
    assert out == {"account_key": "family checking", "policy": "auto"}
    assert _rows(base)["setup:Family Checking"]["policy"] == "auto"
    with pytest.raises(reconcile.ReconcileError):
        reconcile.set_policy(base / "input", "mystery", "auto")   # nothing to match it to


def test_unresolved_app_or_ignore_matches_are_parked_not_in_the_inbox(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.monarch.set_mapping("mystery", "pending", "SS, Pensions, & Annuities|Matt Single Annuity", "app")
    data = reconcile.build_rows(base / "input", today=TODAY)
    assert [p["label"] for p in data["parked_accounts"]] == ["Mystery Account"]
    assert "Mystery Account" not in [u["label"] for u in data["unmatched"]]


def test_apply_rejects_an_unknown_source(tmp_path):
    base = _workspace(tmp_path)
    with pytest.raises(reconcile.ReconcileError):
        reconcile.apply(base / "input", [{"id": "setup:Family Checking"}], today=TODAY, source="nightly")


def test_bare_card_names_and_heloc_type_resolve_to_liabilities(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.liabilities.replace_all([
            {"liability_id": "1", "type": "HELOC", "label": "Home Equity Line", "balance": "171.80"},
            {"liability_id": "2", "type": "Credit card", "label": "Amex", "balance": ""}])
        store.monarch.upsert_balances([(d, k, n, b) for d in ("2026-10-13", "2026-10-14") for k, n, b in
                                       (("platinum", "Platinum Card (...1008)", -2500.0), ("heloc", "HELOC $199K", -171.8))])
        store.monarch.set_mapping("platinum", "pending", "Other Assets and Liabilities|Amex", "auto")
        store.monarch.set_mapping("heloc", "pending", "Other Assets and Liabilities|Liabilities - HELOC Balance", "auto")
    rows = _rows(base)
    assert rows["liability:2"]["monarch_value"] == 2500.0 and rows["liability:2"]["write"]["new"] == "2500.00"
    assert rows["liability:1"]["monarch_accounts"][0]["account"] == "HELOC $199K"


def test_cash_only_holding_is_updated_with_its_date_and_undone(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.holdings.replace_all([{"account": "Brokerage A", "symbol": "CASH", "purchase_date": "06/01/2026", "shares": "1000",
                                     "purchase_price": "$1", "lot_type": "buy", "note": ""}])
    row = _rows(base)["setup:Brokerage A"]
    assert row["write"] and row["write"]["field"] == reconcile.CASH_LOT_FIELD, row["status"]
    out = reconcile.apply(base / "input", [{"id": "setup:Brokerage A"}], today=TODAY)
    assert len(out["applied"]) == 1, out["rejected"]
    with active_plan.workspace_store(base) as store:
        lot = store.holdings.rows()[0]
        assert lot["shares"] == row["write"]["new"].split("|")[0] and lot["purchase_date"] == "10/14/2026"
    reconcile.undo(base / "input", out["applied"][0]["change_id"])
    with active_plan.workspace_store(base) as store:
        assert store.holdings.rows()[0]["shares"] == "1000" and store.holdings.rows()[0]["purchase_date"] == "06/01/2026"


def test_cash_account_linked_to_a_cash_holding_updates_the_holding_too(tmp_path):
    base = _workspace(tmp_path)
    rows = [dict(r, **({"Mapped Investment Account": "Chk_Hold"} if r["Account"] == "Family Checking" else {})) for r in ytd.read_account_setup(base / "input")]
    ytd.write_account_setup(base / "input", rows)
    with active_plan.workspace_store(base, write=True) as store:
        store.holdings.replace_all([{"account": "Chk_Hold", "symbol": "CASH", "purchase_date": "06/01/2026", "shares": "15000",
                                     "purchase_price": "$1", "lot_type": "buy", "note": ""}])
    out = reconcile.apply(base / "input", [{"id": "setup:Family Checking"}], today=TODAY)
    assert len(out["applied"]) == 1, out["rejected"]
    assert _setup_value(base, "Family Checking", "Current Value") == "13894.27"
    with active_plan.workspace_store(base) as store:
        assert store.holdings.rows()[0]["shares"] == "13894.27"
    logged = reconcile.change_log(base / "input")
    assert len(logged) == 2
    for e in logged:
        reconcile.undo(base / "input", e["id"])
    with active_plan.workspace_store(base) as store:
        assert store.holdings.rows()[0]["shares"] == "15000"


def test_linked_cash_holding_that_disagrees_makes_a_matching_account_updatable(tmp_path):
    base = _workspace(tmp_path)
    rows = [dict(r, **({"Mapped Investment Account": "Chk_Hold", "Current Value": "13894.27"} if r["Account"] == "Family Checking" else {})) for r in ytd.read_account_setup(base / "input")]
    ytd.write_account_setup(base / "input", rows)
    with active_plan.workspace_store(base, write=True) as store:
        store.holdings.replace_all([{"account": "Chk_Hold", "symbol": "CASH", "purchase_date": "06/01/2026", "shares": "15000",
                                     "purchase_price": "$1", "lot_type": "buy", "note": ""}])
    row = _rows(base)["setup:Family Checking"]
    assert row["difference"] == 0 and row["status"] == "differs" and row["updatable"]


def test_card_mapped_to_a_liability_also_updates_its_same_named_accounts_row(tmp_path):
    base = _workspace(tmp_path)
    with active_plan.workspace_store(base, write=True) as store:
        store.liabilities.replace_all([{"liability_id": "v1", "type": "credit_card", "label": "Visa", "balance": ""}])
        store.monarch.set_mapping("visa card", "liability:v1", "", "ask")
    row = _rows(base)["liability:v1"]
    assert row["monarch_value"] == 10021.2 and row["write"]["new"] == "10021.20" and row["write_also"]["ref"] == "Visa Card"
    out = reconcile.apply(base / "input", [{"id": "liability:v1"}], today=TODAY)
    assert len(out["applied"]) == 1, out["rejected"]
    with active_plan.workspace_store(base) as store:
        assert store.liabilities.rows()[0]["balance"] == "10021.20"
    assert _setup_value(base, "Visa Card", "Current Balance") == "-10021.20"
    for e in reconcile.change_log(base / "input"):
        reconcile.undo(base / "input", e["id"])
    assert _setup_value(base, "Visa Card", "Current Balance") == "900"
