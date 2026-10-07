from pathlib import Path


def test_plan_data_file_service_exists_and_is_runtime_independent():
    service = Path("src/server_services/plan_data_file_service.py").read_text(encoding="utf-8")
    assert "class PlanDataFileService" in service
    assert "PlanDataFileServiceContext" in service
    assert "def files_payload" in service
    assert "def start_blank_payload" in service
    assert "def get_file_payload" in service
    assert "def save_file_payload" in service
    # HTTP-runtime-independence itself is asserted once, for every service
    # module, by the AST-based check in test_service_extraction_functional.py.


def test_workbook_routes_delegate_plan_data_files_budget_lines_and_liabilities():
    routes = Path("src/server/workbook_routes.py").read_text(encoding="utf-8")
    assert "def _plan_data_file_feature_service()" in routes
    assert "PlanDataFileServiceContext" in routes
    assert ".files_payload()" in routes
    assert ".start_blank_payload(ytd_blend_enabled=ytd_blend_enabled)" in routes
    assert ".get_file_payload(file_name)" in routes
    assert ".save_file_payload(file_name" in routes
    assert "holdings_service.read_liabilities(" in routes
    assert "holdings_service.save_liabilities(" in routes
    assert ".budget_lines_payload()" in routes
    assert ".save_budget_lines_payload(" in routes
    assert ".budget_lines_defaults_payload()" in routes
    assert "def _spending_tracker_module" not in routes
    assert "def _unified_budget_lines_for_ui" not in routes
    assert "retirement_system_v10.db.before_blank" not in routes
    assert "workspace_file(\"client_liabilities.csv" not in routes


def test_spending_service_owns_budget_line_contracts(tmp_path):
    from src.server_services.spending_service import SpendingService, SpendingServiceContext

    written = {}

    def read_file(name):
        return None

    def write_file(name, content):
        written[name] = content
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    plan = {"Cashflow": {"Spending": {"annual_charitable_giving_high": "1200"}}}  # the plan's rows
    service = SpendingService(SpendingServiceContext(base_dir=tmp_path, read_plan_data_file=read_file, write_plan_data_file=write_file,
                                                     plan_data=lambda: plan))
    payload, status = service.budget_lines_defaults_payload()
    assert status == 200
    assert payload["success"] is True
    assert any(line["category_id"] == "charitable_donations" for line in payload["lines"])

    save_payload, save_status = service.save_budget_lines_payload({"lines": payload["lines"]})
    assert save_status == 200
    assert save_payload["success"] is True
    # Lines persist through the unified budget store (the plan file's spending_budget table,
    # the same one spending_tracker reads for reporting) rather than the legacy
    # budget-lines dataset, so a reload sees the saved line.
    from tests.plan_fixture import plan_dataset_rows
    budget_rows = plan_dataset_rows(tmp_path, "client_spending_budget.csv")
    assert any(r["kind"] == "line" and r["key"] == "charitable_donations" for r in budget_rows)
    reload_payload, reload_status = service.budget_lines_payload()
    assert reload_status == 200
    assert any(line["category_id"] == "charitable_donations" and line["amount_per_year"] for line in reload_payload["lines"])


def _blank_service(tmp_path, events, written, blank_calls, blank_rows=lambda **kw: 3):
    from src.server_services.plan_data_file_service import PlanDataFileService, PlanDataFileServiceContext

    db = tmp_path / "retirement_system_v10.db"
    db.write_bytes(b"sqlite placeholder")
    plan = tmp_path / "plan.rpx"
    plan.write_bytes(b"plan placeholder")

    def write(name, content):
        written[name] = content
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    def blank_plan_rows(**kwargs):
        blank_calls.append(kwargs)
        return blank_rows(**kwargs)

    return PlanDataFileService(PlanDataFileServiceContext(
        plan_data_files=["client_holdings.csv"],
        sqlite_db=lambda: db,
        plan_db=lambda: plan,
        normalize_plan_data_file_name=lambda name: name,
        read_plan_data_file=lambda name: "account,symbol\n" if name == "client_holdings.csv" else None,
        write_plan_data_file=write,
        make_blank_plan_files=lambda: {"client_holdings.csv": "account,symbol\n"},
        blank_plan_rows=blank_plan_rows,
        protected_client_data_status=lambda: {"member_1_retirement_date_present": False},
        ensure_user_ui_plan_data_rows=lambda: None,
        audit=lambda event, details=None: events.append((event, details or {})),
    ))


def test_plan_data_file_service_blank_backup_and_write_callbacks(tmp_path):
    events, written, blank_calls = [], {}, []
    service = _blank_service(tmp_path, events, written, blank_calls)

    payload, status = service.start_blank_payload()
    assert status == 200
    assert payload["success"] is True and payload["plan_values_cleared"] == 3
    assert written == {"client_holdings.csv": "account,symbol\n"}
    assert blank_calls == [{"ytd_blend_enabled": None}]
    # the plan file (the rows a blank plan clears) and the legacy database are both backed up first
    assert any(event == "blank_plan_backup" for event, _ in events)
    assert any(event == "blank_plan_plan_file_backup" for event, _ in events)
    assert list(tmp_path.glob("plan.rpx.before_blank_*")) and list(tmp_path.glob("retirement_system_v10.db.before_blank_*"))

    payload, status = service.save_file_payload("client_holdings.csv", "new")
    assert status == 200
    assert written["client_holdings.csv"] == "new"


def test_a_retired_plan_part_file_answers_410_from_both_routes_of_the_service(tmp_path):
    from src.plan_data_registry import RetiredPlanDataFile
    from src.server_services.plan_data_file_service import PlanDataFileService, PlanDataFileServiceContext

    def normalize(name):
        raise RetiredPlanDataFile("The plan data is stored in the plan file")

    service = PlanDataFileService(PlanDataFileServiceContext(
        plan_data_files=[], sqlite_db=lambda: tmp_path / "x.db", plan_db=lambda: tmp_path / "p.rpx",
        normalize_plan_data_file_name=normalize, read_plan_data_file=lambda n: None, write_plan_data_file=lambda n, c: tmp_path,
        make_blank_plan_files=lambda: {}, blank_plan_rows=lambda **kw: 0, protected_client_data_status=lambda: {},
        ensure_user_ui_plan_data_rows=lambda: None))
    assert service.get_file_payload("client_household.csv")[1] == 410
    assert service.save_file_payload("client_household.csv", "x")[1] == 410


def test_start_blank_payload_passes_the_ytd_blend_choice_to_the_plan_rows(tmp_path):
    """'Start New Plan' can carry an explicit real-actuals blend choice into the freshly blanked
    plan rows (blanking clears every value, including this flag, to an implicit-default-True blank)."""
    events, written, blank_calls = [], {}, []
    service = _blank_service(tmp_path, events, written, blank_calls)

    assert service.start_blank_payload(ytd_blend_enabled=False)[1] == 200
    assert service.start_blank_payload(ytd_blend_enabled=True)[1] == 200
    # No choice supplied (no live YTD data, prompt never fired): the blanked value is left alone;
    # the data_io.py parser defaults it to True.
    assert service.start_blank_payload(ytd_blend_enabled=None)[1] == 200
    assert blank_calls == [{"ytd_blend_enabled": False}, {"ytd_blend_enabled": True}, {"ytd_blend_enabled": None}]
    assert [e for e, _ in events if e == "blank_plan_ytd_blend_choice"] == ["blank_plan_ytd_blend_choice"] * 2
