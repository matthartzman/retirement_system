"""estate_planning.py — Estate Planning scalar parameter parsing.

Extracted from src/data_io.py's parse_client() as part of system review
2026-08-31, finding A5 / Wave 3 item 3.13 ("split parse_client into
src/parsing/ siblings; move validation out"). src/data_io.py re-exports
parse_estate_planning for backward compatibility with existing callers.

Reads only the "Estate Planning" section plus one "Household" flag
(survivor_has_dependent, folded in here as qss_dependent because it is
consumed alongside the other Estate Planning scalars). No plan_start /
TAX_BASE_YEAR threading is needed -- every field here is a plain scalar or
boolean with a literal default, not a year computed relative to the plan.

``trust_type`` (Estate Planning / Trust Structure) is included here too,
even though in the pre-extraction parse_client() it was set much earlier
(right after the residency-schedule block, well before the rest of this
"# Estate" block ran). It was folded in because moving it is safe: it's a
plain, side-effect-free ``_v(data, ...)`` read of static input, and nothing
in parse_client() between its old position and this block's old position
reads or otherwise depends on ``c['trust_type']`` -- so relocating the read
does not change its value or any evaluation order that matters. The net
effect is only that ``c['trust_type']`` is now populated later during
parse_client() (still well before parse_client() returns).

Imports the small scalar-coercion helpers (_v, _b, _n) back from src.data_io
rather than duplicating them: those helpers are still shared primitives used
throughout parse_client and are themselves slated for their own future
extraction (see the item 3.13 tracking note in src/parsing/__init__.py).
This works because src.data_io defines them before importing this module
(see the "===== BEGIN data_parser.py =====" section), the same
partial-circular-import pattern already used by src/parsing/daf.py and
src/parsing/advanced_modules.py.
"""
from __future__ import annotations

from ..data_io import _b, _n, _v


def parse_estate_planning(data):
    """Parse the "Estate Planning" input section (plus one Household flag).

    Reads the already-loaded sectioned ``data`` dict (``{section:
    {subsection: {label: value}}}``) and returns the estate-planning fields
    that parse_client merges into the engine config ``c``. See the module
    docstring for the ``trust_type`` exception.
    """
    trust_type = _v(data, 'Estate Planning', 'Trust Structure', 'trust_type', 'revocable living trust')
    fed_exempt = _n(_v(data, 'Estate Planning', 'Federal', 'exemption_mfj', '30000000'), 30000000)
    # Section 'State' (item 291 Class 4; was 'Illinois' -- migrate_sectioned_data,
    # called above, upgrades any legacy row to this shape before this read runs).
    # Label itself was already state-generic (state_estate_exemption); only the
    # subsection baked in the state name.
    il_exempt = _n(_v(data, 'Estate Planning', 'State', 'state_estate_exemption', '4000000'), 4000000)
    # #227/#303: a funded Credit Shelter Trust shelters decedent assets from the
    # survivor's estate entirely (see cs_enabled/cs_amount below) rather than
    # doubling il_exempt directly -- il_exempt itself must stay the survivor's
    # own plain exemption or the trust benefit gets double-counted. This cap
    # governs how much of the FIRST decedent's own exemption can be carried
    # into the trust at first death, so it defaults to the same $4,000,000 as
    # il_exempt: decedent's $4M (CST-sheltered) + survivor's own separate $4M
    # (il_exempt) = the $8,000,000 combined household IL exemption Illinois'
    # lack of portability otherwise loses at the first death. A default of
    # $8,000,000 here would let the trust shelter the survivor's own exemption
    # a second time, understating combined household exposure by up to $4M.
    il_cst_shelter_cap = _n(_v(data, 'Estate Planning', 'Credit Shelter Trust', 'shelter_cap', '4000000'), 4000000)
    cst_enabled = _b(_v(data, 'Estate Planning', 'Credit Shelter Trust', 'enabled', 'FALSE'))
    basis_step_up_at_death = _b(_v(data, 'Estate Planning', 'Step-Up', 'basis_step_up_at_death', 'TRUE'))
    basis_step_up_property_regime = str(
        _v(data, 'Estate Planning', 'Step-Up', 'property_regime', 'COMMON_LAW') or 'COMMON_LAW'
    ).strip().upper()
    if basis_step_up_property_regime not in ('COMMON_LAW', 'COMMUNITY_PROPERTY', 'HALF_STEP_UP', 'FULL_STEP_UP'):
        basis_step_up_property_regime = 'COMMON_LAW'
    federal_portability_enabled = _b(_v(data, 'Estate Planning', 'Federal', 'portability_enabled', 'TRUE'))
    # Item 4.7 (P8): optional, used only by beneficiary_titling_audit() to flag
    # a former spouse still named as a beneficiary somewhere. Blank by default.
    former_spouse_name = _v(data, 'Estate Planning', 'Step-Up', 'former_spouse_name', '')
    qss_dependent = _b(_v(data, 'Household', '', 'survivor_has_dependent', 'FALSE'))
    # Do not double the IL exemption as a shortcut.  The projection now tracks
    # actual first-death credit-shelter funding and subtracts that funded amount
    # from the survivor's taxable estate.
    gift_excl = _n(_v(data, 'Estate Planning', 'Gifting', 'annual_exclusion_per_donee', '19000'), 19000)
    # QTIP Trust — elected by executor to qualify marital deduction; controls disposition after survivor's death
    qtip_enabled = _b(_v(data, 'Estate Planning', 'QTIP Trust', 'enabled', 'FALSE'))
    qtip_amount = _n(_v(data, 'Estate Planning', 'QTIP Trust', 'funding_amount', '0'), 0)
    qtip_note = _v(data, 'Estate Planning', 'QTIP Trust', 'note',
                   'Provides income to surviving spouse; controls ultimate beneficiaries')
    # Credit Shelter Trust (Bypass Trust) — preserves IL $4M exemption at first death
    cs_enabled = _b(_v(data, 'Estate Planning', 'Credit Shelter Trust', 'enabled', 'TRUE'))
    cs_amount = _n(_v(data, 'Estate Planning', 'Credit Shelter Trust', 'amount',
                       str(il_cst_shelter_cap)), il_cst_shelter_cap)
    cs_note = _v(data, 'Estate Planning', 'Credit Shelter Trust', 'note',
                 'Funds up to the CST shelter cap (decedent\'s own $4M IL exemption by default); bypasses survivor estate for IL tax, on top of the survivor\'s own separate $4M IL exemption -- $8M combined by default')
    # QTIP manages annuity income after first death (annuity held in QTIP for benefit of survivor)
    qtip_manages_annuity = _b(_v(data, 'Estate Planning', 'QTIP Trust', 'manages_annuity_after_first_death', 'TRUE'))
    # Desired minimum after-tax terminal bequest; 0/unset means no target is configured.
    # Consumed by monte_carlo()/monte_carlo_exact_scalar()'s probability_legacy_floor_met.
    legacy_floor = _n(_v(data, 'Estate Planning', 'Legacy', 'legacy_floor', '0'), 0)

    return {
        'trust_type': trust_type,
        'fed_exempt': fed_exempt,
        'il_exempt': il_exempt,
        'il_cst_shelter_cap': il_cst_shelter_cap,
        'cst_enabled': cst_enabled,
        'basis_step_up_at_death': basis_step_up_at_death,
        'basis_step_up_property_regime': basis_step_up_property_regime,
        'federal_portability_enabled': federal_portability_enabled,
        'former_spouse_name': former_spouse_name,
        'qss_dependent': qss_dependent,
        'gift_excl': gift_excl,
        'qtip_enabled': qtip_enabled,
        'qtip_amount': qtip_amount,
        'qtip_note': qtip_note,
        'cs_enabled': cs_enabled,
        'cs_amount': cs_amount,
        'cs_note': cs_note,
        'qtip_manages_annuity': qtip_manages_annuity,
        'legacy_floor': legacy_floor,
    }
