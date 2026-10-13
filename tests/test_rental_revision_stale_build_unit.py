"""Editing a rental property changes the plan revision, the build input fingerprint and the
plan state, so the last build shows as stale (WP12.7).

A plan with no rental property keeps exactly the revision it always had (the rows' hash)."""
from __future__ import annotations

from pathlib import Path

import src.server.workbook_routes as workbook_routes
from src.active_plan import (
    PLAN_DB_ENV, edit_active_plan, ensure_plan_file, plan_state, rental_fingerprint, write_build_results,
)
from src.build_snapshot import SNAPSHOT_SCHEMA
from src.reporting.workbook_builder import _build_plan_input_fingerprint
from src.stores import PlanStore
from src.stores.plan_store import hash_rows

CONDO = {"name": "Condo", "purchase_price": 300000, "monthly_rent": 2000,
         "improvements": [{"year": 2030, "amount": 5000}], "overrides": [{"year": 2031, "gross_rent": 1}]}


def test_empty_plan_revision_is_the_plain_rows_hash(tmp_path):
    with PlanStore.open(tmp_path / "p.rpx") as store:
        assert store.all_rows() == [] and store.revision() == hash_rows(())
        assert store.rental_state_text() == ""


def test_revision_follows_every_rental_edit_and_returns_when_they_are_removed(tmp_path):
    with PlanStore.open(tmp_path / "p.rpx") as store:
        base = store.revision()
        store.rental.replace_all([CONDO])
        with_condo = store.revision()
        assert with_condo != base
        # the same content written again (new ids) is the same revision
        store.rental.replace_all([CONDO])
        assert store.revision() == with_condo
        for change in ({**CONDO, "monthly_rent": 2100},
                       {**CONDO, "improvements": []},
                       {**CONDO, "overrides": [{"year": 2031, "gross_rent": 2}]}):
            store.rental.replace_all([change])
            assert store.revision() not in (base, with_condo)
            store.rental.replace_all([CONDO])
            assert store.revision() == with_condo
        store.rental.replace_all([])
        assert store.revision() == base


def test_build_input_fingerprint_and_plan_state_change_with_a_rental_edit(tmp_path, monkeypatch):
    plan = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    ensure_plan_file(plan)
    meta = {"plan_db": str(plan)}
    fp0 = _build_plan_input_fingerprint(tmp_path, meta)
    state0 = plan_state(plan)
    assert rental_fingerprint(plan) == ""
    assert not any(f["file"] == "rental_properties" for f in fp0["files"])

    with edit_active_plan() as edit:
        edit.store.rental.replace_all([CONDO])
    fp1 = _build_plan_input_fingerprint(tmp_path, meta)
    assert fp1["sha256"] != fp0["sha256"] and fp1["plan_state"] != state0
    assert plan_state(plan) != state0
    assert any(f["file"] == "rental_properties" for f in fp1["files"])

    with edit_active_plan() as edit:
        edit.store.rental.replace_all([{**CONDO, "monthly_rent": 2500}])
    fp2 = _build_plan_input_fingerprint(tmp_path, meta)
    assert fp2["sha256"] not in (fp0["sha256"], fp1["sha256"])
    entry = {f["file"]: f["sha256"] for f in fp1["files"]}["rental_properties"]
    assert rental_fingerprint(plan) not in ("", entry)


def test_last_build_is_stale_after_a_rental_edit(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    plan = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    ensure_plan_file(plan)
    write_build_results("b1", path=plan, plan_state=plan_state(plan), summary={"qc_result": "QC: pass"},
                        explorer={"schema": "m"}, snapshot={"schema": SNAPSHOT_SCHEMA})

    def meta(path):
        return {"exists": True, "path": str(Path(path)), "bytes": 10, "mtime": 120.0, "modified_at": "2026-10-13 05:00:00"}

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_file_meta", meta)
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    def stale() -> bool:
        payload = workbook_routes._build_preflight_payload()
        return any("newer than one or more report outputs" in r for r in payload["recommendations"])

    assert not stale()
    with edit_active_plan() as edit:
        edit.store.rental.replace_all([CONDO])
    assert stale()
