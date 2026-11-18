"""Deny-by-default admin guard: walks the gateway's route map so a new admin route without the guard fails here.

Every route in the gateway's own namespace (``/login``, ``/gateway/...``, ``/api/auth/...``) is either on the
``USER_ROUTES`` list below (reachable by an ordinary signed-in user, and deliberately so) or it must refuse an
ordinary user (403) and an anonymous caller (302 or 401), whatever its path. Adding a route therefore forces a
decision: list it here as a user route, or leave it admin-only and this test proves the gate covers it.
"""
from __future__ import annotations

import re

import pytest

from src.gateway.app import ADMIN_PREFIXES, is_admin_path
from tests.gateway_rig import Rig

# (method, rule) pairs an ordinary user is meant to reach.
USER_ROUTES = {
    ("GET", "/login"), ("GET", "/gateway/enrol"), ("GET", "/gateway/account"), ("GET", "/gateway/static/<name>"),
    ("POST", "/api/auth/login"), ("POST", "/api/auth/totp/verify"), ("POST", "/api/auth/totp/enrol/confirm"),
    ("POST", "/api/auth/totp/enrol/start"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/session"),
    ("POST", "/api/auth/password"),
}
# Phase 9: the guest's own routes. A member reaches none of them (a page sends them to "/", an API answers 404);
# viewers are walked by tests/test_gateway_viewer_gate_contract.py.
VIEWER_ONLY_ROUTES = {
    ("GET", "/gateway/viewer"), ("GET", "/gateway/viewer/static/<name>"), ("GET", "/api/viewer/shares"),
    ("GET", "/api/viewer/shares/<share_id>"), ("GET", "/api/viewer/shares/<share_id>/status"),
}
GATEWAY_NAMESPACE = ("/login", "/gateway/", "/api/auth/", "/api/viewer/", "/api/share/")


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


def _routes(rig):
    for rule in rig.app.url_map.iter_rules():
        for method in sorted(set(rule.methods) - {"HEAD", "OPTIONS"}):
            yield method, rule.rule


def _concrete(rule: str) -> str:
    return re.sub(r"<(?:int:)?[^>]+>", lambda m: "1" if m.group(0).startswith("<int:") else "x", rule)


def test_every_route_is_in_the_gateway_namespace(rig):
    """A route outside it would be forwarded to a worker before it was ever matched, so it could never work."""
    for _method, rule in _routes(rig):
        assert rule.startswith(GATEWAY_NAMESPACE), rule


def test_every_route_that_mentions_admin_lives_under_an_admin_prefix(rig):
    for _method, rule in _routes(rig):
        if "admin" in rule.lower():
            assert is_admin_path(_concrete(rule)), f"{rule} looks like an admin route but the gate would not guard it"


def test_the_user_route_list_has_no_stale_entries(rig):
    assert USER_ROUTES <= set(_routes(rig))


def test_user_list_never_contains_an_admin_path(rig):
    for _method, rule in USER_ROUTES:
        assert not is_admin_path(_concrete(rule)), rule


def test_every_route_not_on_the_user_list_refuses_users_and_anonymous_callers(rig):
    user, _ = rig.signed_in("ann")
    anon = rig.browser(ip="203.0.113.77")
    pending = rig.browser(ip="203.0.113.78")  # signed in with a password only: two-factor not finished
    rig.add_user("pat")
    assert pending.login("pat").status_code == 200
    checked = 0
    for method, rule in _routes(rig):
        if (method, rule) in USER_ROUTES:
            continue
        path = _concrete(rule)
        if (method, rule) in VIEWER_ONLY_ROUTES or rule.startswith(("/api/share/", "/gateway/sharing")):
            continue  # checked below and in the share routes tests
        body = {"id": 1, "role": "admin", "username": "zz", "temp_password": "a long enough password"}
        call = (lambda c, p: c.get(p)) if method == "GET" else (lambda c, p: c.post(p, json=body))
        assert call(user, path).status_code == 403, (method, rule)
        assert call(anon, path).status_code in (302, 401), (method, rule)
        assert call(pending, path).status_code in (302, 401), (method, rule)
        checked += 1
    assert checked >= 10  # the sweep really ran over the admin routes


def test_admin_prefix_matching_is_case_and_shape_proof(rig):
    for p in ("/gateway/admin", "/gateway/admin/", "/gateway/admin/static/users.js", "/gateway/administrator",
              "/gateway/Admin", "/GATEWAY/ADMIN", "/api/auth/admin", "/api/auth/admin/", "/api/auth/admin/console/users",
              "/api/auth/Admin/users", "/gateway/users", "/gateway/users/"):
        assert is_admin_path(p), p
    for p in ("/gateway/account", "/gateway/static/gateway.js", "/api/auth/session", "/api/plan/rows", "/"):
        assert not is_admin_path(p), p
    assert ADMIN_PREFIXES  # the list exists and is not empty


def test_a_user_gets_the_same_answer_for_real_and_made_up_ids(rig):
    """Ids are not enumerable: an ordinary user cannot tell which person ids exist."""
    user, uid = rig.signed_in("ann")
    other = rig.add_user("bob")
    answers = set()
    for target in (other, uid, 999, 0, 10_000_000):
        for suffix in ("update", "disable", "delete", "reset-password", "reset-totp", "unlock"):
            r = user.post(f"/api/auth/admin/console/users/{suffix}", json={"id": target})
            answers.add((r.status_code, r.get_data(as_text=True)))
        r = user.post(f"/api/auth/admin/users/{target}/delete")
        answers.add((r.status_code, r.get_data(as_text=True)))
    assert len(answers) == 1 and next(iter(answers))[0] == 403, answers
    assert rig.store.get_user(other) is not None


def test_ordinary_users_get_no_directory_of_people_anywhere(rig):
    user, _ = rig.signed_in("ann")
    rig.add_user("bob")
    for path in ("/api/auth/session", "/gateway/account", "/gateway/static/gateway.js", "/gateway/static/gateway.css"):
        text = user.get(path).get_data(as_text=True)
        assert "bob" not in text.lower(), path


def test_members_reach_none_of_the_viewer_routes(tmp_path):
    rig = Rig(tmp_path, shared_views=True)
    user, _ = rig.signed_in("ann")
    anon = rig.browser(ip="203.0.113.77")
    assert VIEWER_ONLY_ROUTES <= set(_routes(rig))
    for method, rule in VIEWER_ONLY_ROUTES:
        path = _concrete(rule)
        r = user.get(path)
        assert r.status_code in (302, 404), (method, rule)
        if r.status_code == 302:
            assert r.headers["Location"] == "/"
        assert anon.get(path).status_code in (302, 401), (method, rule)
    assert rig.upstream.calls == []
