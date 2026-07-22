"""Progress overlay simplification: title + elapsed time + progress bar only.

Covers the request to drop per-phase "detail" copy and the "please wait"
suffix from the shared build/loading overlay, and to reuse that overlay for
the initial plan load (previously silent for most of its multi-step sequence).
"""
from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"


def test_please_wait_suffix_removed_from_css():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    assert "please wait" not in css.lower()


def test_overlay_detail_line_shows_only_elapsed_time():
    text = dashboard_js_text()
    assert "Elapsed ${formatElapsed(Date.now() - buildOverlayStartedAt)}" in text
    # The old per-phase copy translator and static duration estimate are gone
    # entirely, not just unused -- the detail line no longer has anything to
    # feed it.
    for token in [
        "friendlyBuildDetail",
        "estimateBuildDurationLabel",
        "buildOverlayExpectedLabel",
        "buildOverlayLastDetail",
        "overlayTimerSuffix",
    ]:
        assert token not in text


def test_overlay_supports_reentrant_show_hide_for_nested_load_steps():
    text = dashboard_js_text()
    assert "buildOverlayDepth++" in text
    assert "if (buildOverlayDepth > 0) buildOverlayDepth--;" in text
    assert "if (buildOverlayDepth > 0) return;" in text


def test_initial_plan_load_uses_the_overlay():
    text = dashboard_js_text()
    idx = text.index("async function loadAll(opts = {}) {")
    body = text[idx : idx + 4000]
    assert 'setBuildOverlay(true, "Loading plan", "", "waiting");' in body
    assert "finally {\n    hideBuildOverlay();\n  }" in body
