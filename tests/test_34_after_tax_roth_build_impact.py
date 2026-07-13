from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_impact_has_after_tax_third_and_risk_fourth_cards():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    assert "after_tax_terminal_nw" in js
    assert "total_roth_conversions" in js
    assert "Post-Tax Inheritance" in js
    start = js.index("function buildImpactCardsHtml")
    fn = js[start: js.index("function mhBool", start)]
    assert "impact-grid-four" in fn
    return_expr = fn[fn.index("return `<div class=\"impact-grid impact-grid-four\">"):]
    assert return_expr.index("Terminal net worth") < return_expr.index("Lifetime taxes")
    assert return_expr.index("Lifetime taxes") < return_expr.index("${afterTaxCard}")
    assert return_expr.index("${afterTaxCard}") < return_expr.index("${riskCard}")


def test_plan_summary_writes_after_tax_and_roth_conversion_kpis():
    src = (ROOT / "src/reporting/workbook_builder.py").read_text(encoding="utf-8")
    assert "after_tax_terminal_nw" in src
    assert "after_tax_terminal_net_worth" in src
    assert "terminal_deferred_pretax_tax" in src
    assert "terminal_pretax_nw" in src
    assert "terminal_roth_nw" in src
    assert "total_roth_conversions" in src
    assert "sum(float(r.get('roth_conv'" in src


def test_impact_grid_supports_five_cards():
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")
    assert ".impact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr))" in css


def test_impact_card_uses_current_build_value_when_baseline_missing():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    assert "Number.isFinite(Number(delta))" in js
    assert "deltaFormatter(delta)" in js
    assert 'valueFormatter(afterVal)' in js and '"Not available"' in js
    assert "Current build" in js
    assert "impact-headline-label" in js


def test_kpi_normalizer_accepts_new_and_legacy_field_names():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    assert "function deriveAfterTaxTerminalNw" in js
    assert "summary.terminal_deferred_pretax_tax" in js
    assert "summary.after_tax_terminal_net_worth" in js
    assert "function deriveTotalRothConversions" in js
    assert "summary.roth_conversions_total" in js
    assert "summary.total_conversions" in js
