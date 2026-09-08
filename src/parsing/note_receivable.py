"""note_receivable.py — "Note Receivable" input-section parsing.

Extracted from src/data_io.py's parse_client() as part of system review
2026-08-31, finding A5 / Wave 3 item 3.13 ("split parse_client into
src/parsing/ siblings; move validation out"). src/data_io.py re-exports
parse_note_receivable for backward compatibility with existing callers.

Note Receivable is repeatable like other typed "Other Assets" (one or more
named notes). Each note is entered as its own "Note N" subsection with a
descriptive name plus the same fields the single legacy note used to have
(face value, first/last payment year, annual principal, final-year
principal, and an interest-by-year schedule). The projection engine
consumes per-note detail via c['note_items'] and also needs simple scalar
aggregates for legacy call sites (deterministic engine, balance sheet,
optimization) — those are summed/derived across all notes here.

Imports the small scalar-coercion helpers (_v, _n, _y) back from
src.data_io rather than duplicating them: those helpers are still shared
primitives used throughout parse_client and are themselves slated for their
own future extraction (see the item 3.13 tracking note in
src/parsing/__init__.py). This works because src.data_io defines them before
importing this module, the same partial-circular-import pattern already
used by src/parsing/daf.py and src/parsing/advanced_modules.py.
"""
from __future__ import annotations

import re

from ..core import TAX_BASE_YEAR
from ..data_io import _n, _v, _y


def parse_note_receivable(data, plan_start):
    """Parse the "Note Receivable" input section.

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and ``plan_start`` (already computed
    earlier in parse_client) and returns the note-receivable fields that
    parse_client merges into the engine config ``c``: the per-note detail
    list (``note_items``) plus the legacy scalar aggregates summed/derived
    across all notes (``note_face``, ``note_first``, ``note_last``,
    ``note_princ``, ``note_princ_final``, ``note_interest``).
    """
    note_items = []
    _note_section = data.get('Note Receivable') or {}
    _note_subs = [s for s in _note_section.keys()
                  if re.match(r'^Note\s+\d+$', str(s or '').strip(), re.I)]
    # Backward compat: a pre-multi-note plan snapshot (single Note Receivable,
    # subsection "Summary") predates the "Note N" repeatable-note convention.
    # A stale plan_snapshots row using that older shape must still parse as
    # one note instead of silently producing an empty note_items (zero note
    # income/balance everywhere, with no error to say why).
    if not _note_subs and 'Summary' in _note_section:
        _note_subs = ['Summary']
    _note_subs = sorted(_note_subs, key=lambda s: (0, int(re.search(r'(\d+)', s).group(1))) if re.search(r'(\d+)', s) else (1, s))
    for _nsub in _note_subs:
        _nvals = _note_section[_nsub]
        _nname = str(_nvals.get('name') or _nsub).strip() or _nsub
        _nface  = _n(_nvals.get('face_value', '0'), 0.0)
        _nfirst = _y(_nvals.get('first_payment', f"1/2/{plan_start}"), plan_start)
        _nlast  = _y(_nvals.get('last_payment', '1/2/2033'), 2033)
        _nprinc = _n(_nvals.get(f'annual_principal_{TAX_BASE_YEAR}_{TAX_BASE_YEAR + 6}',
                                 _nvals.get('annual_principal_base_period', '0')), 0.0)
        _nprinc_final = _n(_nvals.get('final_principal_2033', _nvals.get('final_principal', '0')), 0.0)
        _ninterest = {}
        # The legacy single-note shape (subsection "Summary") kept its
        # interest schedule under "Interest by Year" rather than
        # "{subsection} Interest" -- matches the fallback above.
        _nint_sub = 'Interest by Year' if _nsub == 'Summary' else f'{_nsub} Interest'
        for yr in range(plan_start, plan_start + 8):
            iv = _v(data, 'Note Receivable', _nint_sub, str(yr), '0')
            _ninterest[yr] = _n(iv, 0)
        note_items.append({
            'section': _nsub, 'name': _nname, 'face_value': _nface,
            'first_payment_year': _nfirst, 'last_payment_year': _nlast,
            'annual_principal': _nprinc, 'final_principal': _nprinc_final,
            'interest_by_year': _ninterest,
        })

    # Legacy scalar aggregates used by the deterministic engine, balance
    # sheet, and optimization scoring. face_value/annual_principal sum
    # across notes; first/last payment years span the earliest start and
    # latest end of any note; interest-by-year sums across notes.
    note_face   = sum(n['face_value'] for n in note_items) if note_items else 0.0
    note_first  = min((n['first_payment_year'] for n in note_items), default=plan_start)
    note_last   = max((n['last_payment_year'] for n in note_items), default=plan_start)
    note_princ  = sum(n['annual_principal'] for n in note_items) if note_items else 0.0
    note_princ_final = sum(n['final_principal'] for n in note_items) if note_items else 0.0
    note_interest = {}
    for yr in range(plan_start, plan_start + 8):
        note_interest[yr] = sum(n['interest_by_year'].get(yr, 0) for n in note_items)

    return {
        'note_items': note_items,
        'note_face': note_face,
        'note_first': note_first,
        'note_last': note_last,
        'note_princ': note_princ,
        'note_princ_final': note_princ_final,
        'note_interest': note_interest,
    }
