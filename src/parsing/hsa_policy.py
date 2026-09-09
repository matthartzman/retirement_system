"""hsa_policy.py — "HSA Policy" input-section parsing.

Extracted from src/data_io.py's parse_client() per ticket 312 and the
design doc docs/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md
(section 1, "HSA Policy scalars"), following the pattern already
established by src/parsing/daf.py, note_receivable.py, insurance.py, and
estate_planning.py. src/data_io.py re-exports both functions below for
backward compatibility with existing callers.

Two functions, per the design doc's recommendation:

- ``parse_hsa_policy(data, plan_start)`` — pure ``data``-dict reads, no
  file I/O. Combines what were historically two separate blocks in
  parse_client (withdrawal mode/window/contribution scalars, and
  beneficiary/death-tax-treatment scalars) that happened to sit in
  different parts of the function purely as a matter of code-order
  convenience: neither reads anything the other computes, and neither
  reads any value built in between them (confirmed against the current
  parse_client body, not just the design doc's line numbers).
- ``parse_hsa_withdrawal_schedule()`` — loads ``client_hsa_schedule.csv``
  (a separate file, not a ``data`` section), mirroring the adjacent
  liabilities-CSV load it was written to model. Left with no ``data``/
  ``plan_start`` parameters since it reads only the filesystem, matching
  its original body exactly.

Imports the small scalar-coercion helpers (_v, _b, _n, _y) back from
src.data_io rather than duplicating them: those helpers are still shared
primitives used throughout parse_client and are themselves slated for
their own future extraction (see the item 3.13 tracking note in
src/parsing/__init__.py). This works because src.data_io defines them
before importing this module, the same partial-circular-import pattern
already used by src/parsing/daf.py, note_receivable.py, insurance.py, and
estate_planning.py.
"""
from __future__ import annotations

import csv
import os

from ..data_io import _b, _n, _v, _y
from ..workspace_context import active_workspace_id, candidate_input_files


def parse_hsa_policy(data, plan_start):
    """Parse the "HSA Policy" input section's scalar fields.

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and ``plan_start`` (already computed
    earlier in parse_client) and returns the HSA Policy scalar fields that
    parse_client merges into the engine config ``c``. Does not include
    ``hsa_schedule_rows``/``hsa_schedule_by_year`` — see
    ``parse_hsa_withdrawal_schedule`` for those (a separate CSV file load).
    """
    # HSA withdrawal policy. Default is spend_as_needed: do not schedule HSA
    # draws; use HSA only when needed for a funding gap before touching Roth.
    # Optional annual_pct and smooth_window modes allow an advisor/user to
    # spend HSA over a controlled window. Legacy withdrawal_window is still
    # honored when present. optimize admitted 2026-08-19: see
    # withdraw_hsa_window's own 'optimize' branch and
    # c['hsa_schedule_rows']/hsa_schedule_by_year (parse_hsa_withdrawal_
    # schedule) for what it actually does today -- per-year override entries
    # via resolve_year_amount, falling back to an even/level draw for any
    # year with no schedule row. The automatic search (rerun_optimizer/
    # build_schedule) is NOT wired into the projection yet; see the module
    # docstring at the top of hsa_schedule.py.
    hsa_withdrawal_mode = str(_v(data, 'HSA Policy', 'Withdrawals', 'hsa_withdrawal_mode', 'spend_as_needed') or 'spend_as_needed').strip().lower()
    if hsa_withdrawal_mode not in ('spend_as_needed', 'annual_pct', 'smooth_window', 'optimize'):
        hsa_withdrawal_mode = 'spend_as_needed'
    hsa_annual_spend_pct = min(1.0, max(0.0, _n(_v(data, 'HSA Policy', 'Withdrawals', 'hsa_annual_spend_pct', '10%'), 0.10)))
    hsa_win_start = 9999
    hsa_win_end = 0
    hsa_start_raw = str(_v(data, 'HSA Policy', 'Withdrawals', 'hsa_withdrawal_start_year', '') or '').strip()
    hsa_end_raw = str(_v(data, 'HSA Policy', 'Withdrawals', 'hsa_withdrawal_end_year', '') or '').strip()
    try:
        hsa_win_start = int(float(hsa_start_raw)) if hsa_start_raw else plan_start
        hsa_win_end = int(float(hsa_end_raw)) if hsa_end_raw else 9999
    except Exception:
        hsa_win_start, hsa_win_end = 9999, 0
    # Be forgiving with legacy UI/data entry: older files sometimes stored the
    # HSA window as 2040/2031 instead of 2031/2040.  The Other Assets page now
    # exposes the start/end controls directly, and the projection normalizes
    # the window before applying scheduled HSA cash-flow withdrawals.
    if hsa_withdrawal_mode != 'spend_as_needed' and hsa_win_start > hsa_win_end:
        hsa_win_start, hsa_win_end = hsa_win_end, hsa_win_start
    hsa_contrib_base = (
        _n(_v(data, 'HSA Policy', 'Contributions', 'family_annual_limit_base_year', '8750'), 8750) *
        _n(_v(data, 'HSA Policy', 'Contributions', 'coverage_base_year_family_months', '6'), 6) / 12 +
        _n(_v(data, 'HSA Policy', 'Contributions', 'self_only_annual_limit_base_year', '4400'), 4400) *
        _n(_v(data, 'HSA Policy', 'Contributions', 'coverage_base_year_self_only_months', '6'), 6) / 12 +
        _n(_v(data, 'HSA Policy', 'Contributions', 'catchup_amount', '1000'), 1000)
    )
    hsa_last_contrib = _y(_v(data, 'HSA Policy', 'Contributions', 'contribution_last_year', str(plan_start)), plan_start)

    # ── HSA Policy: beneficiary / death-tax-treatment ────────────────────────
    # The engine currently treats an HSA as tax-free at every stage including
    # death, which is wrong for a non-spouse beneficiary (the whole balance
    # becomes ordinary income to them in the year of death). These inputs are
    # consumed by later HSA-optimizer work; this task only parses them.
    hsa_beneficiary_type = str(_v(data, 'HSA Policy', 'Beneficiary',
                                   'hsa_beneficiary_type', 'spouse') or 'spouse').strip().lower()
    hsa_consume_by = str(_v(data, 'HSA Policy', 'Withdrawals',
                             'hsa_consume_by', 'second_death_p90') or 'second_death_p90').strip()
    _bank = _v(data, 'HSA Policy', 'Withdrawals', 'hsa_expense_bank', '')
    hsa_expense_bank = None if (_bank is None or str(_bank).strip() == '') else _n(_bank, 0.0)
    hsa_nonqualified_treatment = str(_v(data, 'HSA Policy', 'Withdrawals',
                                         'hsa_nonqualified_treatment', 'block') or 'block').strip().lower()
    hsa_state_conformity = _b(_v(data, 'HSA Policy', 'Withdrawals', 'hsa_state_conformity', 'TRUE'))

    return {
        'hsa_withdrawal_mode': hsa_withdrawal_mode,
        'hsa_annual_spend_pct': hsa_annual_spend_pct,
        'hsa_win_start': hsa_win_start,
        'hsa_win_end': hsa_win_end,
        'hsa_contrib_base': hsa_contrib_base,
        'hsa_last_contrib': hsa_last_contrib,
        'hsa_beneficiary_type': hsa_beneficiary_type,
        'hsa_consume_by': hsa_consume_by,
        'hsa_expense_bank': hsa_expense_bank,
        'hsa_nonqualified_treatment': hsa_nonqualified_treatment,
        'hsa_state_conformity': hsa_state_conformity,
    }


def parse_hsa_withdrawal_schedule():
    """Load the HSA withdrawal schedule from ``client_hsa_schedule.csv``.

    Flat table: year, optimizer_amount, override_amount, locked, note. Rows
    feed hsa_schedule.resolve_year_amount, consumed by
    withdraw_hsa_window's 'optimize' branch. Mirrors the liabilities load in
    parse_client; an absent/unparseable file yields an empty list, which
    resolve_year_amount treats as "no schedule entry for any year" (mode
    fallback for every year), matching a plan that never used this feature.
    """
    hsa_schedule_rows = []
    hsa_sched_file = None
    for _hs_path in candidate_input_files('client_hsa_schedule.csv', active_workspace_id()):
        _hs = str(_hs_path)
        if os.path.exists(_hs):
            hsa_sched_file = _hs
            break
    if hsa_sched_file:
        try:
            with open(hsa_sched_file, newline='', encoding='utf-8-sig') as hf:
                for row in csv.DictReader(hf):
                    year_raw = (row.get('year', '') or '').strip()
                    if not year_raw:
                        continue
                    try:
                        year = int(float(year_raw))
                    except Exception:
                        continue

                    def _clean_opt_num(raw):
                        raw = (str(raw or '')).replace('$', '').replace(',', '').strip()
                        if not raw:
                            return None
                        try:
                            return float(raw)
                        except Exception:
                            return None
                    hsa_schedule_rows.append({
                        'year': year,
                        'optimizer_amount': _clean_opt_num(row.get('optimizer_amount')),
                        'override_amount': _clean_opt_num(row.get('override_amount')),
                        'locked': str(row.get('locked', '') or '').strip().lower() in ('true', '1', 'yes'),
                        'note': (row.get('note', '') or '').strip(),
                    })
        except Exception:
            hsa_schedule_rows = []

    return {
        'hsa_schedule_rows': hsa_schedule_rows,
        'hsa_schedule_by_year': {r['year']: r for r in hsa_schedule_rows},
    }
