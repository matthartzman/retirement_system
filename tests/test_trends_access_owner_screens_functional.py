"""Remote access: owner-only People and Activity screens (local listener only)."""
from __future__ import annotations

import json

from tests.test_trends_access_gate_functional import PW, Rig


def _add(rig, username="ann", name="Ann", temp="temp password 1"):
    return rig.call(rig.local, "POST", "/api/people", {"display_name": name, "username": username, "temp_password": temp})


def test_people_crud_on_local_with_no_accounts_existing(tmp_path):
    rig = Rig(tmp_path)
    assert rig.call(rig.local, "GET", "/api/people").get_json()["people"] == []
    assert _add(rig).status_code == 200
    people = rig.call(rig.local, "GET", "/api/people").get_json()["people"]
    assert [p["username"] for p in people] == ["ann"] and people[0]["must_change"] is True
    # the temporary password works on the remote listener and forces a change
    resp, token = rig.signin("ann", "temp password 1")
    assert resp.get_json()["must_change"] is True


def test_duplicate_username_and_short_password_rejected(tmp_path):
    rig = Rig(tmp_path)
    _add(rig)
    assert _add(rig).status_code == 400
    assert _add(rig, username="bob", temp="short").status_code == 400


def test_reset_sets_must_change_unlocks_and_ends_sessions(tmp_path):
    rig = Rig(tmp_path)
    uid = rig.add()
    _, token = rig.signin()
    for _ in range(5):
        rig.signin("ann", "nope nope nope")
    resp = rig.call(rig.local, "POST", "/api/people/reset", {"id": uid, "temp_password": "reset password 1"})
    assert resp.status_code == 200
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 401
    again, _ = rig.signin("ann", "reset password 1")
    assert again.status_code == 200 and again.get_json()["must_change"] is True


def test_delete_ends_sessions(tmp_path):
    rig = Rig(tmp_path)
    uid = rig.add()
    _, token = rig.signin()
    assert rig.call(rig.local, "POST", "/api/people/delete", {"id": uid}).status_code == 200
    assert rig.call(rig.remote, "GET", "/api/history", cookie=token).status_code == 401
    assert rig.call(rig.local, "GET", "/api/people").get_json()["people"] == []


def test_people_list_never_returns_hashes(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    text = rig.call(rig.local, "GET", "/api/people").get_data(as_text=True)
    assert "pw_hash" not in text and "pw_salt" not in text and PW not in text


def test_owner_actions_are_logged_and_activity_api_filters(tmp_path):
    rig = Rig(tmp_path)
    uid = _add(rig).get_json()["id"]
    rig.call(rig.local, "POST", "/api/people/reset", {"id": uid, "temp_password": "reset password 1"})
    rig.call(rig.local, "POST", "/api/people/delete", {"id": uid})
    events = rig.call(rig.local, "GET", "/api/activity").get_json()["events"]
    assert [e["event"] for e in events][:3] == ["person deleted", "password reset", "person added"]
    assert all(e["person"] == "owner (PC)" for e in events)
    assert rig.call(rig.local, "GET", "/api/activity?person=nobody").get_json()["events"] == []
    assert len(rig.call(rig.local, "GET", "/api/activity?from=0&to=9999999999").get_json()["events"]) == 3


def test_owner_screen_assets_served_on_local_only(tmp_path):
    rig = Rig(tmp_path)
    resp = rig.call(rig.local, "GET", "/access.js")
    assert resp.status_code == 200 and "javascript" in resp.headers["Content-Type"]
    assert rig.call(rig.remote, "GET", "/access.js").status_code == 404


def test_remote_index_html_carries_no_owner_screen_markup(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    _, token = rig.signin()
    page = rig.call(rig.remote, "GET", "/", cookie=token).get_data(as_text=True)
    assert "api/people" not in page and "api/activity" not in page
    json.dumps(page)
