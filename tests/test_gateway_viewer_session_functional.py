"""Viewer sign-in and sessions (Phase 9, design 5.7): stages, limits, the enrol-by deadline, resets, sign-out.

Controls C8-C11, C26 and C27, plus the admin console's Add viewer (design 6.3). In process, no worker.
"""
from __future__ import annotations

import pytest

from src.gateway import store as gstore
from src.gateway.share_store import ShareStore
from src.gateway.store import GatewayStore
from tests.gateway_rig import CLI, PW, Rig, build_old_gateway_db
from tests.test_gateway_admin_console_functional import Recorder

HOUR = 3600.0
API = "/api/auth/admin/console"
TEMP = "temporary password 1"


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path, shared_views=True, lifecycle=Recorder())


def _share(rig, owner, viewer, state="active"):
    shares = ShareStore(rig.store, rig.tmp_path / "shares")
    sid = shares.create(owner, viewer_id=viewer, title="For Vic", money_view="percent", views=["trends"],
                        expires_in_days=90, plan_id="p1", now=rig.now[0], actor=CLI)
    return shares, sid


# ---- C8: the existing stages apply to viewers ----
def test_pending_viewer_reaches_only_the_second_factor(rig):
    owner = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner)
    b = rig.browser()
    assert b.login("vic").get_json()["next"] == "enrol"
    for path in ("/api/viewer/shares", "/api/plans", "/gateway/account"):
        r = b.get(path)
        assert r.status_code in (302, 401), path
    assert b.get("/gateway/viewer").headers.get("Location") == "/gateway/enrol"
    rig.enrol(b, vid)
    assert b.get("/api/viewer/shares").status_code == 200
    assert b.get("/api/auth/session").get_json()["kind"] == "viewer"
    assert b.get("/api/auth/session").get_json()["insights"] is False
    assert rig.upstream.calls == []


def test_viewer_must_change_password_first(rig):
    owner = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner, must_change=True)
    b = rig.browser()
    b.login("vic")
    rig.enrol(b, vid)
    assert b.get("/api/viewer/shares").status_code == 409
    assert b.get("/gateway/viewer").headers["Location"] == "/gateway/account"
    assert b.get("/gateway/account").status_code == 200
    r = b.post("/api/auth/password", json={"current": PW, "new": "a brand new long password"})
    assert r.status_code == 200
    assert b.get("/api/viewer/shares").status_code == 200
    assert rig.upstream.calls == []


# ---- C9: shorter sessions ----
def test_viewer_idle_and_absolute_limits(rig):
    owner_b, owner = rig.signed_in("olive")
    v, _vid = rig.signed_in_viewer("vic", sponsor=owner)
    assert v.get("/api/viewer/shares").status_code == 200
    rig.advance(9 * 60)
    assert v.get("/api/viewer/shares").status_code == 200  # 9 minutes idle: still signed in
    rig.advance(10 * 60 + 1)
    assert v.get("/api/viewer/shares").status_code == 401  # 10 minutes idle: signed out
    assert owner_b.get("/api/auth/session").status_code == 401  # the member was idle 19 minutes too
    # Absolute: 2 hours, however active.
    m, _ = rig.signed_in("mel")
    v2, _ = rig.signed_in_viewer("val", sponsor=owner)
    for _ in range(14):  # 14 x 9 minutes = 126 minutes
        rig.advance(9 * 60)
        v2.get("/api/viewer/shares")
        m.get("/api/plans")
    assert v2.get("/api/viewer/shares").status_code == 401
    assert m.get("/api/plans").status_code == 200  # members keep 12 hours


# ---- C10: the enrol-by deadline, for every account ----
def test_viewer_not_enrolled_within_the_deadline_is_locked(rig):
    owner = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner)
    rig.advance(72 * HOUR - 60)
    pending = rig.browser()
    assert pending.login("vic").status_code == 200  # just inside the deadline: the password works
    rig.advance(120)
    pending.post("/api/auth/totp/enrol/start")
    r = pending.post("/api/auth/totp/enrol/confirm", json={"code": rig.code(vid)})
    assert r.status_code in (400, 401)  # a session opened before the deadline cannot finish after it
    assert rig.browser().login("vic").status_code == 401  # locked out: the generic error
    reasons = [e["details"] for e in rig.store.read_audit(50) if e["event"] == "login failed"]
    assert "reason enrol_overdue" in reasons
    # An admin issues a new temporary password: a fresh 72 hours.
    rig.store.set_password(vid, TEMP, must_change=True, now=rig.now[0], actor=CLI, event="password reset")
    b = rig.browser()
    assert b.login("vic", password=TEMP).status_code == 200
    rig.enrol(b, vid)
    rig.advance(100 * HOUR)  # enrolled: the deadline no longer matters
    assert rig.store.verify_password("vic", TEMP, rig.now[0]).ok


def test_member_not_enrolled_within_the_deadline_is_locked(rig):
    uid = rig.add_user("mel")
    rig.advance(72 * HOUR + 1)
    assert rig.browser().login("mel").status_code == 401
    assert rig.store.verify_password("mel", PW, rig.now[0]).reason == "enrol_overdue"
    # An admin TOTP reset is a reset too: a fresh deadline.
    rig.store.reset_totp(uid, now=rig.now[0], actor=CLI)
    b = rig.browser()
    assert b.login("mel").status_code == 200
    rig.enrol(b, uid)
    assert b.get("/api/plans").status_code == 200
    # An enrolled member is never affected, however old the account.
    rig.advance(1000 * HOUR)
    assert rig.store.verify_password("mel", PW, rig.now[0]).ok


def test_unenrolled_account_gets_a_fresh_deadline_at_upgrade(tmp_path):
    path = tmp_path / "gateway.db"
    build_old_gateway_db(path, 3, users=(("root", "admin"), ("ann", "user")), enrolled=("root",))
    upgrade = 50_000_000.0  # long after both accounts were created (at 1000)
    s = GatewayStore(path, scrypt_n=2**4, clock=lambda: upgrade)
    assert s.schema_version() == gstore.SCHEMA_VERSION
    ann, root = s.find_user("ann"), s.find_user("root")
    s.set_password(ann["id"], PW, must_change=False, now=upgrade, actor=CLI)  # a real hash for the check below
    assert ann["enrol_by"] == upgrade + gstore.ENROL_DEADLINE_SECONDS
    assert root["enrol_by"] is None  # enrolled: unaffected
    assert s.verify_password("ann", PW, upgrade + 71 * HOUR).ok
    assert s.verify_password("ann", PW, upgrade + 73 * HOUR).reason == "enrol_overdue"
    assert not s.enrol_overdue(root["id"], upgrade + 10_000 * HOUR)


# ---- C11: an admin reset suspends the viewer's shares ----
def test_admin_reset_suspends_the_viewers_shares(rig):
    admin, _ = rig.signed_in("root", role="admin")
    owner = rig.add_user("olive")
    vid = rig.add_viewer("vic", sponsor=owner)
    other_owner = rig.add_user("otto")
    other_viewer = rig.add_viewer("val", sponsor=other_owner)
    shares, sid = _share(rig, owner, vid)
    _s2, keep = _share(rig, other_owner, other_viewer)
    r = admin.post(API + "/users/reset-password", json={"id": vid, "temp_password": TEMP})
    assert r.status_code == 200
    row = shares.owner_get(owner, sid)
    assert row["state"] == "suspended" and row["state_reason"] == "credentials reset"
    assert shares.owner_get(other_owner, keep)["state"] == "active"
    shares.enable(owner, sid, now=rig.now[0], actor=CLI)
    assert admin.post(API + "/users/reset-totp", json={"id": vid}).status_code == 200
    assert shares.owner_get(owner, sid)["state"] == "suspended"
    events = [e["event"] for e in rig.store.read_audit(50)]
    assert events.count("share_suspended") == 2
    # A member's own password change never suspends anything, and a member's reset has no shares to suspend.
    assert admin.post(API + "/users/reset-password", json={"id": owner, "temp_password": TEMP}).status_code == 200
    assert shares.owner_get(other_owner, keep)["state"] == "active"


# ---- C26: viewer sign-out ----
def test_viewer_logout_clears_the_cache(rig):
    _ob, owner = rig.signed_in("olive")
    v, _vid = rig.signed_in_viewer("vic", sponsor=owner)
    r = v.post("/api/auth/logout")
    assert r.status_code == 200 and r.headers["Clear-Site-Data"] == '"cache"'
    assert "Max-Age=0" in r.headers["Set-Cookie"]
    assert v.get("/api/viewer/shares").status_code == 401
    m, _ = rig.signed_in("mel")
    assert "Clear-Site-Data" not in m.post("/api/auth/logout").headers


# ---- C27: the status poll does not keep the session alive ----
def test_status_poll_does_not_keep_the_session_alive(rig):
    _ob, owner = rig.signed_in("olive")
    v, _vid = rig.signed_in_viewer("vic", sponsor=owner)
    status = "/api/viewer/shares/" + "a" * 32 + "/status"
    v.get("/api/viewer/shares")
    for _ in range(3):  # 3 x 4 minutes of background polling = 12 minutes with no real request
        rig.advance(4 * 60)
        v.get(status, headers={"X-Background-Poll": "1"})
    assert v.get("/api/viewer/shares").status_code == 401
    # The header is honoured on that one route only: anywhere else it is an ordinary request.
    v2, _ = rig.signed_in_viewer("val", sponsor=owner)
    for _ in range(3):
        rig.advance(4 * 60)
        v2.get("/api/viewer/shares", headers={"X-Background-Poll": "1"})
    assert v2.get("/api/viewer/shares").status_code == 200


# ---- Add viewer (design 6.3) ----
def test_admin_console_adds_a_viewer_without_a_workspace(tmp_path):
    rec = Recorder()
    rig = Rig(tmp_path, shared_views=True, lifecycle=rec)
    admin, admin_id = rig.signed_in("root", role="admin")
    owner = rig.add_user("olive")
    rec.calls.clear()
    r = admin.post(API + "/viewers", json={"username": "vic", "display_name": "Vic", "temp_password": TEMP,
                                           "sponsor_id": owner})
    assert r.status_code == 200, r.get_data(as_text=True)
    vid = r.get_json()["id"]
    assert rec.calls == []  # no user_created: no workspace, no Windows account, no worker
    users = {u["id"]: u for u in admin.get(API + "/users").get_json()["users"]}
    assert users[vid]["kind"] == "viewer" and users[vid]["sponsor_id"] == owner
    assert users[vid]["expires_at"] == pytest.approx(rig.now[0] + 90 * 86400)
    assert admin.get(API + "/users").get_json()["features"]["viewers"] is True
    # Role change is refused; disable and delete never reach the lifecycle for a viewer.
    assert admin.post(API + "/users/update", json={"id": vid, "role": "admin"}).status_code == 400
    assert admin.post(API + "/users/disable", json={"id": vid}).status_code == 200
    assert admin.post(API + "/users/delete", json={"id": vid, "confirm_username": "vic"}).status_code == 200
    assert rec.calls == []
    # A member is still provisioned through the same console.
    r = admin.post(API + "/users", json={"username": "mel", "display_name": "Mel", "temp_password": TEMP})
    assert rec.calls == [("user_created", r.get_json()["id"])]
    # The sponsor must be a member.
    assert admin.post(API + "/viewers", json={"username": "vx", "display_name": "V", "temp_password": TEMP,
                                              "sponsor_id": admin_id + 999}).status_code == 400


def test_add_viewer_is_refused_with_the_flag_off(tmp_path):
    rig = Rig(tmp_path)
    admin, _ = rig.signed_in("root", role="admin")
    owner = rig.add_user("olive")
    r = admin.post(API + "/viewers", json={"username": "vic", "display_name": "Vic", "temp_password": TEMP,
                                           "sponsor_id": owner})
    assert r.status_code == 404
    assert rig.store.find_user("vic") is None
    assert "viewers" not in admin.get(API + "/users").get_json()["features"] or \
        admin.get(API + "/users").get_json()["features"]["viewers"] is False
