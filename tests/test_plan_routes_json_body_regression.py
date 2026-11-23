"""PR-05 / PR-06: a non-object JSON body is a 400 (never a 500) on every plan route that reads a body, and a year made
of non-ASCII digits is a 400 (never a 500)."""
from __future__ import annotations

import inspect

import pytest

from src.server import app, plan_routes

HEADERS = {"X-User-Role": "admin"}
BODY_ROUTES = sorted({(r.rule, m) for r in app.routes if getattr(r.func, "__module__", "") == plan_routes.__name__
                      and "_json_obj(" in inspect.getsource(r.func) for m in r.methods if m in ("POST", "PUT", "DELETE") and "<" not in r.rule})


def test_the_body_helper_is_used_on_many_routes():
    assert len(BODY_ROUTES) > 40


@pytest.mark.parametrize("rule,method", BODY_ROUTES)
@pytest.mark.parametrize("body", [[1, 2], "text", 7])
def test_non_object_bodies_never_produce_a_server_error(rule, method, body):
    resp = app.test_client().open(rule, method=method, headers=HEADERS, json=body)
    assert resp.status_code < 500, (rule, resp.status_code, resp.get_data(as_text=True)[:200])


def test_a_list_body_is_a_400_with_a_clear_message():
    resp = app.test_client().post("/api/plan/backups/config", headers=HEADERS, json=[1])
    assert resp.status_code == 400 and "JSON object" in resp.get_json()["error"]


@pytest.mark.parametrize("path", ["/api/cash/year-close?year=%C2%B2", "/api/sales/holding-period-check?year=%C2%B2"])
def test_non_ascii_digit_years_are_a_400(path):
    resp = app.test_client().get(path, headers=HEADERS)
    assert resp.status_code == 400
