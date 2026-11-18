"""The sign-in page offers a choice of app (Planner or Financial Insight) only when the server offers Financial Insight.

The page learns that from the signed-out session JSON; a signed-in member and guest still get their own flags. The page's
own redirect rule is tested in tests/frontend/gateway_login_landing.test.mjs.
"""
from __future__ import annotations

from tests.gateway_rig import Rig


def test_signed_out_session_says_whether_financial_insight_is_offered(tmp_path):
    on, off = Rig(tmp_path / "on", insights=True), Rig(tmp_path / "off")
    r = on.browser().get("/api/auth/session")
    assert r.status_code == 401 and r.get_json()["insights"] is True and r.get_json()["authenticated"] is False
    r = off.browser().get("/api/auth/session")
    assert r.status_code == 401 and r.get_json()["insights"] is False


def test_signed_out_session_says_nothing_about_accounts(tmp_path):
    body = Rig(tmp_path, insights=True).browser().get("/api/auth/session").get_json()
    assert set(body) == {"success", "authenticated", "insights"}

