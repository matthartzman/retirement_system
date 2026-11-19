"""Encrypted backups hold every registered plan of a user (archive format 2) and restore them together."""
from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
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
    assert manifest["format"] == 3
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


def test_a_junction_inside_the_workspace_is_not_followed(server):
    import subprocess

    root = server["data"] / "users" / "2"
    target = server["tmp"] / "bobs"
    _db(target / f"{HEX_B}.rpx", "bob")
    link = root / "linked"
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:  # no junctions off Windows: a directory symlink is the same hazard and fsguard treats it as a link
        os.symlink(target, link, target_is_directory=True)
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


# ---- format 3: each plan's Financial Insight files (trend log, pass-through decisions, live-snapshot settings) ----

LOG, DEC, SET = bs.INSIGHT_FILES
INS_A = Path("output") / "plans" / HEX_A / "insights"
INS_P = Path("output") / "plans" / "plan" / "insights"


def _insights(server, uid: int = 1) -> dict[str, bytes]:
    root = server["data"] / "users" / str(uid)
    files = {INS_A / LOG: b'{"as_of_date": "2026-10-30", "v": 1}\n{"as_of_date": "2026-10-31", "v": 2}\n',
             INS_A / DEC: b'{"k1": "approve"}', INS_P / LOG: b'{"as_of_date": "2026-10-31", "u": %d}\n' % uid,
             INS_P / SET: b'{"pre_tax_rate": "22%"}', INS_A / "monarch_balances.sqlite3": b"rebuilt from the export"}
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return {str(rel): data for rel, data in files.items()}


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _forge_bytes(server, members: dict[str, bytes], fmt: int) -> Path:
    from src.gateway.backup_crypto import EncryptingWriter

    dest = server["tmp"] / f"forged{fmt}.rpbak"
    with open(dest, "wb") as sink:
        writer = EncryptingWriter(sink, server["key"])
        with tarfile.open(fileobj=writer, mode="w|") as tar:
            for name, data in {**members, "manifest.json": json.dumps(
                    {"format": fmt, "members": list(members), "users": [1], "errors": []}).encode()}.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        writer.finish()
    return dest


def test_insight_files_round_trip_byte_equal_and_the_balances_db_is_not_archived(server):
    files = _insights(server)
    u2 = _insights(server, 2)
    archive = _run(server)
    manifest = bs.verify_archive(archive, server["key"])
    got = {m for m in manifest["members"] if "/insights/" in m}
    assert got == {f"users/1/insights/{HEX_A}/{LOG}", f"users/1/insights/{HEX_A}/{DEC}", f"users/1/insights/plan/{LOG}",
                   f"users/1/insights/plan/{SET}", f"users/2/insights/{HEX_A}/{LOG}", f"users/2/insights/{HEX_A}/{DEC}",
                   f"users/2/insights/plan/{LOG}", f"users/2/insights/plan/{SET}"}
    root = server["data"] / "users" / "1"
    (root / INS_A / LOG).write_bytes(b'{"as_of_date": "2026-11-02"}\n')  # a later run
    (root / INS_P / SET).unlink()
    u2_tree = _tree(server["data"] / "users" / "2")
    out = bs.restore_user(archive, server["key"], data_root=server["data"], user_id=1, stamp="t5")
    for rel, data in files.items():
        if not rel.endswith(".sqlite3"):
            assert (root / rel).read_bytes() == data, rel
    assert (root / INS_A / f"{LOG}.before-restore-t5").read_bytes() == b'{"as_of_date": "2026-11-02"}\n'
    assert (root / INS_A / "monarch_balances.sqlite3").read_bytes() == b"rebuilt from the export"  # left alone
    assert f"output/plans/{HEX_A}/insights/{LOG}" in out["restored"]
    assert _tree(server["data"] / "users" / "2") == u2_tree
    assert u2[str(INS_P / LOG)] == (server["data"] / "users" / "2" / INS_P / LOG).read_bytes()


def test_a_format_3_restore_moves_aside_insight_files_made_after_the_backup(server):
    archive = _run(server)  # no insight files yet
    files = _insights(server)
    root = server["data"] / "users" / "1"
    bs.restore_user(archive, server["key"], data_root=server["data"], user_id=1, stamp="t6")
    for rel, data in files.items():
        if rel.endswith(".sqlite3"):
            continue
        assert not (root / rel).exists(), rel
        assert (root / rel).with_name(Path(rel).name + ".before-restore-t6").read_bytes() == data


def test_a_format_2_archive_restores_as_before_and_leaves_live_insight_files_untouched(server):
    files = _insights(server)
    root = server["data"] / "users" / "1"
    plan = (root / "plan.rpx").read_bytes()
    forged = _forge_bytes(server, {"users/1/plan.rpx": plan, f"users/1/insights/{HEX_A}/{LOG}": b'{"x": 1}\n'}, fmt=2)
    before = _tree(root / "output")
    out = bs.restore_user(forged, server["key"], data_root=server["data"], user_id=1, stamp="t7")
    assert _tree(root / "output") == before
    assert out["restored"] == ["plan.rpx"]
    assert files[str(INS_A / LOG)] == (root / INS_A / LOG).read_bytes()


@pytest.mark.parametrize("bad", [
    f"users/1/insights/../../2/{LOG}", f"users/1/insights/{HEX_A}/../../../2/plan.rpx", f"users/1/insights/{'A' * 32}/{LOG}",
    f"users/1/insights/{'a' * 31}/{LOG}", f"users/1/insights/{HEX_A}/monarch_balances.sqlite3",
    f"users/1/insights/{HEX_A}/sub/{LOG}", f"users/1/insights/{HEX_A}/{LOG}.rejected", f"users/1/insights/{HEX_A}",
    f"users/2/insights/{HEX_A}/{LOG}", f"users/01/insights/{HEX_A}/{LOG}", f"users/1/output/plans/{HEX_A}/insights/{LOG}",
])
def test_crafted_insight_member_names_are_never_extracted(server, bad):
    root = server["data"] / "users" / "1"
    forged = _forge_bytes(server, {"users/1/plan.rpx": (root / "plan.rpx").read_bytes(), bad: b'{"evil": 1}\n'}, fmt=3)
    u2 = _tree(server["data"] / "users" / "2")
    out = bs.restore_user(forged, server["key"], data_root=server["data"], user_id=1, stamp="t8")
    assert out["restored"] == ["plan.rpx"]
    assert _tree(server["data"] / "users" / "2") == u2
    assert not any(p.read_bytes() == b'{"evil": 1}\n' for p in server["tmp"].rglob("*") if p.is_file() and p.suffix != ".rpbak")


def test_an_oversize_insight_file_is_skipped_and_reported_on_backup_and_ignored_on_restore(server, monkeypatch):
    _insights(server)
    monkeypatch.setattr(bs, "INSIGHT_MAX_BYTES", 40)
    _, report = bs.write_archive(server["tmp"] / "o.rpbak", server["key"], data_root=server["data"], user_ids=[1],
                                 gateway_db=None, now=T0)
    assert f"users/1/insights/{HEX_A}/{LOG}" not in report["members"]  # 72 bytes: over the cap, never truncated
    assert f"users/1/insights/{HEX_A}/{DEC}" in report["members"]
    assert any(f"insights/{HEX_A}/{LOG}: larger than" in e for e in report["errors"])
    root = server["data"] / "users" / "1"
    forged = _forge_bytes(server, {"users/1/plan.rpx": (root / "plan.rpx").read_bytes(),
                                   f"users/1/insights/{HEX_B}/{LOG}": b"x" * 41}, fmt=3)
    bs.restore_user(forged, server["key"], data_root=server["data"], user_id=1, stamp="t9")
    assert not (root / "output" / "plans" / HEX_B).exists()


def test_a_torn_last_log_line_is_left_out_and_reported(server):
    root = server["data"] / "users" / "1"
    (root / INS_A).mkdir(parents=True)
    (root / INS_A / LOG).write_bytes(b'{"as_of_date": "2026-10-30"}\n{"as_of_date": "2026-10-3')
    archive, report = bs.write_archive(server["tmp"] / "t.rpbak", server["key"], data_root=server["data"], user_ids=[1],
                                       gateway_db=None, now=T0)
    assert any("torn last line" in e for e in report["errors"])
    (root / INS_A / LOG).unlink()
    bs.restore_user(archive, server["key"], data_root=server["data"], user_id=1, stamp="t10")
    assert (root / INS_A / LOG).read_bytes() == b'{"as_of_date": "2026-10-30"}\n'


@pytest.mark.parametrize("what", ["file", "folder"])
def test_a_linked_insight_file_or_folder_is_skipped_and_reported(server, what):
    root = server["data"] / "users" / "1"
    outside = server["tmp"] / "outside"
    outside.mkdir()
    (outside / LOG).write_bytes(b'{"secret": 1}\n')
    (root / INS_A).parent.mkdir(parents=True)
    try:
        if what == "file":
            (root / INS_A).mkdir()
            os.symlink(outside / LOG, root / INS_A / LOG)
        else:
            os.symlink(outside, root / INS_A, target_is_directory=True)
    except OSError:  # Windows without the symlink right: a junction (no right needed) on the folder instead
        import subprocess

        if (root / INS_A).is_dir():
            (root / INS_A).rmdir()
        subprocess.run(["cmd", "/c", "mklink", "/J", str(root / INS_A), str(outside)], check=True, capture_output=True)
    _, report = bs.write_archive(server["tmp"] / "l.rpbak", server["key"], data_root=server["data"], user_ids=[1],
                                 gateway_db=None, now=T0)
    assert not any("/insights/" in m for m in report["members"])
    assert any(f"insights/{HEX_A}/{LOG}: link inside the workspace" in e for e in report["errors"])
