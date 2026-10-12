"""WP10.3: the conversion's verification and safeguard, with failures injected.

* a verification difference (converter fault) blocks the done marker and the activation, leaves
  the live plan and every original untouched, and is reported by key NAME only; a rerun after
  the fault is gone converts (reusing the verified backup); the user can accept the difference;
* the tier safeguard: a mapping that changes the projection blocks; keeping the switches converts;
* a backup whose copy does not hash back aborts before anything changes;
* a process killed in the plan phase, right before the swap, or after the swap leaves the
  originals and the live plan intact (or replaced as a whole by the verified copy) and a rerun
  finishes;
* idempotency, dry run, the persisted result, advisory checks (old build KPIs, source agreement),
  the secrets file kept out of the backup unless the user opts in;
* the production engine mode (Roth strategy scored) on the frozen sample.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import keyring
import pytest

from src import module_catalog as mc
from src import plan_registry
from src.app_state import APP_DB_ENV, open_app_store
from src.legacy_conversion import backup, convert_workspace, runner, verify
from src.legacy_conversion.result import LAST_RESULT_KEY
from src.legacy_conversion.steps import c3_plan_rows, t8_tier_mapping
from src.stores import PlanStore
from tests import plan_fixture as pf
from tests.test_legacy_conversion_workspace_functional import MemoryKeyring, _legacy_db, _texts

ROOT = Path(__file__).resolve().parents[1]
FROZEN = pf.fixture_dir("sample_frozen")
SENTINEL = "TAMPERED_SENTINEL_VALUE"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    (root / "local_state").mkdir(parents=True)
    shutil.copytree(FROZEN, root / "input", ignore=shutil.ignore_patterns("*.md"))
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv(APP_DB_ENV, str(root / "local_state" / "app.db"))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.setattr(verify, "ROTH_OPTIMIZED", False)
    plan_registry.invalidate()
    prev = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield root
    keyring.set_keyring(prev)
    plan_registry.invalidate()


def _originals(root: Path) -> dict[str, str]:
    """sha256 of every original (everything but the files a conversion may write)."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and rel.parts[0] not in ("backups",) and not p.name.startswith(("plan.rpx", "demo.rpx", "app.db")) \
                and "conversion_staging" not in rel.parts:
            out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _plan_view(plan: Path) -> dict | None:
    """The live plan's content (rows, dataset counts, conversion markers), or None."""
    if not plan.is_file():
        return None
    with PlanStore.open(plan, create=False, readonly=True) as store:
        return {"rows": store.sectioned_data(),
                "counts": {n: store.dataset(n).count() for n in ("holdings", "ytd_transactions")},
                "markers": {k: store.get_meta(k) for k in runner.marker_keys()}}


def _placeholder_plan(root: Path) -> Path:
    """A live plan that is not the user's (rows, no household): the conversion replaces it."""
    plan = root / "plan.rpx"
    with PlanStore.open(plan) as store, store.transaction():
        store.set_value("Withdrawal Policy", "Order", "placeholder", "1")
    return plan


def _app(root: Path):
    return open_app_store(root / "local_state" / "app.db", readonly=True)


def _tamper_c3(monkeypatch, label: str = "member_1_name") -> None:
    real = c3_plan_rows.convert_rows

    def tampered(rows):
        out, renamed, retired = real(rows)
        out = [dataclasses.replace(r, value=SENTINEL) if (r.section, r.subsection, r.label) == ("Household", "", label) else r
               for r in out]
        return out, renamed, retired

    monkeypatch.setattr(c3_plan_rows, "convert_rows", tampered)


# ----------------------------------------------------------------------------- verification blocks
def test_verification_difference_blocks_done_marker_and_activation(ws, monkeypatch):
    live = _placeholder_plan(ws)
    before_live, before = _plan_view(live), _originals(ws)
    _tamper_c3(monkeypatch)
    res = convert_workspace(ws)
    assert res.status == "blocked" and res.blocked_reason == "verification_differences" and res.can_accept
    assert not res.verified and not res.plan_replaced
    assert "/Household//member_1_name" in res.differing_keys["plan_rows"]
    assert res.check("engine_config").status == "diff"  # the old view and the converted plan run apart
    assert _plan_view(live) == before_live  # live plan untouched: no rows, no markers, no done marker
    assert _originals(ws) == before
    assert not (ws / "local_state" / "conversion_staging").exists()
    with _app(ws) as app:
        assert app.list_plans() == []  # not registered, not activated
        assert app.get_setting("legacy_conversion.done") is None
        last = app.get_setting(LAST_RESULT_KEY)
    assert last["status"] == "blocked" and last["blocked_reason"] == "verification_differences"
    assert SENTINEL not in json.dumps(res.as_dict()) and SENTINEL not in json.dumps(last)  # names, never values
    assert res.backup["verified"] and (ws / res.backup["path"] / "manifest.json").is_file()

    monkeypatch.undo()  # the fault is gone; same workspace, same environment
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv(APP_DB_ENV, str(ws / "local_state" / "app.db"))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.setattr(verify, "ROTH_OPTIMIZED", False)
    plan_registry.invalidate()
    again = convert_workspace(ws)
    assert again.status == "done" and again.verified, again.as_dict()
    assert again.backup["reused"] and again.backup["path"] == res.backup["path"]  # retries do not pile up copies
    assert again.plan_replaced and again.plan_backup and (ws / again.plan_backup).is_file()
    with PlanStore.open(live, create=False, readonly=True) as store:
        assert store.get_meta(runner.DONE_MARKER) and store.find_rows("Household", "", "member_1_name")[-1]["value"] == "Matthew"
        assert "accepted=0" in store.get_meta(runner.VERIFIED_MARKER)
    with PlanStore.open(ws / again.plan_backup, create=False, readonly=True) as store:
        assert store.find_rows("Withdrawal Policy", "Order", "placeholder")  # the old live plan, kept
    assert plan_registry.same_path(plan_registry.active_plan_file(), live)
    assert _originals(ws) == before


def test_user_can_accept_differences_and_it_is_recorded(ws, monkeypatch):
    _tamper_c3(monkeypatch)
    res = convert_workspace(ws, extra={"accept_differences": True})
    assert res.status == "done" and res.accepted_differences and not res.verified
    assert "accepted:verification_differences" in res.warnings
    with PlanStore.open(ws / "plan.rpx", create=False, readonly=True) as store:
        assert "accepted=1" in store.get_meta(runner.VERIFIED_MARKER) and store.get_meta(runner.DONE_MARKER)


def test_dry_run_reports_the_block_and_writes_nothing(ws, monkeypatch):
    _tamper_c3(monkeypatch)
    before = sorted(str(p) for p in ws.rglob("*"))
    res = convert_workspace(ws, dry_run=True)
    assert res.status == "dry_run" and res.blocked_reason == "verification_differences" and not res.ok
    assert res.backup["planned"] and res.backup["files"] > 0
    assert sorted(str(p) for p in ws.rglob("*")) == before  # no plan, no app.db, no backup, no staging


# ----------------------------------------------------------------------------- tier safeguard
def _tamper_tier(monkeypatch, key: str = "housing_location_search") -> None:
    """A mapping that also switches off an engine feature whose data moves the projection."""
    real = t8_tier_mapping.map_tier

    def tampered(features):
        m = real(features)
        if m.switches.get(key):
            m.switches[key] = False
            m.turn_off.append(key)
        return m

    monkeypatch.setattr(t8_tier_mapping, "map_tier", tampered)


def test_tier_mapping_that_moves_the_projection_blocks_and_keeping_switches_converts(ws, monkeypatch):
    before = _originals(ws)
    _tamper_tier(monkeypatch)
    res = convert_workspace(ws)
    assert res.status == "blocked" and res.blocked_reason == "tier_mapping_changes_results" and res.can_accept
    tier = res.check("tier_mapping")
    assert tier.status == "diff" and tier.differing > 0 and "housing_location_search" in tier.note
    assert res.differing_keys["tier_mapping"] and all(c.status == "match" for c in res.checks if c.name in ("plan_rows", "datasets"))
    assert not (ws / "plan.rpx").exists() and _originals(ws) == before

    res = convert_workspace(ws, extra={"tier_mapping": "keep"})  # the user keeps the plan's switches
    assert res.status == "done" and res.verified, res.as_dict()
    assert res.check("tier_mapping").status == "not_applicable"
    with PlanStore.open(ws / "plan.rpx", create=False, readonly=True) as store:
        assert not mc.plan_profile(store)["tier_stored"]
        assert store.get_meta(t8_tier_mapping.MARKER_KEY) == "switches kept"
        assert mc.stored_switch(store, "housing_location_search")


def test_real_tier_mapping_leaves_the_projection_unchanged(ws):
    res = convert_workspace(ws)
    tier = res.check("tier_mapping")
    assert res.status == "done" and tier.status == "match" and tier.compared > 0
    assert "switched:" in tier.note


# ----------------------------------------------------------------------------- backup
def test_backup_hash_mismatch_aborts_before_anything_changes(ws, monkeypatch):
    live = _placeholder_plan(ws)
    before_live, before = _plan_view(live), _originals(ws)
    real = backup.copy_file

    def corrupt(src, dest):
        real(src, dest)
        if src.name == "client_holdings.csv":
            with open(dest, "ab") as fh:
                fh.write(b"x")

    monkeypatch.setattr(backup, "copy_file", corrupt)
    res = convert_workspace(ws)
    assert res.status == "blocked" and res.blocked_reason == "backup_failed" and not res.can_accept
    assert not res.backup["verified"] and res.backup["error"] == "hash_mismatch:1"
    assert res.steps == []  # nothing converted
    manifest = json.loads((ws / res.backup["path"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verified"] is False
    assert _plan_view(live) == before_live and _originals(ws) == before

    monkeypatch.setattr(backup, "copy_file", real)
    again = convert_workspace(ws)
    assert again.status == "done" and not again.backup["reused"] and again.backup["path"] != res.backup["path"]


def test_backup_holds_verified_copies_of_the_originals_without_secrets_unless_opted(ws):
    (ws / "system_config.csv").write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
    secrets = ws / "local_state" / "secrets.local.json"
    secrets.write_text(json.dumps({"fmp_api_key": "k"}), encoding="utf-8")
    snap = runner.snapshot_sources(backup.backup_paths(ws))
    res = backup.ensure_backup(ws, snap, stamp="t1")
    assert res.verified and not res.secrets_included
    manifest = json.loads((res.path / "manifest.json").read_text(encoding="utf-8"))
    paths = {e["path"]: e for e in manifest["files"]}
    assert "system_config.csv" in paths and "input/client_data.csv" in paths
    assert "local_state/secrets.local.json" not in paths
    for rel, e in paths.items():
        copy = res.path / "files" / rel
        assert hashlib.sha256(copy.read_bytes()).hexdigest() == e["sha256"] == hashlib.sha256((ws / rel).read_bytes()).hexdigest()
    assert backup.ensure_backup(ws, snap, stamp="t2").reused  # same originals: reused
    opted = backup.ensure_backup(ws, snap, extra={"backup_legacy_secrets": True}, stamp="t3")
    assert opted.verified and opted.secrets_included and not opted.reused
    assert (opted.path / "files" / "local_state" / "secrets.local.json").is_file()
    (ws / "input" / "client_data.csv").write_text("changed\n", encoding="utf-8")
    assert not backup.ensure_backup(ws, runner.snapshot_sources(backup.backup_paths(ws)), stamp="t4").reused


# ----------------------------------------------------------------------------- killed mid-run
CHILD = r"""
import os, sys
sys.path.insert(0, {root!r})
from src.legacy_conversion import verify
verify.ROTH_OPTIMIZED = False

def die(*a, **k):
    os._exit(17)

point = {point!r}
if point == "plan_phase":
    from src.legacy_conversion.steps import t8_tier_mapping
    t8_tier_mapping.run = die
elif point == "swap":
    import src.plan_db_replace as pdr
    pdr.remove_sidecars = die  # replace_active_db calls it right before the atomic os.replace
elif point == "install":
    from src.legacy_conversion.steps import c6c_register
    c6c_register.run = die
from src.legacy_conversion import convert_workspace
convert_workspace({ws!r})
os._exit(0)
"""


@pytest.mark.parametrize("point", ["plan_phase", "swap", "install"])
def test_killed_mid_run_leaves_originals_and_live_plan_and_rerun_finishes(ws, point):
    live = _placeholder_plan(ws)
    before_live, before = _plan_view(live), _originals(ws)
    env = {**os.environ, "RETIREMENT_SYSTEM_WORKSPACE_ROOT": str(ws), APP_DB_ENV: str(ws / "local_state" / "app.db")}
    env.pop("RETIREMENT_SYSTEM_PLAN_DB", None)
    proc = subprocess.run([sys.executable, "-c", CHILD.format(root=str(ROOT), point=point, ws=str(ws))],
                          env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    assert proc.returncode == 17, proc.stderr[-2000:]
    assert _originals(ws) == before
    after = _plan_view(live)
    if point == "install":
        # The verified copy replaced the live plan as a whole; no done marker yet.
        assert after["markers"][runner.VERIFIED_MARKER] and after["markers"][runner.DONE_MARKER] is None
        assert after["rows"]["Household"][""]["member_1_name"] == "Matthew"
    else:
        assert after == before_live  # the live plan is exactly as it was
    plan_registry.invalidate()
    res = convert_workspace(ws)
    assert res.status == "done" and res.verified, res.as_dict()
    assert res.backup is None or res.backup["reused"]  # the killed run's verified backup serves
    assert _plan_view(live)["markers"][runner.DONE_MARKER]
    assert not (ws / "local_state" / "conversion_staging").exists()
    assert _originals(ws) == before


# ----------------------------------------------------------------------------- idempotency, results
def test_rerun_is_idempotent_one_backup_one_swap(ws):
    first = convert_workspace(ws)
    assert first.status == "done" and first.plan_replaced and first.plan_backup is None  # no live plan before
    again = convert_workspace(ws)
    assert again.status == "not_needed" and again.reason == "already converted" and not again.steps
    rep = runner.run_conversion(ws, ws / "plan.rpx", runner.CONVERSION_STEPS)
    assert rep.ok and not rep.converted
    assert len(list((ws / "backups").glob("pre_conversion_*"))) == 1
    with _app(ws) as app:
        assert app.get_setting(LAST_RESULT_KEY)["status"] == "done"


def test_result_is_machine_readable_and_privacy_safe(ws):
    res = convert_workspace(ws)
    d = res.as_dict()
    json.dumps(d)  # serialisable
    assert d["status"] == "done" and d["verified"] and d["ok"] and not d["blocked_reason"]
    assert {c["name"] for c in d["checks"]} == {"plan_rows", "engine_config", "engine_output", "datasets",
                                                "tier_mapping", "old_build_kpis", "source_agreement"}
    assert d["backup"]["path"].startswith("backups/pre_conversion_") and d["backup"]["verified"]
    assert [s["step"] for s in d["steps"]] == ["SRC", "C3", "C3b", "C4a", "C4b", "C4c", "C6a", "T8", "C6a.flags", "C6b", "C6c"]
    text = json.dumps(res.summary())
    for value in ("Matthew", "Illinois"):  # plan values never reach the stored summary
        assert value not in text


def test_old_build_kpis_and_source_disagreement_only_warn(ws):
    texts = _texts(FROZEN)
    texts["client_holdings.csv"] = texts["client_holdings.csv"] + "\n"  # a db copy that differs from input/
    _legacy_db(ws / "local_state" / "retirement_system_v10.db", {"client_holdings.csv": texts["client_holdings.csv"] + "X,Y,,,,\n"})
    with closing(sqlite3.connect(ws / "local_state" / "retirement_system_v10.db")) as con, con:
        con.execute("CREATE TABLE kpi_snapshots(snapshot_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, build_id TEXT,"
                    " kpi_json TEXT NOT NULL)")
        con.execute("INSERT INTO kpi_snapshots VALUES('k1','2026-09-01T00:00:00Z','b1',?)",
                    (json.dumps({"terminal_nw_deterministic": 1.0, "lifetime_tax": 2.0}),))
    res = convert_workspace(ws)
    assert res.status == "done" and res.verified, res.as_dict()
    kpis, agree = res.check("old_build_kpis"), res.check("source_agreement")
    assert not kpis.blocking and kpis.status == "diff" and set(kpis.names) == {"terminal_nw_deterministic", "lifetime_tax"}
    assert not agree.blocking and agree.names == ["client_holdings.csv"]
    assert "old_build_kpis:diff" in res.warnings and "source_agreement:diff" in res.warnings


def test_old_build_kpis_read_from_snapshot_or_summary(tmp_path):
    ws = tmp_path
    assert verify.old_build_kpis(ws) is None
    (ws / "output").mkdir()
    (ws / "output" / "plan_summary.json").write_text(json.dumps({"terminal_nw": 10.0, "lifetime_tax": "x"}), encoding="utf-8")
    assert verify.old_build_kpis(ws) == ("plan_summary.json", {"terminal_nw_deterministic": 10.0})
    assert verify.kpi_check(("s", {"lifetime_tax": 5.0}), {"lifetime_tax": 5.004}).status == "match"  # to the cent
    assert verify.kpi_check(("s", {"lifetime_tax": 5.0}), {"lifetime_tax": 6.0}).names == ["lifetime_tax"]


def test_production_engine_mode_verifies_the_frozen_sample(ws, monkeypatch):
    """The projection as the build reports it (Roth strategy scored): every check matches."""
    monkeypatch.setattr(verify, "ROTH_OPTIMIZED", True)
    res = convert_workspace(ws)
    assert res.status == "done" and res.verified, res.as_dict()
    for name in ("plan_rows", "engine_config", "engine_output", "datasets", "tier_mapping"):
        assert res.check(name).status == "match", name
