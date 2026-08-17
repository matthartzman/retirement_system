"""Shared helper for the dashboard.js decomposition.

Cohesive UI blocks are being moved out of the monolithic frontend/js/dashboard.js
into sibling classic scripts named frontend/js/dashboard_decomp_*.js, loaded
before dashboard.js in index.html. Content-assertion tests that used to read
dashboard.js alone should read dashboard.js plus those extracted modules so the
assertions target the assembled frontend behavior regardless of which file a
given function now lives in.

Not a test module (name does not match pytest's test discovery patterns).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "frontend" / "js"

# The start of a top-level declaration, at the start of a line, in EITHER file
# shape: dashboard.js writes `function foo(`, an extracted module writes
# `export function foo(`.
_TOP_LEVEL_DECL = re.compile(
    r"^(?:export\s+)?(?:async\s+)?(?:function\s+\w+\s*\(|(?:const|let|var|class)\s+\w+)",
    re.M,
)


def decomp_module_paths():
    return sorted(JS_DIR.glob("dashboard_decomp_*.js"))


def dashboard_js_text() -> str:
    """dashboard.js concatenated with every extracted dashboard_decomp_*.js
    module, in index.html load order (extracted modules after dashboard.js so
    positional .find()/.index() lookups into dashboard.js are unaffected)."""
    parts = [(JS_DIR / "dashboard.js").read_text(encoding="utf-8")]
    parts += [p.read_text(encoding="utf-8") for p in decomp_module_paths()]
    return "\n".join(parts)


def dashboard_function_source(name: str, text: str | None = None) -> str:
    """The source of one top-level function, wherever it currently lives.

    Tests that assert about a single function used to slice the assembled text
    between two landmark symbols -- the function itself and whichever function
    happened to follow it. Extraction breaks that in two ways at once, and both
    were live failures during F3.1/F3.3:

      * The two landmarks end up in different files. dashboard_js_text() puts
        dashboard.js first, so if the subject moved to a module and its old
        neighbour stayed behind, the end landmark now sits BEFORE the start one
        and `.index(end, start)` raises ValueError.

      * Scanning for the next ``\\nfunction `` misses, because an extracted
        module declares ``export function``. The slice then runs past every
        remaining function in that module and into the next file, and the test
        fails on a count assertion with no hint that its boundary is wrong.

    Bounding by "the next top-level declaration in either shape" removes both.
    Callers get the function they named and nothing else, and never have to know
    which file it is in or what follows it.
    """
    js = dashboard_js_text() if text is None else text
    m = re.search(
        r"^(?:export\s+)?(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(",
        js,
        re.M,
    )
    if not m:
        raise AssertionError(
            f"no top-level function {name!r} in dashboard.js or any "
            f"dashboard_decomp_*.js module"
        )
    nxt = _TOP_LEVEL_DECL.search(js, m.end())
    return js[m.start() : nxt.start()] if nxt else js[m.start() :]
