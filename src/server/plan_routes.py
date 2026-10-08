try:
    from ..plan_data_registry import PLAN_TABLE_DATASET_FILES
    from .app_core import (
        BASE_DIR,
        PLAN_DATA_CSV_FILES,
        YTD_PLAN_DATA_FILES,
        Path,
        TRAVEL_EXTRA_TYPES,
        WORKSPACE_ROOT,
        platform_runtime,
        _audit,
        _edit_active_plan,
        _edit_active_plan_protected,
        _csv_rows_payload,
        _ensure_user_ui_plan_data_rows,
        _normalize_date_for_csv,
        _normalize_large_discretionary_type,
        _all_account_ids_from_holdings,
        _plan_data_path,
        _pre_tax_account_options_from_holdings,
        _read_active_plan,
        _read_plan_data_file,
        _read_schema_map,
        _reference_file_path,
        _request_system_config_csv,
        _require,
        _runtime_config,
        _spending_budget_save_result,
        _sqlite_db,
        _workspace_id,
        _workspace_output,
        _write_plan_data_file,
        app,
        encryption_status,
        jsonify,
        load_active_config,
        make_response,
        re,
        request,
    )
except ImportError:
    from src.plan_data_registry import PLAN_TABLE_DATASET_FILES
    from src.server.app_core import (
        BASE_DIR,
        PLAN_DATA_CSV_FILES,
        YTD_PLAN_DATA_FILES,
        Path,
        TRAVEL_EXTRA_TYPES,
        WORKSPACE_ROOT,
        platform_runtime,
        _audit,
        _edit_active_plan,
        _edit_active_plan_protected,
        _csv_rows_payload,
        _ensure_user_ui_plan_data_rows,
        _normalize_date_for_csv,
        _normalize_large_discretionary_type,
        _all_account_ids_from_holdings,
        _plan_data_path,
        _pre_tax_account_options_from_holdings,
        _read_active_plan,
        _read_plan_data_file,
        _read_schema_map,
        _reference_file_path,
        _request_system_config_csv,
        _require,
        _runtime_config,
        _spending_budget_save_result,
        _sqlite_db,
        _workspace_id,
        _workspace_output,
        _write_plan_data_file,
        app,
        encryption_status,
        jsonify,
        load_active_config,
        make_response,
        re,
        request,
    )
from ..active_plan import active_plan_path, peek_plan_data
from ..version import VERSION
from ..server_services import base_service, config_service, demo_plan_service, plan_tier_service, pricing_service, ytd_service, plan_file_service, portfolio_service, secret_service, spending_service, strategy_asset_service
from ..portfolio_analytics import freeze_latest_pricing_snapshot, unfreeze_pricing_snapshot
from .. import local_backup_scheduler
from .. import monarch_autoupdate
from ..monarch_autoimport_job import run as _run_monarch_autoimport
from ..secrets_store import set_secret as _set_secret_value



def _strategy_asset_feature_service() -> strategy_asset_service.StrategyAssetService:
    return strategy_asset_service.StrategyAssetService(
        strategy_asset_service.StrategyAssetServiceContext(
            base_dir=BASE_DIR,
            reference_file_path=_reference_file_path,
            edit_plan=_edit_active_plan,
            read_plan=_read_active_plan,
            normalize_large_discretionary_type=_normalize_large_discretionary_type,
            pre_tax_account_options_from_holdings=_pre_tax_account_options_from_holdings,
            all_account_ids_from_holdings=_all_account_ids_from_holdings,
            audit=_audit,
            travel_extra_types=TRAVEL_EXTRA_TYPES,
        )
    )


def _config_feature_service() -> config_service.ConfigService:
    return config_service.ConfigService(
        config_service.ConfigServiceContext(
            version=VERSION,
            base_dir=BASE_DIR,
            edit_plan=_edit_active_plan_protected,
            read_plan=_read_active_plan,
            csv_rows_payload=_csv_rows_payload,
            read_schema_map=_read_schema_map,
            load_active_config=load_active_config,
            runtime_config=_runtime_config,
            normalize_date_for_csv=_normalize_date_for_csv,
            audit=_audit,
        )
    )

def _plan_tier_feature_service() -> plan_tier_service.PlanTierService:
    return plan_tier_service.PlanTierService(
        plan_tier_service.PlanTierServiceContext(
            edit_plan=_edit_active_plan,
            read_plan=_read_active_plan,
            audit=_audit,
        )
    )

def _service_json(result):
    payload, status_code = result
    return jsonify(payload), status_code


def _path_roots_from_config():
    cfg = _runtime_config()
    raw = str(getattr(cfg, "local_plan_data_roots", "") or "")
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
    return roots


def _server_path_requires_allowlist():
    # System review 4.5: this package only ever ships as LOCAL (see
    # runtime_config.py), so the `app_mode != "LOCAL"` disjunct here could
    # never be true -- removed as dead code. The host check remains fully
    # live: a locally-run server whose dashboard_host is configured to
    # something other than loopback (e.g. exposed on a home LAN) still
    # requires the allowlist below.
    cfg = _runtime_config()
    host = str(getattr(cfg, "dashboard_host", "127.0.0.1") or "127.0.0.1").strip().lower()
    return host not in {"127.0.0.1", "localhost", "::1"}


def _server_path_allowed(folder: Path):
    # System review 4.5: the `app_mode == "SAAS"` early-reject here could
    # never fire for the same reason -- removed as dead code.
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
    payload = local_backup_scheduler.scheduler_status(WORKSPACE_ROOT, _sqlite_db())
    return jsonify(payload)


@app.route("/api/plan/backups/config", methods=["POST"])
def local_backup_config():
    denied = _require("write_config")
    if denied:
        return denied
    payload = local_backup_scheduler.save_policy(WORKSPACE_ROOT, request.get_json(silent=True) or {})
    status = local_backup_scheduler.scheduler_status(WORKSPACE_ROOT, _sqlite_db())
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
        WORKSPACE_ROOT,
        _sqlite_db(),
        trigger=str(body.get("trigger") or "manual"),
        force=bool(body.get("force")),
    )
    _audit("local_backup_run", {"created": payload.get("created"), "trigger": body.get("trigger") or "manual"})
    return jsonify(payload), 200 if payload.get("success", True) else 400


@app.route("/api/plan/monarch-autoupdate", methods=["GET"])
def monarch_autoupdate_status():
    denied = _require("view_dashboard")
    if denied:
        return denied
    payload = monarch_autoupdate.load_policy(WORKSPACE_ROOT)
    payload["status"] = monarch_autoupdate.load_status(WORKSPACE_ROOT)
    payload["extractor_freshness"] = monarch_autoupdate.get_extractor_freshness(WORKSPACE_ROOT)
    return jsonify(payload)


@app.route("/api/plan/monarch-autoupdate/config", methods=["POST"])
def monarch_autoupdate_config():
    denied = _require("write_config")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        payload = monarch_autoupdate.save_policy(WORKSPACE_ROOT, body)
    except monarch_autoupdate.SourceDirOutsideWorkspaceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    # Best-effort: keep the OS-level Task Scheduler entry in sync with the
    # toggle. A failure here (non-Windows dev box, no PowerShell, missing
    # privilege) does not undo the just-saved policy -- it's surfaced to the
    # UI's status chip instead.
    registration = None
    if "enabled" in body:
        registration = monarch_autoupdate.register_scheduled_task(WORKSPACE_ROOT, bool(body.get("enabled")))
    payload["task_registration"] = registration
    _audit("monarch_autoupdate_policy_saved", {"policy": payload.get("policy"), "task_registration": registration})
    return jsonify(payload)


@app.route("/api/plan/monarch-autoupdate/run", methods=["POST"])
def monarch_autoupdate_run():
    denied = _require("write_config")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    payload = _run_monarch_autoimport(WORKSPACE_ROOT, force=bool(body.get("force", True)))
    _audit("monarch_autoupdate_run", {"success": payload.get("success"), "skipped": payload.get("skipped")})
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




@app.route("/api/plan/tier", methods=["POST"])
def plan_tier():
    """WP5.1: pick the plan's tier (``{tier}``), or with ``preview: true`` only answer what
    picking it would change. A preview reads; applying writes the plan rows."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"success": False, "error": "JSON object body required"}), 400
    denied = _require("read_config" if body.get("preview") is True else "write_config")
    if denied:
        return denied
    if body.get("preview") is not True and not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    return _service_json(_plan_tier_feature_service().apply_tier_payload(body))


@app.route("/api/plan/feature", methods=["POST"])
def plan_feature():
    """WP5.1: override one feature switch (``{key, on}``) through ``module_catalog.set_feature``."""
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"success": False, "error": "JSON object body required"}), 400
    return _service_json(_plan_tier_feature_service().set_feature_payload(body))


@app.route("/api/plan/interview", methods=["GET"])
def plan_interview_questions():
    """WP5.3: the interview's questions (the one place their wording lives)."""
    denied = _require("read_config")
    if denied:
        return denied
    from ..plan_interview import questions
    return jsonify({"success": True, "questions": questions()})


@app.route("/api/plan/interview", methods=["POST"])
def plan_interview():
    """WP5.3: ``{answers, apply?}`` -> the tier and switches the answers suggest; ``apply: true``
    writes them (tier preset plus extras) in one edit."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"success": False, "error": "JSON object body required"}), 400
    denied = _require("write_config" if body.get("apply") is True else "read_config")
    if denied:
        return denied
    if body.get("apply") is True and not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    return _service_json(_plan_tier_feature_service().interview_payload(body))


@app.route("/api/allocation-preview", methods=["POST"])
def allocation_preview():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _config_feature_service().allocation_preview_payload(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/daf/recommendation", methods=["POST"])
def daf_recommendation():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _config_feature_service().daf_recommendation_payload(request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/qlac/recommendation", methods=["POST"])
def qlac_recommendation():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _config_feature_service().qlac_recommendation_payload(request.get_json(silent=True) or {})
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

@app.route("/api/spending-adjustments", methods=["GET"])
def get_spending_adjustments():
    """#335: Spending Model Adjustments table (Cashflow / Spending Adjustments)."""
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().spending_adjustments_payload())

@app.route("/api/spending-adjustments", methods=["POST"])
def save_spending_adjustments():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_spending_adjustments_payload(body))

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

@app.route("/api/home-sale-splits", methods=["GET"])
def get_home_sale_splits():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().home_sale_splits_payload())

@app.route("/api/home-sale-splits", methods=["POST"])
def save_home_sale_splits():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_home_sale_splits_payload(body))

@app.route("/api/tax-assumptions", methods=["GET"])
def get_tax_assumptions():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().tax_assumptions_payload())

@app.route("/api/tax-assumptions", methods=["POST"])
def save_tax_assumptions():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_tax_assumptions_payload(body))

@app.route("/api/residency-schedule", methods=["GET"])
def get_residency_schedule():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().residency_schedule_payload())

@app.route("/api/residency-schedule", methods=["POST"])
def save_residency_schedule():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_residency_schedule_payload(body))

@app.route("/api/withdrawal-account-order", methods=["GET"])
def get_withdrawal_account_order():
    denied = _require("read_config")
    if denied:
        return denied
    return _service_json(_strategy_asset_feature_service().withdrawal_account_order_payload())

@app.route("/api/withdrawal-account-order", methods=["POST"])
def save_withdrawal_account_order():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_withdrawal_account_order_payload(body))

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

@app.route("/api/note-receivable/add", methods=["POST"])
def add_note_receivable():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().add_note_receivable_payload(body))

@app.route("/api/note-receivable/delete", methods=["POST"])
def delete_note_receivable():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().delete_note_receivable_payload(body))

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

@app.route("/api/life-illustration/seed", methods=["POST"])
def add_life_illustration():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().add_life_illustration_payload(body))

def _save_override_rows(kind: str, audit_event: str):
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _service_json(_strategy_asset_feature_service().save_override_rows_payload(kind=kind, body=body, audit_event=audit_event))


# Plan-side override tables over the read-only reference data (plan_overrides; plan_rows sections).
@app.route("/api/capital-market/assumptions", methods=["POST"])
def import_capital_market_assumptions():
    return _save_override_rows("capital_market", "capital_market_assumptions_saved")

@app.route("/api/capital-market/correlations", methods=["POST"])
def import_asset_correlations():
    return _save_override_rows("correlations", "asset_correlations_saved")

@app.route("/api/capital-market/real-loss-curves", methods=["POST"])
def save_real_loss_curves():
    return _save_override_rows("real_loss", "real_loss_curves_saved")

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

# #330 §3.2, "Housing \"Where to live\"": off means "the UI panel is hidden;
# `src/housing/` is not invoked". Hiding the panel is half of that and it is
# the half a direct POST walks straight past, so the gate lives here too --
# these two routes are the only server-side entry into the location search.
#
# Deliberately NOT applied to `/api/housing/zip-lookup`, `/api/housing/
# top-cities`, `/api/housing/state-estimate` or `/api/housing/seed`: those are
# reference/estimate helpers the ALWAYS-ON "Home & Housing" input page calls
# (see dashboard_decomp_housing_scenarios.js), so gating them would take plan
# input away from a page this switch does not own. #330 §3.2 names the two
# search endpoints, and they are the two that run a search.
#
# The check reads the ACTIVE plan's toggles, the same `c` every other
# `module_enabled` call site reads, which is why it comes after the config
# load -- there is no toggle state before one. The search package is imported
# only once the gate passes, so an off module costs no import either.
def _housing_search_config_or_disabled():
    """``(c0, None)`` when the location search may run, ``(None, response)``
    when its module is off."""
    from ..module_catalog import module_enabled
    from ..report_compute import prepare_config_from_sectioned_data
    data, _meta = load_active_config()
    c0 = prepare_config_from_sectioned_data(data, "", optimize_roth=False)
    if not module_enabled(c0, "housing_location_search"):
        return None, (jsonify({
            "success": False,
            "error": ("Next Housing Move is turned off for this plan. "
                      "Enable it on Plan Features to run a location search."),
            "module": "housing_location_search",
        }), 403)
    return c0, None

@app.route("/api/housing/optimize", methods=["POST"])
def housing_optimize():
    denied = _require("read_config")
    if denied:
        return denied
    c0, disabled = _housing_search_config_or_disabled()
    if disabled:
        return disabled
    from ..housing import optimize_housing_from_request
    return _service_json(optimize_housing_from_request(c0, request.get_json(force=True, silent=True) or {}))

@app.route("/api/housing/zip-screen", methods=["POST"])
def housing_zip_screen():
    denied = _require("read_config")
    if denied:
        return denied
    c0, disabled = _housing_search_config_or_disabled()
    if disabled:
        return disabled
    from ..housing import zip_screen_from_request
    return _service_json(zip_screen_from_request(c0, request.get_json(force=True, silent=True) or {}))

@app.route("/api/housing/top-cities", methods=["GET"])
def housing_top_cities():
    denied = _require("read_config")
    if denied:
        return denied
    from ..housing import top_cities_payload
    return _service_json(top_cities_payload())

@app.route("/api/housing/zip-lookup", methods=["GET"])
def housing_zip_lookup():
    denied = _require("read_config")
    if denied:
        return denied
    from ..housing import zip_lookup
    return _service_json(zip_lookup(request.args.get("zip", "")))

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
    period = request.args.get("period")
    return jsonify(_ytd_feature_service().status_payload(period=period))


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
    # The spending service's root is the WORKSPACE (where the active plan and the YTD files live),
    # read fresh per request; BASE_DIR is the code folder, which in a frozen build is not it.
    return spending_service.SpendingService(
        spending_service.SpendingServiceContext(
            base_dir=platform_runtime.workspace_root(),
            read_plan_data_file=_read_plan_data_file,
            plan_data=peek_plan_data,
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
    body = request.get_json(silent=True) or {}
    return _spending_budget_save_result(lambda: _spending_feature_service().save_budget_taxonomy_payload(body))


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
    body = request.get_json(silent=True) or {}
    return _spending_budget_save_result(lambda: _spending_feature_service().save_unified_budget_payload(body))

# PlanFileService owns the plan file's copy/replace/backup semantics (wal_checkpoint, validated
# atomic replace, before_load backups); WP4.5: Save As / Load / snapshot restore / the demo swap
# operate on the plan file itself, with no CSV step.
def _migrate_after_db_replace(plan_path):
    from ..plan_data_migration import migrate_plan_file

    return migrate_plan_file(plan_path)


def _plan_file_feature_service() -> plan_file_service.PlanFileService:
    return plan_file_service.PlanFileService(
        plan_file_service.PlanFileServiceContext(
            sqlite_db=_sqlite_db,
            plan_db=active_plan_path,
            audit=_audit,
            retention_count=10,
            output_dir=_workspace_output,
            migrate=_migrate_after_db_replace,
        )
    )


@app.route("/api/plan/exit-snapshot", methods=["POST"])
def plan_exit_snapshot():
    """Create a versioned copy of the plan file and the local database at exit time. Keeps only the last 10 of each."""
    try:
        return jsonify(_plan_file_feature_service().exit_snapshot())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/save-as", methods=["POST"])
def plan_save_as():
    """Copy the current plan file to a user-chosen path (.rpx file)."""
    try:
        return jsonify(_plan_file_feature_service().save_as(request.get_json(silent=True) or {}))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/load-file", methods=["POST"])
def plan_load_file():
    """Replace the current plan file with a user-chosen .rpx plan file."""
    try:
        return jsonify(_plan_file_feature_service().load_file(request.get_json(silent=True) or {}))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


# DemoPlanService owns Open Demo Plan / Open Current Plan swap semantics (#240): it swaps the
# plan file (the demo household is built from input/demo through the csv_exchange importer, or
# taken from the demo slot). Every flat dataset, the YTD tables included (WP6.4), is a table of the
# plan file, so it is swapped to the demo fixture on open and back to the real plan on restore with
# the plan file itself (#248).
def _demo_plan_feature_service() -> demo_plan_service.DemoPlanService:
    # The datasets in the plan file's tables travel with the plan file swap, not as files.
    _FILE_BACKED_PLAN_DATA_FILES = [f for f in PLAN_DATA_CSV_FILES + YTD_PLAN_DATA_FILES if f not in PLAN_TABLE_DATASET_FILES]  # none left

    return demo_plan_service.DemoPlanService(
        demo_plan_service.DemoPlanServiceContext(
            sqlite_db=_sqlite_db,
            plan_db=active_plan_path,
            demo_dir=lambda: WORKSPACE_ROOT / "input" / "demo",
            plan_data_csv_files=_FILE_BACKED_PLAN_DATA_FILES,
            read_plan_data_file=_read_plan_data_file,
            write_plan_data_file=_write_plan_data_file,
            ensure_user_ui_plan_data_rows=_ensure_user_ui_plan_data_rows,
            materialize=lambda: None,  # every flat dataset is a table of the plan file: nothing to restore as a file
            audit=_audit,
            migrate=_migrate_after_db_replace,
        )
    )


@app.route("/api/plan/demo-status", methods=["GET"])
def plan_demo_status():
    """Whether Open Demo Plan is currently active (a real-plan backup exists)."""
    denied = _require("read_config")
    if denied:
        return denied
    try:
        return jsonify(_demo_plan_feature_service().status_payload())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/open-demo", methods=["POST"])
def plan_open_demo():
    """Swap in the fictional input/demo/*.csv household, backing up the real plan first."""
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    try:
        return jsonify(_demo_plan_feature_service().open_demo_payload())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/restore-current", methods=["POST"])
def plan_restore_current():
    """Restore the real plan backed up by Open Demo Plan, if one is active."""
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    try:
        return jsonify(_demo_plan_feature_service().restore_current_payload())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})


@app.route("/api/plan/reset-demo", methods=["POST"])
def plan_reset_demo():
    """Delete the persistent demo slot so the next Open Demo Plan re-seeds
    from the shipped input/demo/ fixtures. Refused while a demo is open."""
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    try:
        payload = _demo_plan_feature_service().reset_demo_payload()
        return jsonify(payload), (200 if payload.get("success") else 400)
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
