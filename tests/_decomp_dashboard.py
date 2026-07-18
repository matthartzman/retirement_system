"""Shared helper for the dashboard.js decomposition.

Cohesive UI blocks are being moved out of the monolithic frontend/js/dashboard.js
into sibling classic scripts named frontend/js/dashboard_decomp_*.js, loaded
before dashboard.js in index.html. Content-assertion tests that used to read
dashboard.js alone should read dashboard.js plus those extracted modules so the
assertions target the assembled frontend behavior regardless of which file a
given function now lives in.

Not a test module (name does not match pytest's test discovery patterns).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "frontend" / "js"


def decomp_module_paths():
    return sorted(JS_DIR.glob("dashboard_decomp_*.js"))


def dashboard_js_text() -> str:
    """dashboard.js concatenated with every extracted dashboard_decomp_*.js
    module, in index.html load order (extracted modules after dashboard.js so
    positional .find()/.index() lookups into dashboard.js are unaffected)."""
    parts = [(JS_DIR / "dashboard.js").read_text(encoding="utf-8")]
    parts += [p.read_text(encoding="utf-8") for p in decomp_module_paths()]
    return "\n".join(parts)
