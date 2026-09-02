from pathlib import Path

from _decomp_dashboard import dashboard_function_source, dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_build_impact_has_lcv_first_npv_tax_second_worst_case_third_eftr_fourth_cards():
    # #225: Post-Tax Inheritance is no longer its own headline card here --
    # PTI is computed at a different point in time on Estate & Legacy Plan
    # (second-death year) than a terminal-plan-year Impact comparison would
    # use, so showing both as equivalent headline figures read as a bug.
    # Impact now only notes the estate-tax bite baked into the LCV card (and
    # only when nonzero), pointing to Estate & Legacy Plan for the
    # authoritative PTI figure.
    # #293: the headline cards were converted from Terminal Net Worth /
    # Lifetime Taxes / Probability of Success to Expected After-Tax LCV /
    # NPV of Future Taxes / Worst-Case Ending Wealth (5th %ile), plus a new
    # 4th Effective Future Tax Rate (EFTR) card.
    js = dashboard_js_text()
    assert "after_tax_terminal_nw" in js
    assert "total_roth_conversions" in js
    assert "post_tax_inheritance" in js
    fn = dashboard_function_source("buildImpactCardsHtml", js)
    assert "impact-grid" in fn
    assert '"Post-Tax Inheritance (PTI)"' not in fn
    assert "estateTaxNote" in fn
    return_expr = fn[fn.index("return `<div class=\"impact-grid\">"):]
    assert (
        return_expr.index("${lcvCard}")
        < return_expr.index("NPV of Future Taxes")
        < return_expr.index("${worstCaseCard}")
        < return_expr.index("${eftrCard}")
    )


def test_impact_card_help_shows_as_info_icon_not_inline_text():
    # #240 follow-up: card help text used to sit inline under the After
    # value; it now surfaces via an "i" info icon next to the headline
    # (reusing the field-info-i tooltip pattern) so the card body stays to
    # headline + Before/After only.
    js = dashboard_js_text()
    start = js.index("function impactCardHtml")
    fn = js[start: js.index("function buildImpactCardsHtml", start)]
    assert "field-info-i" in fn
    assert '<div class="small">${esc(help)}</div>' not in fn


def test_impact_notes_render_below_the_grid_not_as_a_phantom_card():
    # estateTaxNote/noRuinNote used to be concatenated onto a card's HTML,
    # which made each render as its own extra grid box. They now collect
    # into a single .impact-notes block below the 3-card grid.
    js = dashboard_js_text()
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
    # #309: minmax narrowed from 185px to 160px (plus a tighter gap) so the
    # 4 current cards fit one row without wrapping their longer new titles
    # ("NPV of Future Taxes", "Effective Future Tax Rate (EFTR)") -- the
    # auto-fit grid mechanism this test guards is unchanged, just the pinned
    # width.
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")
    assert ".impact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr))" in css


def test_impact_card_uses_current_build_value_when_baseline_missing():
    js = dashboard_js_text()
    assert "Number.isFinite(Number(delta))" in js
    assert "deltaFormatter(delta)" in js
    assert 'valueFormatter(afterVal)' in js and '"Not available"' in js
    assert "Current build" in js
    assert "impact-headline-label" in js


def test_kpi_normalizer_accepts_new_and_legacy_field_names():
    js = dashboard_js_text()
    assert "function deriveAfterTaxTerminalNw" in js
    assert "summary.terminal_deferred_pretax_tax" in js
    assert "summary.after_tax_terminal_net_worth" in js
    assert "function deriveTotalRothConversions" in js
    assert "summary.roth_conversions_total" in js
    assert "summary.total_conversions" in js
