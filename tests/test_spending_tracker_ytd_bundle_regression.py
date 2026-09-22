"""W8b: one switch, three modules — the Spending Tracker / YTD bundle.

Master plan `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-
master-plan.md` §4, W8b (#330 P6b); design in #330 §3.3 and §3.2. Notes:
`docs/superpowers/plans/2026-09-22-w8b-newly-optional-medium-risk-notes.md`.

Every other workstream on this branch has used one toggle per module. This one
does not, and the reason is in #330 §3.3: `spending_summary` and
`account_reconciliation` are the Spending Tracker's *output* —

> a household not tracking transactions has no use for either and neither can
> compute without the other's data

— so two independent toggles would not be two features, they would be one
feature with a way to reach an incoherent state (reconciliation on, the data it
reconciles off).

The mechanism is `OutputModule.gated_by`, resolved in exactly one place:
`module_catalog._base_enabled`. That placement is the W7 lesson applied in
advance — every consumer (the build gate's generic loop over
`OPTIONAL_MODULE_SHEETS`, `effective_enabled_modules`, `module_status`,
`module_enabled`) already routes through that function, so none of them can
forget the bundle the way `deterministic_engine.py` forgot the accessor.

`tests/test_module_catalog_prereq_gating.py` owns the gate-resolution
assertions (parent decides, member's key inert, env tier still per-key). This
file owns the two things W8b added *around* that gate: the registry wiring that
makes the switch remove sheets, and the engine site that makes it change the
projection.
"""
from __future__ import annotations

from datetime import date

import src.module_catalog as mc
from src import ytd_tracking as ytd
from src.reporting.workbook_common import OPTIONAL_MODULE_SHEETS
from src.ytd_projection_blend import compute_current_year_overrides

PARENT = "spending_tracker_ytd"
MEMBERS = ("spending_summary", "account_reconciliation")


# ── The bundle's shape ───────────────────────────────────────────────────────

def test_the_bundle_is_one_parent_over_exactly_these_two_members():
    assert mc.CATALOG[PARENT].optional is True
    assert mc.CATALOG[PARENT].gated_by is None
    assert mc.CATALOG[PARENT].sheet is None, (
        "the parent owns no workbook sheet -- what it owns is the two sheets "
        "that are its output, plus the current-year blend")
    assert sorted(k for k, m in mc.CATALOG.items() if m.gated_by) == sorted(MEMBERS)
    for key in MEMBERS:
        assert mc.CATALOG[key].gated_by == PARENT
        assert mc.CATALOG[key].optional is True, (
            "a bundled module is switched -- by its parent's row -- so calling "
            "it core would put it in core_keys(), which means always-on")


def test_both_member_sheets_are_wired_into_the_build_gate_under_their_own_keys():
    """W8a's finding, applied to the bundle: `optional=True` alone does not stop
    a sheet building -- `OPTIONAL_MODULE_SHEETS` derives from
    `SHEET_REGISTRY.module_key`. Each member's sheet names its OWN key rather
    than the parent's, which is what keeps that map's one-key-one-sheet shape
    and lets the generic build gate stay unchanged; the bundle is resolved
    inside `_base_enabled`, one layer down."""
    assert OPTIONAL_MODULE_SHEETS["spending_summary"] == ["29. Spending Summary"]
    assert OPTIONAL_MODULE_SHEETS["account_reconciliation"] == [
        "25. Account Reconciliation"]
    assert PARENT not in OPTIONAL_MODULE_SHEETS, (
        "the parent owns no sheet, so it must not appear in the sheet gate")


def test_the_parent_is_the_only_one_of_the_three_on_the_switch_surface():
    """The user-facing half of "one switch": the parent carries the toggle row,
    the members carry none. `tests/test_module_catalog.py` enforces both
    directions against the actual CSV; this pins the intent next to the
    mechanism."""
    assert mc.CATALOG[PARENT].gated_by is None
    assert all(mc.CATALOG[k].gated_by == PARENT for k in MEMBERS)


# ── The engine site (#330 §3.2: "`ytd_blend_enabled` forced off") ────────────

def _cfg(**overrides):
    c = {"plan_start": 2026, "plan_end": 2060, "ret": 0.08}
    c.update(overrides)
    return c


def _with_actuals(tmp_path):
    (tmp_path / "client_spending.csv").write_text(
        "section,subsection,label,value,units,notes\n"
        'Cashflow,Spending,annual_spending_base_year,"$120,000",,\n',
        encoding="utf-8",
    )
    ytd.import_transactions(
        tmp_path,
        "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"
        "2026-02-01,Employer,Paychecks,Checking,Bank,,50000,,Household\n"
        "2026-02-01,Grocery,Groceries,Checking,Bank,,-40000,,Household\n",
        mode="replace",
        today=date(2026, 7, 2),
    )


def test_the_module_declares_that_it_moves_the_projection():
    assert mc.CATALOG[PARENT].engine_participation is True
    assert PARENT in mc.engine_participants()


def test_tracker_on_blends_real_actuals_into_the_current_year(tmp_path):
    """The control: without this the assertion below could pass on a plan whose
    blend never fired for an unrelated reason."""
    _with_actuals(tmp_path)
    overrides = compute_current_year_overrides(
        _cfg(opt={PARENT: True}), tmp_path, today=date(2026, 7, 2))
    assert overrides["ytd_blend_applied"]["flow_blend_enabled"] is True
    assert overrides["ytd_blend_applied"]["flows_blended"] is True
    assert "ytd_blend_earned_override" in overrides


def test_tracker_off_suppresses_the_flow_blend_but_keeps_growth_proration(tmp_path):
    """#330 §3.2's off-column for this module: "`ytd_blend_enabled` forced
    off". The growth/contribution proration is *not* part of that -- it is pure
    date math with no real-data blending, and this module's own docstring says
    it always applies. A module toggle that silently stopped it would change a
    number for a reason no user asked about."""
    _with_actuals(tmp_path)
    c = _cfg(opt={PARENT: False})
    overrides = compute_current_year_overrides(c, tmp_path, today=date(2026, 7, 2))

    assert overrides["ytd_blend_applied"]["flow_blend_enabled"] is False
    assert overrides["ytd_blend_applied"]["flows_blended"] is False
    assert "ytd_blend_earned_override" not in overrides
    assert "ytd_blend_spend_override" not in overrides

    # Still prorated -- date math, not blending.
    assert overrides["return_by_year"][2026] < c["ret"]
    assert 2026 in overrides["ytd_blend_contrib_proration"]


def test_the_two_suppression_reasons_are_told_apart(tmp_path):
    """Executive Summary discloses *why* the current year was modeled as fully
    hypothetical, and before W8b the only possible reason was
    `ytd_blend_enabled = FALSE`, so that string was hardcoded there. Two
    reasons reach that branch now; telling a household that never touched that
    field to go change it would send them to the wrong screen."""
    _with_actuals(tmp_path)

    by_setting = compute_current_year_overrides(
        _cfg(ytd_blend_enabled=False, opt={PARENT: True}),
        tmp_path, today=date(2026, 7, 2))["ytd_blend_applied"]
    assert by_setting["flow_blend_skipped_by_user_choice"] is True
    assert by_setting["flow_blend_skipped_by"] == "ytd_blend_enabled"

    by_module = compute_current_year_overrides(
        _cfg(opt={PARENT: False}), tmp_path, today=date(2026, 7, 2))["ytd_blend_applied"]
    assert by_module["flow_blend_skipped_by_user_choice"] is True
    assert by_module["flow_blend_skipped_by"] == "module_off"


def test_the_engine_gate_reads_through_the_accessor_not_a_raw_opt_lookup(tmp_path):
    """W7's exact defect class, which this workstream's new engine site could
    have reintroduced: a raw `c['opt']` read skips the env overrides and the
    prerequisite auto-selection that `module_enabled()` applies. Exercised
    through the override the raw read would have ignored."""
    _with_actuals(tmp_path)
    import os

    os.environ["RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"] = PARENT
    try:
        meta = compute_current_year_overrides(
            _cfg(opt={PARENT: True}), tmp_path, today=date(2026, 7, 2)
        )["ytd_blend_applied"]
        assert meta["flow_blend_enabled"] is False, (
            "FORCE_DISABLE did not reach the blend -- the site is reading the "
            "toggle raw rather than through module_enabled()")
    finally:
        del os.environ["RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"]
