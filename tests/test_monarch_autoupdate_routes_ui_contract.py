from __future__ import annotations

from pathlib import Path
from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_monarch_autoupdate_api_routes_are_registered() -> None:
    routes = read("src/server/plan_routes.py")
    for route in (
        "/api/plan/monarch-autoupdate",
        "/api/plan/monarch-autoupdate/config",
        "/api/plan/monarch-autoupdate/run",
    ):
        assert route in routes
    assert "monarch_autoupdate" in routes
    assert "_run_monarch_autoimport" in routes


def test_monarch_autoupdate_script_loads_before_dashboard_js() -> None:
    # Same startup-race guarantee dashboard_decomp_local_backups.js relies on
    # (test_dashboard_startup_race_and_script_order.py): the boot chain calls
    # refreshMonarchAutoUpdateStatus(true), defined only in this classic script.
    html = read("frontend/index.html")
    monarch_pos = html.index('<script src="js/dashboard_decomp_monarch_autoupdate.js')
    dashboard_pos = html.index('<script type="module" src="js/dashboard.js')
    assert monarch_pos < dashboard_pos


def test_normal_settings_exposes_monarch_autoupdate_controls() -> None:
    js = dashboard_js_text() + read("frontend/js/dashboard_decomp_monarch_autoupdate.js") + read("frontend/js/dashboard_decomp_checklist_closeout.js")
    assert "monarch_autoupdate_v1" not in js  # contract stays server-side; UI uses API routes
    assert "Monarch auto-update" in js
    assert "Enable daily auto-update" in js
    assert "monarchAutoUpdateControlsHtml()" in js
