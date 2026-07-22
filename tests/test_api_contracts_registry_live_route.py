import json

from src.api_contracts import CONTRACT_BY_KEY, contract_summary, validate_payload

# Q1/Q8 (system review 2026-07-21): this file used to also carry four
# string-presence-only checks (file existence, script load order via
# hardcoded `?v=N` cache-bust numbers, route-delegation substrings, and a
# validator-script content check). Two of those hardcoded exact `?v=N`
# version numbers, so they broke on the next unrelated cache-bust bump for no
# real reason -- a concrete instance of the brittleness this review flagged.
# Only the two tests that actually execute code and check a real result
# remain below.


def test_api_contracts_endpoint_is_framework_neutral_and_live():
    from src.server import app

    resp = app.test_client().get("/api/contracts")
    assert resp.status_code == 200
    payload = json.loads(resp.get_data(as_text=True))
    assert payload["success"] is True
    assert payload["schema"] == "api_contract_registry_v1"
    assert any(c["route"] == "/api/build/preflight" for c in payload["contracts"])
    assert payload["route_manifest"]["schema"] == "phase3_route_manifest_v1"


def test_contract_registry_validates_contract_shapes():
    assert "GET /api/contracts" in CONTRACT_BY_KEY
    assert "GET /api/build/preflight" in CONTRACT_BY_KEY
    assert all(c["route"] and c["method"] and c["schema"] for c in contract_summary())
    errors = validate_payload("GET", "/api/contracts", {"success": True, "schema": "api_contract_registry_v1", "contracts": []})
    assert errors == []
