"""The operator CLI end to end against fixture users and a real gateway.db: backup, restore, migrate-all, rollback."""
from __future__ import annotations

import io
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.gateway import backup_crypto as bc
from src.gateway import backup_dest as bd
from src.gateway import backup_store as bs
from src.gateway import migrate_all as ma
from src.gateway import ops
from src.gateway.store import Actor, GatewayStore

pytestmark = pytest.mark.integration
SEED = Path(__file__).resolve().parents[1] / "src" / "reference" / "demo_seed.rpx"


def _dump(path: Path) -> list[str]:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return list(con.iterdump())
    finally:
        con.close()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for name in bd.SYNC_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(bd, "profiles_root", lambda: tmp_path / "Users")


@pytest.fixture()
def srv(tmp_path):
    root = tmp_path / "srv"
    store = GatewayStore(root / "state" / "gateway.db", scrypt_n=2**4)
    ids = [store.create_user(n, n.title(), "user", "a long enough password 1", now=1.0, actor=Actor(None, "t", listener="cli"),
                             must_change=False) for n in ("ann", "bob", "cy")]
    data = root / "data"
    for uid in ids:
        ws = data / "users" / str(uid)
        (ws).mkdir(parents=True)
        shutil.copy2(SEED, ws / "plan.rpx")
    key = tmp_path / "keys" / "backup.key"
    return SimpleNamespace(root=root, data=data, db=root / "state" / "gateway.db", dest=tmp_path / "bk", key=key,
                           ids=ids, tmp=tmp_path)


def _ops(srv, *argv):
    out, err = io.StringIO(), io.StringIO()
    base = ["--data-root", str(srv.data), "--gateway-db", str(srv.db), "--backup-dir", str(srv.dest),
            "--key-file", str(srv.key)]
    head = [a for a in argv[:2] if not a.startswith("--")]
    code = ops.main([*head, *base, *argv[len(head):]], stdout=out, stderr=err)  # later options win
    return code, out.getvalue(), err.getvalue()


def _make_key(srv):
    srv.key.parent.mkdir(parents=True, exist_ok=True)  # existing folder: the command never re-permissions it
    code, out, err = _ops(srv, "backup-key", "create")
    assert code == 0, err
    return bc.read_key_file(srv.key)


def test_key_is_created_once_and_kept_out_of_the_backup_folder_and_synced_folders(srv):
    _make_key(srv)
    code, _, err = _ops(srv, "backup-key", "create")
    assert code == 1 and "never overwritten" in err
    bad = SimpleNamespace(**{**srv.__dict__, "key": srv.dest / "backup.key"})
    assert _ops(bad, "backup-key", "create")[0] == 2
    onedrive = SimpleNamespace(**{**srv.__dict__, "key": srv.tmp / "OneDrive" / "backup.key"})
    assert _ops(onedrive, "backup-key", "create")[0] == 2
    assert not (srv.dest / "backup.key").exists()


def test_backup_run_list_verify_then_restore_one_user_and_the_gateway_db(srv):
    master = _make_key(srv)
    code, out, err = _ops(srv, "backup", "run")
    assert code == 0, err
    archive = next(srv.dest.glob("*.rpbak"))
    assert _ops(srv, "backup", "list")[1].count(".rpbak") == 1
    assert _ops(srv, "backup", "verify", "--archive", str(archive))[0] == 0
    ann, bob, cy = srv.ids
    before = {uid: (srv.data / "users" / str(uid) / "plan.rpx").read_bytes() for uid in (ann, cy)}
    good = _dump(srv.data / "users" / str(bob) / "plan.rpx")
    (srv.data / "users" / str(bob) / "plan.rpx").write_bytes(b"corrupted by a bad disk" * 50)
    code, out, err = _ops(srv, "restore", "--archive", str(archive), "--user", str(bob))
    assert code == 0, err
    assert _dump(srv.data / "users" / str(bob) / "plan.rpx") == good
    assert {uid: (srv.data / "users" / str(uid) / "plan.rpx").read_bytes() for uid in (ann, cy)} == before
    new_db = srv.tmp / "gateway.restored.db"
    assert _ops(srv, "restore", "--archive", str(archive), "--gateway-db-out", str(new_db))[0] == 0
    assert {u["username"] for u in GatewayStore(new_db).list_users(2.0)} == {"ann", "bob", "cy"}
    assert master  # the key never appears in output
    assert base64_of(master) not in out + err


def base64_of(key: bytes) -> str:
    import base64

    return base64.b64encode(key).decode()


def test_wrong_key_and_corrupt_archive_exit_nonzero_and_restore_nothing(srv):
    _make_key(srv)
    _ops(srv, "backup", "run")
    archive = next(srv.dest.glob("*.rpbak"))
    plan = srv.data / "users" / str(srv.ids[0]) / "plan.rpx"
    before = plan.read_bytes()
    other = srv.tmp / "other.key"
    bc.write_key_file(other)
    code, _, err = _ops(srv, "restore", "--archive", str(archive), "--user", str(srv.ids[0]), "--key-file", str(other))
    assert code == 1 and "Wrong or missing key" in err
    raw = bytearray(archive.read_bytes())
    raw[len(raw) // 3] ^= 0x55
    archive.write_bytes(bytes(raw))
    code, _, err = _ops(srv, "restore", "--archive", str(archive), "--user", str(srv.ids[0]))
    assert code == 1 and "damaged" in err
    assert _ops(srv, "backup", "verify", "--archive", str(archive))[0] == 1
    assert plan.read_bytes() == before


def test_destination_refusals_are_reported_with_exit_2(srv):
    _make_key(srv)
    for bad in (srv.tmp / "OneDrive" / "bk", srv.data / "users" / "bk", srv.tmp / "Users" / "me" / "bk"):
        moved = SimpleNamespace(**{**srv.__dict__, "dest": bad})
        code, _, err = _ops(moved, "backup", "run")
        assert code == 2 and err.startswith("Refused:"), (bad, err)
        assert not bad.exists()


def test_config_file_supplies_the_defaults(srv):
    cfg = srv.tmp / "gateway.json"
    cfg.write_text(json.dumps({"argv": ["--db", str(srv.db), "--funnel-port", "5065", "--public-origin",
                                        "https://node.example.ts.net:8443", "--data-root", str(srv.data),
                                        "--backup-dir", str(srv.dest), "--backup-key-file", str(srv.key)]}))
    _make_key(srv)
    out, err = io.StringIO(), io.StringIO()
    assert ops.main(["backup", "run", "--config", str(cfg)], stdout=out, stderr=err) == 0, err.getvalue()
    assert len(list(srv.dest.glob("*.rpbak"))) == 1


def test_migrate_all_backs_up_first_migrates_each_user_and_rollback_restores_the_snapshot(srv):
    _make_key(srv)
    ann, bob, cy = srv.ids
    report_file = srv.tmp / "report.json"
    plan_bob = srv.data / "users" / str(bob) / "plan.rpx"
    original = _dump(plan_bob)
    code, out, err = _ops(srv, "migrate-all", "--report", str(report_file))
    assert code == 0, out + err
    report = json.loads(report_file.read_text())
    assert report["ok"] and [r["status"] for r in report["users"]] == ["ok", "ok", "ok"]
    snaps = sorted(p.name for p in srv.dest.glob("*.user*.rpbak"))
    assert len(snaps) == 3 and all(r["snapshot"] in snaps for r in report["users"])
    assert "schema version" in out
    # rollback: the migration (or later damage) is undone from bob's pre-migration snapshot, only for bob
    snap = srv.dest / next(r["snapshot"] for r in report["users"] if r["user"] == bob)
    plan_bob.write_bytes(b"half migrated garbage" * 40)
    cy_before = (srv.data / "users" / str(cy) / "plan.rpx").read_bytes()
    assert _ops(srv, "restore", "--archive", str(snap), "--user", str(bob))[0] == 0
    assert _dump(plan_bob) == original
    assert (srv.data / "users" / str(cy) / "plan.rpx").read_bytes() == cy_before


def test_migrate_all_reports_a_failing_user_and_still_does_the_others(srv):
    _make_key(srv)
    ann, bob, cy = srv.ids
    (srv.data / "users" / str(bob) / "plan.rpx").write_bytes(b"this is not a database" * 100)
    code, out, err = _ops(srv, "migrate-all")
    assert code == 1
    lines = {int(l.split(":")[0].split()[1]): l for l in out.splitlines() if l.startswith("user ")}
    assert "OK" in lines[ann] and "OK" in lines[cy] and "FAILED" in lines[bob]
    assert f"failed [{bob}]" in out
    # the unmigratable user was not given a false snapshot-as-rollback and nothing else was changed
    assert (srv.data / "users" / str(bob) / "plan.rpx").read_bytes().startswith(b"this is not a database")


def test_migrate_all_orchestration_skips_busy_users_and_requires_a_snapshot(tmp_path):
    for uid in (1, 2, 3, 4):
        (tmp_path / "users" / str(uid)).mkdir(parents=True)
    migrated: list[int] = []

    def snapshot(uid):
        if uid == 3:
            raise OSError("disk full")
        return Path(f"s{uid}.rpbak")

    def migrate(ws):
        migrated.append(int(ws.name))
        return {"ok": True, "detail": "migrated"}

    rep = ma.migrate_all(data_root=tmp_path, user_ids=[4, 1, 2, 3, 9], snapshot=snapshot, migrate=migrate,
                         in_use=lambda ws: ws.name == "2")
    by = {r["user"]: r for r in rep["users"]}
    assert migrated == [1, 4]
    assert by[2]["status"] == "skipped" and by[3]["status"] == "failed" and "no pre-migration snapshot" in by[3]["detail"]
    assert by[9]["status"] == "skipped" and not rep["ok"]
    assert "RESULT: failed [3], skipped [2, 9]" in ma.format_report(rep)


def test_funnel_and_power_commands_do_nothing_without_yes(srv):
    calls: list[list[str]] = []

    def fake(argv, **kw):
        calls.append(list(argv))
        return SimpleNamespace(stdout=json.dumps({}), stderr="", returncode=0)

    out, err = io.StringIO(), io.StringIO()
    assert ops.main(["funnel", "apply", "--funnel-port", "5065", "--external-port", "8443"], stdout=out, stderr=err,
                    run=fake) == 0
    assert "Command: tailscale funnel --bg --https=8443 http://127.0.0.1:5065" in out.getvalue() and calls == []
    assert ops.main(["funnel", "apply", "--funnel-port", "5065", "--external-port", "443"], stdout=out, stderr=err,
                    run=fake) == 2 and calls == []
    assert ops.main(["funnel", "off", "--funnel-port", "5065", "--external-port", "443", "--yes"], stdout=out,
                    stderr=err, run=fake) == 2 and calls == []
    assert ops.main(["power", "apply"], stdout=out, stderr=err, run=fake) == 0 and calls == []


def test_funnel_apply_with_yes_refuses_over_an_existing_misconfiguration_and_verifies_after(srv):
    bad = {"Web": {"n:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5057"}}}}, "AllowFunnel": {"n:8443": True}}
    good_after = {"Web": {"n:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5058"}}},
                          "n:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5065"}}}},
                  "AllowFunnel": {"n:443": True, "n:8443": True}}
    state = {"doc": bad, "ran": []}

    def fake(argv, **kw):
        if argv[:3] == ["tailscale", "serve", "status"]:
            return SimpleNamespace(stdout=json.dumps(state["doc"]), returncode=0)
        state["ran"].append(argv)
        state["doc"] = good_after
        return SimpleNamespace(stdout="ok", stderr="", returncode=0)

    args = ["funnel", "apply", "--funnel-port", "5065", "--external-port", "8443", "--yes"]
    out, err = io.StringIO(), io.StringIO()
    assert ops.main(args, stdout=out, stderr=err, run=fake) == 1 and state["ran"] == []
    assert "5057" in err.getvalue()
    state["doc"] = {}
    out, err = io.StringIO(), io.StringIO()
    assert ops.main(args, stdout=out, stderr=err, run=fake) == 0
    assert state["ran"] == [["tailscale", "funnel", "--bg", "--https=8443", "http://127.0.0.1:5065"]]
    assert "Verified: Funnel configuration OK." in out.getvalue()
    out, err = io.StringIO(), io.StringIO()
    assert ops.main(["funnel", "check", "--funnel-port", "5065"], stdout=out, stderr=err, run=fake) == 0


def test_funnel_check_fails_when_tailscale_cannot_be_read(srv):
    def missing(*a, **k):
        raise FileNotFoundError

    out, err = io.StringIO(), io.StringIO()
    assert ops.main(["funnel", "check", "--funnel-port", "5065"], stdout=out, stderr=err, run=missing) == 1
    assert "UNVERIFIED" in err.getvalue()


def test_gateway_start_refuses_unencrypted_or_misplaced_backups(srv, tmp_path):
    import threading

    from src.gateway.server import run_gateway

    base = ["--db", str(srv.db), "--local-port", "0", "--no-tailscale-check", "--data-root", str(srv.data)]
    stop = threading.Event()
    assert run_gateway([*base, "--backup-dir", str(srv.dest)], stop) == 2  # no key file: refused
    key = _make_key(srv) and srv.key
    assert run_gateway([*base, "--backup-dir", str(tmp_path / "OneDrive" / "bk"), "--backup-key-file", str(key)], stop) == 2
    assert run_gateway([*base, "--backup-dir", str(srv.dest), "--backup-key-file", str(srv.dest / "k.key")], stop) == 2
    assert run_gateway([*base, "--backup-dir", str(srv.dest), "--backup-key-file", str(srv.tmp / "missing.key")], stop) == 2
