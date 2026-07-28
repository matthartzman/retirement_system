"""T1h (system review 2026-07-21, U3): .field-list's max-width ceiling must
be raised enough for a third auto-fit track to actually form on wide screens,
instead of being permanently capped at two tracks regardless of viewport
width. The narrow-viewport single-column fallback must be unaffected.

The track width and column gap are read out of the rule rather than pinned to
literals: the density pass narrowed the track (360px -> 300px) and the gap
(16px -> 14px) so short-value fields pack three-up sooner, which serves U3's
goal rather than undoing it. What must stay true is the relationship — the
ceiling has to leave room for three tracks plus their gaps.
"""
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


def grid_metrics(rule):
    track = re.search(r"grid-template-columns:repeat\(auto-fit,minmax\((\d+)px,1fr\)\)", rule)
    assert track, f"expected an auto-fit minmax() track definition, got: {rule}"
    gap = re.search(r"gap:0 (\d+)px", rule)
    assert gap, f"expected a `gap:0 Npx` column gap, got: {rule}"
    width = re.search(r"max-width:(\d+)px", rule)
    assert width, f"expected a pixel max-width on .field-list, got: {rule}"
    return int(track.group(1)), int(gap.group(1)), int(width.group(1))


def test_max_width_fits_three_tracks_with_gaps():
    track, gap, max_width = grid_metrics(field_list_rule(read_css()))
    required_for_three_tracks = 3 * track + 2 * gap
    assert max_width >= required_for_three_tracks, (
        f".field-list max-width ({max_width}px) is too small for a third track "
        f"at minmax({track}px,1fr) with a {gap}px gap (needs >= "
        f"{required_for_three_tracks}px)"
    )


def test_auto_fit_minmax_mechanism_unchanged():
    """The layout must still be auto-fit minmax with a zero row gap -- that is
    what lets tracks collapse and reflow instead of being a fixed count."""
    rule = field_list_rule(read_css())
    track, gap, _ = grid_metrics(rule)
    assert f"grid-template-columns:repeat(auto-fit,minmax({track}px,1fr))" in rule
    assert f"gap:0 {gap}px" in rule
    # A track narrow enough to fit four-up would make labels unreadably tight.
    assert 260 <= track <= 400, f"unexpected .field-list track width: {track}px"


def test_narrow_viewport_still_collapses_to_single_column():
    css = read_css()
    assert "@media(max-width:1180px){.field-list{grid-template-columns:1fr;max-width:none}}" in css
