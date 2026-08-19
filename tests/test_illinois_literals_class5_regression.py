"""Item 291, Classes 5/6: remaining Illinois literals after Classes 1-4.

Three locations were investigated (per the plan's own Step 7.6). Two were
real defects, fixed here; the third was ruled out as a false positive after
reading its actual fallback behavior -- recorded below so a future pass
doesn't re-flag it without re-deriving the same investigation.

1. src/reporting/sheets_allocation_helpers.py's _trade_tax_rates: THREE
   layers of dead code, not a simple hardcode. `_td` there is the `taxes`
   module (via .workbook_common), which never defines STATE_TAX_RULES (only
   core.py computes that, module-level) -- so `getattr(_td, 'STATE_TAX_RULES',
   {})` always returned the {} default, for every state, unconditionally. On
   top of that, the (dead) lookup uppercased the state name against
   proper-case keys, and the 'IL' fallback compared against a 2-letter code
   c['state'] never actually holds (it stores the full name). `state` was
   therefore silently 0.0 for every household including an Illinois one --
   not just an Illinois-specific bug, a state-tax-blind one. Fixed by calling
   _td.load_state_tax([]) directly (the exact mechanism core.py itself uses)
   and comparing against c['state']'s real full-name format. Confirmed safe
   for the golden master: this function only feeds the Asset Allocation
   sheet's taxable-sale recommendation helper, not the projection engine.

2. src/reporting/sheets_strategy.py's build_sheet9: two prose spots
   ('Illinois Residency' key-risk row, 'Illinois Corp Surcharge' S-corp
   comparison row + its note sentence) stated Illinois unconditionally
   regardless of the household's actual resident state. The residency row
   is now dispatched through the same state_estate_tax() Class 2 built for
   Sheet 14, so this summary agrees with the detailed section rather than
   presenting a different picture of the same underlying mechanism. The
   S-corp surcharge RATE itself (c['scorp_state_rate']) was already a
   generic, user-configurable plan-data field defaulting to Illinois's own
   1.5% PPRT rate -- only the prose calling it "Illinois" unconditionally
   was the defect; the number needed no change.

3. src/server_services/strategy_asset_service.py's STATE_ESTIMATES: NOT a
   defect. Already a genuine 4-state table (TX/IL/FL/AZ), and an
   unrecognized/missing state already falls back to a neutral,
   national-average-style default dict, not to Illinois's specific numbers.
   No test needed here since there is no behavior to guard; this
   note exists so a future sweep doesn't re-flag it without re-checking.

Step 7.7's own closing `grep -rin illinois` sweep also found src.core's
state_income_tax and the deterministic engine's SALT estimate both falling
back to Illinois's specific rate for a genuinely BLANK residence_state. A fix
was attempted and then REVERTED -- not a false positive, but a genuine scope
conflict with Class 1's own deliberate, tested design at this exact
low-level, defensive layer (see test_residence_state_required_for_build_regression.py
::test_existing_low_level_leniency_is_unaffected and
test_unsupported_state_preflight_regression.py
::test_blank_state_still_falls_back_silently_not_bricked -- both explicitly
assert `state_income_tax('', ...) == state_income_tax('Illinois', ...)`, and
both docstrings say "this ticket adds a new gate, it does not change the old
one"). A blank state can never reach a real build
(require_residence_state_for_build already blocks that); this fallback exists
only for defensive/partial-snapshot callers Class 1 deliberately kept lenient.
Human decision (2026-08-19): revert the code change, keep those two tests
passing as originally written. See core.py's state_income_tax and
deterministic_engine.py's SALT-estimate comments for the full reasoning.
"""
from __future__ import annotations

from openpyxl import Workbook

from src.core import state_estate_tax
from src.reporting.sheets_allocation_helpers import _trade_tax_rates
from src.reporting.sheets_strategy import build_sheet9


def _minimal_sheet9_config(state, il_exempt=4_000_000.0):
    return {
        "state": state,
        "il_exempt": il_exempt,
        "ret": 0.07,
        "inf": 0.025,
        "entity": "s_corp",
        "scorp_salary": 80000,
        "scorp_state_rate": 0.015,
    }


def _sheet9_text(c):
    wb = Workbook()
    ws = wb.active
    build_sheet9(ws, c, [{"year": 2026}])
    return [str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None]


# --- _trade_tax_rates: the dead-code state-lookup fix ----------------------


def test_trade_tax_rates_applies_illinois_marginal_rate():
    rates = _trade_tax_rates({"state": "Illinois"})
    assert rates["state"] == 0.0495


def test_trade_tax_rates_applies_a_different_states_own_rate():
    # Not just "does IL work" -- proves this is genuinely state-driven, not
    # a second hardcode with a different name.
    rates_ca = _trade_tax_rates({"state": "California"})
    rates_fl = _trade_tax_rates({"state": "Florida"})
    assert rates_ca["state"] == 0.093
    assert rates_fl["state"] == 0.0
    assert rates_ca["state"] != rates_fl["state"]


def test_trade_tax_rates_handles_missing_state_without_crashing():
    rates = _trade_tax_rates({})
    assert rates["state"] == 0.0


# --- build_sheet9: Illinois Residency row -----------------------------------


def test_sheet9_residency_row_names_the_households_actual_state():
    text = _sheet9_text(_minimal_sheet9_config("Florida", il_exempt=0.0))
    assert any("Florida Residency" in t for t in text)
    assert not any("Illinois Residency" in t for t in text)


def test_sheet9_residency_row_discloses_not_modeled_for_new_york():
    # New York has estate=True but no real calculation exists (Class 2) --
    # this row must say so explicitly, matching Sheet 14, not silently show
    # a $0/none result that looks the same as "no estate tax here".
    text = _sheet9_text(_minimal_sheet9_config("New York", il_exempt=6_940_000.0))
    combined = " ".join(text)
    assert "New York Residency" in combined
    assert "does not yet compute" in combined or "not yet compute" in combined


def test_sheet9_residency_row_states_no_estate_tax_for_a_none_state():
    text = _sheet9_text(_minimal_sheet9_config("Texas", il_exempt=0.0))
    combined = " ".join(text)
    assert "Texas Residency" in combined
    assert "does not levy a state estate tax" in combined


def test_sheet9_residency_row_still_correct_for_illinois():
    # No regression for the frozen golden-master household itself.
    text = _sheet9_text(_minimal_sheet9_config("Illinois", il_exempt=4_000_000.0))
    combined = " ".join(text)
    assert "Illinois Residency" in combined
    assert "$4.0M Illinois exemption" in combined


# --- build_sheet9: S-corp surcharge prose -----------------------------------


def test_sheet9_scorp_surcharge_row_names_the_households_actual_state():
    text = _sheet9_text(_minimal_sheet9_config("Florida", il_exempt=0.0))
    assert any("Florida Corp Surcharge" in t for t in text)
    assert not any("Illinois Corp Surcharge" in t for t in text)


def test_sheet9_scorp_surcharge_note_names_the_households_actual_state():
    text = _sheet9_text(_minimal_sheet9_config("Florida", il_exempt=0.0))
    combined = " ".join(text)
    assert "Florida " in combined and "corporate surcharge applies" in combined
    assert "Illinois 1.5%" not in combined


def test_sheet9_scorp_surcharge_rate_itself_is_unchanged_by_state():
    # The RATE was never the defect -- it's already a generic plan-data
    # field. Only the label should change; the number must not.
    fl = _sheet9_text(_minimal_sheet9_config("Florida", il_exempt=0.0))
    il = _sheet9_text(_minimal_sheet9_config("Illinois", il_exempt=4_000_000.0))
    assert any("1.5% on taxable income" in t for t in fl)
    assert any("1.5% on taxable income" in t for t in il)


# --- ruled-out false positive, kept as a regression guard against a rewrite ---


def test_state_estimates_missing_state_does_not_silently_fall_back_to_illinois():
    from src.server_services.strategy_asset_service import housing_state_estimate_payload

    payload, status = housing_state_estimate_payload({"state": "ZZ"})
    assert status == 200
    il_payload, _ = housing_state_estimate_payload({"state": "IL"})
    # Illinois's own re_tax_pct (0.0205) is distinctive enough that an
    # accidental IL fallback would show up here; the neutral default is
    # 0.0100.
    assert payload["estimate"]["re_tax_pct"] != il_payload["estimate"]["re_tax_pct"]
