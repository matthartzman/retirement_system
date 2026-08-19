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
  must equal the newest changelog entry that *records a pin regeneration of
  these exact values*, identified by an explicit machine-readable marker:

      <!-- pin-provenance: terminal_nw=<value> lifetime_tax=<value> -->

  The marker, not prose, is the binding. Fix round 1 bound this to "any
  dated entry whose body contains both formatted values somewhere", which
  read as an improvement over `max(all dated headers)` but was not durable:
  this changelog's established convention for UNRELATED changes is to
  restate the current pins as unchanged-confirmation boilerplate -- "pins
  stay at 5,824,239.30 / 1,290,848.91" appears that way at lines 3, 29, 90,
  218 and 350 of the changelog, and the 2026-08-18 entry added by ticket 286
  itself used that very phrasing. Under a substring rule, the next routine
  entry following that convention would have become the newest "documenting"
  entry and forced the provenance date to be bumped with no pin move -- the
  same train-date-bumping-to-silence failure the substring rule was meant to
  fix, merely deferred by one commit. An HTML comment cannot be produced
  accidentally by prose, is invisible in rendered markdown, and is written
  by `tools/regen_golden_master.py regen` as part of a real regeneration.
  If NO entry carries a marker for the current pin values, that is a
  failure, not a vacuous pass -- see the "guards that cannot fail" memory.

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

# Written by `tools/regen_golden_master.py regen`. Prose cannot satisfy this by
# accident, which is the entire point -- see this module's docstring.
PIN_PROVENANCE_MARKER_RE = re.compile(
    r"<!--\s*pin-provenance:\s*terminal_nw=([0-9.]+)\s+lifetime_tax=([0-9.]+)\s*-->"
)

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

    # Bind to the explicit marker, NOT to prose mentioning the values. This
    # changelog routinely restates unchanged pins in entries about unrelated
    # work; a substring rule would let those entries advance the required
    # date with no pin move. Compare as floats so 5824239.3 and 5824239.30
    # are the same value, while still rejecting a genuinely different number.
    documenting_dates = []
    for date, body in entries:
        for m in PIN_PROVENANCE_MARKER_RE.finditer(body):
            if float(m.group(1)) == actual_nw and float(m.group(2)) == actual_tax:
                documenting_dates.append(date)
                break

    assert documenting_dates, (
        f"No entry in {CHANGELOG_FILE} carries a pin-provenance marker for the current "
        f"pins (terminal_nw={actual_nw:.2f}, lifetime_tax={actual_tax:.2f}). A real pin "
        "regeneration writes\n"
        f"    <!-- pin-provenance: terminal_nw={actual_nw:.2f} lifetime_tax={actual_tax:.2f} -->\n"
        "into its dated entry. Prose restating the values does NOT count, deliberately: "
        "this changelog states unchanged pins in entries about unrelated work, so prose "
        f"cannot distinguish a regeneration from a passing mention. {HELP}"
    )
    newest_documenting_date = max(documenting_dates)

    assert provenance["date"] == newest_documenting_date, (
        f"Provenance date ({provenance['date']}) does not match the newest changelog entry "
        f"carrying a pin-provenance marker for these values ({newest_documenting_date}) in "
        f"{CHANGELOG_FILE}. Every pin move needs a dated changelog entry, same day as the "
        f"pin file's provenance line, whose marker states the new values. {HELP}"
    )
