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
    # module, by the AST-based check in test_126_service_extraction.py.


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
        if name == "client_spending.csv":
            return "section,subsection,label,value\nCashflow,Spending,annual_charitable_giving_high,1200\n"
        return None

    def write_file(name, content):
        written[name] = content
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    service = SpendingService(SpendingServiceContext(base_dir=tmp_path, read_plan_data_file=read_file, write_plan_data_file=write_file))
    payload, status = service.budget_lines_defaults_payload()
    assert status == 200
    assert payload["success"] is True
    assert any(line["category_id"] == "charitable_donations" for line in payload["lines"])

    save_payload, save_status = service.save_budget_lines_payload({"lines": payload["lines"]})
    assert save_status == 200
    assert save_payload["success"] is True
    # Lines persist through the unified budget store (client_spending_budget.csv,
    # the same file spending_tracker reads for reporting) rather than the legacy
    # client_spending_budget_lines.csv file, so a reload sees the saved line.
    budget_csv = tmp_path / "input" / "client_spending_budget.csv"
    assert budget_csv.exists()
    assert "charitable_donations" in budget_csv.read_text(encoding="utf-8")
    reload_payload, reload_status = service.budget_lines_payload()
    assert reload_status == 200
    assert any(line["category_id"] == "charitable_donations" and line["amount_per_year"] for line in reload_payload["lines"])


def test_plan_data_file_service_blank_backup_and_write_callbacks(tmp_path):
    from src.server_services.plan_data_file_service import PlanDataFileService, PlanDataFileServiceContext

    db = tmp_path / "retirement_system_v10.db"
    db.write_bytes(b"sqlite placeholder")
    events = []
    blank_written = {}
    normal_written = {}

    def write_normal(name, content):
        normal_written[name] = content
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    def write_blank(name, content):
        blank_written[name] = content
        path = tmp_path / f"blank_{name}"
        path.write_text(content, encoding="utf-8")
        return path

    service = PlanDataFileService(PlanDataFileServiceContext(
        plan_data_files=["client_data.csv"],
        client_data_csv_file_set={"client_data.csv"},
        sqlite_db=lambda: db,
        normalize_plan_data_file_name=lambda name: name,
        read_plan_data_file=lambda name: "section,subsection,label,value\n" if name == "client_data.csv" else None,
        write_plan_data_file=write_normal,
        write_blank_plan_data_file=write_blank,
        make_blank_plan_files=lambda: {"client_data.csv": "section,subsection,label,value\n"},
        protected_client_data_status=lambda: {"husband_retirement_date_present": False},
        ensure_user_ui_plan_data_rows=lambda: None,
        sync_config_backends=lambda: {"success": True},
        audit=lambda event, details=None: events.append((event, details or {})),
    ))
    payload, status = service.start_blank_payload()
    assert status == 200
    assert payload["success"] is True
    assert "client_data.csv" in blank_written
    assert not normal_written
    assert any(event == "blank_plan_backup" for event, _ in events)

    payload, status = service.save_file_payload("client_data.csv", "new")
    assert status == 200
    assert normal_written["client_data.csv"] == "new"


def test_start_blank_payload_stamps_ytd_blend_choice_onto_spending_csv(tmp_path):
    """Finding A fix: 'Start New Plan' can carry an explicit real-actuals
    blend choice through to the freshly blanked client_spending.csv, since
    the normal blank-template blanking pass clears every value column
    (including this flag) to an implicit-default-True blank."""
    from src.server_services.plan_data_file_service import PlanDataFileService, PlanDataFileServiceContext

    db = tmp_path / "retirement_system_v10.db"
    db.write_bytes(b"sqlite placeholder")
    blank_written = {}

    def write_blank(name, content):
        blank_written[name] = content
        return tmp_path / f"blank_{name}"

    blank_spending_csv = (
        "section,subsection,label,value,units,notes\n"
        "Cashflow,Spending,annual_spending_base_year,,,\n"
        "Cashflow,Spending,ytd_blend_enabled,,,\n"
    )

    service = PlanDataFileService(PlanDataFileServiceContext(
        plan_data_files=["client_data.csv", "client_spending.csv"],
        client_data_csv_file_set={"client_data.csv", "client_spending.csv"},
        sqlite_db=lambda: db,
        normalize_plan_data_file_name=lambda name: name,
        read_plan_data_file=lambda name: None,
        write_plan_data_file=lambda name, content: tmp_path / name,
        write_blank_plan_data_file=write_blank,
        make_blank_plan_files=lambda: {"client_data.csv": "section,subsection,label,value\n", "client_spending.csv": blank_spending_csv},
        protected_client_data_status=lambda: {"husband_retirement_date_present": False},
        ensure_user_ui_plan_data_rows=lambda: None,
        sync_config_backends=lambda: {"success": True},
        audit=lambda event, details=None: None,
    ))

    payload, status = service.start_blank_payload(ytd_blend_enabled=False)
    assert status == 200
    assert "Cashflow,Spending,ytd_blend_enabled,FALSE" in blank_written["client_spending.csv"]

    payload, status = service.start_blank_payload(ytd_blend_enabled=True)
    assert status == 200
    assert "Cashflow,Spending,ytd_blend_enabled,TRUE" in blank_written["client_spending.csv"]

    # No choice supplied (no live YTD data, prompt never fired) - leave the
    # blanked value alone; the data_io.py parser defaults it to True.
    payload, status = service.start_blank_payload(ytd_blend_enabled=None)
    assert status == 200
    assert blank_written["client_spending.csv"] == blank_spending_csv
