"""Percent view on the remote listener: scaled JSON, withheld detail, generic errors."""
from __future__ import annotations

import json

from tests.test_trends_access_gate_functional import SHARED_MONEY_JSON, Rig

MARK = {"mode": "percent", "basis": "net_worth_today"}


def _rig(tmp_path, basis=lambda: 10000.0, users=(("ann", "percent"),)):
    rig = Rig(tmp_path, percent_basis=basis, test_routes=True)
    tokens = {}
    for name, view in users:
        rig.add(name, money_view=view)
        tokens[name] = rig.signin(name)[1]
    return rig, tokens


def test_percent_user_gets_scaled_json(tmp_path):
    rig, t = _rig(tmp_path)
    resp = rig.call(rig.remote, "GET", "/api/test-money", cookie=t["ann"])
    assert resp.status_code == 200
    assert resp.get_json() == {"total": 0.5, "days": 3, "money_view": MARK}
    who = rig.call(rig.remote, "GET", "/api/whoami", cookie=t["ann"]).get_json()
    assert who["money_view"] == "percent"  # whoami is pass-through: the page learns its mode


def test_dollars_and_both_users_and_local_get_dollars(tmp_path):
    rig, t = _rig(tmp_path, users=(("dee", "dollars"), ("bo", "both")))
    for name in ("dee", "bo"):
        assert rig.call(rig.remote, "GET", "/api/test-money", cookie=t[name]).get_json() == {"total": 5000.0, "days": 3}
    assert rig.call(rig.local, "GET", "/api/test-money").get_json() == {"total": 5000.0, "days": 3}


def test_transactions_withheld_403(tmp_path):
    rig, t = _rig(tmp_path, users=(("ann", "percent"), ("dee", "dollars")))
    resp = rig.call(rig.remote, "GET", "/api/spending/transactions", cookie=t["ann"])
    assert resp.status_code == 403
    assert resp.get_json() == {"success": False, "error": "Not available in the percent view."}
    assert rig.call(rig.remote, "GET", "/api/spending/transactions", cookie=t["dee"]).status_code != 403


def test_basis_missing_gives_503(tmp_path):
    rig, t = _rig(tmp_path, basis=lambda: None)
    resp = rig.call(rig.remote, "GET", "/api/test-money", cookie=t["ann"])
    assert resp.status_code == 503
    assert resp.get_json() == {"success": False, "error": "The percent view is not available until account balances are imported."}
    assert rig.call(rig.remote, "GET", "/api/whoami", cookie=t["ann"]).status_code == 200


def test_error_text_replaced(tmp_path):
    rig, t = _rig(tmp_path)
    generic = {"success": False, "error": "Something went wrong. Try again later."}
    for path in ("/api/test-money-error", "/api/test-money-raises"):
        resp = rig.call(rig.remote, "GET", path, cookie=t["ann"])
        assert resp.status_code == 500 and resp.get_json() == generic and "$" not in resp.get_data(as_text=True)
    assert "1,234" in rig.call(rig.local, "GET", "/api/test-money-error").get_data(as_text=True)


def test_cached_string_not_mutated_for_owner(tmp_path):
    rig, t = _rig(tmp_path)
    guest = rig.call(rig.remote, "GET", "/api/test-money-cached", cookie=t["ann"]).get_json()
    assert guest["total"] == 0.5
    assert rig.call(rig.local, "GET", "/api/test-money-cached").get_json() == {"total": 5000.0, "days": 3}
    assert json.loads(SHARED_MONEY_JSON) == {"total": 5000.0, "days": 3}


def test_view_change_applies_next_request(tmp_path):
    rig, t = _rig(tmp_path)
    uid = 1  # first user in a fresh store
    assert rig.call(rig.remote, "GET", "/api/test-money", cookie=t["ann"]).get_json()["total"] == 0.5
    assert rig.call(rig.local, "POST", "/api/people/view", {"id": uid, "money_view": "dollars"}).status_code == 200
    assert rig.call(rig.remote, "GET", "/api/test-money", cookie=t["ann"]).get_json() == {"total": 5000.0, "days": 3}


def test_remote_still_404s_people_for_percent_user(tmp_path):
    rig, t = _rig(tmp_path)
    assert rig.call(rig.remote, "GET", "/api/people", cookie=t["ann"]).status_code == 404
