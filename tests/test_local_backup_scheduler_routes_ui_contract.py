from __future__ import annotations

from pathlib import Path
from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_backup_api_routes_and_stub_map_are_registered() -> None:
    # src/server/plan_routes.py is where these routes are actually registered
    # (@app.route(...)) -- src/server/__init__.py just imports the route
    # modules for their registration side effect and was never a second
    # source of truth here. It used to also list these route strings, but
    # only inside `_ensure_test_url_map`'s dead fallback URL map (item 1.3 /
    # finding A8), which this test was inadvertently grepping like a text
    # fixture rather than checking real route registration.
    routes = read("src/server/plan_routes.py")
    for route in ("/api/plan/backups", "/api/plan/backups/config", "/api/plan/backups/run"):
        assert route in routes
    assert "local_backup_scheduler" in routes
    assert "local_backup_run" in routes


def test_normal_settings_exposes_backup_controls() -> None:
    # The local-backups card/controls live in dashboard_decomp_local_backups.js,
    # a sibling module loaded alongside dashboard.js (see frontend/index.html).
    js = dashboard_js_text() + read("frontend/js/dashboard_decomp_local_backups.js") + read("frontend/js/dashboard_decomp_row_model.js")
    assert "local_backup_scheduler_v1" not in js  # contract stays server-side; UI uses API routes
    assert "Local backups" in js
    assert "Enable automatic backups" in js
    assert "Every build" in js
    assert 'maybeRunLocalBackup("save")' in js
    assert 'maybeRunLocalBackup("build")' in js


def test_backup_contract_is_documented() -> None:
    api = read("documentation/API_CONTRACTS.md")
    changelog = read("documentation/GOLDEN_MASTER_CHANGELOG.md")
    assert "local_backup_scheduler_v1" in api
    assert "/api/plan/backups/run" in api
    assert "# v11 local backup scheduler" in changelog
