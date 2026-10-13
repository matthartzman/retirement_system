from __future__ import annotations

"""Route ownership manifest for the local desktop API."""

ROUTE_MODULES = {
    "build_results": ["/api/build/preflight", "/api/build/start", "/api/build", "/api/build/status", "/api/build/progress/<job_id>", "/api/build/events/<job_id>", "/api/build/events/<job_id>/snapshot", "/api/detailed-results", "/api/report-package", "/api/history", "/api/xlsx", "/api/workbook-format", "/files/<path:filename>", "/api/kpi-snapshots", "/api/kpi-snapshots/compare"],
    "app_shell": ["/", "/admin", "/login", "/frontend", "/frontend/<path:filename>", "/system-configuration"],
    "runtime": [
        "/api/ping", "/api/status", "/api/runtime", "/api/shutdown", "/api/prefs", "/api/schema", "/api/summary", "/api/validate",
        "/api/auth/login", "/api/auth/logout", "/api/auth/session", "/api/settings/workbook-download",
    ],
    "plan_data": ["/api/plan/forms", "/api/plan/save-as", "/api/plan/load-file", "/api/plan/snapshot/compare", "/api/plan/snapshot/restore", "/api/plan/revisions",
        "/api/plan", "/api/plan/forms/<path:section_path>", "/api/plan/backups", "/api/plan/backups/config", "/api/plan/backups/run",
        "/api/plan/monarch-autoupdate", "/api/plan/monarch-autoupdate/config", "/api/plan/monarch-autoupdate/run",
        "/api/plan/demo-status", "/api/plan/open-demo", "/api/plan/reset-demo", "/api/plan/exit-demo", "/api/plan/exit-snapshot",
        "/api/plans", "/api/plans/switch", "/api/plans/rename", "/api/plans/forget",
        "/api/import/preview", "/api/import/commit", "/api/export/plan-set", "/api/export/<dataset>",
        "/api/plan/blank", "/api/conversion/status", "/api/conversion/check", "/api/conversion/run",
    ],
    "rental": [
        "/api/rental/properties", "/api/rental/property", "/api/rental/home", "/api/rental/property/duplicate",
        "/api/rental/property/delete", "/api/rental/improvements", "/api/rental/overrides",
    ],
    "plan_config": ["/api/config/backends", "/api/config/rows", "/api/allocation-preview", "/api/plan/tier", "/api/plan/feature", "/api/plan/interview"],
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
        "/api/capital-market/correlations", "/api/capital-market/real-loss-curves", "/api/housing/seed", "/api/housing/state-estimate", "/api/housing/optimize", "/api/wellness/seed",
        "/api/home-sale-splits", "/api/residency-schedule", "/api/tax-assumptions",
        "/api/daf/recommendation", "/api/qlac/recommendation", "/api/housing/top-cities", "/api/housing/zip-lookup", "/api/housing/zip-screen",
        "/api/hsa-schedule", "/api/liabilities", "/api/withdrawal-account-order",
    ],
    "admin": ["/api/admin/diagnostics", "/api/admin/system-config", "/api/contracts", "/api/glossary",
        "/api/admin/clear-webview-cache", "/api/admin/csv-backup", "/api/admin/mode",
        "/api/admin/server", "/api/admin/server/shutdown",
        "/api/admin/tax-law-dashboard",
    ],
}

def route_manifest() -> dict:
    return {
        "schema": "phase3_route_manifest_v1",
        "modules": ROUTE_MODULES,
    }
