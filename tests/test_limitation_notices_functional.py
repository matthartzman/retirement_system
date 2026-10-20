"""WI-010 / WI-010a: limitation and preflight notices N1-N7.

Display conditions, preflight output, wording against the approved file, and the
retirement check (a notice is not shown once its removal triggers are shipped).
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from src import limitation_notices as ln
from src.active_plan import PLAN_DB_ENV, ensure_plan_file, plan_state, write_build_results
from src.server_services import build_service

ROOT = Path(__file__).resolve().parents[1]
WORDING = ROOT / "documentation" / "archive" / "reports" / "SYSTEM_REVIEW_2026-10-19_WAVE1_NOTICE_WORDING.md"

ALL_IDS = ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]
# The registry as shipped, captured before any test patches it.
REAL_NOTICES = ln.NOTICES
# Notices whose fix has shipped (their removal triggers are marked shipped in the registry).
RETIRED_IDS = ["N1", "N2", "N4"]


@pytest.fixture(autouse=True)
def _all_notices_in_force(monkeypatch):
    """The display and retirement mechanics are tested against every notice in force, so a
    retired notice (its fix shipped) still has its condition and preflight behaviour covered.
    ``test_shipped_fixes_have_retired_their_notices`` checks the real registry."""
    unshipped = tuple(
        dataclasses.replace(n, triggers=tuple(dataclasses.replace(t, shipped=False) for t in n.triggers))
        for n in REAL_NOTICES)
    monkeypatch.setattr(ln, "NOTICES", unshipped)
    monkeypatch.setattr(ln, "NOTICE_BY_ID", {n.id: n for n in unshipped})


def _acct(aid, tax, owner_idx=0, balance=100000.0):
    return {"id": aid, "owner_idx": owner_idx, "tax": tax, "balance": balance}


def _base_config(**over):
    c = {
        "members": [{"name": "A"}, {"name": "B"}], "household_size": 2,
        "account_registry": [_acct("Member_1_IRA", "pre_tax", 0), _acct("Member_1_Trust", "taxable", 0)],
        "account_taxable_income_assumptions": {"Member_1_Trust": {"qualified_yield": 0.0}},
        "h_ss_claim_age_precise": 67.0, "h_fra_age": 67.0,
        "w_ss_claim_age_precise": 67.0, "w_fra_age": 67.0,
    }
    c.update(over)
    return c


def _row(**over):
    r = {"year": 2030, "h_age": 65, "w_age": 65, "h_alive": True, "w_alive": True,
         "ltcg_gain": 0.0, "earned": 0.0, "_account_withdrawals": {}}
    r.update(over)
    return r


# (notice id, config that triggers it, rows that trigger it)
TRIGGERS = {
    "N1": (_base_config(), [_row(ltcg_gain=5000.0)]),
    "N2": (_base_config(account_taxable_income_assumptions={"Member_1_Trust": {"qualified_yield": 0.015}}), [_row()]),
    "N3": (_base_config(), [_row(h_age=55, _account_withdrawals={"Member_1_IRA": 20000.0})]),
    "N4": (_base_config(account_registry=[_acct("Joint_Trust", "taxable", 0)]), [_row()]),
    "N5": (_base_config(h_ss_claim_age_precise=62.0), [_row(h_age=63, earned=90000.0)]),
    "N6": (_base_config(members=[{"name": "A"}], household_size=1), [_row()]),
}
# A plan where none of N1-N6 holds.
QUIET = (_base_config(), [_row()])


def _ids(config, rows):
    return [n["id"] for n in ln.evaluate_notices(config, rows)]


@pytest.mark.parametrize("nid", sorted(TRIGGERS))
def test_notice_shown_only_when_condition_holds(nid):
    config, rows = TRIGGERS[nid]
    assert nid in _ids(config, rows)
    assert nid not in _ids(*QUIET)


def test_quiet_plan_shows_only_the_always_on_data_status():
    assert _ids(*QUIET) == ["N7"]


def test_n3_not_shown_for_draws_at_or_after_59_5_or_non_pretax():
    c = _base_config()
    assert "N3" not in _ids(c, [_row(h_age=60, _account_withdrawals={"Member_1_IRA": 1000.0})])
    assert "N3" not in _ids(c, [_row(h_age=55, _account_withdrawals={"Member_1_Trust": 1000.0})])


def test_n5_not_shown_without_wages_or_at_fra():
    c = _base_config(h_ss_claim_age_precise=62.0)
    assert "N5" not in _ids(c, [_row(h_age=63, earned=0.0)])
    assert "N5" not in _ids(_base_config(), [_row(h_age=63, earned=90000.0)])


def test_n4_needs_two_members():
    config, rows = TRIGGERS["N4"]
    assert "N4" not in _ids({**config, "members": [{"name": "A"}], "household_size": 1}, rows)


def test_n7_lists_the_six_families_with_dataset_vocabulary():
    n7 = next(n for n in ln.evaluate_notices(*QUIET) if n["id"] == "N7")
    assert [f["family"] for f in n7["families"]] == list(ln.DATA_FAMILIES)
    assert {f["status"] for f in n7["families"]} <= {"verified", "assumption", "unreviewed"}
    by = {f["family"]: f["status"] for f in n7["families"]}
    assert by["AMT"] != "verified"  # the dataset holds no AMT rows


def test_n7_never_verified_when_a_row_in_force_is_assumption():
    from src.stores.ref_getters.tax_law import tax_law_dataset
    ds = tax_law_dataset()
    rows = [dataclasses.replace(v, status="assumption") if v.name == "part_d_base_premium_monthly" else v
            for v in ds.values]
    statuses = ln._rows_in_force(dataclasses.replace(ds, values=tuple(rows)), 2026,
                                 values=lambda n: n == "part_d_base_premium_monthly", brackets=False)
    assert ln._roll_up(statuses) == "assumption"
    assert ln._roll_up([]) == "unreviewed"
    assert ln._roll_up(["verified", "legislated"]) == "verified"
    assert ln._roll_up(["verified", "assumption"]) == "assumption"


# ── Frozen sample plan: real engine output, and the notices change no number ──

def test_frozen_sample_plan_notices_and_numbers_untouched():
    from plan_fixture import plan_config
    from src.planning_engines import project
    c = plan_config("sample_frozen")
    rows = project(c)
    before = [dict(r) for r in rows]
    ids = _ids(c, rows)
    assert {"N1", "N2", "N7"} <= set(ids)
    assert not {"N3", "N4", "N5", "N6"} & set(ids)
    assert "N6" not in ids
    assert rows == before  # evaluation is read-only


# ── Preflight ──

@pytest.fixture
def plan(tmp_path, monkeypatch):
    path = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(path))
    ensure_plan_file(path)
    return path


def _preflight(plan, tmp_path, notices):
    summary = {"qc_result": "QC: pass", "limitation_notices": notices}
    write_build_results("b1", path=plan, plan_state=plan_state(plan), summary=summary)
    return build_service.build_preflight_payload(
        output_dir=tmp_path / "output", db_path=plan, csv_rows_payload=lambda: {"rows": []},
        validate_rows_func=lambda rows: [])


@pytest.mark.parametrize("nid", sorted(TRIGGERS))
def test_preflight_shows_notice_when_condition_held_at_build(plan, tmp_path, nid):
    config, rows = TRIGGERS[nid]
    payload = _preflight(plan, tmp_path, ln.evaluate_notices(config, rows))
    shown = {n["id"]: n for n in payload["limitation_notices"]}
    assert nid in shown
    assert shown[nid]["text"] == ln.NOTICE_BY_ID[nid].text
    assert shown[nid]["severity"] == ln.NOTICE_BY_ID[nid].severity
    assert payload["readiness"] != "blocked"  # notices never block


@pytest.mark.parametrize("nid", sorted(TRIGGERS))
def test_preflight_hides_notice_when_condition_did_not_hold(plan, tmp_path, nid):
    payload = _preflight(plan, tmp_path, ln.evaluate_notices(*QUIET))
    ids = [n["id"] for n in payload["limitation_notices"]]
    assert nid not in ids
    assert "N7" in ids


def test_preflight_without_a_build_still_shows_data_status(plan, tmp_path):
    payload = build_service.build_preflight_payload(
        output_dir=tmp_path / "output", db_path=plan, csv_rows_payload=lambda: {"rows": []},
        validate_rows_func=lambda rows: [])
    assert [n["id"] for n in payload["limitation_notices"]] == ["N7"]
    assert len(payload["limitation_notices"][0]["families"]) == 6


# ── Wording ──

def _approved_text():
    md = WORDING.read_text(encoding="utf-8")
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^\*\*(N\d)\.\*\*\s+(.+)$", md, re.M)}


def test_notice_text_matches_approved_wording_file():
    approved = _approved_text()
    assert sorted(approved) == ALL_IDS
    # N7 is specified as a per-family status list, not as prose: its rows are data, checked above.
    for nid in ALL_IDS[:6]:
        assert ln.NOTICE_BY_ID[nid].text == approved[nid], nid


def test_severities_match_approved_table():
    md = WORDING.read_text(encoding="utf-8")
    for m in re.finditer(r"^\| (N\d) \| ([^|]+) \| (warning|info) \|", md, re.M):
        nid, finding, severity = m.groups()
        assert ln.NOTICE_BY_ID[nid].severity == severity, nid
        assert ln.NOTICE_BY_ID[nid].finding == finding.strip(), nid


# ── Retirement triggers ──

def test_every_notice_records_removal_triggers_as_data():
    assert [n.id for n in ln.NOTICES] == ALL_IDS
    for n in ln.NOTICES:
        assert n.triggers, n.id
        for t in n.triggers:
            assert re.fullmatch(r"WI-\d{3}[a-z]?", t.work_item), (n.id, t.work_item)
            assert t.effect in {"remove", "update_wording", "update_status"}


def _with_shipped(monkeypatch, nid, *, effects=("remove",)):
    notice = ln.NOTICE_BY_ID[nid]
    shipped = dataclasses.replace(notice, triggers=tuple(
        dataclasses.replace(t, shipped=True) if t.effect in effects else t for t in notice.triggers))
    monkeypatch.setattr(ln, "NOTICES", tuple(shipped if n.id == nid else n for n in ln.NOTICES))
    monkeypatch.setattr(ln, "NOTICE_BY_ID", {n.id: n for n in ln.NOTICES})
    return shipped


def test_registry_has_no_shown_notice_whose_trigger_is_shipped(monkeypatch):
    """Fails if a work item is marked shipped but its notice is still in force."""
    monkeypatch.setattr(ln, "NOTICES", REAL_NOTICES)
    for n in REAL_NOTICES:
        removers = [t for t in n.triggers if t.effect == "remove"]
        if removers and all(t.shipped for t in removers):
            assert n.retired
            assert n.id not in {a.id for a in ln.active_notices()}, f"{n.id} still shown after its trigger shipped"


def test_shipped_fixes_have_retired_their_notices(monkeypatch):
    """N1 (WI-024 phases 1 and 2), N2 (WI-023) and N4 (WI-025) shipped; the rest stay in force."""
    monkeypatch.setattr(ln, "NOTICES", REAL_NOTICES)
    monkeypatch.setattr(ln, "NOTICE_BY_ID", {n.id: n for n in REAL_NOTICES})
    assert sorted(n.id for n in REAL_NOTICES if n.retired) == RETIRED_IDS
    shown = {a.id for a in ln.active_notices()}
    assert not set(RETIRED_IDS) & shown and {"N3", "N5", "N6", "N7"} <= shown
    for nid in RETIRED_IDS:
        config, rows = TRIGGERS[nid]
        assert nid not in _ids(config, rows)


@pytest.mark.parametrize("nid", sorted(TRIGGERS))
def test_notice_disappears_everywhere_once_its_trigger_ships(monkeypatch, plan, tmp_path, nid):
    config, rows = TRIGGERS[nid]
    stored = ln.evaluate_notices(config, rows)
    assert nid in [n["id"] for n in stored]
    _with_shipped(monkeypatch, nid)
    assert nid not in _ids(config, rows)  # build-time evaluation
    assert nid not in [n["id"] for n in ln.shown_notices(stored)]  # stored by an older build
    assert nid not in [t[0] for t in ln.display_lines(stored)]  # workbook, dashboard
    payload = _preflight(plan, tmp_path, stored)
    assert nid not in [n["id"] for n in payload["limitation_notices"]]  # preflight


def test_n1_phase_one_updates_wording_but_only_phase_two_removes(monkeypatch):
    n1 = ln.NOTICE_BY_ID["N1"]
    assert [t.effect for t in n1.triggers] == ["update_wording", "remove"]
    _with_shipped(monkeypatch, "N1", effects=("update_wording",))
    assert not ln.NOTICE_BY_ID["N1"].retired
    _with_shipped(monkeypatch, "N1", effects=("remove",))
    assert ln.NOTICE_BY_ID["N1"].retired


def test_n7_is_never_retired_by_shipping_a_data_update(monkeypatch):
    _with_shipped(monkeypatch, "N7", effects=("update_status",))
    assert not ln.NOTICE_BY_ID["N7"].retired
