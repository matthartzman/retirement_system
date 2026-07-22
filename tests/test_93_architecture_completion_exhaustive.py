"""Despite the "exhaustive" name, this file is a MIX (system review
2026-07-21, Q1 cross-check): some tests genuinely execute code and check
real computed values (e.g. the tax-law dataset lookup, PlanConfig
immutability), while others are pure source-text substring checks with no
execution (e.g. the SSE-route / observability / money-boundary tests below
just grep for a class or string). Read each test's body before trusting it
as behavioral proof -- the file name alone doesn't tell you which kind it is.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_projection_public_project_is_thin_and_stage_module_owns_math():
    import src.planning_engines as pe
    from src.projection_stages.deterministic_engine import run_deterministic_projection_stage
    src = inspect.getsource(pe.project)
    assert "run_deterministic_projection_stage" in src
    assert len(src.splitlines()) <= 30
    stage_src = inspect.getsource(run_deterministic_projection_stage)
    assert "def _spending_factor(year):" in stage_src
    assert "create_initial_year_state" in stage_src


def test_federal_tax_constants_are_loaded_from_dated_dataset_not_embedded_tables():
    taxes = read("src/taxes.py")
    assert "FEDERAL_BRACKETS_BASE_YEAR = {" not in taxes
    assert "STANDARD_DEDUCTION_BASE_YEAR = {" not in taxes
    assert "IRMAA_TIERS_BASE_YEAR = {\n" not in taxes
    assert "LTCG_BRACKETS_BASE_YEAR = {" not in taxes
    assert "_load_federal_tax_law_tables" in taxes
    from src.tax_law import load_tax_law_dataset
    ds = load_tax_law_dataset()
    tables = ds.as_engine_tables(2025)
    assert tables["ordinary_brackets"]["MFJ"][0] == (0, 23850, 0.10)
    assert tables["irmaa_tiers"]["MFJ"][0][0] == 212000


def test_optimizer_and_monte_carlo_share_vectorized_fast_core():
    assert "vectorized_fast_core" in read("src/optimization.py")
    assert "portfolio_moments" in read("src/planning_engines.py")
    from src.vectorized_fast_core import portfolio_moments
    assert callable(portfolio_moments)


def test_async_local_build_queue_and_sse_event_routes_exist():
    routes = read("src/server/workbook_routes.py")
    assert "/api/build/events/<job_id>" in routes
    assert "text/event-stream" in routes


def test_database_backed_forms_are_first_class_runtime_routes():
    routes = read("src/server/workbook_routes.py")
    assert "/api/plan/forms" in routes
    assert "latest_sectioned_data" in routes
    assert "import_sectioned_plan" in routes
    assert '"backend": "sqlite"' in routes


def test_structured_performance_observability_is_in_result_contract():
    assert "class PerformanceEvent" in read("src/observability.py")
    assert "summarize_performance_events" in read("src/observability.py")
    result_contract = read("src/result_contract.py")
    assert "performance_observability" in result_contract


def test_money_boundaries_use_decimal_or_cents_and_execution_copy_is_explicit():
    money = read("src/money.py")
    data_io = read("src/data_io.py")
    domain = read("src/domain_models.py")
    assert "Decimal" in money and "cents_from_user_value" in money
    assert "_money_decimal" in data_io
    assert "current_value_cents" in domain
    assert "annual_core_spending_cents" in domain


def test_run_config_is_immutable_and_year_state_is_separate():
    from src.plan_config import PlanConfig
    pc = PlanConfig({"plan_start": 2026, "forced_roth": {2026: 1000}}, source="unit")
    assert isinstance(pc.values, MappingProxyType)
    try:
        pc.values["plan_start"] = 2027  # type: ignore[index]
        mutated = True
    except TypeError:
        mutated = False
    assert not mutated
    assert pc.as_engine_dict()["forced_roth"][2026] == 1000
    year_state = read("src/projection_stages/year_state.py")
    assert "class MutableYearState" in year_state
