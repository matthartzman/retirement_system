"""WI-403 (system review 2026-09-25-2, QA-003): the frozen-date seam must hold
on the production workbook-build path.

``platform_runtime.today()`` honors ``RETIREMENT_SYSTEM_FROZEN_TODAY`` so a
frozen fixture projects the same figures on any run date (plan_start and the
YTD blend's day-of-year proration both depend on "today"). The workbook build
used to pass ``datetime.date.today()`` explicitly into
``compute_current_year_overrides`` -- overriding the blend's own seam default
-- and ``optimization.py`` / ``spending_tracker.py`` read the wall clock
directly, so a frozen build still prorated by the real date.

* ``test_no_bare_date_today_outside_allowlist`` is a source-scan guard: any
  new ``date.today()`` in ``src/`` fails unless it is added to the allowlist
  below with a reason (display-only dates such as "Plan Prepared" are fine).
* ``test_ytd_blend_is_independent_of_the_real_clock`` runs the YTD blend on
  the frozen fixture twice -- once with the real clock moved years away --
  and requires identical figures.
"""
from __future__ import annotations

import datetime as _real_datetime
import re
from pathlib import Path

from conftest import TEST_INPUT_DIR

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

DATE_TODAY_RE = re.compile(r"\bdate\.today\(\)")

# path (relative to src/) -> (allowed occurrence count, reason). Counts are
# exact so a new wall-clock read in an allow-listed file still fails.
ALLOWLIST: dict[str, tuple[int, str]] = {
    "platform_runtime.py": (1, "the seam itself: returns the real date when no frozen date is set"),
    "reporting/sheets_tax_reporter.py": (1, "display-only 'As of <date>' balance-sheet heading"),
    "reporting/sheets_summary_builder.py": (2, "display-only 'Plan Prepared' / 'Built:' stamps"),
    "reporting/dashboard.py": (1, "display-only build date on the HTML chart dashboard"),
    "server_services/ytd_service.py": (1, "user-initiated year-rollover action keyed to the real calendar"),
    "import_preview.py": (1, "default for an injectable `today` argument on an import preview"),
    "governance.py": (1, "fallback reference year for tax-table staleness warnings, not a projection input"),
    "taxes.py": (1, "TAX_REFERENCE_YEAR import-time default; overridable via TAX_REFERENCE_YEAR / RETIREMENT_TAX_YEAR env"),
}


def _counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for path in sorted(SRC.rglob("*.py")):
        n = len(DATE_TODAY_RE.findall(path.read_text(encoding="utf-8")))
        if n:
            out[path.relative_to(SRC).as_posix()] = n
    return out


def test_no_bare_date_today_outside_allowlist():
    counts = _counts()
    problems = []
    for rel, n in counts.items():
        allowed = ALLOWLIST.get(rel, (0, ""))[0]
        if n > allowed:
            problems.append(f"src/{rel}: {n} date.today() call(s), {allowed} allow-listed")
    assert not problems, (
        "Calculation-path code must read the date through platform_runtime.today() so "
        "RETIREMENT_SYSTEM_FROZEN_TODAY pins it:\n  " + "\n  ".join(problems)
        + "\nIf a new call is genuinely display-only, add it to ALLOWLIST with a reason."
    )


def test_allowlist_is_not_stale():
    counts = _counts()
    stale = [rel for rel, (n, _) in ALLOWLIST.items() if counts.get(rel, 0) < n]
    assert not stale, f"ALLOWLIST entries allow more calls than exist (tighten them): {stale}"


def test_workbook_build_passes_the_seam_into_the_ytd_blend():
    text = (SRC / "reporting" / "workbook_builder.py").read_text(encoding="utf-8")
    call = re.search(r"compute_current_year_overrides\([^\n]*\)", text)
    assert call, "workbook_builder no longer calls compute_current_year_overrides"
    assert "today=_platform_runtime.today()" in call.group(0), call.group(0)


class _ShiftedDate(_real_datetime.date):
    """A date class whose today() is years away from the frozen fixture date."""

    @classmethod
    def today(cls):
        return _real_datetime.date(2031, 3, 15)


class _ShiftedDatetimeModule:
    date = _ShiftedDate
    datetime = _real_datetime.datetime
    timedelta = _real_datetime.timedelta


def test_ytd_blend_is_independent_of_the_real_clock(monkeypatch):
    import os

    from src import platform_runtime
    from src.data_io import load_csv, parse_client
    from src.ytd_projection_blend import compute_current_year_overrides

    assert os.environ.get(platform_runtime.FROZEN_TODAY_ENV), "conftest must pin the frozen date"
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")

    def run():
        return compute_current_year_overrides(dict(c), TEST_INPUT_DIR, today=platform_runtime.today())

    baseline = run()
    monkeypatch.setattr(platform_runtime, "_datetime", _ShiftedDatetimeModule)
    # The seam still answers with the frozen date even though the "real" clock moved.
    assert platform_runtime.today() != _ShiftedDate.today()
    shifted = run()
    assert shifted == baseline
