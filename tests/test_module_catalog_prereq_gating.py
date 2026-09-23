"""Phase-2 prerequisite auto-selection at the gating layer.

When an optional output module is enabled but one of its prerequisite outputs
(per ``src.module_catalog``) is disabled, the prerequisite must be treated as
enabled anyway — otherwise the dependent module produces a broken/empty sheet.
This is enforced in ``module_catalog.module_enabled`` /
``effective_enabled_modules`` (A9 - moved from ``workbook_common``) and
covered here as fast unit tests (no workbook build required).

Precedence exercised (highest first):
  1. FORCE_DISABLE on the directly-named key — always off, even for a prereq.
  2. Directly enabled (env force / saved toggle / default-on).
  3. Auto-selected as a prerequisite of an enabled optional module.
  4. Otherwise off.

The only optional→optional prerequisite in the catalog today is
``survivor_stress_test`` (required by ``life_insurance_need`` and
``existing_life_insurance``); every other prerequisite is a core, always-on
module. The tests use that real relationship.
"""
import os

import pytest

import src.module_catalog as mc
from src.module_catalog import (
    OPTIONAL_MODULE_SHEETS,
    effective_enabled_modules,
    module_enabled,
    module_status,
)


DEPENDENT = "life_insurance_need"
PREREQ = "survivor_stress_test"
INDEPENDENT = "roth_conversion_plan"

# Every optional module that lists PREREQ as a (transitive) prerequisite. To
# keep PREREQ from being auto-selected, *all* of these must be off — otherwise
# a default-on dependent (e.g. existing_life_insurance) legitimately pulls it in.
PREREQ_DEPENDENTS = [
    k for k in OPTIONAL_MODULE_SHEETS
    if k in mc.CATALOG and PREREQ in mc.prerequisite_outputs(k)
]


@pytest.fixture(autouse=True)
def _clear_force_env(monkeypatch):
    """Every test controls gating through ``c['opt']`` unless it sets env knobs
    itself; clear the process-wide FORCE_* overrides so a stray env var from the
    outer shell can't mask the behavior under test."""
    for var in (
        "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES",
        "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
        "RETIREMENT_SYSTEM_FORCE_ALL_MODULES",
    ):
        monkeypatch.delenv(var, raising=False)


def _cfg(**toggles):
    """Build a config dict whose ``opt`` map holds the given boolean toggles.
    Any optional module not named defaults to enabled (matching production)."""
    return {"opt": dict(toggles)}


# ── Sanity: the relationship these tests rely on is real ──────────────────────

def test_catalog_relationship_holds():
    assert PREREQ in mc.prerequisite_outputs(DEPENDENT)
    assert mc.CATALOG[PREREQ].optional  # the prereq is itself toggle-gated
    assert DEPENDENT in OPTIONAL_MODULE_SHEETS
    assert PREREQ in OPTIONAL_MODULE_SHEETS


# ── (3) Prerequisite auto-selection ───────────────────────────────────────────

def test_disabled_prereq_is_auto_enabled_when_dependent_on():
    # Dependent ON, prerequisite explicitly OFF → prerequisite reported enabled.
    c = _cfg(**{DEPENDENT: True, PREREQ: False})
    assert module_enabled(c, DEPENDENT) is True
    assert module_enabled(c, PREREQ) is True, "prereq must be pulled in"
    assert PREREQ in effective_enabled_modules(c)


def test_prereq_stays_disabled_when_dependent_also_off():
    # No enabled module needs it → an explicit OFF stays OFF. Every dependent of
    # PREREQ must be off (existing_life_insurance also requires it).
    c = _cfg(**{k: False for k in PREREQ_DEPENDENTS}, **{PREREQ: False})
    assert module_enabled(c, DEPENDENT) is False
    assert module_enabled(c, PREREQ) is False
    assert PREREQ not in effective_enabled_modules(c)


def test_transitive_core_prereqs_need_no_gating():
    # Core prerequisites (net_worth, cash_flow) carry no toggle and are never in
    # the gate; auto-selection must not invent keys for them.
    c = _cfg(**{DEPENDENT: True, PREREQ: False})
    eff = effective_enabled_modules(c)
    assert "net_worth" not in eff and "cash_flow" not in eff
    # They are always-on core modules regardless of gating.
    assert module_enabled(c, "net_worth") is True
    assert module_enabled(c, "cash_flow") is True


# ── (2) Independent modules are unaffected ────────────────────────────────────

def test_independent_module_unaffected_when_off():
    # A module that is nobody's prerequisite stays off when toggled off, even
    # while auto-selection is pulling in an unrelated prerequisite.
    c = _cfg(**{DEPENDENT: True, PREREQ: False, INDEPENDENT: False})
    assert module_enabled(c, INDEPENDENT) is False
    assert INDEPENDENT not in effective_enabled_modules(c)


def test_independent_module_unaffected_when_on():
    c = _cfg(**{INDEPENDENT: True, DEPENDENT: False, PREREQ: False})
    assert module_enabled(c, INDEPENDENT) is True


# ── Disabling everything stays disabled ───────────────────────────────────────

def test_all_optional_off_stays_off():
    # W8b: the off-map is built from `optional_keys()` -- the catalog's list of
    # switches -- not from OPTIONAL_MODULE_SHEETS, which is the sheet-gate map.
    # The two were interchangeable while every toggle owned a sheet. #330 §3.3's
    # bundle parent (`spending_tracker_ytd`) owns none, so it is absent from the
    # sheet map; building "everything off" from that map left the parent's key
    # unset, `_base_enabled` defaulted it on, and its two bundled members read
    # as ON in a test whose whole subject is that nothing is.
    c = _cfg(**{k: False for k in mc.optional_keys()})
    assert effective_enabled_modules(c) == set()
    for key in OPTIONAL_MODULE_SHEETS:
        assert module_enabled(c, key) is False, f"{key} should remain disabled"
    for key in mc.optional_keys():
        assert module_enabled(c, key) is False, f"{key} should remain disabled"


def test_a_bundled_module_follows_its_parents_switch_only():
    """#330 §3.3 (W8b). One switch, several modules: the member's own key is not
    a switch, and setting it cannot make the member disagree with its parent.

    This is the property the bundle exists for -- Spending Summary and Account
    Reconciliation are the Spending Tracker's output, and "neither can compute
    without the other's data" -- so a state where one is on and the other off is
    not a configuration, it is a bug.
    """
    members = sorted(k for k, m in mc.CATALOG.items() if m.gated_by is not None)
    assert members, "no bundled modules in the catalog; this test has no subject"
    parents = {mc.CATALOG[k].gated_by for k in members}
    assert len(parents) == 1
    parent = parents.pop()

    # The parent decides, in both directions.
    off = _cfg(**{parent: False})
    on = _cfg(**{parent: True})
    for key in members:
        assert module_enabled(off, key) is False, f"{key} ignored its parent's OFF"
        assert module_enabled(on, key) is True, f"{key} ignored its parent's ON"

    # A member's own key is inert -- it cannot override the parent either way.
    # (A row that *sets* it is separately forbidden; see
    # tests/test_module_catalog.py::test_every_optional_module_has_a_toggle_row.)
    for key in members:
        assert module_enabled(_cfg(**{parent: False, key: True}), key) is False
        assert module_enabled(_cfg(**{parent: True, key: False}), key) is True


def test_force_env_still_reaches_a_bundled_module_by_its_own_name(monkeypatch):
    """The bundle resolves BELOW the env tier, on purpose: RETIREMENT_SYSTEM_FORCE_*
    is a per-key admin tier that the gating tests use to name individual
    modules, and a member named there must still win for itself."""
    member = next(k for k, m in mc.CATALOG.items() if m.gated_by is not None)
    parent = mc.CATALOG[member].gated_by

    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", member)
    c_on = _cfg(**{parent: True})
    assert module_enabled(c_on, member) is False, "FORCE_DISABLE on the member lost"
    assert module_enabled(c_on, parent) is True, "the parent was dragged off with it"

    monkeypatch.delenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES")
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES", member)
    c_off = _cfg(**{parent: False})
    assert module_enabled(c_off, member) is True, "FORCE_ENABLE on the member lost"

    # And force-disabling the PARENT takes the member with it -- the recursive
    # resolution runs the parent through the same precedence ladder from the top.
    monkeypatch.delenv("RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES")
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", parent)
    assert module_enabled(_cfg(**{parent: True}), member) is False


# ── (1) FORCE_DISABLE precedence ──────────────────────────────────────────────

def test_force_disable_wins_over_autoselect(monkeypatch):
    # Dependent enabled and would pull in the prerequisite, but the prerequisite
    # is explicitly force-disabled by env → FORCE_DISABLE wins (precedence 1).
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", PREREQ)
    c = _cfg(**{DEPENDENT: True, PREREQ: False})
    assert module_enabled(c, DEPENDENT) is True
    assert module_enabled(c, PREREQ) is False, "FORCE_DISABLE must beat auto-selection"
    assert PREREQ not in effective_enabled_modules(c)


def test_force_disable_on_dependent_does_not_autoselect_prereq(monkeypatch):
    # All dependents force-disabled → none is "enabled", so the prereq is pulled
    # in by nothing and its explicit OFF stands.
    monkeypatch.setenv(
        "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", ",".join(PREREQ_DEPENDENTS)
    )
    c = _cfg(**{k: True for k in PREREQ_DEPENDENTS}, **{PREREQ: False})
    assert module_enabled(c, DEPENDENT) is False
    assert module_enabled(c, PREREQ) is False


# ── Non-breaking: all-on behavior is unchanged ────────────────────────────────

def test_force_all_modules_all_enabled(monkeypatch):
    # The canonical fixtures force every module on; auto-selection must be a
    # no-op there (everything already on, nothing pruned).
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_ALL_MODULES", "1")
    c = _cfg()  # no explicit toggles
    for key in OPTIONAL_MODULE_SHEETS:
        assert module_enabled(c, key) is True


def test_default_toggles_match_baseline():
    # With no config at all, every optional module defaults enabled (unchanged
    # pre-Phase-2 default-on behavior).
    for key in OPTIONAL_MODULE_SHEETS:
        assert module_enabled(None, key) is True
        assert module_enabled({}, key) is True


# ── module_status: UI-facing gating explanation ───────────────────────────────

def test_module_status_reports_auto_enabled_with_required_by():
    # Dependent ON, prerequisite explicitly OFF, every other dependent of PREREQ
    # off too (existing_life_insurance is default-on and also requires PREREQ,
    # same caveat as PREREQ_DEPENDENTS above) → status must explain that the
    # prereq is only on because DEPENDENT needs it.
    toggles = {k: False for k in PREREQ_DEPENDENTS if k != DEPENDENT}
    toggles[DEPENDENT] = True
    toggles[PREREQ] = False
    c = _cfg(**toggles)
    status = module_status(c)
    assert set(status.keys()) == set(OPTIONAL_MODULE_SHEETS)

    assert status[PREREQ]["enabled"] is True
    assert status[PREREQ]["auto_enabled"] is True
    assert status[PREREQ]["required_by"] == [DEPENDENT]

    # The dependent itself is directly enabled, not auto-enabled.
    assert status[DEPENDENT]["enabled"] is True
    assert status[DEPENDENT]["auto_enabled"] is False
    assert status[DEPENDENT]["required_by"] == []


def test_module_status_all_off_is_fully_off():
    # See test_all_optional_off_stays_off: `optional_keys()`, not the sheet map,
    # is what "every switch" means once a toggle can own no sheet (W8b).
    c = _cfg(**{k: False for k in mc.optional_keys()})
    status = module_status(c)
    for key in OPTIONAL_MODULE_SHEETS:
        assert status[key] == {
            "enabled": False,
            "auto_enabled": False,
            "required_by": [],
            # #330 Q7 (W4). Present and null, not absent: the UI branches on
            # these keys, and this exact-shape assertion is what catches a
            # silent change to the contract it depends on.
            "forced": None,
            "forced_by": None,
        }, f"{key} should be fully off"
