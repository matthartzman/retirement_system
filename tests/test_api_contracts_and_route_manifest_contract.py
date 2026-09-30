import importlib.util
from pathlib import Path

from src.api_contracts import CONTRACT_BY_KEY, contract_summary, validate_payload

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("route_manifest_for_test", ROOT / "src/server/route_manifest.py")
route_manifest_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(route_manifest_mod)
ROUTE_MODULES = route_manifest_mod.ROUTE_MODULES
route_manifest = route_manifest_mod.route_manifest


def test_high_value_api_contracts_are_typed_and_exposed():
    keys = set(CONTRACT_BY_KEY)
    assert "GET /api/build/preflight" in keys
    assert "POST /api/plan/snapshot/restore" in keys
    assert "GET /api/plan/snapshot/compare" in keys
    assert "GET /api/report-package" in keys
    assert "POST /api/ytd/transactions/preview" in keys
    summary = contract_summary()
    assert all(c["route"] and c["method"] and c["schema"] for c in summary)


def test_contract_validation_reports_missing_required_fields():
    errors = validate_payload("GET", "/api/build/preflight", {"success": True, "schema": "build_preflight_v1"})
    assert "Missing required response field: readiness" in errors
    ok = validate_payload("GET", "/api/plan/snapshot/compare", {"success": True, "schema": "plan_snapshot_compare_v1", "database_matches": False})
    assert ok == []


def test_phase3_route_manifest_groups_domains():
    manifest = route_manifest()
    assert manifest["schema"] == "phase3_route_manifest_v1"
    assert "build_results" in ROUTE_MODULES
    assert "/api/report-package" in ROUTE_MODULES["build_results"]
    assert "/api/spending/model" in ROUTE_MODULES["spending"]


def test_route_manifest_classifies_every_registered_route_and_no_stale_ones():
    """ARC-009: the manifest served via /api/contracts must equal the registered routes."""
    from src.server import app

    registered = {r.rule for r in app.url_map.iter_rules()}
    classified = [p for paths in ROUTE_MODULES.values() for p in paths]
    assert len(classified) == len(set(classified)), "a route is classified under two groups"
    assert sorted(registered - set(classified)) == [], "registered routes missing from ROUTE_MODULES"
    assert sorted(set(classified) - registered) == [], "ROUTE_MODULES lists routes that are not registered"
