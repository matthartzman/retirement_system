from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_impact_has_terminal_nw_first_lifetime_tax_second_risk_third_cards():
    # #225: Post-Tax Inheritance is no longer its own headline card here --
    # PTI is computed at a different point in time on Estate & Legacy Plan
    # (second-death year) than a terminal-plan-year Impact comparison would
    # use, so showing both as equivalent headline figures read as a bug.
    # Impact now only notes the estate-tax bite on the Terminal Net Worth
    # card (and only when nonzero), pointing to Estate & Legacy Plan for the
    # authoritative PTI figure.
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    js += (ROOT / 'frontend/js/dashboard_decomp_build_history.js').read_text(encoding='utf-8')
    assert "after_tax_terminal_nw" in js
    assert "total_roth_conversions" in js
    assert "post_tax_inheritance" in js
    start = js.index("function buildImpactCardsHtml")
    fn = js[start: js.index("function mhBool", start)]
    assert "impact-grid" in fn
    assert '"Post-Tax Inheritance (PTI)"' not in fn
    assert "estateTaxNote" in fn
    return_expr = fn[fn.index("return `<div class=\"impact-grid\">"):]
    assert return_expr.index("${nwCard}") < return_expr.index("Lifetime taxes")
    assert return_expr.index("Lifetime taxes") < return_expr.index("${riskCard}")


def test_impact_card_help_shows_as_info_icon_not_inline_text():
    # #240 follow-up: card help text used to sit inline under the After
    # value; it now surfaces via an "i" info icon next to the headline
    # (reusing the field-info-i tooltip pattern) so the card body stays to
    # headline + Before/After only.
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    js += (ROOT / 'frontend/js/dashboard_decomp_build_history.js').read_text(encoding='utf-8')
    start = js.index("function impactCardHtml")
    fn = js[start: js.index("function buildImpactCardsHtml", start)]
    assert "field-info-i" in fn
    assert '<div class="small">${esc(help)}</div>' not in fn


def test_impact_notes_render_below_the_grid_not_as_a_phantom_card():
    # estateTaxNote/noRuinNote used to be concatenated onto a card's HTML,
    # which made each render as its own extra grid box. They now collect
    # into a single .impact-notes block below the 3-card grid.
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    js += (ROOT / 'frontend/js/dashboard_decomp_build_history.js').read_text(encoding='utf-8')
    start = js.index("function buildImpactCardsHtml")
    fn = js[start: js.index("function mhBool", start)]
    assert "impact-notes" in fn
    assert ") + noRuinNote" not in fn
    assert ") + estateTaxNote" not in fn


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
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    js += (ROOT / 'frontend/js/dashboard_decomp_build_history.js').read_text(encoding='utf-8')
    assert "Number.isFinite(Number(delta))" in js
    assert "deltaFormatter(delta)" in js
    assert 'valueFormatter(afterVal)' in js and '"Not available"' in js
    assert "Current build" in js
    assert "impact-headline-label" in js


def test_kpi_normalizer_accepts_new_and_legacy_field_names():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert "function deriveAfterTaxTerminalNw" in js
    assert "summary.terminal_deferred_pretax_tax" in js
    assert "summary.after_tax_terminal_net_worth" in js
    assert "function deriveTotalRothConversions" in js
    assert "summary.roth_conversions_total" in js
    assert "summary.total_conversions" in js
