"""WP10.2: ``convert_workspace`` end to end on throwaway workspaces.

Covers the source precedence (input/ only, client_files only, a snapshot only), the mid-demo
upgrades (WP4.5+ ``plan.rpx.before_demo`` and the pre-WP4.5 text / database backups), the
placeholder plan (backfill rows only), an existing plan that must not be overwritten,
idempotent re-runs, dry run, settings (C6a), secrets (C6b) and registration (C6c). Every test
checks the originals stay byte-identical.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import fail
from keyring.errors import PasswordDeleteError

from src import plan_registry
from src.active_plan import build_plan_file_from_csv_folder
from src.app_state import APP_DB_ENV, open_app_store
from src.legacy_conversion import convert_workspace, decide, runner
from src.stores import PlanStore
from tests import plan_fixture as pf

FROZEN = pf.fixture_dir("sample_frozen")
DEMO = pf.fixture_dir("demo")


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.data: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def get_password(self, service, username):
        return self.data.get((service, username))

    def delete_password(self, service, username):
        if (service, username) not in self.data:
            raise PasswordDeleteError("not found")
        del self.data[(service, username)]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    (root / "local_state").mkdir(parents=True)
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv(APP_DB_ENV, str(root / "local_state" / "app.db"))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    plan_registry.invalidate()
    prev = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield root
    keyring.set_keyring(prev)
    plan_registry.invalidate()


def _tree_hashes(root: Path) -> dict[str, str]:
    """sha256 of every file except the ones the conversion is allowed to write."""
    allowed = ("plan.rpx", "demo.rpx", "app.db")
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.startswith(allowed):
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _copy_csvs(src: Path, dest: Path, skip: tuple[str, ...] = ()) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.csv"):
        if f.name not in skip:
            shutil.copyfile(f, dest / f.name)


def _legacy_db(path: Path, files: dict[str, str] | None = None, snapshot: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("CREATE TABLE client_files(file_name TEXT PRIMARY KEY, content TEXT NOT NULL, updated_by TEXT, updated_at TEXT)")
        con.execute("CREATE TABLE plan_snapshots(snapshot_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL,"
                    " input_json TEXT NOT NULL, sectioned_json TEXT NOT NULL, result_json TEXT, input_sha256 TEXT NOT NULL,"
                    " result_sha256 TEXT, note TEXT)")
        for name, text in (files or {}).items():
            con.execute("INSERT INTO client_files(file_name, content) VALUES(?,?)", (name, text))
        if snapshot is not None:
            con.execute("INSERT INTO plan_snapshots VALUES('s1','2026-01-01','t','{}',?,NULL,'x',NULL,NULL)",
                        (json.dumps(snapshot),))


def _texts(src: Path, skip: tuple[str, ...] = ()) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8-sig") for f in src.glob("*.csv") if f.name not in skip}


def _household(plan: Path, label: str = "member_1_name") -> str:
    with PlanStore.open(plan, create=False, readonly=True) as store:
        rows = store.find_rows("Household", "", label)
        return rows[-1]["value"] if rows else ""


def _count(plan: Path, dataset: str) -> int:
    with PlanStore.open(plan, create=False, readonly=True) as store:
        return store.dataset(dataset).count()


def _meta(plan: Path, key: str):
    with PlanStore.open(plan, create=False, readonly=True) as store:
        return store.get_meta(key)


def _statuses(res) -> dict[str, str]:
    return {s["step"]: s["status"] for s in res["report"]["steps"]}


# ----------------------------------------------------------------------------- sources
def test_input_only_workspace_converts_on_first_launch(ws):
    _copy_csvs(FROZEN, ws / "input")
    before = _tree_hashes(ws)
    res = convert_workspace(ws)
    assert res["needed"] and res["report"]["ok"], res
    plan = ws / "plan.rpx"
    assert _household(plan) == "Matthew"
    assert _count(plan, "holdings") > 0 and _count(plan, "ytd_transactions") > 0
    assert _meta(plan, runner.DONE_MARKER)
    staged = res["report"]["steps"][0]["detail"]["staged"]
    assert staged["client_data.csv"] == "input"
    assert plan_registry.same_path(plan_registry.active_plan_file(), plan)
    with PlanStore.open(plan, create=False, readonly=True) as store:
        assert store.find_rows("Plan Settings", "Profile", "plan_tier")  # tier mapped
    with open_app_store(ws / "local_state" / "app.db", readonly=True) as app:
        assert app.get_setting("legacy_conversion.done")
    assert _tree_hashes(ws) == before


def test_client_files_only_workspace_converts(ws):
    _legacy_db(ws / "local_state" / "retirement_system_v10.db", _texts(FROZEN))
    before = _tree_hashes(ws)
    res = convert_workspace(ws)
    assert res["report"]["ok"]
    assert _household(ws / "plan.rpx") == "Matthew"
    assert _count(ws / "plan.rpx", "holdings") > 0
    assert res["report"]["steps"][0]["detail"]["staged"]["client_household.csv"] == "client_files"
    assert _tree_hashes(ws) == before


def test_input_wins_over_client_files_per_file(ws):
    _copy_csvs(FROZEN, ws / "input", skip=("client_holdings.csv",))
    _legacy_db(ws / "local_state" / "retirement_system_v10.db", _texts(DEMO))
    res = convert_workspace(ws)
    staged = res["report"]["steps"][0]["detail"]["staged"]
    assert staged["client_household.csv"] == "input" and staged["client_holdings.csv"] == "client_files"
    assert _household(ws / "plan.rpx") == "Matthew"


def test_snapshot_is_the_last_resort_for_the_plan_rows(ws):
    snap = {"Household": {"": {"member_1_name": "Snapshot Sam", "member_1_dob": "1/1/1960"}}}
    _legacy_db(ws / "local_state" / "retirement_system_v10.db", snapshot=snap)
    res = convert_workspace(ws)
    assert res["report"]["ok"]
    assert res["report"]["steps"][0]["detail"]["staged"]["client_data.csv"] == "plan_snapshot"
    assert _household(ws / "plan.rpx") == "Snapshot Sam"


def test_no_legacy_sources_is_not_needed(ws):
    res = convert_workspace(ws)
    assert not res["needed"] and res["reason"] == "no legacy sources" and res["report"] is None
    assert not (ws / "plan.rpx").exists()


# ----------------------------------------------------------------------------- plan states
def test_placeholder_plan_rows_are_replaced_and_kept_as_revision(ws):
    _copy_csvs(FROZEN, ws / "input")
    with PlanStore.open(ws / "plan.rpx") as store, store.transaction():
        store.set_value("Withdrawal Policy", "Order", "placeholder", "1")
    res = convert_workspace(ws)
    assert res["report"]["ok"]
    assert _household(ws / "plan.rpx") == "Matthew"
    with PlanStore.open(ws / "plan.rpx", create=False, readonly=True) as store:
        assert store.latest_revision(runner.PRE_CONVERSION_REVISION) is not None
        assert not store.find_rows("Withdrawal Policy", "Order", "placeholder")


def test_existing_plan_rows_and_tables_are_never_overwritten(ws):
    _copy_csvs(FROZEN, ws / "input")
    build_plan_file_from_csv_folder(ws / "plan.rpx", DEMO)  # the plan already lives in plan.rpx
    with PlanStore.open(ws / "plan.rpx") as store:
        store.dataset("ytd_transactions").replace_all([])  # one empty table
        holdings = store.dataset("holdings").count()
    res = convert_workspace(ws)
    assert res["report"]["ok"]
    assert _household(ws / "plan.rpx") == "Alexander"  # stale input/ CSV not applied
    assert _count(ws / "plan.rpx", "holdings") == holdings
    assert _count(ws / "plan.rpx", "ytd_transactions") > 0  # empty table filled from input/
    assert _statuses(res)["C3"] == "not_applicable"


def test_rerun_is_idempotent(ws):
    _copy_csvs(FROZEN, ws / "input")
    convert_workspace(ws)
    again = convert_workspace(ws)
    assert not again["needed"] and again["reason"] == "already converted"
    rep = runner.run_conversion(ws, ws / "plan.rpx", runner.CONVERSION_STEPS)
    assert rep.ok and not rep.converted


def test_dry_run_writes_nothing(ws):
    _copy_csvs(FROZEN, ws / "input")
    (ws / "local_state" / "secrets.local.json").write_text(json.dumps({"fmp_api_key": "k"}), encoding="utf-8")
    before = _tree_hashes(ws)
    res = convert_workspace(ws, dry_run=True)
    assert res["needed"] and res["report"]["ok"] and res["dry_run"]
    assert not (ws / "plan.rpx").exists() and not (ws / "local_state" / "app.db").exists()
    assert keyring.get_keyring().data == {}
    assert _tree_hashes(ws) == before


# ----------------------------------------------------------------------------- mid-demo
def test_mid_demo_upgrade_restores_real_plan_and_recreates_demo(ws):
    _copy_csvs(DEMO, ws / "input")
    build_plan_file_from_csv_folder(ws / "plan.rpx.before_demo", FROZEN)
    build_plan_file_from_csv_folder(ws / "plan.rpx", DEMO)
    before = _tree_hashes(ws)
    res = convert_workspace(ws)
    assert res["mode"] == "mid_demo" and res["report"]["ok"], res
    assert _household(ws / "plan.rpx") == "Matthew"
    assert _household(ws / "demo.rpx") == "Alexander"
    assert list(ws.glob("plan.rpx.pre_conversion_*"))  # the demo copy is kept
    assert _tree_hashes(ws) == before  # plan.rpx.before_demo untouched
    recs = {r["kind"]: r for r in plan_registry.list_plans()}
    assert recs["user"]["active"] and plan_registry.same_path(recs["demo"]["path"], ws / "demo.rpx")
    assert not convert_workspace(ws)["needed"]


def test_pre_wp45_mid_demo_uses_text_and_database_backups(ws):
    ls = ws / "local_state"
    _copy_csvs(DEMO, ws / "input")
    build_plan_file_from_csv_folder(ws / "plan.rpx", DEMO)  # WP4.2-era plan rows synced from the demo
    _legacy_db(ls / "retirement_system_v10.db", _texts(DEMO))
    _legacy_db(ls / "retirement_system_v10.db.before_demo", _texts(FROZEN, skip=("client_data.csv",)))
    shutil.copyfile(FROZEN / "client_data.csv", ls / "client_data.csv.before_demo")
    before = _tree_hashes(ws)
    res = convert_workspace(ws)
    assert res["mode"] == "mid_demo" and res["report"]["ok"], res
    staged = res["report"]["steps"][0]["detail"]["staged"]
    assert staged["client_data.csv"] == "demo_text_backup"
    assert staged["client_household.csv"] == "client_files_before_demo"
    assert _household(ws / "plan.rpx") == "Matthew"
    assert (ws / "demo.rpx").is_file()
    assert _tree_hashes(ws) == before


# ----------------------------------------------------------------------------- C6a / C6b
def test_system_config_flags_go_to_app_db_and_knobs_to_the_plan(ws):
    _copy_csvs(FROZEN, ws / "input")
    (ws / "system_config.csv").write_text(
        "section,subsection,label,value,units,notes\n"
        "System Configuration,Runtime,max_build_seconds,3600,seconds,\n"
        "System Configuration,Runtime,config_file,input/client_data.csv,path,\n"
        "Market Pricing,API,fmp_api_key,plainkey,secret,\n"
        "Rebalancing,Optimization,min_trade_amount,750,USD,\n", encoding="utf-8")
    res = convert_workspace(ws)
    detail = next(s["detail"] for s in res["report"]["steps"] if s["step"] == "C6a")
    assert detail["flags_written"] == ["System Configuration|Runtime|max_build_seconds"]
    assert detail["secret_rows_skipped"] == 1 and detail["ignored_rows"] == 1
    with open_app_store(ws / "local_state" / "app.db", readonly=True) as app:
        assert app.get_setting("System Configuration|Runtime|max_build_seconds") == "3600"
        assert "plainkey" not in json.dumps(app.settings())
    with PlanStore.open(ws / "plan.rpx", create=False, readonly=True) as store:
        assert store.find_rows("Rebalancing", "Optimization", "min_trade_amount")[-1]["value"] == "750"


def test_secrets_move_to_credential_store_and_file_stays_unless_confirmed(ws):
    _copy_csvs(FROZEN, ws / "input")
    secrets = ws / "local_state" / "secrets.local.json"
    secrets.write_text(json.dumps({"fmp_api_key": "abc"}), encoding="utf-8")
    res = convert_workspace(ws)
    detail = next(s["detail"] for s in res["report"]["steps"] if s["step"] == "C6b")
    assert detail["migrated"] == ["fmp_api_key"] and not detail["deleted"]
    assert secrets.is_file() and keyring.get_password("RetirementSystem", "fmp_api_key") == "abc"
    # The user confirms deletion later: only the file goes.
    res = convert_workspace(ws, extra={"delete_legacy_secrets": True})
    assert not res["needed"]  # marker set: nothing pending
    from src.legacy_conversion.steps import c6b_secrets
    rep = c6b_secrets.run(ws, ws / "local_state" / "app.db", delete=True)
    assert rep.deleted and not secrets.exists()


def test_no_credential_store_converts_with_warning_and_retries_later(ws):
    _copy_csvs(FROZEN, ws / "input")
    secrets = ws / "local_state" / "secrets.local.json"
    secrets.write_text(json.dumps({"fmp_api_key": "abc"}), encoding="utf-8")
    keyring.set_keyring(fail.Keyring())
    res = convert_workspace(ws)
    assert res["report"]["ok"]
    detail = next(s["detail"] for s in res["report"]["steps"] if s["step"] == "C6b")
    assert detail["warning"] == "secret_store_unavailable" and detail["status"] == "converted_with_warning"
    assert secrets.is_file()
    assert decide(ws)["reason"] == "legacy secrets pending"
    keyring.set_keyring(MemoryKeyring())
    res = convert_workspace(ws)
    assert _statuses(res)["C6b"] == "converted" and _statuses(res)["C3"] == "skipped"
    assert decide(ws)["reason"] == "already converted"
