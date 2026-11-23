"""PR-11 / PR-13 / PR-14: upload caps and a PDF page limit, finite numbers only, bounded and rate-limited forced backups."""
from __future__ import annotations

import base64

import pytest

from src.server import app, plan_routes
from src.server import request_limits as lim
from tests.plan_fixture import make_plan

HEADERS = {"X-User-Role": "admin"}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    return plan


# ---- pure helpers ----
@pytest.mark.parametrize("bad", ["nan", "NaN", "inf", "-inf", "Infinity", float("nan"), float("inf")])
def test_finite_float_refuses_nan_and_infinity(bad):
    with pytest.raises(ValueError):
        lim.finite_float(bad)


def test_finite_float_accepts_ordinary_numbers():
    assert lim.finite_float("12.5") == 12.5 and lim.finite_float(0) == 0.0 and lim.finite_float("-3") == -3.0
    with pytest.raises(ValueError):
        lim.finite_float("abc")


def test_trigger_is_bounded_and_clean():
    assert lim.clean_trigger("manual") == "manual" and lim.clean_trigger(None) == "manual"
    assert lim.clean_trigger("a" * 500) == "a" * lim.MAX_TRIGGER_CHARS
    assert lim.clean_trigger("x; DROP\n<b>") == "xDROPb"


def test_forced_run_limiter_spaces_runs():
    now = [100.0]
    lm = lim.ForcedRunLimiter(300, clock=lambda: now[0])
    assert lm.acquire() == 0.0
    now[0] += 10
    assert 289 < lm.acquire() <= 290
    now[0] += 300
    assert lm.acquire() == 0.0


def test_pdf_page_limit():
    one = b"%PDF-1.4\n1 0 obj<</Type /Pages>>endobj 2 0 obj<</Type /Page>>endobj"
    many = b"%PDF-1.4\n" + b"<</Type /Page>>" * (lim.MAX_PDF_PAGES + 1)
    assert lim.pdf_page_count(one) == 1 and lim.pdf_problem(one) is None
    assert "pages" in lim.pdf_problem(many) and "not a PDF" in lim.pdf_problem(b"hello")


# ---- routes ----
def test_nan_and_infinity_are_refused_by_the_sales_routes(ws):
    client = app.test_client()
    for value in ("nan", "inf", "-Infinity"):
        r = client.post("/api/sales/1/replace", headers=HEADERS, json={"proceeds": value})
        assert r.status_code == 400 and "number" in r.get_json()["error"]
        r = client.post("/api/sales/candidates/1/confirm", headers=HEADERS, json={"fees": value})
        assert r.status_code == 400
        r = client.get(f"/api/sales/candidates/1/panel?shares={value}", headers=HEADERS)
        assert r.status_code == 400
        r = client.get(f"/api/reconcile?tolerance={value}", headers=HEADERS)
        assert r.status_code in (400, 404)


def test_oversized_uploads_are_refused_before_decoding(ws, monkeypatch):
    client = app.test_client()
    monkeypatch.setattr(lim, "MAX_PLAN_UPLOAD_B64", 100)
    r = client.post("/api/plan/upload", headers=HEADERS, json={"content_base64": "A" * 101, "filename": "x.rpx"})
    assert r.status_code == 413
    monkeypatch.setattr(lim, "MAX_STATEMENT_TEXT", 50)
    for path in ("/api/sales/1099b/preview", "/api/sales/broker/preview"):
        r = client.post(path, headers=HEADERS, json={"content": "x" * 51, "broker": "b", "account": "a"})
        assert r.status_code in (400, 413) and "too large" in r.get_json()["error"], path


def test_a_pdf_over_the_page_limit_is_refused_before_parsing(ws, monkeypatch):
    client = app.test_client()
    monkeypatch.setattr(lim, "MAX_PDF_PAGES", 2)
    pdf = b"%PDF-1.4\n" + b"<</Type /Page>>" * 3
    r = client.post("/api/sales/1099b/preview", headers=HEADERS,
                    json={"pdf_base64": base64.b64encode(pdf).decode(), "broker": "b", "account": "a"})
    assert r.status_code == 413 and "pages" in r.get_json()["error"]
    r = client.post("/api/sales/1099b/preview", headers=HEADERS,
                    json={"pdf_base64": base64.b64encode(b"not a pdf").decode(), "broker": "b", "account": "a"})
    assert r.status_code == 413 and "not a PDF" in r.get_json()["error"]


def test_forced_backups_are_rate_limited_and_the_trigger_is_bounded(ws, monkeypatch):
    seen = []
    monkeypatch.setattr(plan_routes.local_backup_scheduler, "run_backup",
                        lambda *a, **k: seen.append(k) or {"success": True, "created": True})
    monkeypatch.setattr(plan_routes, "_FORCED_BACKUPS", lim.ForcedRunLimiter(300))
    client = app.test_client()
    first = client.post("/api/plan/backups/run", headers=HEADERS, json={"force": True, "trigger": "t" * 400})
    assert first.status_code == 200 and seen[0]["trigger"] == "t" * lim.MAX_TRIGGER_CHARS and seen[0]["force"] is True
    second = client.post("/api/plan/backups/run", headers=HEADERS, json={"force": True})
    assert second.status_code == 429 and len(seen) == 1 and int(second.headers["Retry-After"]) > 0
    assert client.post("/api/plan/backups/run", headers=HEADERS, json={}).status_code == 200  # an unforced run is untouched
