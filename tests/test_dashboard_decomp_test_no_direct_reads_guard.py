"""Guard test: no test file reads frontend/js/dashboard.js directly.

Wave 6.4 (F2.2): all tests that need dashboard.js content must use the
tests._decomp_dashboard.dashboard_js_text() helper. This ensures the assembled
frontend (dashboard.js + extracted dashboard_decomp_*.js modules) is read as
a unit, matching how the frontend loads it in index.html.

This guard prevents regression: if a new test is added that directly reads
dashboard.js instead of using the helper, this test fails with the fix named.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "tests"


class DashboardDecompTestGuardTests(unittest.TestCase):
    """F2.2: Guard test for dashboard.js direct reads."""

    def test_no_test_files_read_dashboard_js_directly(self):
        """Fail if any test file reads dashboard.js without using the decomp helper.

        Allowed patterns (using the helper):
        - from tests._decomp_dashboard import dashboard_js_text
        - dashboard_js_text()

        Disallowed patterns (direct reads):
        - (ROOT / "frontend" / "js" / "dashboard.js").read_text()
        - DASHBOARD_JS.read_text()
        - Any variant of direct file read on dashboard.js
        """
        violations = []

        # Patterns that indicate direct reads (should not be found)
        direct_read_patterns = [
            r'frontend["\']?\s*/\s*["\']?js["\']?\s*/\s*["\']?dashboard\.js',  # Path patterns
            r'DASHBOARD(?:_JS)?\.read_text',  # Variable read patterns
        ]

        # Pattern that indicates correct usage (OK)
        correct_pattern = r'dashboard_js_text\s*\('

        for test_file in sorted(TEST_DIR.glob("test_*.py")):
            content = test_file.read_text()

            # Skip conftest and helper files.
            #
            # This file must skip ITSELF. Its docstring and failure message
            # necessarily spell out the very patterns it forbids -- that is
            # what makes the message actionable -- so scanning itself matches
            # every one of them and the guard fails on a clean tree. Same
            # self-defeating loop that find_dead_functions.mjs hits with the
            # dead-code ratchet, and it is excluded there for the same reason:
            # a file whose job is to NAME a pattern cannot also be audited FOR
            # that pattern.
            if test_file.name in ["conftest.py", "_decomp_dashboard.py", Path(__file__).name]:
                continue

            # Check for disallowed patterns
            has_violation = False
            for pattern in direct_read_patterns:
                if re.search(pattern, content):
                    # Check if it's in a comment or string literal
                    if ".read_text()" in content:
                        # Double-check with read_text to find actual reads, not just paths
                        if re.search(
                            r'(?:frontend.*dashboard\.js|DASHBOARD_JS).*\.read_text',
                            content
                        ):
                            has_violation = True
                            break

            if has_violation:
                violations.append(test_file.name)

        if violations:
            self.fail(
                f"The following test files read frontend/js/dashboard.js directly "
                f"instead of using tests._decomp_dashboard.dashboard_js_text(). "
                f"Fix by:\n"
                f"  1. Add: from tests._decomp_dashboard import dashboard_js_text\n"
                f"  2. Replace: (ROOT / 'frontend/js/dashboard.js').read_text(...) "
                f"      with: dashboard_js_text()\n"
                f"  3. Replace: DASHBOARD_JS.read_text(...) "
                f"      with: dashboard_js_text()\n\n"
                f"Violating files:\n" + "\n".join(f"  - {v}" for v in violations)
            )


if __name__ == "__main__":
    unittest.main()
