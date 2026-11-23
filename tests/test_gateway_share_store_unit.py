"""gateway.db step 4 (Phase 9, design 5.2) and the share rows: migration, account kinds, sponsors, scoped queries.

Controls C7 (random share ids) and C34 (migration, the kind and role CHECK, member_ids). No HTTP, no worker.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from src.gateway import store as gstore
from src.gateway.share_store import SHARE_ID_RE, ShareLimit, ShareNotFound, ShareSettings, ShareStore
from src.gateway.store import Actor, GatewayStore
from tests.gateway_rig import PW, build_old_gateway_db

CLI = Actor(None, "test")
NOW = 1_000_000.0


@pytest.fixture()
def store(tmp_path):
    return GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4, clock=lambda: NOW)


def _member(store, name="olive", role="user"):
    return store.create_user(name, name.title(), role, PW, now=NOW, actor=CLI, must_change=False)


def _viewer(store, sponsor, name="vic", **kw):
    return store.create_viewer(name, name.title(), PW, sponsor_user_id=sponsor, now=NOW, actor=CLI, **kw)


def _share(shares, owner, viewer, **kw):
    args = {"viewer_id": viewer, "title": "For my advisor", "money_view": "percent",
            "views": ["live", "trends", "projections"], "expires_in_days": 90, "plan_id": "p1"}
    args.update(kw)
    return shares.create(owner, now=NOW, actor=CLI, **args)


def test_migration_keeps_every_row_as_a_member(tmp_path):
    path = tmp_path / "gateway.db"
    build_old_gateway_db(path, 3, users=(("root", "admin"), ("ann", "user"), ("bob", "user")), enrolled=("root",))
    before = sqlite3.connect(path).execute("SELECT id, username, role FROM users ORDER BY id").fetchall()
    s = GatewayStore(path, scrypt_n=2**4, clock=lambda: NOW)
    assert s.schema_version() == gstore.SCHEMA_VERSION == 5
    rows = s._read("SELECT id, username, role, kind, sponsor_user_id FROM users ORDER BY id")
    assert [(r["id"], r["username"], r["role"]) for r in rows] == before
    assert all(r["kind"] == "member" and r["sponsor_user_id"] is None for r in rows)
    assert s.member_ids() == {r["id"] for r in rows} == s.user_ids()
    tables = {r[0] for r in s._read("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"shares", "share_access_log"} <= tables
    # Reopening is idempotent; a newer database is refused by this gateway.
    assert GatewayStore(path, scrypt_n=2**4).schema_version() == gstore.SCHEMA_VERSION
    con = sqlite3.connect(path)
    con.execute("PRAGMA user_version = 6")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError):
        GatewayStore(path, scrypt_n=2**4)


def test_viewer_cannot_be_made_admin(store):
    owner = _member(store)
    vid = _viewer(store, owner)
    with pytest.raises(ValueError):
        store.set_role(vid, "admin", now=NOW, actor=CLI)
    assert store.get_user(vid)["role"] == "user"
    # The CHECK holds even for a write that bypasses the store's methods.
    root = store.create_user("root", "Root", "admin", PW, now=NOW, actor=CLI)
    con = sqlite3.connect(store.path, isolation_level=None)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE users SET role='admin' WHERE id=?", (vid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE users SET kind='guest' WHERE id=?", (owner,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE users SET kind='viewer' WHERE id=?", (root,))
    con.close()


def test_member_ids_exclude_viewers(store):
    a, b = _member(store, "olive"), _member(store, "otto")
    v1, v2 = _viewer(store, a, "vic"), _viewer(store, b, "val")
    assert store.member_ids() == {a, b}
    assert store.user_ids() == {a, b, v1, v2}
    assert store.is_member(a) and not store.is_member(v1) and not store.is_member(9999)
    kinds = {u["id"]: u["kind"] for u in store.list_users(NOW)}
    assert kinds == {a: "member", b: "member", v1: "viewer", v2: "viewer"}


def test_viewer_needs_an_active_member_sponsor_and_the_sponsor_limit_holds(store):
    owner = _member(store)
    with pytest.raises(ValueError):
        _viewer(store, 9999, "nobody")
    vid = _viewer(store, owner, "vic")
    with pytest.raises(ValueError):
        _viewer(store, vid, "chain")  # a viewer cannot sponsor
    store.set_disabled(owner, True, now=NOW, actor=CLI)
    with pytest.raises(ValueError):
        _viewer(store, owner, "late")
    store.set_disabled(owner, False, now=NOW, actor=CLI)
    for i in range(4):
        _viewer(store, owner, f"v{i}x")
    with pytest.raises(ValueError):
        _viewer(store, owner, "sixth")
    row = store.get_user(vid)
    assert row["kind"] == "viewer" and row["sponsor_user_id"] == owner and row["must_change"] == 1
    assert [e["event"] for e in store.read_audit(50)].count("viewer_created") == 5


def test_sponsor_cascade(store, tmp_path):
    shares = ShareStore(store, tmp_path / "shares")
    owner, other = _member(store, "olive"), _member(store, "otto")
    vid = _viewer(store, owner)
    keep = _viewer(store, other, "val")
    sid = _share(shares, owner, vid)
    store.create_session(vid, "active", NOW, "1.2.3.4")
    store.delete_user(owner, now=NOW, actor=CLI)
    assert store.get_user(vid) is None and store.get_user(keep) is not None
    assert store._read("SELECT COUNT(*) FROM shares WHERE id=?", (sid,))[0][0] == 0
    assert store._read("SELECT COUNT(*) FROM sessions WHERE user_id=?", (vid,))[0][0] == 0
    deleted = [e for e in store.read_audit(20) if e["event"] == "viewer deleted"]
    assert deleted and deleted[0]["target_user_id"] == vid


def test_share_ids_are_random_hex_and_never_reused(store, tmp_path):
    shares = ShareStore(store, tmp_path / "shares", ShareSettings(max_shares_per_owner=1000))
    owner = _member(store)
    vid = _viewer(store, owner)
    ids = [_share(shares, owner, vid) for _ in range(200)]
    assert all(SHARE_ID_RE.match(i) for i in ids) and len(set(ids)) == len(ids)
    assert ids != sorted(ids)  # not sequential
    for i in ids[:20]:
        shares.revoke(owner, i, now=NOW, actor=CLI)
    more = [_share(shares, owner, vid) for _ in range(20)]
    assert not set(more) & set(ids)
    assert re.fullmatch(r"[0-9a-f]{32}", ids[0])
    with sqlite3.connect(store.path) as con, pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO shares(id, owner_user_id, grantee_user_id, title, money_view, views, created_at,"
                    " updated_at, expires_at) VALUES ('short', ?, ?, 't', 'percent', '[]', 0, 0, 1)", (owner, vid))


def test_scoped_queries_never_cross_owners_or_viewers(store, tmp_path):
    shares = ShareStore(store, tmp_path / "shares")
    a, b = _member(store, "olive"), _member(store, "otto")
    va, vb = _viewer(store, a, "vic"), _viewer(store, b, "val")
    sa = _share(shares, a, va)
    assert shares.owner_get(a, sa) is not None
    assert shares.owner_get(b, sa) is None
    assert shares.owner_get(a, "x" * 32) is None and shares.owner_get(a, "../../etc") is None
    with pytest.raises(ShareNotFound):
        shares.revoke(b, sa, now=NOW, actor=CLI)
    with pytest.raises(ShareNotFound):
        _share(shares, a, vb)  # owner A cannot grant to B's viewer (C29)
    with pytest.raises(ShareNotFound):
        _share(shares, a, b)  # a member is never a grantee
    assert shares.viewer_get(vb, sa, NOW) is None
    assert shares.viewer_get(va, sa, NOW) is None  # not published yet
    assert [v["id"] for v in shares.sponsored_viewers(a, NOW)] == [va]


def test_share_limit_per_owner(store, tmp_path):
    shares = ShareStore(store, tmp_path / "shares", ShareSettings(max_shares_per_owner=2))
    owner = _member(store)
    vid = _viewer(store, owner)
    first = _share(shares, owner, vid)
    _share(shares, owner, vid)
    with pytest.raises(ShareLimit):
        _share(shares, owner, vid)
    shares.revoke(owner, first, now=NOW, actor=CLI)
    _share(shares, owner, vid)  # a revoked share no longer counts
