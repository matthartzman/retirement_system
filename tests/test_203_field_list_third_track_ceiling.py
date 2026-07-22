"""T1h (system review 2026-07-21, U3): .field-list's max-width ceiling must
be raised enough for a third auto-fit track (minmax(360px,1fr) x3 + 2 column
gaps) to actually form on wide screens, instead of being permanently capped
at two tracks regardless of viewport width. The narrow-viewport single-column
fallback must be unaffected."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_css():
    return (ROOT / "frontend" / "css" / "dashboard.css").read_text(encoding="utf-8")


def field_list_rule(css):
    # dashboard.css has more than one `.field-list{...}` rule (e.g. a
    # padding-only override); anchor on the grid-defining one specifically.
    match = re.search(r"\.field-list\{(display:grid[^}]*)\}", css)
    assert match, "expected the grid-defining .field-list{display:grid...} rule in dashboard.css"
    return match.group(1)


def test_max_width_fits_three_360px_tracks_with_gaps():
    rule = field_list_rule(read_css())
    m = re.search(r"max-width:(\d+)px", rule)
    assert m, f"expected a pixel max-width on .field-list, got: {rule}"
    max_width = int(m.group(1))
    # repeat(auto-fit, minmax(360px,1fr)) with a 16px column gap needs
    # 3*360 + 2*16 = 1112px to actually lay out three tracks side by side.
    required_for_three_tracks = 3 * 360 + 2 * 16
    assert max_width >= required_for_three_tracks, (
        f".field-list max-width ({max_width}px) is too small for a third "
        f"track (needs >= {required_for_three_tracks}px)"
    )


def test_auto_fit_minmax_mechanism_unchanged():
    rule = field_list_rule(read_css())
    assert "grid-template-columns:repeat(auto-fit,minmax(360px,1fr))" in rule
    assert "gap:0 16px" in rule


def test_narrow_viewport_still_collapses_to_single_column():
    css = read_css()
    assert "@media(max-width:1180px){.field-list{grid-template-columns:1fr;max-width:none}}" in css
