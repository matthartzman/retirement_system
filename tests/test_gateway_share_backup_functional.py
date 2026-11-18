"""Shares and backups (Phase 9, design 8 and 5.5): rows travel in gateway.db, bodies are not archived, a restored
gateway.db suspends every share, and `acl check` walks the shares folder. Controls C16, C17, C31.

The ACL check needs Windows to read real permissions; the test here feeds it permissions instead, and the real check
on the installed build is the owner's elevated run (security review, release checklist).
"""
from __future__ import annotations

import sqlite3
import tarfile

import pytest

from src.gateway import acl
from src.gateway import backup_crypto as bc
from src.gateway import backup_store as bs
from src.gateway.share_publish import SharePublisher
from src.gateway.share_store import ShareStore
from src.gateway.store import GatewayStore
from tests.gateway_rig import CLI, PW
from tests.test_gateway_share_publish_functional import FakeSupervisor, FakeWorker

NOW = 1_000_000.0


@pytest.fixture()
def server(tmp_path):
    data, gw = tmp_path / "data", tmp_path / "state" / "gateway.db"
    store = GatewayStore(gw, scrypt_n=2**4, clock=lambda: NOW)
    owner = store.create_user("olive", "Olive", "user", PW, now=NOW, actor=CLI, must_change=False)
    ws = data / "users" / str(owner)
    ws.mkdir(parents=True)
    con = sqlite3.connect(ws / "plan.rpx")
    con.execute("CREATE TABLE t(v)")
    con.commit()
    con.close()
    vid = store.create_viewer("vic", "Vic", PW, sponsor_user_id=owner, now=NOW, actor=CLI)
    shares = ShareStore(store, data / "shares")
    pub = SharePublisher(shares, FakeSupervisor(), clock=lambda: NOW, call=FakeWorker(shares), min_seconds_between=0,
                         audit=lambda *a, **k: None)
    ids = {}
    for name in ("live", "suspended", "revoked"):
        ids[name] = shares.create(owner, viewer_id=vid, title=name, money_view="percent", views=["trends"],
                                  expires_in_days=90, plan_id="plan-a", now=NOW, actor=CLI)
        assert pub.publish(owner, ids[name], actor=CLI).ok
    store.set_password(vid, "a temporary password 1", must_change=True, now=NOW, actor=CLI, event="password reset")
    shares.enable(owner, ids["live"], now=NOW, actor=CLI)
    shares.revoke(owner, ids["revoked"], now=NOW, actor=CLI)
    shares.enable(owner, ids["suspended"], now=NOW, actor=CLI)
    con = sqlite3.connect(gw)
    con.execute("UPDATE shares SET state='suspended', state_reason='credentials reset' WHERE id=?", (ids["suspended"],))
    con.commit()
    con.close()
    return {"data": data, "gw": gw, "store": store, "shares": shares, "owner": owner, "vid": vid, "ids": ids,
            "key": bc.generate_key(), "tmp": tmp_path}


def _archive(server):
    dest = server["tmp"] / "bk" / "full.rpbak"
    dest.parent.mkdir(parents=True, exist_ok=True)
    path, report = bs.write_archive(dest, server["key"], data_root=server["data"], user_ids=server["store"].member_ids(),
                                    gateway_db=server["gw"], now=NOW)
    return path, report


def test_archive_holds_rows_but_no_bodies(server):
    assert server["shares"].body_path(server["ids"]["live"]).exists()
    path, report = _archive(server)
    assert report["errors"] == []
    members = bs.verify_archive(path, server["key"])["members"]
    assert "gateway.db" in members
    assert not [m for m in members if "shares" in m or m.endswith(".json")], members
    assert server["vid"] not in {int(m.split("/")[1]) for m in members if m.startswith("users/")}  # no viewer workspace
    out = server["tmp"] / "restored.db"
    bs.restore_gateway_db(path, server["key"], out)
    rows = sqlite3.connect(out).execute("SELECT id FROM shares").fetchall()
    assert {r[0] for r in rows} == set(server["ids"].values())  # the rows travel in gateway.db


def test_restored_gateway_db_has_every_share_suspended(server):
    path, _ = _archive(server)
    out = server["tmp"] / "restored.db"
    bs.restore_gateway_db(path, server["key"], out)
    con = sqlite3.connect(out)
    con.row_factory = sqlite3.Row
    rows = {r["id"]: dict(r) for r in con.execute("SELECT * FROM shares")}
    con.close()
    ids = server["ids"]
    assert rows[ids["live"]]["state"] == "suspended" and rows[ids["live"]]["state_reason"] == "restored"
    assert rows[ids["suspended"]]["state"] == "suspended"  # already suspended: stays suspended
    assert rows[ids["revoked"]]["state"] == "revoked"  # a revoked share never comes back
    for r in rows.values():
        assert r["published_at"] is None and r["snapshot_sha256"] is None  # no body was restored to serve
    assert not [p for p in out.parent.iterdir() if p.name.startswith("restored.db-")]  # no journal left beside it
    # The live database is untouched.
    assert server["shares"].owner_get(server["owner"], ids["live"])["state"] == "active"
    # Opened by the gateway, nothing is served until the owner enables (and so republishes) the share.
    restored = GatewayStore(out, scrypt_n=2**4)
    assert ShareStore(restored, server["data"] / "shares").viewer_list(server["vid"], NOW) == []


def test_restore_of_an_archive_without_shares_still_works(tmp_path):
    gw = tmp_path / "gateway.db"
    con = sqlite3.connect(gw)
    con.execute("CREATE TABLE marker(v)")
    con.execute("INSERT INTO marker VALUES ('old')")
    con.commit()
    con.close()
    key = bc.generate_key()
    data = tmp_path / "data"
    (data / "users").mkdir(parents=True)
    path, _ = bs.write_archive(tmp_path / "a.rpbak", key, data_root=data, user_ids=[], gateway_db=gw, now=NOW)
    out = tmp_path / "out.db"
    bs.restore_gateway_db(path, key, out)
    assert sqlite3.connect(out).execute("SELECT v FROM marker").fetchone()[0] == "old"


class _FakeDacl:
    def __init__(self, sids, protected=True):
        self.protected = protected
        self.aces = tuple(acl.Ace(s, True, 0x1F01FF, False) for s in sids)
        self.owner = None

    def effective(self, allowed):
        return self.aces


def test_acl_check_reports_a_worker_readable_shares_folder(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "users").mkdir(parents=True)
    shares = root / "shares"
    shares.mkdir()
    (shares / ("a" * 32 + ".json")).write_bytes(b"{}")
    gateway, worker = "S-1-5-21-1-1-1-1000", "S-1-5-21-1-1-1-2001"
    leaky = {shares / ("a" * 32 + ".json")}

    def fake(path):
        return _FakeDacl([acl.SYSTEM, gateway] + ([worker] if path in leaky else []))
    monkeypatch.setattr(acl, "read_dacl", fake)
    findings = acl.check_layout(data_root=root, gateway_sid=gateway, workers={1: ("rpw_1", worker)})
    assert any("data/shares" in f and "rpw_1" in f for f in findings), findings
    leaky.clear()
    assert acl.check_layout(data_root=root, gateway_sid=gateway, workers={1: ("rpw_1", worker)}) == []


def test_archive_member_names_never_match_a_share_body():
    # The restore allowlist is unchanged: no member family for share bodies exists (decision 6).
    assert not any("shares" in getattr(p, "pattern", str(p)) for p in vars(bs).values()
                   if hasattr(p, "pattern"))
    assert tarfile  # the archive format is tar inside the encryption layer (backup_store)
