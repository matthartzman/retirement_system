"""The gateway tells the supervisor about account changes (create, disable, delete, sign-out), keeps
working when a hook fails, and refuses a request carrying two session cookies."""
from __future__ import annotations

import pytest

from src.gateway.app import GatewayConfig, GatewayListener, create_gateway_app
from tests.gateway_rig import FUNNEL_PORT, LOCAL_PORT, PUBLIC_ORIGIN, Rig

pytestmark = pytest.mark.integration


class Recorder:
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[tuple] = []
        self.fail = fail

    def _rec(self, name, *args):
        self.calls.append((name, *args))
        if name == self.fail:
            raise RuntimeError("hook failed with a detail that must not reach the client: C:\\secret\\path")

    def user_created(self, uid):
        self._rec("user_created", uid)

    def user_disabled(self, uid, disabled):
        self._rec("user_disabled", uid, disabled)

    def user_deleted(self, uid):
        self._rec("user_deleted", uid)

    def signed_out(self, uid, left):
        self._rec("signed_out", uid, left)


def _rig(tmp_path, recorder):
    rig = Rig(tmp_path)
    rig.app = create_gateway_app(rig.store, config=GatewayConfig(public_origins=(PUBLIC_ORIGIN,)),
                                 clock=lambda: rig.now[0], upstream=rig.upstream, lifecycle=recorder)
    rig.funnel = GatewayListener(rig.app, "funnel", FUNNEL_PORT)
    rig.local = GatewayListener(rig.app, "local", LOCAL_PORT)
    return rig


def test_admin_actions_and_sign_out_reach_the_lifecycle(tmp_path):
    rec = Recorder()
    rig = _rig(tmp_path, rec)
    admin, _ = rig.signed_in("root", role="admin")
    r = admin.post("/api/auth/admin/users", json={"username": "ann", "display_name": "Ann", "role": "user",
                                                   "temp_password": "temporary password 1"})
    uid = r.get_json()["id"]
    admin.post(f"/api/auth/admin/users/{uid}/disabled", json={"disabled": True})
    admin.post(f"/api/auth/admin/users/{uid}/disabled", json={"disabled": False})
    admin.post(f"/api/auth/admin/users/{uid}/delete", json={})
    assert rec.calls == [("user_created", uid), ("user_disabled", uid, True), ("user_disabled", uid, False),
                         ("user_deleted", uid)]
    second = rig.browser(ip="203.0.113.77")
    rig.advance(31)
    second.login("root")
    second.post("/api/auth/totp/verify", json={"code": rig.code(1)})
    second.refresh_csrf()
    second.post("/api/auth/logout")
    admin.post("/api/auth/logout")
    assert rec.calls[-2:] == [("signed_out", 1, 1), ("signed_out", 1, 0)]


def test_a_failing_hook_keeps_the_change_and_hides_the_detail(tmp_path):
    rec = Recorder(fail="user_deleted")
    rig = _rig(tmp_path, rec)
    admin, _ = rig.signed_in("root", role="admin")
    uid = rig.add_user("bob")
    r = admin.post(f"/api/auth/admin/users/{uid}/delete", json={})
    body = r.get_json()
    assert r.status_code == 200 and body["success"] is True and "warning" in body
    assert "secret" not in r.get_data(as_text=True)
    assert rig.store.get_user(uid) is None
    assert any(e["event"] == "worker cleanup failed" for e in rig.store.read_audit())


def test_two_session_cookies_are_refused(tmp_path):
    rig = Rig(tmp_path)
    ann, _ = rig.signed_in("ann")
    bob, _ = rig.signed_in("bob")
    both = f"{next(iter(ann.cookies.items()))[0]}={ann.cookies['__Host-rp_session']}; __Host-rp_session={bob.cookies['__Host-rp_session']}"
    r = ann.get("/api/plan/rows", headers={"Cookie": both})
    assert r.status_code == 400
    assert rig.upstream.calls == []
