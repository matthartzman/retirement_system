from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


# The "service exists" + "routes delegate" checks that used to live here are
# generalized (system review 2026-07-21, Q6) into SERVICE_ROUTE_PAIRS in
# test_126_service_extraction.py, alongside every other extracted service's
# equivalent pair. Only this file's manifest/packaging test remains.


def test_manifest_contracts_and_packaging_include_new_services():
    manifest = read("src/server/route_manifest.py")
    contracts = read("src/api_contracts.py")
    package = read("tools/build_release_package.py")
    validator = read("tools/validate_clean_overlay.py")
    assert '"portfolio": ["/api/portfolio/drift"]' in manifest
    assert '"security": ["/api/secrets"]' in manifest
    assert "portfolio_drift_v1" in contracts
    assert "secret_set_v1" in contracts
    assert "runtime_status_v1" in contracts
    assert "portfolio_service.py" in package
    assert "secret_service.py" in package
    assert "portfolio_service.py" in validator
    assert "secret_service.py" in validator
