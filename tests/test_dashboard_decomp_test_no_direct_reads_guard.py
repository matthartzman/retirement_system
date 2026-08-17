"""Guard: no test file reads frontend/js/dashboard.js directly.

Wave 6.4 (F2.2). Tests that assert on frontend content must go through
tests._decomp_dashboard.dashboard_js_text(), which concatenates dashboard.js
with every extracted dashboard_decomp_*.js module. A test that reads
dashboard.js alone breaks the moment its subject is extracted -- and it breaks
by going red on a working frontend, which is the expensive kind of false alarm
this decomposition generates by the dozen.

WHY THIS FILE WAS REWRITTEN (2026-08-17)
----------------------------------------
The first version of this guard could not fail. It only recorded a violation if
the literal string ``.read_text()`` -- with EMPTY parentheses -- appeared
anywhere in the file, as a second gate after its real pattern matched. Every
actual read in this repo passes an encoding (``.read_text(encoding="utf-8")``),
so that literal is essentially never present and the guard passed on a tree
where 26 test files read dashboard.js directly, including two that went red in
the very next extraction pass.

That is the same shape as the find_dead_functions.mjs defect fixed in 3979d17:
a check that is structurally unable to report the thing it exists to report,
and whose green result was read as evidence for years. The lesson worth keeping
is that a guard needs a test proving it FAILS on a known violation, not just
that it passes on a clean tree -- so that is what
test_guard_detects_a_planted_violation does below.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "tests"

# Files that legitimately read dashboard.js AS A FILE rather than as "the
# frontend". Each one is here because concatenating the extracted modules would
# make its assertion mean something different, not merely because it was
# inconvenient to change.
ALLOWED = {
    # measures dashboard.js's own line count -- that file IS the subject
    "test_frontend_size_ratchet.py": "asserts on dashboard.js's own size",
    # guards the auto-generated window-bridge block that lives in dashboard.js
    "test_dashboard_js_module_bridge_regression.py": "guards the generated bridge block",
    # asserts about dashboard.js's own boot code and its index.html load order
    "test_dashboard_startup_race_and_script_order.py": "asserts on boot code + script order",
    # reports dashboard.js line numbers; concatenation makes those numbers lie
    "test_help_text_no_html_entities_regression.py": "reports dashboard.js line numbers",
}

# A read of dashboard.js, in the forms this repo actually uses. Kept as separate
# alternatives rather than one clever regex so a failure names which shape hit.
_READ_PATTERNS = [
    r"""\(\s*ROOT\s*/\s*['"]frontend['"]\s*/\s*['"]js['"]\s*/\s*['"]dashboard\.js['"]\s*\)\s*\.read_text""",
    r"""\(\s*ROOT\s*/\s*['"]frontend/js/dashboard\.js['"]\s*\)\s*\.read_text""",
    r"""Path\(\s*['"]frontend/js/dashboard\.js['"]\s*\)\s*\.read_text""",
    r"""open\(\s*['"]frontend/js/dashboard\.js['"]""",
    r"""\bread\(\s*['"]frontend/js/dashboard\.js['"]\s*\)""",
]


def _path_vars(text: str) -> set[str]:
    """Names bound to the dashboard.js path, so `NAME.read_text(...)` counts.

    Excludes bindings to a dashboard_decomp_*.js or spending_dashboard.js path;
    those are different files and reading them directly is fine.
    """
    names = set()
    for m in re.finditer(r"^[ \t]*(\w+)[ \t]*=[ \t]*([^\r\n]*dashboard\.js[^\r\n]*)", text, re.M):
        target = m.group(2)
        if "decomp" in target or "spending_dashboard" in target:
            continue
        names.add(m.group(1))
    return names


def find_direct_reads(text: str) -> list[str]:
    """Every direct read of dashboard.js in `text`, as 'lineno: source'."""
    hits = []
    varnames = _path_vars(text)
    var_re = (
        re.compile(r"\b(?:" + "|".join(re.escape(v) for v in varnames) + r")[ \t]*\.[ \t]*read_text")
        if varnames
        else None
    )
    for lineno, line in enumerate(text.splitlines(), 1):
        if any(re.search(p, line) for p in _READ_PATTERNS) or (var_re and var_re.search(line)):
            hits.append(f"{lineno}: {line.strip()}")
    return hits


class DashboardDecompTestGuardTests(unittest.TestCase):
    def test_guard_detects_a_planted_violation(self):
        """The guard must FAIL on a known violation.

        Without this, a detector that matches nothing looks identical to a clean
        tree -- which is exactly how the previous version of this file passed
        while 26 real violations sat in tests/.
        """
        for source in [
            'js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")',
            "js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')",
            "text = Path('frontend/js/dashboard.js').read_text(encoding='utf-8')",
            "text = open('frontend/js/dashboard.js', encoding='utf-8').read()",
            'DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"\n'
            'js = DASHBOARD_JS.read_text(encoding="utf-8")',
        ]:
            with self.subTest(source=source):
                self.assertTrue(
                    find_direct_reads(source),
                    f"guard failed to flag a direct read it must catch:\n{source}",
                )

    def test_guard_does_not_flag_the_approved_helper(self):
        """And it must not fire on the form we are steering people toward."""
        for source in [
            "js = dashboard_js_text()",
            "from tests._decomp_dashboard import dashboard_js_text",
            'js = (ROOT / "frontend/js/dashboard_decomp_row_model.js").read_text(encoding="utf-8")',
            'js = (ROOT / "frontend/js/spending_dashboard.js").read_text(encoding="utf-8")',
        ]:
            with self.subTest(source=source):
                self.assertEqual([], find_direct_reads(source))

    def test_no_test_files_read_dashboard_js_directly(self):
        violations = {}
        for test_file in sorted(TEST_DIR.glob("test_*.py")):
            if test_file.name == Path(__file__).name or test_file.name in ALLOWED:
                continue
            hits = find_direct_reads(test_file.read_text(encoding="utf-8"))
            if hits:
                violations[test_file.name] = hits

        if violations:
            detail = "\n".join(
                f"  {name}\n" + "\n".join(f"      {h}" for h in hits)
                for name, hits in violations.items()
            )
            self.fail(
                "These test files read frontend/js/dashboard.js directly instead of\n"
                "tests._decomp_dashboard.dashboard_js_text(). A test that reads only\n"
                "dashboard.js goes red the moment its subject is extracted into a\n"
                "dashboard_decomp_*.js module, even though the frontend still works.\n\n"
                "Fix:\n"
                "  from tests._decomp_dashboard import dashboard_js_text\n"
                "  js = dashboard_js_text()\n\n"
                "If the test genuinely asserts on dashboard.js AS A FILE (its size, its\n"
                "generated bridge block, its own boot code, its line numbers), add it to\n"
                "ALLOWED at the top of this file with the reason.\n\n"
                f"{detail}"
            )


if __name__ == "__main__":
    unittest.main()
