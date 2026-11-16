"""Folder permissions, unelevated, on temp folders this test owns: apply the layout, then check that
the checker finds every widening (a broad group, another worker, inheritance left on)."""
from __future__ import annotations

import os
import subprocess

import pytest

from src.gateway import acl, winapi

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != "nt", reason="Windows-only")]
# Stand-ins for two worker accounts: real local groups, so icacls accepts them without creating accounts.
WORKER_A = "S-1-5-32-559"  # Performance Log Users
WORKER_B = "S-1-5-32-558"  # Performance Monitor Users


@pytest.fixture
def layout(tmp_path):
    me = winapi.current_user_sid()
    root = tmp_path / "data"
    (root / "users" / "1").mkdir(parents=True)
    (root / "users" / "2").mkdir(parents=True)
    (root / "users" / "1" / "plan.rpx").write_bytes(b"a")
    gw = tmp_path / "gw"
    gw.mkdir()
    (gw / "gateway.db").write_bytes(b"")
    acl.lock_gateway_only(root, gateway_sid=me)
    acl.lock_gateway_only(root / "users", gateway_sid=me)
    acl.lock_user_folder(root / "users" / "1", account_sid=WORKER_A, gateway_sid=me)
    acl.lock_user_folder(root / "users" / "2", account_sid=WORKER_B, gateway_sid=me)
    acl.lock_gateway_only(gw, gateway_sid=me)
    workers = {1: ("rpw_1", WORKER_A), 2: ("rpw_2", WORKER_B)}
    yield root, gw, me, workers
    subprocess.run(["icacls", str(tmp_path), "/reset", "/T", "/C", "/Q"], capture_output=True)


def test_the_applied_layout_checks_clean(layout):
    root, gw, me, workers = layout
    assert acl.check_layout(data_root=root, gateway_sid=me, workers=workers, gateway_db=gw / "gateway.db") == []
    dacl = acl.read_dacl(root / "users" / "1")
    assert dacl.protected and {a.sid for a in dacl.aces} == {acl.SYSTEM, acl.ADMINISTRATORS, me, WORKER_A}
    child = acl.read_dacl(root / "users" / "1" / "plan.rpx")
    assert WORKER_B not in {a.sid for a in child.aces}


def test_another_workers_access_to_a_user_folder_is_found(layout):
    root, gw, me, workers = layout
    subprocess.run(["icacls", str(root / "users" / "1" / "plan.rpx"), "/grant", f"*{WORKER_B}:R"], check=True,
                   capture_output=True)
    findings = acl.check_layout(data_root=root, gateway_sid=me, workers=workers)
    assert any("data/users/1 [plan.rpx]" in f and "rpw_2" in f for f in findings), findings


def test_a_broad_group_or_inheritance_is_found(layout):
    root, gw, me, workers = layout
    subprocess.run(["icacls", str(root / "users"), "/grant", f"*{acl.USERS}:(OI)(CI)RX"], check=True, capture_output=True)
    subprocess.run(["icacls", str(gw), "/inheritance:e"], check=True, capture_output=True)
    findings = acl.check_layout(data_root=root, gateway_sid=me, workers=workers, gateway_db=gw / "gateway.db")
    assert any(f.startswith("data/users:") and "Users has access" in f for f in findings), findings
    assert any("gateway.db folder: still inherits" in f for f in findings), findings


def test_the_install_folder_may_be_read_but_not_written(tmp_path):
    me = winapi.current_user_sid()
    inst = tmp_path / "install"
    inst.mkdir()
    acl.lock_install_readonly(inst, gateway_sid=me)
    assert acl.check_readonly(inst, writers={acl.SYSTEM, acl.ADMINISTRATORS, me}, workers={}, what="install") == []
    subprocess.run(["icacls", str(inst), "/grant", f"*{acl.USERS}:(OI)(CI)M"], check=True, capture_output=True)
    assert acl.check_readonly(inst, writers={acl.SYSTEM, acl.ADMINISTRATORS, me}, workers={}, what="install")
    subprocess.run(["icacls", str(tmp_path), "/reset", "/T", "/C", "/Q"], capture_output=True)


def test_a_folder_readable_by_workers_is_reported_never_changed(tmp_path):
    findings = acl.check_not_readable_by_workers(tmp_path, workers={}, what="owner folder")
    # A temp folder under the profile normally grants only the owner, SYSTEM and Administrators.
    before = acl.read_dacl(tmp_path)
    subprocess.run(["icacls", str(tmp_path), "/grant", f"*{acl.USERS}:R"], check=True, capture_output=True)
    after = acl.check_not_readable_by_workers(tmp_path, workers={}, what="owner folder")
    assert any("Users can read it" in f for f in after) and len(after) > len(findings)
    assert before.aces is not None


def test_setup_refuses_drive_roots_and_git_working_copies(tmp_path):
    with pytest.raises(acl.AclError):
        acl.lock_gateway_only(tmp_path.anchor and type(tmp_path)(tmp_path.anchor), gateway_sid="S-1-5-18")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(acl.AclError):
        acl.lock_gateway_only(repo / "data", gateway_sid="S-1-5-18")
    assert not (repo / "data").exists()


def test_the_check_command_fails_loudly(layout, capsys):
    root, gw, me, _workers = layout
    subprocess.run(["icacls", str(root), "/grant", "*S-1-1-0:R"], check=True, capture_output=True)
    code = acl.main(["check", "--data-root", str(root), "--gateway-sid", me])
    err = capsys.readouterr().err
    assert code == 1 and "FAILED" in err and "Everyone has access" in err


def test_an_owner_rights_ace_is_benign_only_while_the_owner_is_trusted(tmp_path):
    """CI runners add an OWNER RIGHTS ACE to folders; it reaches only the owner, so it must not be flagged
    while the owner is the gateway/Administrators, but must be once some other account owns the object."""
    me = winapi.current_user_sid()
    inst = tmp_path / "install"
    inst.mkdir()
    acl.lock_install_readonly(inst, gateway_sid=me)
    subprocess.run(["icacls", str(inst), "/grant", f"*{acl.OWNER_RIGHTS}:(OI)(CI)F"], check=True, capture_output=True)
    dacl = acl.read_dacl(inst)
    assert acl.OWNER_RIGHTS in {a.sid for a in dacl.aces} and dacl.owner
    trusted = {acl.SYSTEM, acl.ADMINISTRATORS, me, dacl.owner}
    assert acl.check_readonly(inst, writers=trusted, workers={}, what="install") == []
    # Owned by an account outside the trusted set, the same ACE is a real grant to that account.
    assert acl.check_readonly(inst, writers={acl.SYSTEM, acl.ADMINISTRATORS}, workers={}, what="install")
    subprocess.run(["icacls", str(tmp_path), "/reset", "/T", "/C", "/Q"], capture_output=True)
