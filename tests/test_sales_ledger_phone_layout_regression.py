"""Sales Ledger page at phone width: its panels sit in a ``.field-list`` grid whose single column must be allowed to
shrink (``min-width: 0``), otherwise the wide queue / 1099-B tables push the panels past the card and clip on a phone
(seen in a real browser at 390px: the bulk-review panel measured 508px inside a 344px page)."""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "frontend" / "css" / "dashboard.css"


def test_field_list_children_may_shrink_below_their_content_width():
    rule = re.search(r"\.field-list>\*\{([^}]*)\}", CSS.read_text(encoding="utf-8"))
    assert rule, ".field-list>* rule missing"
    assert "min-width:0" in rule.group(1).replace(" ", "")


# --- Task 16b: layout rules introduced by the redesign must not force horizontal overflow ---
JS = CSS.parents[1] / "js"

def _css_text() -> str:
    return CSS.read_text(encoding="utf-8")


def _top_level_rules(css: str) -> list[tuple[str, str]]:
    """(selector, body) for rules outside any @media block; @media bodies are skipped (min-width allowed there)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, depth, buf, sel, media = [], 0, "", "", 0
    for ch in css:
        if ch == "{":
            depth += 1
            if depth == 1 and buf.strip().startswith("@"):
                media = 1
            elif depth == 1:
                sel = buf.strip()
            buf = ""
        elif ch == "}":
            if depth == 1 and not media:
                out.append((sel, buf))
            if depth == 1:
                media = 0
            depth -= 1
            buf = ""
        else:
            buf += ch
    return out


def test_sl_rules_have_no_fixed_pixel_widths():
    rules = [(s, b) for s, b in _top_level_rules(_css_text()) if any(p.strip().startswith(".sl-") for p in s.split(","))]
    assert rules, "no .sl-* rules found"
    bad = []
    for sel, body in rules:
        for prop, px in re.findall(r"(?<![-\w])((?:min-)?width)\s*:\s*(\d+(?:\.\d+)?)px", body):
            if float(px) > 24:  # <=24px: badge/marker minimums, not layout
                bad.append((sel, f"{prop}:{px}px"))
    assert not bad, f"fixed pixel width in a top-level .sl-* rule: {bad}"


def test_sl_tab_hidden_wins_over_display_rules():
    assert re.search(r"\.sl-tab\[hidden\]\s*\{\s*display:\s*none\s*!important", _css_text())


def test_chevron_transition_is_guarded_by_reduced_motion():
    css = _css_text()
    assert re.search(r"\.sl-sec-chev\{[^}]*transition:\s*transform", css), "chevron transition rule missing"
    m = re.search(r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{([^@]*?\.sl-sec-chev\{[^}]*transition:\s*none)", css)
    assert m, "reduced-motion media block must turn off the .sl-sec-chev transition"


def test_density_control_is_hidden_on_coarse_pointers():
    css = _css_text()
    assert re.search(r"@media \(pointer:coarse\)\s*\{[^}]*\.sl-density\{[^}]*display:\s*none", css)
    assert re.search(r"\.sl-page\.sl-compact\s*\{\s*--sl-row:\s*24px", css)


def test_tax_grid_stays_single_column_until_wide():
    css = _css_text()
    assert re.search(r"\.sl-tax-cols\{[^}]*grid-template-columns:\s*1fr\s*[;}]", css)
    assert re.search(r"@media \(min-width:1100px\)\{\.sl-tax-cols\{grid-template-columns:minmax\(0,", css)


def test_every_table_in_the_sales_ledger_panels_scrolls_inside_a_wrapper():
    for name in ("dashboard_decomp_cash_investment.js", "dashboard_decomp_broker_import.js"):
        text = (JS / name).read_text(encoding="utf-8")
        opens = text.count("<table")
        assert opens, name
        assert text.count('<div class="rc-scroll"><table') == opens, f"{name}: an unwrapped <table> would clip on a phone"
