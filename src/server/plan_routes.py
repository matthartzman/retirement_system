from .app_core import *
import csv
import io
import hashlib
try:
    from ..version import VERSION
except Exception:
    from src.version import VERSION
try:
    from ..server_services import base_service, config_service, pricing_service, ytd_service, plan_file_service, portfolio_service, secret_service, spending_service, strategy_asset_service
except Exception:
    from src.server_services import base_service, config_service, pricing_service, ytd_service, plan_file_service, portfolio_service, secret_service, spending_service, strategy_asset_service
try:
    from ..portfolio_analytics import freeze_latest_pricing_snapshot, unfreeze_pricing_snapshot
except Exception:
    from src.portfolio_analytics import freeze_latest_pricing_snapshot, unfreeze_pricing_snapshot
try:
    from .. import local_backup_scheduler
except Exception:
    from src import local_backup_scheduler
try:
    from ..secrets_store import set_secret as _set_secret_value
except Exception:
    from src.secrets_store import set_secret as _set_secret_value



def _strategy_asset_feature_service() -> strategy_asset_service.StrategyAssetService:
    return strategy_asset_service.StrategyAssetService(
        strategy_asset_service.StrategyAssetServiceContext(
            base_dir=BASE_DIR,
            plan_data_path=_plan_data_path,
            client_section_path=_client_section_path,
            reference_file_path=_reference_file_path,
            csv_read_rows=_csv_read_rows,
            csv_write_rows=_csv_write_rows,
            ensure_header=_ensure_header,
            write_client_rows=_write_client_rows,
            read_client_section_rows=_read_client_section_rows,
            large_discretionary_expenses_from_plan_data=_large_discretionary_expenses_from_plan_data,
            normalize_large_discretionary_type=_normalize_large_discretionary_type,
            replace_large_discretionary_expenses=_replace_large_discretionary_expenses,
            pre_tax_account_options_from_holdings=_pre_tax_account_options_from_holdings,
            forced_roth_conversions_from_csv_rows=_forced_roth_conversions_from_csv_rows,
            replace_forced_roth_conversions=_replace_forced_roth_conversions,
            liquidity_buffers_from_csv_rows=_liquidity_buffers_from_csv_rows,
            replace_liquidity_buffers=_replace_liquidity_buffers,
            ensure_user_ui_plan_data_rows=_ensure_user_ui_plan_data_rows,
            sync_config_backends=_sync_config_backends,
            audit=_audit,
            travel_extra_types=TRAVEL_EXTRA_TYPES,
        )
    )


def _config_feature_service() -> config_service.ConfigService:
    return config_service.ConfigService(
        config_service.ConfigServiceContext(
            version=VERSION,
            base_dir=BASE_DIR,
            csv_path=CSV_PATH,
            plan_data_csv_files=PLAN_DATA_CSV_FILES,
            client_data_csv_file_set=CLIENT_DATA_CSV_FILE_SET,
            plan_data_path=_plan_data_path,
            client_csv_rows=_client_csv_rows,
            csv_rows_payload=_csv_rows_payload,
            read_schema_map=_read_schema_map,
            write_client_rows=_write_client_rows,
            load_active_config=load_active_config,
            runtime_config=_runtime_config,
            normalize_date_for_csv=_normalize_date_for_csv,
            sync_config_backends=_sync_config_backends,
            audit=_audit,
        )
    )

def _service_json(result):
    payload, status_code = result
    return jsonify(payload), status_code


def _path_roots_from_config():
    cfg = _runtime_config()
    raw = str(getattr(cfg, "local_plan_data_roots", "") or getattr(cfg, "local_plan_data_dir", "") or "")
    roots = []
    for part in re.split(r"[;|]", raw):
        part = part.strip()
        if not part:
            continue
        p = Path(part).expanduser()
        if not p.is_absolute():
            p = (BASE_DIR / p)
        try:
            roots.append(p.resolve())
        except Exception:
            pass
    # LOCAL loopback mode may use the configured local Plan Data directory. local
    # must opt into explicit allowlisted roots.
    return roots


def _server_path_requires_allowlist():
    cfg = _runtime_config()
    host = str(getattr(cfg, "dashboard_host", "127.0.0.1") or "127.0.0.1").strip().lower()
    return str(getattr(cfg, "app_mode", "LOCAL") or "LOCAL").upper() != "LOCAL" or host not in {"127.0.0.1", "localhost", "::1"}




def _validate_rows_for_csv_file(name: str, rows: list[list[str]]) -> list[str]:
    """Run the shared schema/cross-field validator on one CSV payload before saving."""
    if name not in PLAN_DATA_CSV_FILE_SET:
        return []
    if not rows:
        return []
    try:
        from ..schema_registry import validate_rows as _schema_validate_rows_full
    except Exception:  # pragma: no cover - direct execution fallback
        from src.schema_registry import validate_rows as _schema_validate_rows_full
    header = list(rows[0])
    dict_rows = []
    for raw in rows[1:]:
        padded = list(raw) + [""] * max(0, len(header) - len(raw))
        dict_rows.append({header[i]: padded[i] if i < len(padded) else "" for i in range(len(header))})
    return _schema_validate_rows_full(dict_rows)

def _validate_all_workspace_plan_rows(file_rows: dict[str, list[list[str]]]) -> list[str]:
    """Validate the effective full Plan Data set after pending edits.

    Cross-field rules can span rows that were not in the current POST. Load the
    existing workspace files, overlay edited files, and validate all editable Plan
    Data rows as one set before any write reaches disk.
    """
    try:
        from ..schema_registry import validate_rows as _schema_validate_rows_full
    except Exception:  # pragma: no cover
        from src.schema_registry import validate_rows as _schema_validate_rows_full
    combined=[]
    names = [n for n in PLAN_DATA_CSV_FILES if n != 'client_holdings.csv']
    for name in names:
        rows = file_rows.get(name)
        if rows is None:
            p = _plan_data_path(name)
            if not p.exists():
                continue
            with p.open(newline='', encoding='utf-8-sig') as f:
                rows = list(csv.reader(f))
        if not rows:
            continue
        header = list(rows[0])
        if not {'section','subsection','label','value'}.issubset(set(header)):
            continue
        for raw in rows[1:]:
            padded = list(raw) + [''] * max(0, len(header) - len(raw))
            combined.append({header[i]: padded[i] if i < len(padded) else '' for i in range(len(header))})
    return _schema_validate_rows_full(combined)

def _server_path_allowed(folder: Path):
    cfg = _runtime_config()
    if str(getattr(cfg, "app_mode", "LOCAL") or "LOCAL").upper() == "SAAS":
        return False, "Server-side path loading is disabled in local-only package; saving is also disabled."
    if not _server_path_requires_allowlist():
        return True, ""
    roots = _path_roots_from_config()
    if not roots:
        return False, "LAN/server-side Plan Data paths require System Configuration > Security > local_plan_data_roots allowlist."
    try:
        resolved = folder.resolve()
        for root in roots:
            resolved.relative_to(root)
            return True, ""
    except Exception:
        pass
    return False, "Requested Plan Data path is outside the configured local_plan_data_roots allowlist."

@app.route("/api/status", methods=["GET"])
def status():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return jsonify(base_service.status_payload(version=VERSION, cfg=_runtime_config(), base_dir=BASE_DIR, output_dir=_workspace_output(), encryption=encryption_status()))



@app.route("/api/prices/refresh", methods=["POST"])
def refresh_prices():
    denied = _require("refresh_prices")
    if denied:
        return denied
    payload = pricing_service.refresh_prices(
        base_dir=BASE_DIR,
        output_dir=_workspace_output(),
        system_config_csv=_request_system_config_csv(),
        max_build_seconds=_runtime_config().max_build_seconds,
    )
    _audit("prices_refreshed", {"returncode": payload.get("returncode"), "payload": payload.get("result")})
    return jsonify({k: v for k, v in payload.items() if k != "returncode"})

_PRICE_SYMBOL_TESTS = pricing_service.PriceSymbolTestRegistry()
# Pricing diagnostics ultimately call MarketDataProvider.verbose_symbol_test and
# return live_pricing_working in the route payload. The route adapters delegate
# the trace itself to pricing_service.run_price_symbol_trace.


@app.route("/api/prices/test-symbol", methods=["POST"])
def test_price_symbol():
    denied = _require("refresh_prices")
    if denied:
        return denied
    payload, status = pricing_service.single_symbol_test_payload(request.get_json(silent=True) or {}, workspace_id=_workspace_id(), audit=_audit)
    return jsonify(payload), status


@app.route("/api/prices/test-symbol/start", methods=["POST"])
def start_price_symbol_test():
    denied = _require("refresh_prices")
    if denied:
        return denied
    payload, status = _PRICE_SYMBOL_TESTS.start_payload(request.get_json(silent=True) or {}, workspace_id=_workspace_id())
    return jsonify(payload), status


@app.route("/api/prices/test-symbol/status/<job_id>", methods=["GET"])
def price_symbol_test_status(job_id):
    denied = _require("refresh_prices")
    if denied:
        return denied
    payload, status = _PRICE_SYMBOL_TESTS.status_payload(job_id)
    return jsonify(payload), status


@app.route("/api/prices/snapshots", methods=["GET"])
def price_snapshots():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return jsonify({"success": True, "latest": pricing_service.latest_price_snapshots(workspace_id=_workspace_id(), db_path=_sqlite_db())})


@app.route("/api/prices/freeze", methods=["POST"])
def freeze_prices():
    denied = _require("refresh_prices")
    if denied:
        return denied
    payload = freeze_latest_pricing_snapshot(workspace_id=_workspace_id(), db_path=_sqlite_db())
    _audit("prices_frozen", {k: v for k, v in payload.items() if k != "symbols"})
    return jsonify(payload)


@app.route("/api/prices/unfreeze", methods=["POST"])
def unfreeze_prices():
    denied = _require("refresh_prices")
    if denied:
        return denied
    payload = unfreeze_pricing_snapshot(workspace_id=_workspace_id(), db_path=_sqlite_db())
    _audit("prices_unfrozen", payload)
    return jsonify(payload)


@app.route("/api/plan/backups", methods=["GET"])
def local_backups_status():
    denied = _require("view_dashboard")
    if denied:
        return denied
    payload = local_backup_scheduler.scheduler_status(BASE_DIR, _sqlite_db())
    return jsonify(payload)


@app.route("/api/plan/backups/config", methods=["POST"])
def local_backup_config():
    denied = _require("write_config")
    if denied:
        return denied
    payload = local_backup_scheduler.save_policy(BASE_DIR, request.get_json(silent=True) or {})
    status = local_backup_scheduler.scheduler_status(BASE_DIR, _sqlite_db())
    status.update(payload)
    _audit("local_backup_policy_saved", {"policy": status.get("policy")})
    return jsonify(status)


@app.route("/api/plan/backups/run", methods=["POST"])
def local_backup_run():
    denied = _require("write_config")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    payload = local_backup_scheduler.run_backup(
        BASE_DIR,
        _sqlite_db(),
        trigger=str(body.get("trigger") or "manual"),
        force=bool(body.get("force")),
    )
    _audit("local_backup_run", {"created": payload.get("created"), "trigger": body.get("trigger") or "manual"})
    return jsonify(payload), 200 if payload.get("success", True) else 400



@app.route("/api/portfolio/drift", methods=["GET"])
def portfolio_drift():
    denied = _require("view_dashboard")
    if denied:
        return denied
    payload = portfolio_service.drift_payload(
        base_dir=BASE_DIR,
        output_dir=_workspace_output(),
        system_config_csv=_request_system_config_csv(),
        max_build_seconds=_runtime_config().max_build_seconds,
    )
    return jsonify({k: v for k, v in payload.items() if k != "returncode"})



@app.route("/api/secrets", methods=["POST"])
def set_secret_route():
    denied = _require("manage_secrets")
    if denied:
        return denied
    payload, status = secret_service.set_secret_payload(
        request.get_json(silent=True) or {},
        workspace_id=_workspace_id(),
        db_path=_sqlite_db(),
        set_secret_fn=_set_secret_value,
    )
    if status == 200:
        _audit("secret_set", {"name": payload.get("name")})
    return jsonify(payload), status




@app.route("/api/config/backends", methods=["GET"])
def config_backends():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _config_feature_service().config_backends_payload()
    return jsonify(payload), status


@app.route("/api/config/rows", methods=["GET"])
def config_rows():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _config_feature_service().config_rows_payload()
    return jsonify(payload), status




@app.route("/api/allocation-preview", methods=["POST"])
def allocation_preview():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _config_feature_service().allocation_preview_payload(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/config/rows", methods=["POST"])
def update_config_rows():
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _config_feature_service().update_config_rows_payload(
        request.get_json(silent=True) or {},
        allow_csv_write=bool(_runtime_config().allow_csv_write),
    )
    return jsonify(payload), status







WITHDRAWAL_ORDER_TYPES = {
    "RMD": ["mandatory"],
    "HSA": ["spend_as_needed", "annual_pct", "smooth_window"],
    "IRA_elective": ["gross_up_tax", "net_amount", "skip_until_needed"],
    "Trust": ["with_buffer", "spend_first", "preserve"],
    "Roth": ["tax_free", "last_resort", "preserve_for_legacy"],
    "Home_equity_tap": ["heloc_or_downsize", "heloc", "downsize", "never"],
}

@app.route("/api/withdrawal-order", methods=["POST"])
def update_withdrawal_order():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().withdrawal_order_payload(body))

@app.route("/api/large-discretionary-expenses", methods=["GET"])
def get_large_discretionary_expenses():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().large_discretionary_payload())

@app.route("/api/large-discretionary-expenses", methods=["POST"])
def save_large_discretionary_expenses():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_large_discretionary_payload(body))

@app.route("/api/forced-roth-conversions", methods=["GET"])
def get_forced_roth_conversions():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().forced_roth_conversions_payload())

@app.route("/api/forced-roth-conversions", methods=["POST"])
def save_forced_roth_conversions():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_forced_roth_conversions_payload(body))

@app.route("/api/liquidity-buffers", methods=["GET"])
def get_liquidity_buffers():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().liquidity_buffers_payload())

@app.route("/api/liquidity-buffers", methods=["POST"])
def save_liquidity_buffers():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_liquidity_buffers_payload(body))

@app.route("/api/other-asset/add", methods=["POST"])
def add_other_asset_item():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().add_other_asset_payload(body))

@app.route("/api/other-asset/delete", methods=["POST"])
def delete_other_asset_item():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().delete_other_asset_payload(body))

@app.route("/api/education-529/add", methods=["POST"])
def add_education_529_section():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    return _service_json(_strategy_asset_feature_service().add_education_529_payload())

@app.route("/api/estate-state-options", methods=["GET"])
def estate_state_options():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().estate_state_options_payload())

@app.route("/api/estate-state/add", methods=["POST"])
def add_estate_state():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().add_estate_state_payload(body))

@app.route("/api/trust-account/add", methods=["POST"])
def add_trust_account():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().add_trust_account_payload(body))

@app.route("/api/insurance-policy/add", methods=["POST"])
def add_insurance_policy():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().add_insurance_policy_payload(body))

@app.route("/api/insurance-policy/delete", methods=["POST"])
def delete_insurance_policy():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().delete_insurance_policy_payload(body))

@app.route("/api/capital-market/assumptions", methods=["POST"])
def import_capital_market_assumptions():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().import_reference_csv_payload(file_name="capital_market_assumptions.csv", body=body, audit_event="capital_market_assumptions_imported"))

@app.route("/api/capital-market/correlations", methods=["POST"])
def import_asset_correlations():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().import_reference_csv_payload(file_name="asset_correlations.csv", body=body, audit_event="asset_correlations_imported"))

@app.route("/api/housing/seed", methods=["POST"])
def seed_housing_rows():
    denied = _require("write_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().seed_housing_payload())

@app.route("/api/wellness/seed", methods=["POST"])
def seed_wellness_oop_rows():
    denied = _require("write_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().seed_healthcare_oop_payload())

@app.route("/api/housing/state-estimate", methods=["POST"])
def housing_state_estimate():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(strategy_asset_service.housing_state_estimate_payload(request.get_json(force=True, silent=True) or {}))

@app.route("/api/config/sync", methods=["POST"])
def config_sync():
    denied = _require("write_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().config_sync_payload())

# ---------------------------------------------------------------------------
# YTD spending, income, and growth tracking
# ---------------------------------------------------------------------------

def _ytd_feature_service() -> ytd_service.YtdService:
    return ytd_service.YtdService(
        ytd_service.YtdServiceContext(
            base_dir=BASE_DIR,
            plan_data_path=_plan_data_path,
            path_roots_from_config=_path_roots_from_config,
            server_path_allowed=_server_path_allowed,
            workspace_id=_workspace_id,
            client_id=_client_id,
            sqlite_db=_sqlite_db,
            current_user_id=lambda: _current_user().user_id,
            get_client_file=get_client_file,
            set_client_file=set_client_file,
            audit=_audit,
        )
    )

def _ytd_input_root() -> Path:
    return _ytd_feature_service().input_root()

def _ytd_module():
    return ytd_service._load_ytd_module()

# Compatibility seam for older static tests/docs; implementation lives in
# src/server_services/ytd_service.py. Legacy route code used:
# _mirror_ytd_file_to_sqlite("ytd_account_setup.csv")
# get_client_file("ytd_account_setup.csv", ...)
# _recover_ytd_account_setup
# ytd_account_setup_recovered

@app.route("/api/ytd/status", methods=["GET"])
def ytd_status():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return jsonify(_ytd_feature_service().status_payload())


@app.route("/api/ytd/account-setup/recover", methods=["POST"])
def ytd_account_setup_recover():
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _ytd_feature_service().account_setup_recover_payload(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/ytd/transactions/template", methods=["GET"])
def ytd_transactions_template():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return make_response(_ytd_feature_service().transactions_template_csv(), 200, {"Content-Type": "text/csv; charset=utf-8"})


@app.route("/api/ytd/transactions/preview", methods=["POST"])
def preview_ytd_transactions_import():
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _ytd_feature_service().preview_transactions_import(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/ytd/transactions/upload", methods=["POST"])
def ytd_transactions_upload():
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _ytd_feature_service().upload_transactions(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/ytd/transactions", methods=["POST"])
def ytd_transaction_add():
    denied = _require("write_config")
    if denied:
        return denied
    return jsonify(_ytd_feature_service().add_transaction(request.get_json(silent=True) or {}))


@app.route("/api/ytd/transactions/<int:index>", methods=["PUT"])
def ytd_transaction_update(index: int):
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _ytd_feature_service().update_transaction(index, request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/ytd/transactions/<int:index>", methods=["DELETE"])
def ytd_transaction_delete(index: int):
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _ytd_feature_service().delete_transaction(index)
    return jsonify(payload), status


@app.route("/api/ytd/transactions", methods=["DELETE"])
def ytd_transactions_delete_all():
    denied = _require("write_config")
    if denied:
        return denied
    return jsonify(_ytd_feature_service().delete_all_transactions())


@app.route("/api/ytd/account-setup", methods=["POST"])
def ytd_account_setup_save():
    denied = _require("write_config")
    if denied:
        return denied
    return jsonify(_ytd_feature_service().save_account_setup(request.get_json(silent=True) or {}))


@app.route("/api/ytd/account-setup/roll-forward", methods=["POST"])
def ytd_account_setup_roll_forward():
    denied = _require("write_config")
    if denied:
        return denied
    return jsonify(_ytd_feature_service().roll_forward_account_setup())


@app.route("/api/ytd/transactions/bulk", methods=["PUT"])
def ytd_transactions_bulk_save():
    denied = _require("write_config")
    if denied:
        return denied
    return jsonify(_ytd_feature_service().bulk_save_transactions(request.get_json(silent=True) or {}))


# ---- Spending Tracker endpoints ----
# SpendingService owns taxonomy/budget/alias/model behavior; this module keeps
# only permissions, request extraction, route decorators, and JSON serialization.
def _spending_feature_service() -> spending_service.SpendingService:
    return spending_service.SpendingService(
        spending_service.SpendingServiceContext(
            base_dir=BASE_DIR,
            read_plan_data_file=_read_plan_data_file,
            audit=_audit,
        )
    )


def _json_service_result(result):
    payload, status = result
    return jsonify(payload), status


@app.route("/api/spending/dashboard", methods=["GET"])
def spending_dashboard():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().dashboard_payload())


@app.route("/api/spending/budget/seed", methods=["POST"])
def spending_budget_seed():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().seed_budget_payload())


@app.route("/api/spending/budget/load-actuals", methods=["POST"])
def spending_budget_load_actuals():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().load_actuals_payload())


@app.route("/api/spending/taxonomy", methods=["GET"])
def spending_taxonomy_get():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().taxonomy_payload())


@app.route("/api/spending/taxonomy/category", methods=["POST"])
def spending_taxonomy_category_add():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().taxonomy_category_add_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/taxonomy/category/<cat_id>", methods=["PUT"])
def spending_taxonomy_category_update(cat_id):
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().taxonomy_category_update_payload(cat_id, request.get_json(silent=True) or {}))


@app.route("/api/spending/taxonomy/category/<cat_id>", methods=["DELETE"])
def spending_taxonomy_category_delete(cat_id):
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().taxonomy_category_delete_payload(cat_id))


@app.route("/api/spending/taxonomy/group", methods=["DELETE"])
def spending_taxonomy_group_delete():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().taxonomy_group_delete_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/rules", methods=["GET"])
def spending_rules_get():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().rules_payload())


@app.route("/api/spending/rules/save", methods=["POST"])
def spending_rules_save():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().save_rules_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/budget/taxonomy", methods=["GET"])
def spending_budget_taxonomy_get():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().budget_taxonomy_payload())


@app.route("/api/spending/budget/taxonomy/save", methods=["POST"])
def spending_budget_taxonomy_save():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().save_budget_taxonomy_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/budget/recover", methods=["POST"])
def spending_budget_recover():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().recover_budget_payload())


@app.route("/api/spending/summary", methods=["GET"])
def spending_summary_taxonomy_get():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().summary_payload(request.args.get("year", type=int)))


@app.route("/api/spending/model", methods=["GET"])
def spending_model_get():
    denied = _require("view_dashboard")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().model_payload(request.args.get("year", type=int)))


@app.route("/api/spending/category", methods=["POST"])
def spending_category_create():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().category_create_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/category/<cat_id>", methods=["PUT"])
def spending_category_update_unified(cat_id):
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().category_update_payload(cat_id, request.get_json(silent=True) or {}))


@app.route("/api/spending/category/<cat_id>", methods=["DELETE"])
def spending_category_delete_unified(cat_id):
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().category_delete_payload(cat_id))


@app.route("/api/spending/category/<cat_id>/restore", methods=["POST"])
def spending_category_restore_unified(cat_id):
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().category_restore_payload(cat_id))


@app.route("/api/spending/restore-template", methods=["POST"])
def spending_restore_template_unified():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().restore_template_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/hide-unused-templates", methods=["POST"])
def spending_hide_unused_templates_unified():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().hide_unused_templates_payload())


@app.route("/api/spending/alias", methods=["POST"])
def spending_alias_add_unified():
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().alias_add_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/aliases", methods=["GET", "POST"])
def spending_aliases_unified():
    if request.method == "GET":
        denied = _require("view_dashboard")
        if denied:
            return denied
        return _json_service_result(_spending_feature_service().aliases_payload())
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().save_aliases_payload(request.get_json(silent=True) or {}))


@app.route("/api/spending/budget", methods=["GET", "POST"])
def spending_budget_unified():
    if request.method == "GET":
        denied = _require("view_dashboard")
        if denied:
            return denied
        return _json_service_result(_spending_feature_service().unified_budget_payload())
    denied = _require("write_config")
    if denied:
        return denied
    return _json_service_result(_spending_feature_service().save_unified_budget_payload(request.get_json(silent=True) or {}))

# PlanFileService owns SQLite copy semantics including wal_checkpoint(FULL),
# wal_checkpoint(TRUNCATE), not src.exists(), and before_load backups.
def _plan_file_feature_service() -> plan_file_service.PlanFileService:
    return plan_file_service.PlanFileService(
        plan_file_service.PlanFileServiceContext(
            sqlite_db=_sqlite_db,
            audit=_audit,
            retention_count=10,
            output_dir=_workspace_output,
        )
    )


@app.route("/api/plan/exit-snapshot", methods=["POST"])
def plan_exit_snapshot():
    """Create a versioned DB copy at exit time. Keeps only the last 10."""
    try:
        return jsonify(_plan_file_feature_service().exit_snapshot())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/save-as", methods=["POST"])
def plan_save_as():
    """Copy the current SQLite database to a user-chosen path (.rpx file)."""
    try:
        return jsonify(_plan_file_feature_service().save_as(request.get_json(silent=True) or {}))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/load-file", methods=["POST"])
def plan_load_file():
    """Replace the current SQLite database with a user-chosen .rpx file."""
    try:
        result = _plan_file_feature_service().load_file(request.get_json(silent=True) or {})
        if result.get("success"):
            # Materialize client files (holdings, spending, YTD, etc.) from the
            # loaded SQLite onto disk so that the disk-first read path in
            # _read_plan_data_file serves loaded-plan data, not stale old files.
            try:
                materialize_workspace_files(
                    workspace_id=_workspace_id(),
                    client_id=_client_id(),
                    db_path=_sqlite_db(),
                    file_names=[n for n in PLAN_DATA_CSV_FILES if n != "client_data.csv"] + YTD_PLAN_DATA_FILES,
                    overwrite_existing=True,
                )
            except Exception as mat_exc:
                _audit("plan_load_file_materialize_warning", {"error": str(mat_exc)})
                result["materialize_warning"] = str(mat_exc)
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/snapshot/compare", methods=["GET", "POST"])
def plan_snapshot_compare():
    denied = _require("view_dashboard")
    if denied:
        return denied
    payload, status = _plan_file_feature_service().snapshot_compare_payload(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/plan/snapshot/restore", methods=["POST"])
def plan_snapshot_restore():
    denied = _require("write_config")
    if denied:
        return denied
    payload, status = _plan_file_feature_service().snapshot_restore_payload(request.get_json(silent=True) or {})
    return jsonify(payload), status
