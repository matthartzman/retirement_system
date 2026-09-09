"""withdrawal_policy.py — Withdrawal Policy bracket-target / spending-decline
parameter parsing.

Extracted from src/data_io.py's parse_client() as part of ticket 312 (see
docs/superpowers/plans/2026-09-09-parse-client-remaining-sections-design.md,
section 2: "Withdrawal Policy bracket-target/spending-decline"). Follows the
same pattern as the four siblings already extracted in PR #101
(src/parsing/daf.py, note_receivable.py, insurance.py, estate_planning.py):
src/data_io.py re-exports parse_withdrawal_spending_policy for backward
compatibility with existing callers.

Imports the small scalar-coercion helpers (_v, _n) back from src.data_io,
and percent_to_float from src.roth_ui_build_guard (both already imported at
src/data_io.py's module top before this module is imported), the same
partial-circular-import pattern used by src/parsing/daf.py.
"""
from __future__ import annotations

from ..data_io import _n, _v
from ..roth_ui_build_guard import percent_to_float


def parse_withdrawal_spending_policy(data):
    """Parse the "Withdrawal Policy" > "Elective Withdrawal" / "Spending
    Policy" input sections.

    Reads only the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and returns the fields that
    parse_client merges into the engine config ``c``:
    ``withdrawal_bracket_target_rate``, ``spending_policy``,
    ``spending_phase_decline_pct``, ``spending_phase_start_age``,
    ``spending_phase_end_age``.
    """
    # ── Elective Withdrawal Bracket-Target Policy (item 3.4, F1 Option 2) ────
    # withdraw_pretax_elective (planning_engines.py) has always capped its
    # Priority-3 draw at a bracket ceiling before falling through to taxable/
    # trust -- but that ceiling was hardcoded to the 24% federal bracket in
    # deterministic_engine.py (top_24_yr), with no input anywhere to change
    # it. This is the input: the actual policy CFPs describe ("fill ordinary
    # income to the Nth bracket, then draw taxable") without restructuring
    # the fixed cascade itself (F1 Option 1, deferred). Default 0.24 exactly
    # reproduces today's hardcoded rate, so an unconfigured plan is unaffected.
    withdrawal_bracket_target_rate = percent_to_float(_v(data, 'Withdrawal Policy', 'Elective Withdrawal',
                                   'withdrawal_bracket_target_rate', '0.24'), 0.24)

    # ── Adoptable Spending Policy (item 3.5, F6) ──────────────────────────────
    # fixed_real (default, today's behavior): spend_base grows with inflation
    #   forever, never adjusted by portfolio performance.
    # guyton_klinger: the 4-rule (minus portfolio-management) guardrail
    #   already modeled as an MC shadow becomes the LIVE policy -- portfolio
    #   draw grows with inflation each year (frozen after a down year in MC,
    #   which has real per-path returns to react to; the deterministic
    #   engine's single flat assumed return has none, so its freeze rule is a
    #   documented no-op there), cut/raised 10% when the withdrawal rate
    #   drifts >20% from the initial rate.
    # floor_ceiling_band: simpler cousin -- withdrawal tracks current
    #   portfolio value directly but is clamped to +/-10% of the plan's own
    #   original real spending level.
    _spending_policy = str(_v(data, 'Withdrawal Policy', 'Spending Policy',
                              'spending_policy', 'fixed_real') or 'fixed_real').strip().lower()
    spending_policy = _spending_policy if _spending_policy in ('fixed_real', 'guyton_klinger', 'floor_ceiling_band') else 'fixed_real'
    # Age-phased real spending curve (Option 2, independent of the selector
    # above): discretionary spend declines by this fraction, phased in
    # linearly between start_age and end_age (of the older/only member still
    # alive that year), then holds at the reduced level. All default to 0 --
    # a no-op multiplier of 1.0 for every existing plan.
    spending_phase_decline_pct = percent_to_float(_v(data, 'Withdrawal Policy', 'Spending Policy',
                                   'spending_phase_decline_pct', '0'), 0.0)
    spending_phase_start_age = int(_n(_v(data, 'Withdrawal Policy', 'Spending Policy',
                                   'spending_phase_start_age', '0'), 0))
    spending_phase_end_age = int(_n(_v(data, 'Withdrawal Policy', 'Spending Policy',
                                   'spending_phase_end_age', '0'), 0))

    return {
        'withdrawal_bracket_target_rate': withdrawal_bracket_target_rate,
        'spending_policy': spending_policy,
        'spending_phase_decline_pct': spending_phase_decline_pct,
        'spending_phase_start_age': spending_phase_start_age,
        'spending_phase_end_age': spending_phase_end_age,
    }
