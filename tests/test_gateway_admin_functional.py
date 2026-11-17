"""Gateway Users admin over HTTP: admin-only access, create, promote/demote, disable, reset, the last-admin rule."""
from __future__ import annotations

import pytest

from src.gateway.store import LastAdminError
from tests.gateway_rig import CLI, PW, Rig


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


def test_admin_routes_and_page_refuse_non_admins(rig):
    b, _uid = rig.signed_in("ann")
    assert b.get("/api/auth/admin/users").status_code == 403
    assert b.post("/api/auth/admin/users", json={"username": "x"}).status_code == 403
    assert b.get("/api/auth/admin/audit").status_code == 403
    assert b.get("/gateway/users").status_code == 403
    anon = rig.browser()
    assert anon.get("/api/auth/admin/users").status_code == 401
    assert anon.get("/gateway/users").status_code == 302


def test_no_self_signup_route(rig):
    anon = rig.browser()
    for path in ["/api/auth/signup", "/api/auth/register", "/api/auth/admin/users"]:
        assert anon.post(path, json={"username": "eve", "password": PW}).status_code in (401, 403, 404)
    assert rig.store.find_user("eve") is None


def test_admin_creates_user_who_must_enrol_and_change_password(rig):
    admin, aid = rig.signed_in("root", role="admin")
    assert admin.get("/gateway/admin").status_code == 200  # /gateway/users redirects here (see the console tests)
    r = admin.post("/api/auth/admin/users", json={"username": "Ann", "display_name": "Ann A", "role": "user",
                                                    "temp_password": "temporary password 1"})
    assert r.status_code == 200, r.get_data(as_text=True)
    uid = r.get_json()["id"]
    users = admin.get("/api/auth/admin/users").get_json()["users"]
    ann = next(u for u in users if u["id"] == uid)
    assert ann["username"] == "ann" and ann["must_change"] is True and ann["totp"] == "none"
    assert "pw_hash" not in repr(users) and "secret" not in repr(users)
    assert admin.post("/api/auth/admin/users", json={"username": "ann", "display_name": "dup", "role": "user",
                                                     "temp_password": "temporary password 1"}).status_code == 400
    b = rig.browser(ip="198.51.100.3")
    assert b.login("ann", "temporary password 1").get_json()["next"] == "enrol"
    created = next(r for r in rig.store.read_audit(limit=30) if r["event"] == "user created" and r["target_user_id"] == uid)
    assert created["actor_user_id"] == aid and created["actor_username"] == "root"


def test_promote_demote_and_last_admin_rule(rig):
    admin, aid = rig.signed_in("root", role="admin")
    for action, body in [("role", {"role": "user"}), ("disabled", {"disabled": True}), ("delete", {})]:
        r = admin.post(f"/api/auth/admin/users/{aid}/{action}", json=body)
        assert r.status_code == 409 and r.get_json()["last_admin"] is True, action
    uid = rig.add_user("ann")
    assert admin.post(f"/api/auth/admin/users/{uid}/role", json={"role": "admin"}).status_code == 200
    assert admin.post(f"/api/auth/admin/users/{uid}/role", json={"role": "owner"}).status_code == 400
    # With a second admin, the first can step down; the second is then the last one.
    assert admin.post(f"/api/auth/admin/users/{aid}/role", json={"role": "user"}).status_code == 200
    assert admin.get("/api/auth/admin/users").status_code == 401  # demotion ended root's sessions
    events = [(r["event"], r["actor_user_id"], r["target_user_id"]) for r in rig.store.read_audit(limit=30)]
    assert ("role changed", aid, uid) in events and ("role changed", aid, aid) in events
    assert rig.store.count_active_admins() == 1
    with pytest.raises(LastAdminError):
        rig.store.set_role(uid, "user", now=rig.now[0], actor=CLI)


def test_promoted_admin_reaches_admin_routes_after_own_totp(rig):
    admin, _aid = rig.signed_in("root", role="admin")
    b, uid = rig.signed_in("ann")
    assert b.get("/api/auth/admin/users").status_code == 403
    admin.post(f"/api/auth/admin/users/{uid}/role", json={"role": "admin"})
    assert b.get("/api/auth/admin/users").status_code == 401  # role change ends sessions
    b2 = rig.browser()
    b2.login("ann")
    b2.post("/api/auth/totp/verify", json={"code": rig.code(uid)})
    b2.refresh_csrf()
    assert b2.get("/api/auth/admin/users").status_code == 200


def test_disable_enable_unlock_reset_password_reset_totp_delete(rig):
    admin, aid = rig.signed_in("root", role="admin")
    b, uid = rig.signed_in("ann")
    assert admin.post(f"/api/auth/admin/users/{uid}/disabled", json={"disabled": True}).status_code == 200
    assert b.get("/api/plan/rows").status_code == 401
    assert admin.post(f"/api/auth/admin/users/{uid}/disabled", json={"disabled": False}).status_code == 200
    for _ in range(5):
        rig.browser(ip="198.51.100.4").login("ann", "wrong password!!")
    assert next(u for u in admin.get("/api/auth/admin/users").get_json()["users"] if u["id"] == uid)["locked"] is True
    assert admin.post(f"/api/auth/admin/users/{uid}/unlock").status_code == 200
    r = admin.post(f"/api/auth/admin/users/{uid}/reset-password", json={"temp_password": "short"})
    assert r.status_code == 400
    r = admin.post(f"/api/auth/admin/users/{uid}/reset-password", json={"temp_password": "reset password 123"})
    assert r.status_code == 200
    assert admin.post(f"/api/auth/admin/users/{uid}/reset-totp").status_code == 200
    b3 = rig.browser(ip="198.51.100.5")
    assert b3.login("ann", "reset password 123").get_json()["next"] == "enrol"
    assert admin.post("/api/auth/admin/users/999/delete").status_code == 404
    assert admin.post(f"/api/auth/admin/users/{uid}/delete").status_code == 200
    assert rig.store.get_user(uid) is None
    audit = admin.get("/api/auth/admin/audit?limit=100").get_json()["events"]
    mine = {e["event"] for e in audit if e["actor_user_id"] == aid}
    assert {"user disabled", "user enabled", "user unlocked", "password reset", "totp reset", "user deleted"} <= mine
    assert "reset password 123" not in repr(audit)


def test_admin_cannot_reach_other_users_data_routes_through_admin_api(rig):
    """Admin routes are gateway-owned; the upstream never sees them."""
    admin, _ = rig.signed_in("root", role="admin")
    admin.get("/api/auth/admin/users")
    assert all(not p.startswith("/api/auth/") for _m, p, _i in rig.upstream.calls)
