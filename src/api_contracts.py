from __future__ import annotations

"""Lightweight typed API contract registry for high-value desktop endpoints.

The application still accepts normal Flask dictionaries at runtime.  These
schemas provide a small, dependency-free contract layer that can be imported by
route tests, documentation checks, and future refactors without introducing
pydantic or changing public payloads.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type_name: str
    required: bool = False
    description: str = ""

    def accepts(self, value: Any) -> bool:
        if value is None:
            return not self.required
        if self.type_name == "any":
            return True
        if self.type_name == "str":
            return isinstance(value, str)
        if self.type_name == "bool":
            return isinstance(value, bool)
        if self.type_name == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if self.type_name == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if self.type_name == "list":
            return isinstance(value, list)
        if self.type_name == "dict":
            return isinstance(value, Mapping)
        return True


@dataclass(frozen=True)
class EndpointContract:
    route: str
    method: str
    schema: str
    request_fields: tuple[FieldSpec, ...] = field(default_factory=tuple)
    response_fields: tuple[FieldSpec, ...] = field(default_factory=tuple)
    notes: str = ""

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.route}"


def _f(name: str, type_name: str, required: bool = False, description: str = "") -> FieldSpec:
    return FieldSpec(name=name, type_name=type_name, required=required, description=description)


CONTRACTS: tuple[EndpointContract, ...] = (
    EndpointContract(
        "/api/build/preflight", "GET", "build_preflight_v1",
        response_fields=(
            _f("success", "bool", True), _f("schema", "str", True), _f("readiness", "str", True),
            _f("blockers", "list", True), _f("warnings", "list", True), _f("recommendations", "list", True),
            _f("artifacts", "dict", True), _f("snapshot", "dict"), _f("pricing_mode", "str"),
        ),
        notes="Fast side-effect-free readiness contract before build.",
    ),
    EndpointContract(
        "/api/config/rows", "GET", "config_rows_v1",
        response_fields=(_f("rows", "list", True), _f("schema_count", "int")),
        notes="Canonical editable Plan Data row list.",
    ),
    EndpointContract(
        "/api/config/rows", "POST", "config_rows_update_v1",
        request_fields=(_f("rows", "list", True),),
        response_fields=(_f("success", "bool", True), _f("saved", "int"), _f("errors", "list")),
    ),
    EndpointContract(
        "/api/spending/model", "GET", "spending_model_v1",
        response_fields=(_f("success", "bool", True), _f("categories", "list"), _f("budget", "list"), _f("summary", "dict")),
    ),
    EndpointContract(
        "/api/holdings", "GET", "holdings_v1",
        response_fields=(_f("success", "bool", True), _f("rows", "list", True), _f("source", "str")),
    ),
    EndpointContract(
        "/api/detailed-results", "GET", "results_model_v10",
        response_fields=(_f("success", "bool", True), _f("sheets", "list"), _f("categories", "list"), _f("schema", "str")),
    ),
    EndpointContract(
        "/api/report-package", "GET", "report_package_v1",
        response_fields=(
            _f("success", "bool", True), _f("schema", "str", True), _f("build_id", "str"),
            _f("contracts", "dict", True), _f("artifacts", "list", True), _f("components", "dict", True),
            _f("summary", "dict"),
        ),
        notes="Canonical advisor report package manifest that treats workbook/PDF/dashboard as renderers of the versioned report bundle.",
    ),
    EndpointContract(
        "/api/ytd/transactions/preview", "POST", "import_preview_v1",
        request_fields=(_f("csv", "str"), _f("content", "str"), _f("filename", "str")),
        response_fields=(_f("success", "bool", True), _f("schema", "str", True), _f("row_count", "int"), _f("warnings", "list")),
    ),
    EndpointContract(
        "/api/holdings/preview", "POST", "import_preview_v1",
        request_fields=(_f("csv", "str"), _f("content", "str"), _f("filename", "str")),
        response_fields=(_f("success", "bool", True), _f("schema", "str", True), _f("row_count", "int"), _f("warnings", "list")),
    ),
    EndpointContract(
        "/api/prices/test-symbol/start", "POST", "price_symbol_test_job_start_v1",
        request_fields=(_f("symbol", "str", True),),
        response_fields=(_f("success", "bool", True), _f("job_id", "str"), _f("symbol", "str"), _f("status", "str")),
    ),
    EndpointContract(
        "/api/prices/test-symbol/status/<job_id>", "GET", "price_symbol_test_job_status_v1",
        response_fields=(_f("success", "bool", True), _f("job_id", "str"), _f("status", "str"), _f("result", "dict"), _f("steps", "list")),
    ),
    EndpointContract(
        "/api/housing/state-estimate", "POST", "housing_state_estimate_v1",
        request_fields=(_f("state", "str", True), _f("type", "str"), _f("city_type", "str"), _f("population_size", "int")),
        response_fields=(_f("success", "bool", True), _f("schema", "str"), _f("estimate", "dict", True)),
    ),
    EndpointContract(
        "/api/portfolio/drift", "GET", "portfolio_drift_v1",
        response_fields=(_f("success", "bool", True), _f("rows", "list", True), _f("stderr", "str")),
    ),
    EndpointContract(
        "/api/secrets", "POST", "secret_set_v1",
        request_fields=(_f("name", "str", True), _f("value", "str", True)),
        response_fields=(_f("success", "bool", True), _f("name", "str")),
    ),
    EndpointContract(
        "/api/status", "GET", "runtime_status_v1",
        response_fields=(_f("version", "str", True), _f("features", "dict", True), _f("encryption", "dict")),
    ),
    EndpointContract(
        "/api/plan/backups", "GET", "local_backup_scheduler_v1",
        response_fields=(_f("success", "bool", True), _f("policy", "dict", True), _f("backups", "list", True), _f("due", "bool")),
    ),
    EndpointContract(
        "/api/plan/snapshot/compare", "GET", "plan_snapshot_compare_v1",
        response_fields=(_f("success", "bool", True), _f("schema", "str", True), _f("database_matches", "bool", True), _f("snapshot_database", "dict"), _f("current_database", "dict")),
    ),
    EndpointContract(
        "/api/plan/snapshot/restore", "POST", "plan_snapshot_restore_v1",
        request_fields=(_f("confirm", "any", True), _f("snapshot_path", "str")),
        response_fields=(_f("success", "bool", True), _f("schema", "str"), _f("active_database", "str"), _f("backup_database", "str")),
    ),


    EndpointContract(
        "/api/spending/budget", "GET", "spending_budget_v1",
        response_fields=(_f("success", "bool", True), _f("budget", "list", True)),
        notes="Unified category budget rows used by Spending Setup and Monthly Trajectory non-tax spending inputs.",
    ),
    EndpointContract(
        "/api/spending/budget", "POST", "spending_budget_update_v1",
        request_fields=(_f("budget", "any"), _f("rows", "list")),
        response_fields=(_f("success", "bool", True),),
        notes="Accepts legacy keyed budget dictionaries or canonical unified budget row arrays.",
    ),
    EndpointContract(
        "/api/spending/taxonomy", "GET", "spending_taxonomy_v1",
        response_fields=(_f("success", "bool", True), _f("taxonomy", "list", True), _f("flat", "dict", True)),
        notes="Tracking Type > Group > Category taxonomy contract; route adapter delegates to SpendingService.",
    ),
    EndpointContract(
        "/api/spending/summary", "GET", "spending_summary_v1",
        response_fields=(_f("success", "bool", True), _f("tracking_types", "list"), _f("year", "int")),
        notes="Taxonomy-aware current-year spending actuals/annualization summary.",
    ),

    EndpointContract(
        "/api/history", "GET", "build_history_v1",
        response_fields=(_f("items", "list"),),
        notes="Returns the local run-history array stored with report outputs; response body is the array for legacy UI compatibility.",
    ),
    EndpointContract(
        "/api/history", "POST", "build_history_append_v1",
        request_fields=(_f("entry", "dict"),),
        response_fields=(_f("success", "bool", True), _f("count", "int", True), _f("path", "str")),
        notes="Appends one local build-history entry and retention-trims to the latest 50 entries.",
    ),

    EndpointContract(
        "/api/withdrawal-order", "POST", "withdrawal_order_update_v1",
        request_fields=(_f("rows", "list", True),),
        response_fields=(_f("success", "bool", True), _f("updated", "int"), _f("sync", "dict")),
        notes="Compressed withdrawal-order table save; route adapter delegates normalization/write behavior to StrategyAssetService.",
    ),
    EndpointContract(
        "/api/large-discretionary-expenses", "GET", "large_discretionary_expenses_v1",
        response_fields=(_f("success", "bool", True), _f("types", "list", True), _f("events", "list", True)),
        notes="Large discretionary expense events used by Travel/Large Discretionary workflow pages.",
    ),
    EndpointContract(
        "/api/large-discretionary-expenses", "POST", "large_discretionary_expenses_update_v1",
        request_fields=(_f("events", "list", True), _f("sync", "bool")),
        response_fields=(_f("success", "bool", True), _f("count", "int", True), _f("sync", "dict")),
    ),
    EndpointContract(
        "/api/forced-roth-conversions", "GET", "forced_roth_conversions_v1",
        response_fields=(_f("success", "bool", True), _f("accounts", "list", True), _f("conversions", "list", True)),
    ),
    EndpointContract(
        "/api/forced-roth-conversions", "POST", "forced_roth_conversions_update_v1",
        request_fields=(_f("conversions", "list", True), _f("sync", "bool")),
        response_fields=(_f("success", "bool", True), _f("count", "int", True), _f("sync", "dict")),
    ),
    EndpointContract(
        "/api/liquidity-buffers", "GET", "liquidity_buffers_v1",
        response_fields=(_f("success", "bool", True), _f("buffers", "list", True)),
    ),
    EndpointContract(
        "/api/liquidity-buffers", "POST", "liquidity_buffers_update_v1",
        request_fields=(_f("buffers", "list", True), _f("sync", "bool")),
        response_fields=(_f("success", "bool", True), _f("count", "int", True), _f("sync", "dict")),
    ),
    EndpointContract(
        "/api/insurance-policy/add", "POST", "insurance_policy_add_v1",
        request_fields=(_f("policy_type", "str"),),
        response_fields=(_f("success", "bool", True), _f("section", "str"), _f("message", "str")),
    ),
    EndpointContract(
        "/api/insurance-policy/delete", "POST", "insurance_policy_delete_v1",
        request_fields=(_f("subsection", "str", True),),
        response_fields=(_f("success", "bool", True), _f("section", "str"), _f("rows_removed", "int")),
    ),
    EndpointContract(
        "/api/config/sync", "POST", "config_sync_v1",
        response_fields=(_f("success", "bool", True),),
        notes="Plan Data adapter synchronization; row bootstrap behavior now lives in StrategyAssetService.",
    ),

    EndpointContract(
        "/api/contracts", "GET", "api_contract_registry_v1",
        response_fields=(_f("success", "bool", True), _f("schema", "str", True), _f("contracts", "list", True), _f("route_manifest", "dict")),
        notes="Framework-neutral contract registry plus route ownership manifest for source-code reconciliation checks.",
    ),
    EndpointContract(
        "/api/admin/system-config", "GET", "system_config_rows_v1",
        response_fields=(_f("success", "bool", True), _f("path", "str", True), _f("rows", "list", True), _f("csv_content", "str")),
        notes="Advanced maintenance row contract used by preview-first batch configuration editing.",
    ),
    EndpointContract(
        "/api/admin/system-config", "POST", "system_config_rows_update_v1",
        request_fields=(_f("rows", "list"), _f("csv_content", "str")),
        response_fields=(_f("success", "bool", True), _f("path", "str", True), _f("change_event", "dict")),
        notes="Writes system_config.csv after explicit preview/confirmation in the user UI.",
    ),
)

CONTRACT_BY_KEY: dict[str, EndpointContract] = {c.key: c for c in CONTRACTS}


def contract_summary() -> list[dict[str, Any]]:
    return [
        {
            "route": c.route,
            "method": c.method,
            "schema": c.schema,
            "request_fields": [field.__dict__ for field in c.request_fields],
            "response_fields": [field.__dict__ for field in c.response_fields],
            "notes": c.notes,
        }
        for c in CONTRACTS
    ]


def validate_payload(method: str, route: str, payload: Mapping[str, Any], *, direction: str = "response") -> list[str]:
    """Return contract violations for a request or response payload."""
    contract = CONTRACT_BY_KEY.get(f"{method.upper()} {route}")
    if not contract:
        return [f"No contract registered for {method.upper()} {route}."]
    fields = contract.response_fields if direction == "response" else contract.request_fields
    errors: list[str] = []
    for spec in fields:
        present = spec.name in payload
        if spec.required and not present:
            errors.append(f"Missing required {direction} field: {spec.name}")
            continue
        if present and not spec.accepts(payload.get(spec.name)):
            errors.append(f"Field {spec.name} expected {spec.type_name}, got {type(payload.get(spec.name)).__name__}")
    if direction == "response" and contract.schema and payload.get("schema") and payload.get("schema") != contract.schema:
        errors.append(f"Schema mismatch: expected {contract.schema}, got {payload.get('schema')}")
    return errors
