"""Regression test for the 2026-09-03 "UnicodeEncodeError: 'charmap' codec
can't encode character" crash surfaced to the user as "Error loading local
database" on app restart.

Root cause: Windows defaults a Python process's stdout/stderr to the legacy
ANSI code page (cp1252) unless PYTHONUTF8/PYTHONIOENCODING is set, which this
app does not require users to set. Several real print() call sites in this
codebase (workbook_builder.py, market_data.py, ...) can echo user-entered
config text -- and input/client_policy.csv ships a note containing "μ"
(U+03BC), a character cp1252 cannot represent. The first print() of any
string containing it crashes the process; inside a Flask route that surfaces
as app_core.py's catch-all @app.errorhandler(Exception) turning the crash
into an opaque 500 with the raw exception text as the "error" message, which
the frontend then displays verbatim in place of whatever the request was
actually trying to do.

The fix (main.py, top of file, before any other code runs) reconfigures
stdout/stderr to UTF-8 with errors="replace" so no print() call anywhere in
the process can raise UnicodeEncodeError again, regardless of which one a
future change happens to exercise.

This test spawns real subprocesses (not an in-process monkeypatch) because
the bug is specifically about the OS-assigned default encoding of a fresh
process's standard streams, which pytest's own output capture can mask.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MU = "μ"


def _run(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Simulate a default Windows user environment: neither variable set.
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=False,
    )


def test_bare_print_of_mu_fails_under_the_default_windows_encoding():
    """Sanity check that this machine's default process encoding really is
    the vulnerable one -- if this ever stops failing (e.g. a future Python
    defaulting to UTF-8 mode everywhere), the regression this file guards
    against can no longer occur and the fix becomes moot, not wrong."""
    if sys.platform != "win32":
        import pytest
        pytest.skip("cp1252-default-stdout is a Windows-only condition")
    proc = _run(f"print('{MU}')")
    assert proc.returncode != 0
    assert b"UnicodeEncodeError" in proc.stderr


def test_importing_main_makes_mu_printable():
    """The actual fix: after `import main` (which runs its module-level
    stdout/stderr reconfiguration before any app code), printing the exact
    character that crashed the real app must succeed."""
    if sys.platform != "win32":
        import pytest
        pytest.skip("cp1252-default-stdout is a Windows-only condition")
    proc = _run(f"import main; print('{MU}')")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert MU.encode("utf-8") in proc.stdout


def test_client_policy_note_that_originally_triggered_this_is_still_present():
    """Guards the regression's own premise: if this note's non-ASCII
    character is ever edited out, this suite is silently testing nothing
    about the real trigger. (Not asserting the fix is meaningless without a
    real offending character in a real shipped input file.)

    Reads the committed frozen fixture, not input/client_policy.csv:
    input/ is gitignored real client data (see CLAUDE.md's data-storage
    section), so it does not exist on a fresh checkout -- this test was
    failing with FileNotFoundError in CI for exactly that reason. The frozen
    fixture is the same file tests/conftest.py stages into input/ for every
    other test, and carries the same μ note (see its mc_sensitivity_simulations
    row) since it was captured from a real shipped plan.
    """
    csv_path = ROOT / "tests" / "fixtures" / "sample_plan_frozen" / "client_policy.csv"
    text = csv_path.read_text(encoding="utf-8-sig")
    assert MU in text, (
        "tests/fixtures/sample_plan_frozen/client_policy.csv no longer contains "
        "a μ character -- this suite's premise (a real shipped file crashes the "
        "default Windows console encoding) needs a new concrete example, not "
        "just removal."
    )
