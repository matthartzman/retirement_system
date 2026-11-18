"""The Admin console's Users UI hosted by the gateway at /gateway/admin (phase 1 of the integration design).

Covers the page, the static allowlist, the console API (compat layer over the gateway store), the lifecycle hooks,
the last-admin rule, the delete confirmation, the 12-character minimum and the served CSP. Route-guard and
isolation properties are in ``test_gateway_admin_guard_contract.py``.
"""
from __future__ import annotations

import threading
from html.parser import HTMLParser

import pytest

from src.gateway.app import CSP, GatewayConfig, GatewayListener, create_gateway_app
from tests.gateway_rig import FUNNEL_PORT, LOCAL_PORT, PUBLIC_ORIGIN, Rig

API = "/api/auth/admin/console"
TEMP = "temporary password 1"


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def user_created(self, uid):
        self.calls.append(("user_created", uid))

    def user_disabled(self, uid, disabled):
        self.calls.append(("user_disabled", uid, disabled))

    def user_deleted(self, uid):
        self.calls.append(("user_deleted", uid))

    def signed_out(self, uid, left):
        self.calls.append(("signed_out", uid, left))


@pytest.fixture()
def rig(tmp_path):
    r = Rig(tmp_path)
    r.recorder = Recorder()
    r.app = create_gateway_app(r.store, config=GatewayConfig(public_origins=(PUBLIC_ORIGIN,)),
                               clock=lambda: r.now[0], upstream=r.upstream, lifecycle=r.recorder)
    r.funnel = GatewayListener(r.app, "funnel", FUNNEL_PORT)
    r.local = GatewayListener(r.app, "local", LOCAL_PORT)
    return r


class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inline_scripts, self.handlers, self.styles, self.srcs = 0, [], 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script":
            if a.get("src"):
                self.srcs.append(a["src"])
            else:
                self.inline_scripts += 1
        if tag == "link" and a.get("href"):
            self.srcs.append(a["href"])
        self.handlers += [k for k in a if k.startswith("on")]
        self.styles += 1 if (tag == "style" or "style" in a) else 0


def test_page_is_served_to_admins_with_the_gateway_csp_and_no_inline_code(rig):
    admin, _ = rig.signed_in("root", role="admin")
    r = admin.get("/gateway/admin")
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == CSP
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Frame-Options"] == "DENY"
    scan = _Scan()
    scan.feed(r.get_data(as_text=True))
    assert scan.inline_scripts == 0 and scan.handlers == [] and scan.styles == 0
    # every script and stylesheet the page loads is same-origin and is itself served (to this admin)
    assert scan.srcs, "page loads nothing"
    for src in scan.srcs:
        assert src.startswith("/gateway/"), src
        assert admin.get(src).status_code == 200, src


def test_static_files_are_an_exact_allowlist_and_admin_only(rig):
    admin, _ = rig.signed_in("root", role="admin")
    user, _ = rig.signed_in("ann")
    anon = rig.browser(ip="203.0.113.99")
    base = "/gateway/admin/static/"
    for name in ("users.js", "admin.css", "admin-gateway.js", "admin-gateway.css"):
        ok = admin.get(base + name)
        assert ok.status_code == 200 and ok.headers["Content-Type"].split(";")[0] in ("text/javascript", "text/css"), name
        assert user.get(base + name).status_code == 403, name
        assert anon.get(base + name).status_code == 302, name
    for name in ("admin.js", "processes.js", "index.html", "../users.js", "..%2fusers.js", "users.js/", "USERS.JS", "",
                 "%2e%2e/admin.js", "users.js%00.css"):
        assert admin.get(base + name).status_code in (404, 400), name


def test_users_page_redirects_to_the_console_for_admins_only(rig):
    admin, _ = rig.signed_in("root", role="admin")
    user, _ = rig.signed_in("ann")
    r = admin.get("/gateway/users")
    assert r.status_code == 302 and r.headers["Location"] == "/gateway/admin#users"
    assert user.get("/gateway/users").status_code == 403
    assert rig.browser(ip="203.0.113.98").get("/gateway/users").status_code == 302


def test_list_has_the_console_shape_and_hides_what_the_gateway_does_not_have(rig):
    admin, aid = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    r = admin.get(f"{API}/users")
    body = r.get_json()
    assert r.status_code == 200 and body["success"] is True
    assert body["min_password"] == 12
    f = body["features"]
    assert f["grants"] is False and f["require_totp"] is False and f["activity"] is False and f["modules"] is True
    assert f["expiry"] is True and f["notes"] is True and f["end_sessions"] is True and f["edit_name"] is True
    assert f["audit"] is True
    ann = next(u for u in body["users"] if u["id"] == uid)
    assert ann["username"] == "ann" and ann["display_name"] == "Ann" and ann["role"] == "user"
    assert ann["status"] == "active" and ann["expired"] is False and ann["locked"] is False
    assert ann["totp_enrolled"] is False and ann["totp_required"] is True and ann["grants"] == []
    assert ann["expires_at"] is None and ann["notes"] == "" and "last_signin_at" in ann and "created_at" in ann
    blob = repr(body)
    assert "pw_hash" not in blob and "secret" not in blob and "csrf" not in blob


def test_add_person_creates_a_user_who_must_change_the_password_and_notifies_the_supervisor(rig):
    admin, aid = rig.signed_in("root", role="admin")
    r = admin.post(f"{API}/users", json={"display_name": "Ann A", "username": "Ann", "role": "user",
                                         "temp_password": TEMP})
    assert r.status_code == 200, r.get_data(as_text=True)
    uid = r.get_json()["id"]
    row = rig.store.get_user(uid)
    assert row["username"] == "ann" and row["must_change"] == 1 and row["role"] == "user"
    assert ("user_created", uid) in rig.recorder.calls
    created = next(e for e in rig.store.read_audit(30) if e["event"] == "user created" and e["target_user_id"] == uid)
    assert created["actor_user_id"] == aid and created["actor_username"] == "root"
    assert TEMP not in repr(rig.store.read_audit(50))


def test_minimum_password_is_twelve_on_the_server_for_create_and_reset(rig):
    admin, _ = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    short = "elevenchars"  # 11
    assert len(short) == 11
    r = admin.post(f"{API}/users", json={"display_name": "Bob", "username": "bob", "role": "user", "temp_password": short})
    assert r.status_code == 400 and rig.store.find_user("bob") is None
    r = admin.post(f"{API}/users/reset-password", json={"id": uid, "temp_password": short})
    assert r.status_code == 400
    r = admin.post(f"{API}/users/reset-password", json={"id": uid, "temp_password": "twelve chars"})
    assert r.status_code == 200
    assert rig.store.get_user(uid)["must_change"] == 1


def test_update_changes_the_role_and_the_last_admin_rule_holds(rig):
    admin, aid = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    r = admin.post(f"{API}/users/update", json={"id": aid, "role": "user"})
    assert r.status_code == 409 and r.get_json()["last_admin"] is True
    assert admin.post(f"{API}/users/update", json={"id": uid, "role": "admin"}).status_code == 200
    assert rig.store.get_user(uid)["role"] == "admin"
    assert admin.post(f"{API}/users/update", json={"id": uid, "role": "owner"}).status_code == 400
    assert admin.post(f"{API}/users/update", json={"id": 9999, "role": "user"}).status_code == 404


def test_disable_enable_unlock_and_reset_totp_drive_the_same_store_and_lifecycle(rig):
    admin, _ = rig.signed_in("root", role="admin")
    b, uid = rig.signed_in("ann")
    assert admin.post(f"{API}/users/disable", json={"id": uid}).status_code == 200
    assert b.get("/api/plan/rows").status_code == 401  # sessions ended
    assert admin.post(f"{API}/users/enable", json={"id": uid}).status_code == 200
    assert [c for c in rig.recorder.calls if c[0] == "user_disabled"] == [("user_disabled", uid, True),
                                                                          ("user_disabled", uid, False)]
    for _ in range(5):
        rig.browser(ip="198.51.100.4").login("ann", "wrong password!!")
    listed = admin.get(f"{API}/users").get_json()["users"]
    assert next(u for u in listed if u["id"] == uid)["locked"] is True
    assert admin.post(f"{API}/users/unlock", json={"id": uid}).status_code == 200
    assert next(u for u in admin.get(f"{API}/users").get_json()["users"] if u["id"] == uid)["locked"] is False
    assert admin.post(f"{API}/users/reset-totp", json={"id": uid}).status_code == 200
    assert rig.store.totp_status(uid) != "enrolled"


def test_disabling_or_deleting_the_only_admin_is_refused(rig):
    admin, aid = rig.signed_in("root", role="admin")
    assert admin.post(f"{API}/users/disable", json={"id": aid}).status_code == 409
    r = admin.post(f"{API}/users/delete", json={"id": aid, "confirm_username": "root"})
    assert r.status_code == 409 and r.get_json()["last_admin"] is True
    assert rig.store.get_user(aid) is not None


def test_two_simultaneous_demotions_cannot_remove_the_last_admin(rig):
    a1, id1 = rig.signed_in("root", role="admin")
    a2, id2 = rig.signed_in("boss", role="admin", ip="203.0.113.6")
    results: list[int] = []
    barrier = threading.Barrier(2)

    def demote(client, target):
        barrier.wait()
        results.append(client.post(f"{API}/users/update", json={"id": target, "role": "user"}).status_code)

    ts = [threading.Thread(target=demote, args=(a1, id2)), threading.Thread(target=demote, args=(a2, id1))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert rig.store.count_active_admins() == 1, results


def test_delete_needs_the_typed_username_and_notifies_the_supervisor(rig):
    admin, _ = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    for body in ({"id": uid}, {"id": uid, "confirm_username": ""}, {"id": uid, "confirm_username": "bob"},
                 {"id": uid, "confirm_username": "ANN"}):
        r = admin.post(f"{API}/users/delete", json=body)
        assert r.status_code == 400, body
        assert rig.store.get_user(uid) is not None
    assert not [c for c in rig.recorder.calls if c[0] == "user_deleted"]
    assert admin.post(f"{API}/users/delete", json={"id": uid, "confirm_username": "ann"}).status_code == 200
    assert rig.store.get_user(uid) is None and ("user_deleted", uid) in rig.recorder.calls


def test_every_console_write_is_refused_without_csrf_origin_or_with_cross_site(rig):
    admin, _ = rig.signed_in("root", role="admin")
    local = rig.browser(ip="127.0.0.1", listener="local")
    local.cookies, local.csrf = dict(admin.cookies), admin.csrf  # the same admin session, presented on loopback
    uid = rig.add_user("ann")
    writes = [(f"{API}/users", {"display_name": "X", "username": "xx", "role": "user", "temp_password": TEMP}),
              (f"{API}/users/update", {"id": uid, "role": "admin"}),
              (f"{API}/users/reset-password", {"id": uid, "temp_password": TEMP}),
              (f"{API}/users/disable", {"id": uid}), (f"{API}/users/enable", {"id": uid}),
              (f"{API}/users/unlock", {"id": uid}), (f"{API}/users/reset-totp", {"id": uid}),
              (f"{API}/users/delete", {"id": uid, "confirm_username": "ann"})]
    for path, body in writes:
        assert admin.post(path, json=body, csrf=False).status_code == 403, path
        assert admin.post(path, json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403, path
        assert admin.post(path, json=body, origin="https://evil.example").status_code == 403, path
        assert admin.post(path, json=body, origin=False).status_code == 403, path
        assert admin.post(path, json=body, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403, path
        assert local.post(path, json=body, headers={"Host": "evil.example"}).status_code == 421, path
        assert local.post(path, json=body, origin=PUBLIC_ORIGIN).status_code == 403, path  # funnel origin on loopback
    assert rig.store.get_user(uid)["role"] == "user" and rig.store.find_user("xx") is None


def test_audit_view_reads_the_gateway_log_with_the_real_actor(rig):
    admin, aid = rig.signed_in("root", role="admin")
    uid = rig.add_user("ann")
    admin.post(f"{API}/users/update", json={"id": uid, "role": "admin"})
    r = admin.get(f"{API}/audit")
    assert r.status_code == 200
    rows = r.get_json()["audit"]
    row = next(a for a in rows if a["action"] == "role changed")
    assert row["admin"] == "root" and row["target_user"] == "ann" and "user -> admin" in row["details"]
    assert set(row) >= {"at", "admin", "action", "target_user", "details"}


def test_unknown_console_paths_are_a_generic_not_found_for_admins(rig):
    admin, _ = rig.signed_in("root", role="admin")
    for path in (f"{API}/activity", f"{API}/users/grants", f"{API}/settings", f"{API}/processes", f"{API}/shutdown"):
        assert admin.get(path).status_code == 404, path
