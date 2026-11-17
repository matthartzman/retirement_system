"""Encrypted backups hold every registered plan of a user (archive format 2) and restore them together."""
from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.gateway import backup_crypto as bc
from src.gateway import backup_store as bs
from src.stores.app_store import AppStore

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
HEX_A, HEX_B = "a" * 32, "b" * 32


def _db(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    con.execute("DELETE FROM t")
    con.execute("INSERT INTO t VALUES (?)", (value,))
    con.commit()
    con.close()


def _val(path: Path) -> str:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("SELECT v FROM t").fetchone()[0]
    finally:
        con.close()


def _user(data: Path, uid: int, extra: list[tuple[str, str, str]]) -> Path:
    """A workspace with plan.rpx plus (relative path, plan id, kind) extras, all registered in app.db."""
    root = data / "users" / str(uid)
    _db(root / "plan.rpx", f"u{uid}-plan")
    (root / "local_state").mkdir(parents=True, exist_ok=True)
    with AppStore.open(root / "local_state" / "app.db") as store:
        store.register_plan(root / "plan.rpx", "My Plan", "user", plan_id="plan")
        for rel, pid, kind in extra:
            _db(root / rel, f"u{uid}-{pid}")
            store.register_plan(root / rel, pid, kind, plan_id=pid)
    return root


@pytest.fixture()
def server(tmp_path):
    data = tmp_path / "data"
    _user(data, 1, [(f"plans/{HEX_A}.rpx", HEX_A, "user"), (f"plans/{HEX_B}.rpx", HEX_B, "case"),
                    ("saved_plans/Uploaded (2).rpx", "up", "user"), ("demo.rpx", "demo", "demo")])
    _user(data, 2, [(f"plans/{HEX_A}.rpx", HEX_A, "user")])
    _db(tmp_path / "gw.db", "gw")
    return {"data": data, "gw": tmp_path / "gw.db", "dest": tmp_path / "bk", "key": bc.generate_key(), "tmp": tmp_path}


def _run(server):
    sched = bs.EncryptedBackupScheduler(data_root=server["data"], gateway_db=server["gw"], dest=server["dest"],
                                        master=server["key"], user_ids=lambda: [1, 2], clock=lambda: T0)
    return sched.run_once()


def test_archive_holds_app_db_and_every_registered_plan_but_not_the_demo(server):
    manifest = bs.verify_archive(_run(server), server["key"])
    assert manifest["format"] == 2
    got = {m for m in manifest["members"] if m.startswith("users/1/")}
    assert got == {"users/1/app.db", "users/1/plan.rpx", f"users/1/plans/{HEX_A}.rpx", f"users/1/plans/{HEX_B}.rpx",
                   "users/1/saved_plans/Uploaded (2).rpx"}


def test_restore_round_trips_every_plan_and_leaves_other_users_alone(server):
    path = _run(server)
    root = server["data"] / "users" / "1"
    other_before = (server["data"] / "users" / "2" / "plans" / f"{HEX_A}.rpx").read_bytes()
    for rel in ("plan.rpx", f"plans/{HEX_A}.rpx", f"plans/{HEX_B}.rpx", "saved_plans/Uploaded (2).rpx"):
        _db(root / rel, "damaged")
    bs.restore_user(path, server["key"], data_root=server["data"], user_id=1, stamp="t1")
    assert _val(root / "plan.rpx") == "u1-plan"
    assert _val(root / "plans" / f"{HEX_A}.rpx") == f"u1-{HEX_A}"
    assert _val(root / "plans" / f"{HEX_B}.rpx") == f"u1-{HEX_B}"
    assert _val(root / "saved_plans" / "Uploaded (2).rpx") == "u1-up"
    assert (server["data"] / "users" / "2" / "plans" / f"{HEX_A}.rpx").read_bytes() == other_before
    assert (root / "plans" / f"{HEX_A}.rpx.before-restore-t1").is_file()  # the damaged file is kept aside


def test_restore_moves_aside_plans_created_after_the_backup(server):
    path = _run(server)
    root = server["data"] / "users" / "1"
    _db(root / "plans" / ("c" * 32 + ".rpx"), "newer")
    bs.restore_user(path, server["key"], data_root=server["data"], user_id=1, stamp="t2")
    assert not (root / "plans" / ("c" * 32 + ".rpx")).exists()
    assert (root / "plans" / ("c" * 32 + ".rpx.before-restore-t2")).is_file()


def test_a_registry_row_outside_the_workspace_or_with_a_bad_name_is_skipped_not_fatal(server):
    root = server["data"] / "users" / "2"
    outside = server["tmp"] / "elsewhere.rpx"
    _db(outside, "secret")
    _db(root / "plans" / "weird name.rpx", "x")
    with AppStore.open(root / "local_state" / "app.db") as store:
        store.register_plan(outside, "evil", "user", plan_id="evil")
        store.register_plan(root / "plans" / "weird name.rpx", "weird", "user", plan_id="weird")
    path = _run(server)
    manifest = bs.verify_archive(path, server["key"])
    members = [m for m in manifest["members"] if m.startswith("users/2/")]
    assert sorted(members) == sorted(["users/2/app.db", "users/2/plan.rpx", f"users/2/plans/{HEX_A}.rpx"])
    assert any("skipped" in e for e in manifest["errors"])
    assert b"secret" not in path.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="junction")
def test_a_junction_inside_the_workspace_is_not_followed(server):
    import subprocess

    root = server["data"] / "users" / "2"
    target = server["tmp"] / "bobs"
    _db(target / f"{HEX_B}.rpx", "bob")
    link = root / "linked"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    with AppStore.open(root / "local_state" / "app.db") as store:
        store.register_plan(link / f"{HEX_B}.rpx", "j", "user", plan_id="j")
    manifest = bs.verify_archive(_run(server), server["key"])
    assert not any("linked" in m for m in manifest["members"])


def _forge(server, names: list[str], fmt: int = 2) -> Path:
    """An authentic archive (right key) carrying crafted member names, as a hostile or buggy writer might."""
    from src.gateway.backup_crypto import EncryptingWriter

    dest = server["tmp"] / "forged.rpbak"
    with open(dest, "wb") as sink:
        writer = EncryptingWriter(sink, server["key"])
        with tarfile.open(fileobj=writer, mode="w|") as tar:
            for n in names:
                data = b"SQLite format 3\x00" + b"0" * 50
                info = tarfile.TarInfo(n)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            blob = json.dumps({"format": fmt, "members": names, "users": [1], "errors": []}).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
        writer.finish()
    return dest


@pytest.mark.parametrize("bad", [
    "users/1/plans/../../2/plan.rpx", "users/1/plans/evil.rpx", "users/1/../2/plan.rpx", "users/1/plans/" + "a" * 31 + ".rpx",
    "users/1/saved_plans/../../plan.rpx", "users/1/saved_plans/a/b.rpx", "users/1/local_state/tmp/x.rpx",
    "users/01/plan.rpx", "users/1/plan.rpx.bak",
])
def test_crafted_member_names_are_never_extracted(server, bad):
    forged = _forge(server, ["users/1/app.db", bad])
    u2 = {str(p): p.read_bytes() for p in (server["data"] / "users" / "2").rglob("*") if p.is_file()}
    bs.restore_user(forged, server["key"], data_root=server["data"], user_id=1, stamp="t3")
    assert {str(p): p.read_bytes() for p in (server["data"] / "users" / "2").rglob("*") if p.is_file()} == u2
    names = {p.name for p in server["tmp"].rglob("*")}
    assert "evil.rpx" not in names and "b.rpx" not in names and "plan.rpx.bak" not in names


def test_a_format_1_archive_still_restores_only_its_two_files(server):
    root = server["data"] / "users" / "1"
    legacy = _forge(server, ["users/1/plan.rpx", "users/1/app.db"], fmt=1)
    # the forged members are not databases we can read back: assert only what is replaced and what is not touched
    keep = (root / "plans" / f"{HEX_A}.rpx").read_bytes()
    bs.restore_user(legacy, server["key"], data_root=server["data"], user_id=1, stamp="t4")
    assert (root / "plans" / f"{HEX_A}.rpx").read_bytes() == keep
    assert (root / "plan.rpx.before-restore-t4").is_file()
