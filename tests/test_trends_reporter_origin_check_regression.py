"""Finding ARC-4 (system review 2026-09-07, Wave 6 item W6-3):
financial_trends_reporter/main.py's GET /api/history (the full net-worth/
spending log) and POST /api/run-now had zero auth/CORS/origin check --
any cross-origin page could hit either route. This pins the explicit
Origin-header rejection added to close that gap, mirroring the main app's
own same-origin-only posture (src/server/app_core.py, finding SEC-1).
"""
from __future__ import annotations

from pathlib import Path

from financial_trends_reporter.main import create_app


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    return base_dir


def test_a_cross_origin_history_request_is_rejected(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.get(
        "/api/history",
        headers={"Host": "127.0.0.1:5057", "Origin": "http://evil.example"},
    )
    assert resp.status_code == 403


def test_a_cross_origin_run_now_request_is_rejected(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.post(
        "/api/run-now",
        json={},
        headers={"Host": "127.0.0.1:5057", "Origin": "http://evil.example"},
    )
    assert resp.status_code == 403


def test_a_same_origin_history_request_still_succeeds(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.get(
        "/api/history",
        headers={"Host": "127.0.0.1:5057", "Origin": "http://127.0.0.1:5057"},
    )
    assert resp.status_code == 200


def test_a_request_with_no_origin_header_still_succeeds(tmp_path):
    # Ordinary same-origin navigation/fetch in most browsers, and every
    # non-browser local script, sends no Origin header at all -- must not
    # be blocked by this check.
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.get("/api/history")
    assert resp.status_code == 200
