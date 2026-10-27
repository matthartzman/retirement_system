"""Remote access: the activity log of sign-ins, views and actions."""
from __future__ import annotations

import json

from tests.test_trends_access_gate_functional import PW, Rig


def _events(rig, **kw):
    return rig.store.read_events(**kw)


def _kinds(rig):
    return [e["event"] for e in _events(rig)]


def test_events_logged_for_signin_failed_signin_lockout_signout_timeout(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    rig.signin("ann", "nope nope nope")
    resp, token = rig.signin()
    rig.call(rig.remote, "POST", "/api/signout", {}, cookie=token)
    _, token2 = rig.signin()
    rig.now[0] += 700
    rig.call(rig.remote, "GET", "/api/history", cookie=token2)  # idle past 10 minutes
    for _ in range(5):
        rig.signin("ann", "nope nope nope")
    kinds = _kinds(rig)
    for expected in ("sign-in failed", "signed in", "signed out", "session timed out", "locked out"):
        assert expected in kinds, expected
    failed = [e for e in _events(rig) if e["event"] == "sign-in failed"][-1]
    assert failed["details"] == "ann" and failed["listener"] == "remote"


def test_failed_signin_logs_attempted_username_and_never_the_password(tmp_path):
    rig = Rig(tmp_path)
    rig.signin("nobody", "super secret guess")
    text = json.dumps(_events(rig))
    assert "nobody" in text and "super secret guess" not in text


def test_actions_logged_with_account_detail_and_no_amounts(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    _, token = rig.signin()
    rig.call(rig.remote, "POST", "/api/account", {"account_key": "Chase Checking", "type": "cash"}, cookie=token)
    rig.call(rig.remote, "POST", "/api/passthrough-decision", {"key": "a|b", "decision": "approve"}, cookie=token)
    rig.call(rig.remote, "POST", "/api/account-prefs", {"items": [1, 2, 3]}, cookie=token)
    by_event = {e["event"]: e for e in _events(rig)}
    assert by_event["account edit"]["person"] == "Ann" and "Chase Checking" in by_event["account edit"]["details"]
    assert "a|b" in by_event["passthrough decision"]["details"]
    assert "3" in by_event["account preferences"]["details"]


def test_view_endpoint_logs_known_views_and_rejects_unknown(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    _, token = rig.signin()
    assert rig.call(rig.remote, "POST", "/api/view", {"view": "live"}, cookie=token).status_code == 200
    assert rig.call(rig.remote, "POST", "/api/view", {"view": "<script>"}, cookie=token).status_code == 400
    views = [e for e in _events(rig) if e["event"] == "view opened"]
    assert [v["details"] for v in views] == ["live"]


def test_local_actions_attributed_to_owner_pc(tmp_path):
    rig = Rig(tmp_path)
    rig.call(rig.local, "POST", "/api/run-cancel", {})
    ev = [e for e in _events(rig) if e["event"] == "run cancelled"][0]
    assert ev["person"] == "owner (PC)" and ev["listener"] == "local"


def test_events_never_contain_cookie_or_token_or_password(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    _, token = rig.signin()
    rig.call(rig.remote, "POST", "/api/change-password", {"current": PW, "new": "a brand new pass"}, cookie=token)
    rig.call(rig.remote, "POST", "/api/account", {"account_key": "X"}, cookie=token)
    text = json.dumps(_events(rig))
    assert token not in text and PW not in text and "a brand new pass" not in text
    assert "password changed" in text


def test_read_events_filters_by_person_and_dates_newest_first(tmp_path):
    rig = Rig(tmp_path)
    rig.store.log_event("Ann", "remote", "view opened", "live", now=100)
    rig.store.log_event("Bob", "remote", "view opened", "trends", now=200)
    rig.store.log_event("Ann", "remote", "view opened", "trends", now=300)
    assert [e["at"] for e in rig.store.read_events(person="Ann")] == [300, 100]
    assert [e["at"] for e in rig.store.read_events(since=150, until=250)] == [200]


def test_source_recorded_from_x_forwarded_for_when_present(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    rig.call(rig.remote, "POST", "/api/signin", {"username": "ann", "password": PW}, headers={"X-Forwarded-For": "203.0.113.9"})
    ev = [e for e in _events(rig) if e["event"] == "signed in"][0]
    assert ev["source"] == "203.0.113.9"
