"""withdrawal_order.py — per-account withdrawal-order override parsing.

Extracted from src/data_io.py's parse_client() per ticket 312 (see
docs/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
section 5, "Per-account withdrawal-order overrides"). src/data_io.py
re-exports parse_account_draw_priority for backward compatibility with
existing callers.

Plan Data rows: [Withdrawal Policy][Account Order][<account_id>] = priority
(lower draws first). Uses the same generic Section/Subsection/Label CSV
convention as every other plan-data field (so the existing generic field
editor/autosave UI can manage it with no new endpoint), rather than a
bespoke file. Absent/empty by default, in which case accounts()/
draw_order() fall back to their existing (account-type-level) ordering
untouched -- see core.py's _apply_draw_priority docstring. Account IDs are
taken as free-form strings straight from the CSV rows, with no cross-check
against the account registry at parse time; validation/fallback happens
downstream in core._apply_draw_priority, which silently ignores priorities
for account IDs it doesn't recognize.
"""
from __future__ import annotations


def parse_account_draw_priority(data):
    """Parse the "Withdrawal Policy > Account Order" input section (#276).

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and returns the per-account
    withdrawal-order override that parse_client merges into the engine
    config ``c``: ``account_draw_priority``, a dict mapping account id
    (str) to priority (int, lower draws first). Blank/unparseable priority
    values are skipped rather than raising.
    """
    account_draw_priority = {}
    for _aid, _pr in (data.get('Withdrawal Policy', {}).get('Account Order', {}) or {}).items():
        _pr = str(_pr or '').strip()
        if _pr:
            try:
                account_draw_priority[str(_aid).strip()] = int(float(_pr))
            except (TypeError, ValueError):
                pass

    return {
        'account_draw_priority': account_draw_priority,
    }
