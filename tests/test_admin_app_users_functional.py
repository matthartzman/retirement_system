"""Admin app user, grant, activity and audit routes, driven through the WSGI facade."""
from __future__ import annotations

import json

import pytest

from admin_app.main import create_app
from src.identity import IdentityStore

PW = "correct horse"


class Rig:
    def __init__(self, tmp_path):
        self.now = [1000.0]
        self.store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
        self.client = create_app(self.store, clock=lambda: self.now[0]).test_client()
        self.store.add_user("Owner", "owner", PW, role="admin", insights=False, must_change=False)

    def post(self, path, body):
        r = self.client.post(path, json=body)
        return r.status_code, json.loads(r.get_data(as_text=True))

    def get(self, path):
        r = self.client.get(path)
        return r.status_code, json.loads(r.get_data(as_text=True))

    def add(self, username="ann", **extra):
        body = {"display_name": username.title(), "username": username, "temp_password": PW,
                "grants": {"insights": {"money_view": "dollars"}}, **extra}
        status, out = self.post("/api/users", body)
        assert status == 200, out
        return out["id"]

    def user(self, uid):
        return next(u for u in self.get("/api/users")[1]["users"] if u["id"] == uid)

    def actions(self):
        return [a["action"] for a in self.store.read_audit()]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_pages_are_served_with_security_headers(rig):
    for path, mime in (("/", "text/html"), ("/users.js", "text/javascript"), ("/admin.css", "text/css")):
        r = rig.client.get(path)
        assert r.status_code == 200 and mime in r.headers["Content-Type"]
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Cache-Control"] == "no-store"
    assert rig.client.get("/../src/identity/store.py").status_code == 404
    assert rig.client.get("/api/ping").status_code == 200


def test_add_user_with_grants_never_returns_or_audits_secrets(rig):
    uid = rig.add("ann", role="user", grants={"insights": {"money_view": "both", "views": ["live"]}, "planner": True})
    u = rig.user(uid)
    assert u["username"] == "ann" and u["must_change"] is True and u["status"] == "active"
    by_app = {g["app"]: g for g in u["grants"]}
    assert by_app["insights"]["money_view"] == "both" and by_app["insights"]["views"] == ["live"]
    assert "planner" in by_app
    assert rig.store.verify_login("ann", PW, 1001.0).ok
    blob = json.dumps([rig.get("/api/users")[1], rig.get("/api/audit")[1]])
    assert PW not in blob and "pw_hash" not in blob and "pw_salt" not in blob
    assert rig.store.read_audit()[0]["action"] == "user.add"


def test_add_user_validation(rig):
    assert rig.post("/api/users", {"display_name": "X", "username": "x", "temp_password": "short"})[0] == 400
    rig.add("ann")
    assert rig.post("/api/users", {"display_name": "A", "username": "ANN", "temp_password": PW})[0] == 400  # duplicate, case-folded
    assert rig.post("/api/users", {"display_name": "B", "username": "bob", "temp_password": PW, "role": "root"})[0] == 400
    bad_view = {"insights": {"money_view": "dollars", "views": ["nope"]}}
    assert rig.post("/api/users", {"display_name": "B", "username": "bob", "temp_password": PW, "grants": bad_view})[0] == 400
    assert rig.store.get_user_by_username("bob") is None  # a refused add leaves nothing behind


def test_add_user_without_grants_cannot_use_insights(rig):
    status, out = rig.post("/api/users", {"display_name": "Cy", "username": "cy", "temp_password": PW})
    assert status == 200
    assert rig.user(out["id"])["grants"] == []


def test_update_user_role_expiry_and_notes(rig):
    uid = rig.add("ann")
    assert rig.post("/api/users/update", {"id": uid, "display_name": "Ann B", "notes": "cousin", "expires_at": 5000.0})[0] == 200
    u = rig.user(uid)
    assert (u["display_name"], u["notes"], u["expires_at"]) == ("Ann B", "cousin", 5000.0)
    assert rig.post("/api/users/update", {"id": uid, "expires_at": None})[0] == 200
    assert rig.user(uid)["expires_at"] is None
    assert rig.post("/api/users/update", {"id": uid, "expires_at": "soon"})[0] == 400
    assert rig.post("/api/users/update", {"id": 999, "notes": "x"})[0] == 404
    assert "cousin" not in json.dumps(rig.get("/api/audit")[1])  # notes content is not audited


def test_expiring_now_ends_sessions(rig):
    uid = rig.add("ann")
    before = rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/update", {"id": uid, "expires_at": 500.0})[0] == 200
    u = rig.user(uid)
    assert u["expired"] and u["session_epoch"] > before
    assert not rig.store.verify_login("ann", PW, 1001.0).ok


def test_last_admin_cannot_be_demoted_disabled_expired_or_deleted(rig):
    owner = rig.store.get_user_by_username("owner")["id"]
    assert rig.post("/api/users/update", {"id": owner, "role": "user"})[0] == 409
    assert rig.post("/api/users/update", {"id": owner, "expires_at": 1.0})[0] == 409
    assert rig.post("/api/users/disable", {"id": owner})[0] == 409
    assert rig.post("/api/users/delete", {"id": owner})[0] == 409
    assert rig.user(owner)["status"] == "active" and rig.user(owner)["role"] == "admin"
    second = rig.add("bea", role="admin")
    assert rig.post("/api/users/disable", {"id": owner})[0] == 200  # now allowed: another admin exists
    assert rig.post("/api/users/disable", {"id": second})[0] == 409


def test_disable_enable_ends_sessions_and_blocks_sign_in(rig):
    uid = rig.add("ann")
    epoch = rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/disable", {"id": uid})[0] == 200
    assert rig.user(uid)["status"] == "disabled" and rig.user(uid)["session_epoch"] > epoch
    assert not rig.store.verify_login("ann", PW, 1001.0).ok
    assert rig.post("/api/users/enable", {"id": uid})[0] == 200
    assert rig.store.verify_login("ann", PW, 1002.0).ok


def test_reset_password_forces_change_and_ends_sessions(rig):
    uid = rig.add("ann")
    epoch = rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/reset-password", {"id": uid, "temp_password": "short"})[0] == 400
    assert rig.post("/api/users/reset-password", {"id": uid, "temp_password": "another long one"})[0] == 200
    u = rig.user(uid)
    assert u["must_change"] and u["session_epoch"] > epoch
    assert rig.store.verify_login("ann", "another long one", 1001.0).ok
    assert "another long one" not in json.dumps(rig.get("/api/audit")[1])


def test_end_sessions_and_reset_totp_bump_the_epoch(rig):
    uid = rig.add("ann")
    e0 = rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/end-sessions", {"id": uid})[0] == 200
    e1 = rig.user(uid)["session_epoch"]
    status, out = rig.post("/api/users/reset-totp", {"id": uid})
    assert status == 200 and out["was_enrolled"] is False
    assert e0 < e1 < rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/end-sessions", {"id": 999})[0] == 404


def test_delete_user(rig):
    uid = rig.add("ann")
    assert rig.post("/api/users/delete", {"id": uid})[0] == 200
    assert rig.store.get_user(uid) is None
    assert rig.post("/api/users/delete", {"id": uid})[0] == 404
    assert rig.post("/api/users/delete", {"id": "abc"})[0] == 404


def test_grants_set_change_and_revoke(rig):
    uid = rig.add("ann", grants={})
    status, out = rig.get(f"/api/users/grants?id={uid}")
    assert status == 200 and out["grants"] == [] and "live" in out["views"]
    assert rig.post("/api/users/grants", {"id": uid, "app": "insights", "money_view": "percent", "views": ["trends", "live"]})[0] == 200
    g = rig.get(f"/api/users/grants?id={uid}")[1]["grants"][0]
    assert (g["money_view"], g["views"]) == ("percent", ["live", "trends"])
    epoch = rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/grants", {"id": uid, "app": "insights", "money_view": "dollars"})[0] == 200
    assert rig.user(uid)["session_epoch"] > epoch  # a changed money view ends sessions
    assert rig.post("/api/users/grants", {"id": uid, "app": "planner"})[0] == 200
    assert {x["app"] for x in rig.user(uid)["grants"]} == {"insights", "planner"}
    epoch = rig.user(uid)["session_epoch"]
    assert rig.post("/api/users/grants", {"id": uid, "app": "insights", "enabled": False})[0] == 200
    assert {x["app"] for x in rig.user(uid)["grants"]} == {"planner"}
    assert rig.user(uid)["session_epoch"] > epoch  # a revoked grant ends sessions
    assert rig.post("/api/users/grants", {"id": uid, "app": "mail"})[0] == 400
    assert rig.post("/api/users/grants", {"id": uid, "app": "insights", "money_view": "euros"})[0] == 400
    assert rig.post("/api/users/grants", {"id": uid, "app": "insights", "views": []})[0] == 400
    assert rig.get("/api/users/grants?id=999")[0] == 404


def test_every_write_is_audited_with_the_admin_name(rig):
    uid = rig.add("ann")
    rig.post("/api/users/update", {"id": uid, "notes": "n"})
    rig.post("/api/users/grants", {"id": uid, "app": "planner"})
    rig.post("/api/users/disable", {"id": uid})
    rig.post("/api/users/enable", {"id": uid})
    rig.post("/api/users/end-sessions", {"id": uid})
    rig.post("/api/users/delete", {"id": uid})
    assert rig.actions()[::-1] == ["user.add", "user.update", "grant.set", "user.disable", "user.enable", "user.end-sessions", "user.delete"]
    audit = rig.get("/api/audit")[1]["audit"]
    assert {a["admin"] for a in audit} == {"owner (PC)"} and all(a["at"] == 1000.0 for a in audit)


def test_activity_filters_by_app_person_and_range_and_masks_account_numbers(rig):
    rig.store.log_event("Ann", "remote", "signed in", "", "1.2.3.4", now=100.0, app="insights")
    rig.store.log_event("Ann", "local", "plan opened", "account 123456789012", now=200.0, app="planner")  # acct-scan: ok (synthetic number)
    rig.store.log_event("Bob", "remote", "signed in", "", "", now=300.0, app="insights")
    events = lambda q="": rig.get("/api/activity" + q)[1]["events"]
    assert len(events()) == 3
    assert [e["person"] for e in events("?app=insights")] == ["Bob", "Ann"]
    assert [e["event"] for e in events("?app=planner")] == ["plan opened"]
    assert [e["person"] for e in events("?person=Ann")] == ["Ann", "Ann"]
    assert [e["person"] for e in events("?from=150&to=250")] == ["Ann"]
    assert "123456789012" not in json.dumps(events()) and "****9012" in json.dumps(events())
    assert rig.get("/api/activity?app=mail")[0] == 400
    assert len(events("?limit=1")) == 1


def test_audit_log_lists_newest_first(rig):
    rig.add("ann")
    rig.now[0] = 2000.0
    rig.add("bob")
    assert [a["target_user"] for a in rig.get("/api/audit")[1]["audit"]] == ["bob", "ann"]
