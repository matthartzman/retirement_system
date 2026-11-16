"""Financial Insights remote gate on the shared identity store: grant, status, expiry and epoch."""
from __future__ import annotations

import pytest

from tests.test_trends_access_gate_functional import Rig


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def _signed_in(rig, name="ann"):
    rig.add(name)
    resp, token = rig.signin(name)
    assert resp.status_code == 200 and token
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200
    return token


def _ended(rig, token):
    return rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 401


def test_person_without_an_insights_grant_cannot_sign_in_and_gets_the_generic_error(rig):
    rig.store.add_user("Pat", "pat", "correct horse", insights=False, must_change=False)
    resp, token = rig.signin("pat")
    assert resp.status_code == 401 and token is None
    assert resp.get_json()["error"] == rig.signin("nobody")[0].get_json()["error"]


def test_revoking_the_grant_ends_the_session_on_the_next_request(rig):
    token = _signed_in(rig)
    rig.store.revoke_grant(1, "insights")
    assert _ended(rig, token)


def test_disabling_the_person_ends_the_session_on_the_next_request(rig):
    token = _signed_in(rig)
    rig.store.set_status(1, "disabled", now=rig.now[0])
    assert _ended(rig, token)
    assert rig.signin()[1] is None


def test_expiry_ends_the_session_on_the_next_request(rig):
    token = _signed_in(rig)
    rig.store.update_user(1, expires_at=rig.now[0] + 60, now=rig.now[0])
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 200
    rig.now[0] += 61
    assert _ended(rig, token)


def test_epoch_bump_ends_every_session_of_that_person_only(rig):
    ann = _signed_in(rig, "ann")
    ann2 = rig.signin("ann")[1]
    bob = _signed_in(rig, "bob")
    rig.store.end_sessions(1)
    assert _ended(rig, ann) and _ended(rig, ann2)
    assert rig.call(rig.remote, "GET", "/api/history", cookie=bob).status_code == 200


def test_changing_own_password_keeps_this_session_and_ends_the_others(rig):
    rig.add("ann")
    here = rig.signin("ann")[1]
    other = rig.signin("ann")[1]
    resp = rig.call(rig.remote, "POST", "/api/change-password", {"current": "correct horse", "new": "another long phrase"}, cookie=here)
    assert resp.status_code == 200
    assert rig.call(rig.remote, "GET", "/api/history", cookie=here).status_code == 200
    assert _ended(rig, other)


def test_money_view_comes_from_the_grant(rig):
    token = _signed_in(rig)
    rig.store.set_grant(1, "insights", money_view="dollars", views=None, now=rig.now[0], bump=False)
    assert rig.call(rig.remote, "GET", "/api/whoami", cookie=token).get_json()["money_view"] == "dollars"


def test_views_come_from_the_grant_and_a_refused_view_is_403(rig):
    token = _signed_in(rig)
    who = rig.call(rig.remote, "GET", "/api/whoami", cookie=token).get_json()
    assert who["views"] == ["live", "trends", "projections"]  # no list on the grant: every view
    rig.store.set_grant(1, "insights", money_view="percent", views=["trends"], now=rig.now[0], bump=False)
    assert rig.call(rig.remote, "GET", "/api/whoami", cookie=token).get_json()["views"] == ["trends"]
    assert rig.call(rig.remote, "POST", "/api/view", {"view": "trends"}, cookie=token).status_code == 200
    assert rig.call(rig.remote, "POST", "/api/view", {"view": "projections"}, cookie=token).status_code == 403
    assert rig.call(rig.local, "GET", "/api/whoami").get_json()["views"] == ["live", "trends", "projections"]
