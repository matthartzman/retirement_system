from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dashboard_js() -> str:
    return (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")


def test_scenario_page_uses_canonical_home_value_and_basis_not_retired_duplicates():
    js = dashboard_js()

    assert "function rowIsCanonicalHomeValue" in js
    assert "function rowIsRetiredScenarioHomeDuplicate" in js
    assert "!rowIsRetiredScenarioHomeDuplicate(r)" in js
    assert "homeValueLabelIsCanonical(r.label)" in js
    assert "The Home Value and Home Basis shown here are shared canonical Home asset facts" in js
    assert "rowIsRetiredScenarioHomeDuplicate(r)" in js


def test_scenario_home_value_routes_to_home_sale_group_not_other_scenario_group():
    js = dashboard_js()

    assert 'const homeSale = rs.filter((r) => rowIsHomeSaleAssumption(r));' in js
    assert '!rowIsEconomyScenario(r) &&\n      !homeSale.includes(r) &&' in js


def test_money_like_scenario_labels_get_currency_formatting_even_without_units():
    js = dashboard_js()

    # Value/basis/proceeds/tax labels can come from older Plan Data without a
    # reliable schema/units match. They should still display as dollars, not
    # raw integers such as plain unformatted scenario amounts.
    assert '"basis",\n      "proceeds"' in js
    assert '"taxes",\n      "tax",\n      "exclusion"' in js
    currency_check = 'if (\n    units.includes("$") ||\n    u.includes("usd") ||\n    u.includes("dollar")'
    number_check = 'if (["year", "integer", "int", "number", "numeric"].includes(type))'
    assert currency_check in js
    assert number_check in js
    assert js.index(currency_check) < js.index(number_check)


def test_engine_reads_current_home_value_alias_used_by_ui_schema():
    source = (ROOT / "src" / "data_io.py").read_text(encoding="utf-8")

    assert "_v(data,'Other Assets','Home','value_as_of_plan_start'" in source
    assert "f'value_4_1_{TAX_BASE_YEAR}'" in source


def test_model_heard_includes_current_home_value():
    source = (ROOT / "src" / "report_compute.py").read_text(encoding="utf-8")
    js = dashboard_js()

    assert "'current_home_value': c.get('home_val', 0.0)" in source
    assert 'Current Home Value is " +\n        mhMoney(home.current_home_value)' in js
