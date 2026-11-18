"""Gateway side of Financial Insight: flag, /insights redirect, session JSON, background-poll idle policy, audit, CSRF.

Design: documentation/future/multi-user-insights-design.md (4.4, 5, 8).
"""
from __future__ import annotations

import pytest

from src.gateway import server as gateway_server
from src.gateway import store as gstore
from src.gateway.app import BACKGROUND_POLL_HEADER
from src.remote_insights_mount import INSIGHTS_ENV
from tests.gateway_rig import Rig


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path, insights=True)


def _events(rig, name="insights_opened"):
    return [e for e in rig.store.read_audit(limit=500) if e["event"] == name]


def test_worker_flag_name_matches_the_mount():
    assert gateway_server.INSIGHTS_ENV == INSIGHTS_ENV


def test_insights_flag_is_a_command_line_switch_off_by_default():
    parser = gateway_server._parser()
    assert parser.parse_args(["--db", "x", "--data-root", "x"]).insights is False
    assert parser.parse_args(["--db", "x", "--data-root", "x", "--insights"]).insights is True


def test_session_json_reports_insights_only_when_on_and_active(tmp_path, rig):
    b, _ = rig.signed_in()
    assert b.get("/api/auth/session").get_json()["insights"] is True
    off = Rig(tmp_path / "off")
    b2, _ = off.signed_in()
    assert b2.get("/api/auth/session").get_json()["insights"] is False


def test_insights_without_slash_redirects_and_keeps_the_query(rig):
    b, _ = rig.signed_in()
    r = b.get("/insights?view=trends")
    assert r.status_code == 302 and r.headers["Location"] == "/insights/?view=trends"
    assert b.get("/insights").headers["Location"] == "/insights/"
    assert rig.upstream.calls == []


def test_insights_redirect_needs_a_session(rig):
    r = rig.browser().get("/insights")
    assert r.status_code == 302 and r.headers["Location"].startswith("/login")


def test_flag_off_forwards_to_the_worker_without_a_redirect(tmp_path):
    off = Rig(tmp_path / "off")
    b, _ = off.signed_in()
    assert b.get("/insights").status_code == 200  # the recording upstream answers; no gateway redirect
    assert off.upstream.calls[-1][1] == "/insights"


def test_insights_paths_forward_to_the_signed_in_users_worker_only(rig):
    b, uid = rig.signed_in()
    r = b.get("/insights/api/history")
    assert r.status_code == 200 and r.get_json()["user_id"] == uid
    assert rig.upstream.calls[-1][1] == "/insights/api/history"
    assert rig.browser().get("/insights/api/history").status_code == 401  # no session: JSON 401, the page goes to sign-in


def test_post_without_csrf_token_is_refused(rig):
    b, _ = rig.signed_in()
    n = len(rig.upstream.calls)
    assert b.post("/insights/api/run-now", csrf=False).status_code == 403
    assert b.post("/insights/api/run-now", origin="https://evil.example").status_code == 403
    assert len(rig.upstream.calls) == n
    assert b.post("/insights/api/run-now").status_code == 200


def test_audit_event_once_per_session_and_no_data(rig):
    b, uid = rig.signed_in()
    b.get("/insights/")
    b.get("/insights/")
    b.get("/insights/api/history")
    events = _events(rig)
    assert len(events) == 1 and events[0]["details"] == "/insights/" and events[0]["actor_user_id"] == uid
    other, _ = rig.signed_in("bob")
    other.get("/insights/")
    assert len(_events(rig)) == 2


def test_background_poll_does_not_keep_the_session_alive(rig):
    b, _ = rig.signed_in()
    poll = {BACKGROUND_POLL_HEADER: "1"}
    step = gstore.TOUCH_EVERY_SECONDS + 1
    for _ in range(int(gstore.IDLE_SECONDS // step) + 2):
        rig.advance(step)
        if b.get("/insights/api/run-status", headers=poll).status_code != 200:
            break
    else:
        pytest.fail("polling kept an idle session alive")
    assert b.get("/api/auth/session").status_code == 401


def test_real_request_still_moves_last_seen(rig):
    b, _ = rig.signed_in()
    poll = {BACKGROUND_POLL_HEADER: "1"}
    rig.advance(gstore.IDLE_SECONDS - 60)
    assert b.get("/insights/api/run-status", headers=poll).status_code == 200
    assert b.get("/insights/api/history").status_code == 200  # a real request refreshes the session
    rig.advance(gstore.IDLE_SECONDS - 60)
    assert b.get("/insights/api/history").status_code == 200


def test_poll_header_is_ignored_outside_insights_and_when_the_flag_is_off(tmp_path, rig):
    b, _ = rig.signed_in()
    poll = {BACKGROUND_POLL_HEADER: "1"}
    rig.advance(gstore.IDLE_SECONDS - 60)
    assert b.get("/api/plan/rows", headers=poll).status_code == 200  # a planner request: counts as activity
    rig.advance(gstore.IDLE_SECONDS - 60)
    assert b.get("/api/plan/rows").status_code == 200
    off = Rig(tmp_path / "off")
    b2, _ = off.signed_in()
    off.advance(gstore.IDLE_SECONDS - 60)
    assert b2.get("/insights/api/run-status", headers=poll).status_code == 200
    off.advance(gstore.IDLE_SECONDS - 60)
    assert b2.get("/insights/api/run-status").status_code == 200


@pytest.mark.parametrize("poll,touched", [(True, 0), (False, 1)])
def test_background_poll_does_not_touch_the_worker(poll, touched):
    from unittest.mock import MagicMock

    from src.gateway.proxy import WorkerProxy
    from src.gateway.upstream import Identity
    from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest

    sup = MagicMock()
    sup.port_owner_ok.return_value = False  # stops after the touch point; nothing is sent
    proxy = WorkerProxy(sup, MagicMock())
    req = LocalRequest("GET", "/insights/api/run-status", HeaderMap({}), b"", environ={"gateway_background_poll": poll})
    assert proxy.forward(req, Identity(7, "ann", "Ann", "user")).status_code == 503
    assert sup.touch.call_count == touched


def test_signed_out_insights_api_call_gets_json_401_not_a_login_redirect(rig):
    # The page's fetch must see a 401 (to leave for /login); a 302 would be followed to the login HTML as a "success".
    resp = rig.browser().get("/insights/api/ping")
    assert resp.status_code == 401
    assert resp.get_json()["authenticated"] is False
    assert rig.browser().get("/insights/").status_code == 302  # the page itself still redirects
