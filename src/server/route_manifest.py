from __future__ import annotations

"""Route ownership manifest for the local desktop API."""

ROUTE_MODULES = {
    "build_results": ["/api/build/preflight", "/api/build/start", "/api/build/status/<job_id>", "/api/detailed-results", "/api/report-package", "/api/history", "/api/xlsx", "/api/pdf", "/api/workbook-format", "/files/<path:filename>"],
    "plan_data": ["/api/plan/forms", "/api/plan/save-as", "/api/plan/load-file", "/api/plan/snapshot/compare", "/api/plan/snapshot/restore"],
    "plan_config": ["/api/config/backends", "/api/config/rows", "/api/allocation-preview"],
    "pricing": ["/api/prices/refresh", "/api/prices/snapshots", "/api/prices/freeze", "/api/prices/unfreeze", "/api/prices/test-symbol", "/api/prices/test-symbol/start", "/api/prices/test-symbol/status/<job_id>"],
    "portfolio": ["/api/portfolio/drift"],
    "security": ["/api/secrets"],
    "spending": [
        "/api/spending/model", "/api/spending/budget", "/api/spending/category", "/api/spending/dashboard",
        "/api/spending/summary", "/api/spending/taxonomy", "/api/spending/taxonomy/category",
        "/api/spending/taxonomy/group", "/api/spending/rules", "/api/spending/rules/save",
        "/api/spending/budget/taxonomy", "/api/spending/budget/taxonomy/save", "/api/spending/budget/recover",
        "/api/spending/aliases", "/api/spending/alias", "/api/spending/restore-template",
        "/api/spending/hide-unused-templates", "/api/spending/budget/load-actuals",
    ],
    "ytd": ["/api/ytd/status", "/api/ytd/transactions", "/api/ytd/transactions/preview"],
    "strategy_assets": [
        "/api/holdings", "/api/holdings/preview",
        "/api/large-discretionary-expenses", "/api/forced-roth-conversions", "/api/liquidity-buffers",
        "/api/other-asset/add", "/api/other-asset/delete", "/api/note-receivable/add", "/api/note-receivable/delete", "/api/education-529/add",
        "/api/estate-state-options", "/api/estate-state/add", "/api/trust-account/add",
        "/api/insurance-policy/add", "/api/insurance-policy/delete", "/api/capital-market/assumptions",
        "/api/capital-market/correlations", "/api/housing/seed", "/api/housing/state-estimate", "/api/wellness/seed", "/api/config/sync",
    ],
    "admin": ["/api/admin/diagnostics", "/api/admin/system-config", "/api/contracts"],
}

def route_manifest() -> dict:
    return {
        "schema": "phase3_route_manifest_v1",
        "modules": ROUTE_MODULES,
    }
