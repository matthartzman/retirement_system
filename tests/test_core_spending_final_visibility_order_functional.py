import re
from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def _js():
    return dashboard_js_text()


def _fn_body(js: str, decl: str) -> str:
    """Slice one top-level function's text out of the assembled frontend source.

    Ends at the NEXT top-level function declaration rather than at a named
    neighbour. The old sentinel here was `function renderFields`, which broke
    the moment renderSpendingCore moved into dashboard_decomp_spending_taxonomy.js:
    the concatenation puts extracted modules after dashboard.js, so a function
    left behind in dashboard.js now sits *before* the slice start and the
    forward search finds nothing. Any neighbour-name sentinel has that same
    failure mode on the next extraction pass; this one does not.
    """
    start = js.index(decl)
    nxt = re.search(r"\n(?:export )?function ", js[start + len(decl):])
    end = start + len(decl) + nxt.start() if nxt else len(js)
    return js[start:end]


def test_core_spending_renderer_is_flat_ordered_and_excludes_daf():
    js = _js()
    body = _fn_body(js, "function renderSpendingCore()")
    assert "pc-fields" in body
    assert "renderFieldGroups(ordered)" not in body
    assert "daf_annual_contribution" not in body.split("const row1Labels =", 1)[1].split("const ordered = [];", 1)[0]
    assert "DAF contributions" in body


def test_core_spending_route_excludes_daf_annual_contribution():
    js = _js()
    # Item 174 also excludes the legacy single Core-Spending base input.
    route = 'case "spending_core":\n        return (\n          (sec === "Cashflow" &&\n            sub === "spending" &&\n            lbl !== "daf_annual_contribution" &&\n            lbl !== "annual_spending_base_year")'
    assert route in js


def test_core_spending_control_order_in_renderer():
    """Two rows: method, rate (mode-dependent), stop year / YTD override, YTD blend."""
    js = _js()
    body = _fn_body(js, "function renderSpendingCore()")
    rate = body.split("const rateLabel =", 1)[1].split(";", 1)[0]
    assert '"core_spending_manual_growth_rate"' in rate and '"inflation_general"' in rate
    row1 = body.split("const row1Labels =", 1)[1].split(";", 1)[0]
    pos = [row1.index(x) for x in ('"core_spending_growth_mode"', "rateLabel", '"spending_freeze_year"')]
    assert pos == sorted(pos)
    row2 = body.split("const row2Labels =", 1)[1].split(";", 1)[0]
    assert row2.index('"ytd_remainder_spending_override"') < row2.index('"ytd_blend_enabled"')
    # The legacy single Core-Spending base input stays out of the controls.
    assert 'norm(r.label) !== "annual_spending_base_year"' in body



