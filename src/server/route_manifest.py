from __future__ import annotations

"""Route ownership manifest for the local desktop API."""

ROUTE_MODULES = {
    "build_results": ["/api/build/preflight", "/api/build/start", "/api/build", "/api/build/status", "/api/build/progress/<job_id>", "/api/build/events/<job_id>", "/api/build/events/<job_id>/snapshot", "/api/detailed-results", "/api/report-package", "/api/history", "/api/xlsx", "/api/workbook-format", "/files/<path:filename>", "/api/kpi-snapshots", "/api/kpi-snapshots/compare"],
    "app_shell": ["/", "/admin", "/login", "/frontend", "/frontend/<path:filename>", "/system-configuration"],
    "runtime": [
        "/api/ping", "/api/status", "/api/runtime", "/api/shutdown", "/api/prefs", "/api/schema", "/api/summary", "/api/validate",
        "/api/auth/login", "/api/auth/logout", "/api/auth/session", "/api/settings/workbook-download",
    ],
    "plan_data": ["/api/plan/forms", "/api/plan/save-as", "/api/plan/load-file", "/api/plan/snapshot/compare", "/api/plan/snapshot/restore",
        "/api/plan", "/api/plan/forms/<path:section_path>", "/api/plan/backups", "/api/plan/backups/config", "/api/plan/backups/run",
        "/api/plan/monarch-autoupdate", "/api/plan/monarch-autoupdate/config", "/api/plan/monarch-autoupdate/run",
        "/api/plan/demo-status", "/api/plan/open-demo", "/api/plan/reset-demo", "/api/plan/restore-current", "/api/plan/exit-snapshot",
        "/api/plan-data/blank", "/api/plan-data/files", "/api/plan-data/<path:file_name>",
    ],
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
        "/api/spending/budget-lines", "/api/spending/budget-lines/defaults", "/api/spending/budget/seed",
        "/api/spending/category/<cat_id>", "/api/spending/category/<cat_id>/restore", "/api/spending/taxonomy/category/<cat_id>",
    ],
    "ytd": ["/api/ytd/status", "/api/ytd/transactions", "/api/ytd/transactions/preview",
        "/api/ytd/transactions/<int:index>", "/api/ytd/transactions/bulk", "/api/ytd/transactions/template", "/api/ytd/transactions/upload",
        "/api/ytd/account-setup", "/api/ytd/account-setup/recover", "/api/ytd/account-setup/roll-forward",
    ],
    "strategy_assets": [
        "/api/holdings", "/api/holdings/preview",
        "/api/large-discretionary-expenses", "/api/spending-adjustments", "/api/forced-roth-conversions", "/api/liquidity-buffers",
        "/api/other-asset/add", "/api/other-asset/delete", "/api/note-receivable/add", "/api/note-receivable/delete", "/api/education-529/add",
        "/api/estate-state-options", "/api/estate-state/add", "/api/trust-account/add",
        "/api/insurance-policy/add", "/api/insurance-policy/delete", "/api/life-illustration/seed", "/api/capital-market/assumptions",
        "/api/capital-market/correlations", "/api/housing/seed", "/api/housing/state-estimate", "/api/housing/optimize", "/api/wellness/seed",
        "/api/home-sale-splits", "/api/residency-schedule", "/api/tax-assumptions",
        "/api/daf/recommendation", "/api/qlac/recommendation", "/api/housing/top-cities", "/api/housing/zip-lookup", "/api/housing/zip-screen",
        "/api/hsa-schedule", "/api/liabilities", "/api/withdrawal-account-order",
    ],
    "admin": ["/api/admin/diagnostics", "/api/admin/system-config", "/api/contracts", "/api/glossary",
        "/api/admin/clear-webview-cache", "/api/admin/csv-backup", "/api/admin/csv-file/<kind>/<path:file_name>", "/api/admin/mode",
        "/api/admin/reference-files", "/api/admin/reference-files/<path:file_name>", "/api/admin/server", "/api/admin/server/shutdown",
        "/api/admin/tax-law-dashboard",
    ],
}

def route_manifest() -> dict:
    return {
        "schema": "phase3_route_manifest_v1",
        "modules": ROUTE_MODULES,
    }
