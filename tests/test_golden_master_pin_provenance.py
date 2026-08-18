"""Test-enforced provenance gate for the frozen golden-master pins.

Ticket 286. The recovery process for this repo's golden-master pins
(`tools/regen_golden_master.py`,
`documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`) is only as strong as its
weakest enforcement point, and a tool that merely *asks nicely* for a
justification is not an enforcement point at all: under time pressure,
someone editing `PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX` by hand to make a
failing test go green bypasses any tool entirely. So this is a TEST, not a
CLI flag -- it has to fail the suite, not just refuse a command.

This repo has shipped five guards that could not fail (see
`documentation/GOLDEN_MASTER_CHANGELOG.md`'s 2026-08-17 (c) entry for the
most recent one). The specific failure mode to avoid here is a guard that
only checks "is there a comment nearby" -- that is trivially satisfied by a
STALE comment left over from the previous pin value, which is exactly the
scenario a hand-edit produces. So this gate binds the provenance entry to
the actual, current numeric value of each `PINNED_*` constant, not merely to
its presence:

* `test_provenance_line_is_present` -- there must be a machine-readable
  provenance line directly above the pins at all. Catches removing the line,
  or writing the pins with no line at all.
* `test_provenance_values_match_current_pins` -- the values recorded in that
  line must equal the constants actually in effect right now. Catches
  hand-editing `PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX` while leaving a
  stale provenance line (any date, any values) untouched -- the case a
  "does a comment exist" check would miss entirely.
* `test_provenance_date_matches_changelog` -- the provenance line's date
  must equal the newest changelog entry that *documents the current pin
  values* -- i.e. the newest `## YYYY-MM-DD` entry whose body contains both
  `PINNED_TERMINAL_NW` and `PINNED_LIFETIME_TAX` formatted as they appear in
  the constants right now (`f"{value:,.2f}"`). Binding to the newest entry
  that documents THESE values, rather than to `max()` over every dated
  header in the changelog, is deliberate (fix round 1, Finding 1): the
  changelog is used for golden-master-adjacent changes generally, not only
  pin moves, and same-day/later unrelated entries are routine (see e.g. the
  2026-08-17 (b)/(c)/(d) entries, which explicitly state the pins are
  unchanged). Binding to `max(all dated headers)` meant the first unrelated
  changelog entry added after this one would advance the required date with
  no pin edit involved, and the only way to silence it would be bumping the
  provenance date without a real justification -- recreating the exact
  stale-provenance shape this gate exists to catch. If NO entry documents
  the current pin values at all, that is a failure, not a vacuous pass --
  see the "guards that cannot fail" project memory.

Planted-defect verification for this file's own guard-that-cannot-fail risk,
including the fix-round-1 cases (an unrelated newer changelog entry must NOT
trip the gate; a total absence of a documenting entry MUST trip it), lives in
`.superpowers/sdd/task-4-report.md` (Ticket 286).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_FILE = ROOT / "tests" / "test_frozen_sample_plan_golden_master_regression.py"
CHANGELOG_FILE = ROOT / "documentation" / "GOLDEN_MASTER_CHANGELOG.md"

PROVENANCE_RE = re.compile(
    r"^# (?P<date>\d{4}-\d{2}-\d{2}): "
    r"PINNED_TERMINAL_NW=(?P<nw>-?\d+(?:\.\d+)?) "
    r"PINNED_LIFETIME_TAX=(?P<tax>-?\d+(?:\.\d+)?)\s*$",
    re.MULTILINE,
)
CONST_NW_RE = re.compile(r"^PINNED_TERMINAL_NW\s*=\s*(-?\d+(?:\.\d+)?)", re.MULTILINE)
CONST_TAX_RE = re.compile(r"^PINNED_LIFETIME_TAX\s*=\s*(-?\d+(?:\.\d+)?)", re.MULTILINE)
CHANGELOG_ENTRY_HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}).*$", re.MULTILINE)

HELP = (
    "Regenerate via `py -3.14 tools/regen_golden_master.py regen --reason <file>` "
    "(see documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md) -- never hand-edit "
    "PINNED_TERMINAL_NW / PINNED_LIFETIME_TAX directly."
)


def _pin_file_text() -> str:
    return PIN_FILE.read_text(encoding="utf-8")


def _last_provenance_match(text: str):
    matches = list(PROVENANCE_RE.finditer(text))
    return matches[-1] if matches else None


def _changelog_entries(changelog_text: str) -> list[tuple[str, str]]:
    """Split the changelog into (date, body) pairs, one per '## YYYY-MM-DD' entry.

    ``body`` runs from that header up to (not including) the next dated
    header, so it is exactly the text a reader would associate with that
    entry.
    """
    headers = list(CHANGELOG_ENTRY_HEADER_RE.finditer(changelog_text))
    entries = []
    for i, m in enumerate(headers):
        start = m.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(changelog_text)
        entries.append((m.group(1), changelog_text[start:end]))
    return entries


def test_provenance_line_is_present():
    text = _pin_file_text()
    provenance = _last_provenance_match(text)
    assert provenance is not None, (
        "No '# <date>: PINNED_TERMINAL_NW=... PINNED_LIFETIME_TAX=...' provenance "
        f"line found in {PIN_FILE}. Every pin move must be recorded. {HELP}"
    )


def test_provenance_values_match_current_pins():
    text = _pin_file_text()
    provenance = _last_provenance_match(text)
    assert provenance is not None, f"No provenance line found in {PIN_FILE}. {HELP}"

    nw_match = CONST_NW_RE.search(text)
    tax_match = CONST_TAX_RE.search(text)
    assert nw_match and tax_match, f"Could not locate PINNED_* constants in {PIN_FILE}."

    actual_nw = float(nw_match.group(1))
    actual_tax = float(tax_match.group(1))
    provenance_nw = float(provenance["nw"])
    provenance_tax = float(provenance["tax"])

    assert provenance_nw == actual_nw, (
        f"PINNED_TERMINAL_NW ({actual_nw!r}) does not match the value recorded in the "
        f"provenance line ({provenance_nw!r}). The pin was changed by hand without "
        f"updating its provenance -- a stale comment does not justify a new value. {HELP}"
    )
    assert provenance_tax == actual_tax, (
        f"PINNED_LIFETIME_TAX ({actual_tax!r}) does not match the value recorded in the "
        f"provenance line ({provenance_tax!r}). The pin was changed by hand without "
        f"updating its provenance -- a stale comment does not justify a new value. {HELP}"
    )


def test_provenance_date_matches_changelog():
    text = _pin_file_text()
    provenance = _last_provenance_match(text)
    assert provenance is not None, f"No provenance line found in {PIN_FILE}. {HELP}"

    nw_match = CONST_NW_RE.search(text)
    tax_match = CONST_TAX_RE.search(text)
    assert nw_match and tax_match, f"Could not locate PINNED_* constants in {PIN_FILE}."
    actual_nw = float(nw_match.group(1))
    actual_tax = float(tax_match.group(1))
    # Same formatting the changelog itself uses when it states pin values
    # (see e.g. the 2026-08-18 / 2026-08-17 entries): comma-grouped, 2dp.
    nw_str = f"{actual_nw:,.2f}"
    tax_str = f"{actual_tax:,.2f}"

    changelog_text = CHANGELOG_FILE.read_text(encoding="utf-8")
    entries = _changelog_entries(changelog_text)
    assert entries, f"No dated '## YYYY-MM-DD' entries found in {CHANGELOG_FILE}."

    documenting_dates = [
        date for date, body in entries if nw_str in body and tax_str in body
    ]
    assert documenting_dates, (
        f"No entry in {CHANGELOG_FILE} documents the current pin values "
        f"(PINNED_TERMINAL_NW={nw_str}, PINNED_LIFETIME_TAX={tax_str} -- checked for both "
        "formatted values appearing together in a single dated entry's body). Every value "
        f"the pins carry must be traceable to a changelog entry that states it. {HELP}"
    )
    newest_documenting_date = max(documenting_dates)

    assert provenance["date"] == newest_documenting_date, (
        f"Provenance date ({provenance['date']}) does not match the newest changelog entry "
        f"that documents the current pin values ({newest_documenting_date}) in "
        f"{CHANGELOG_FILE}. Every pin move needs a changelog entry, dated the same day as the "
        f"pin file's provenance line, that states the new values. {HELP}"
    )
