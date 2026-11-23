"""SEC-11 / PR-05: a JSON body that is not an object is a 400, never a 500, and pre-auth ones are throttle-counted."""
from __future__ import annotations

import pytest

from tests.gateway_rig import Rig

BAD_BODIES = [[], ["a"], "text", 7, 1.5, True]


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


@pytest.mark.parametrize("body", BAD_BODIES)
def test_login_with_a_non_object_body_is_400(rig, body):
    rig.add_user("ann")
    r = rig.browser().post("/api/auth/login", json=body)
    assert r.status_code == 400


def test_non_object_login_bodies_count_toward_the_address_throttle(rig):
    b = rig.browser(ip="203.0.113.77")
    codes = [b.post("/api/auth/login", json=[]).status_code for _ in range(30)]
    assert 429 in codes and set(codes) <= {400, 429}


@pytest.mark.parametrize("body", BAD_BODIES)
def test_second_factor_with_a_non_object_body_is_400(rig, body):
    _enrolled, _uid = rig.signed_in("ann")
    b = rig.browser(ip="198.51.100.9")
    assert b.login("ann").status_code == 200  # enrolled: the pending session is at the code step
    assert b.post("/api/auth/totp/verify", json=body).status_code == 400
    rig.add_user("bob")
    c = rig.browser(ip="198.51.100.10")
    assert c.login("bob").status_code == 200  # not enrolled yet
    assert c.post("/api/auth/totp/enrol/confirm", json=body).status_code == 400


@pytest.mark.parametrize("body", BAD_BODIES)
def test_change_password_and_admin_routes_with_a_non_object_body_are_400(rig, body):
    b, _uid = rig.signed_in("ann")
    assert b.post("/api/auth/password", json=body).status_code == 400
    admin, _ = rig.signed_in("root", role="admin", ip="203.0.113.6")
    assert admin.post("/api/auth/admin/users", json=body).status_code == 400
    assert admin.post(f"/api/auth/admin/users/{_uid}/role", json=body).status_code == 400
    assert admin.post(f"/api/auth/admin/users/{_uid}/reset-password", json=body).status_code == 400
