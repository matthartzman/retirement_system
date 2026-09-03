from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_monarch_autoupdate_api_routes_are_registered() -> None:
    # Deliberately checks src/server/plan_routes.py only (Python, not
    # frontend JS/HTML/CSS) -- see tests/test_freeze_frontend_source_grep.py:
    # new frontend-source string-literal assertions are frozen; behavioral
    # frontend coverage for the settings card lives in
    # tests/frontend/monarch_autoupdate_card.test.mjs (Node vm sandbox,
    # executes the real render function) and the script-load-order check
    # lives in tests/test_dashboard_startup_race_and_script_order.py
    # alongside the equivalent local-backups check.
    routes = read("src/server/plan_routes.py")
    for route in (
        "/api/plan/monarch-autoupdate",
        "/api/plan/monarch-autoupdate/config",
        "/api/plan/monarch-autoupdate/run",
    ):
        assert route in routes
    assert "monarch_autoupdate" in routes
    assert "_run_monarch_autoimport" in routes
