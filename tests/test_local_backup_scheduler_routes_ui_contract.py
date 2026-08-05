from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_backup_api_routes_and_stub_map_are_registered() -> None:
    routes = read("src/server/plan_routes.py")
    init = read("src/server/__init__.py")
    for route in ("/api/plan/backups", "/api/plan/backups/config", "/api/plan/backups/run"):
        assert route in routes
        assert route in init
    assert "local_backup_scheduler" in routes
    assert "local_backup_run" in routes


def test_normal_settings_exposes_backup_controls() -> None:
    # The local-backups card/controls live in dashboard_decomp_local_backups.js,
    # a sibling module loaded alongside dashboard.js (see frontend/index.html).
    js = read("frontend/js/dashboard.js") + read("frontend/js/dashboard_decomp_local_backups.js")
    assert "local_backup_scheduler_v1" not in js  # contract stays server-side; UI uses API routes
    assert "Local backups" in js
    assert "Enable automatic backups" in js
    assert "Every build" in js
    assert 'maybeRunLocalBackup("save")' in js
    assert 'maybeRunLocalBackup("build")' in js


def test_backup_contract_is_documented_and_roadmap_completed() -> None:
    api = read("documentation/API_CONTRACTS.md")
    spec = read("documentation/CURRENT_SYSTEM_DESIGN_SPEC.md")
    changelog = read("documentation/GOLDEN_MASTER_CHANGELOG.md")
    assert "local_backup_scheduler_v1" in api
    assert "/api/plan/backups/run" in api
    assert "Add local backup scheduler with retention policy. Completed" in spec
    assert "Automated local backup retention. Completed" in spec
    assert "# v10 local backup scheduler" in changelog
