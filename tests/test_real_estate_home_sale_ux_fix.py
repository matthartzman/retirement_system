from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_backend import import_csv_to_sqlite
from src.local_store import latest_sectioned_data
from src.report_compute import build_model_heard_assumptions


def test_scenario_ui_separates_base_home_sale_from_stress_only_rows():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")

    assert "function rowIsBaseHomeSaleInput" in js
    assert "function rowIsStressSellHomeInput" in js


def test_retired_scenario_home_basis_cannot_reappear_as_editable_scenario_input():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")

    assert "function rowIsRetiredScenarioHomeDuplicate" in js
    assert "function isEditable(r){return r&&!r.is_header&&!r.is_comment&&r.label&&!rowIsRetiredScenarioHomeDuplicate(r)}" in js
    assert "The Home Value and Home Basis shown here are shared canonical Home asset facts" in js


def test_model_heard_reports_property_tax_and_home_sale_sources():
    heard = build_model_heard_assumptions({
        "plan_start": 2026,
        "plan_end": 2056,
        "real_estate_tax_base": 17_000,
        "real_estate_tax_growth_rate": 0.025,
        "home_sale_yr": 2040,
        "home_sale_px": 0,
        "home_val": 1_000_000,
        "home_basis": 1_000_000,
        "scen_sell_yr": 2040,
        "scen_sell_basis": 1_000_000,
        "scen_sell_basis_source": "Other Assets/Home/home_basis",
    }, [])

    home = heard["home_and_property_tax"]
    assert home["annual_real_estate_taxes_today"] == 17_000
    assert home["current_home_value"] == 1_000_000
    assert home["base_home_sale_year"] == 2040
    assert home["canonical_home_basis"] == 1_000_000
    assert home["sell_home_stress_basis_source"] == "Other Assets/Home/home_basis"


def test_split_plan_data_sync_preserves_canonical_home_basis_and_re_tax(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "client_data.csv").write_text("section,subsection,label,value,units,notes\n", encoding="utf-8")
    (input_dir / "client_spending.csv").write_text(
        "section,subsection,label,value,units,notes\n"
        "Cashflow,Mortgage,annual_real_estate_taxes,\"$17,000\",USD,\n",
        encoding="utf-8",
    )
    retired_duplicate = ",".join(["Scenarios", "Sell Home", "home_basis", "\"$790,000\"", "USD", "retired duplicate"])
    (input_dir / "client_assets.csv").write_text(
        "section,subsection,label,value,units,notes\n"
        "Other Assets,Home,home_basis,\"$1,000,000\",USD,\n"
        "Other Assets,Home,home_sale_year,2040,year,\n"
        f"{retired_duplicate}\n",
        encoding="utf-8",
    )
    db = tmp_path / "store.db"
    import_csv_to_sqlite(input_dir / "client_data.csv", db)
    sectioned = latest_sectioned_data(db)

    assert sectioned["Cashflow"]["Mortgage"]["annual_real_estate_taxes"] == "$17,000"
    assert sectioned["Other Assets"]["Home"]["home_basis"] == "$1,000,000"
    assert sectioned["Other Assets"]["Home"]["home_sale_year"] == "2040"
    assert "home_basis" not in sectioned.get("Scenarios", {}).get("Sell Home", {})
