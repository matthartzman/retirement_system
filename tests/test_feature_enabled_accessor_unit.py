"""WP1.2: ``feature_enabled()`` / ``set_feature()`` and the catalog's profile
metadata (``tier`` / ``nav_group`` / ``default_on``).

The accessor replaces three read paths (module toggle row, plan flag,
``gated_by`` / ``gated_by_any_flag`` bundle) with one resolution, and must not
change a single answer while doing it. So the core test here compares it,
for every catalog key, against a frozen copy of the pre-WP1.2 accessors
(``_legacy_*`` below, transcribed from ``module_catalog`` at WP1.1) across
absent keys, toggles on/off, plan flags on/off, bundle parents off, the
DAF/QCD any-flag rule, prerequisite auto-selection, and every
``RETIREMENT_SYSTEM_FORCE_*`` env override.
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import module_catalog as mc  # noqa: E402
from plan_fixture import make_plan  # noqa: E402

ENV_VARS = ("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES",
            "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
            "RETIREMENT_SYSTEM_FORCE_ALL_MODULES")

TOGGLE_KEYS = [k for k, m in mc.CATALOG.items() if m.gate_kind == mc.GATE_MODULE_TOGGLE]
FLAG_KEYS = mc.plan_flag_keys()
OPTIONAL_TOGGLES = [k for k in TOGGLE_KEYS if mc.CATALOG[k].optional]
# Pre-WP1.2 runtime config keys of each plan flag. HELOC declared no
# gate_config_key before WP1.2; the engine read c['heloc_enabled'] directly.
LEGACY_FLAG_CONFIG_KEY = {"heloc": "heloc_enabled", "hybrid_ltc_policy": "ltc_enabled",
                          "daf_giving": "daf_enabled", "qcd_giving": "qcd_enabled"}


# ── Frozen pre-WP1.2 accessors (reference implementation) ───────────────────

def _env_set(name):
    raw = os.environ.get(name, "")
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def _legacy_force_disabled(key):
    return str(key).strip().lower() in _env_set("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES")


def _legacy_plan_flag_enabled(c, key):
    return bool(c.get(LEGACY_FLAG_CONFIG_KEY[key], False))


def _legacy_base_enabled(c, key):
    k = str(key).strip().lower()
    if _legacy_force_disabled(key):
        return False
    if k in _env_set("RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES"):
        return True
    if os.environ.get("RETIREMENT_SYSTEM_FORCE_ALL_MODULES") == "1":
        return True
    entry = mc.CATALOG.get(key) or mc.CATALOG.get(k)
    parent = getattr(entry, "gated_by", None)
    if parent:
        return _legacy_base_enabled(c, parent)
    flags = getattr(entry, "gated_by_any_flag", ())
    if flags:
        cfg = c or {}
        if any(LEGACY_FLAG_CONFIG_KEY[f] in cfg for f in flags):
            return any(_legacy_plan_flag_enabled(cfg, f) for f in flags)
    opt = (c or {}).get("opt") or {}
    if key in opt:
        return bool(opt[key])
    for kk, vv in opt.items():
        if str(kk).strip().lower() == k:
            return bool(vv)
    return True


def _legacy_effective(c):
    enabled = {k for k in mc.OPTIONAL_MODULE_SHEETS if _legacy_base_enabled(c, k)}
    auto = set()
    for key in enabled:
        if key not in mc.CATALOG:
            continue
        for dep in mc.prerequisite_outputs(key):
            if dep in mc.OPTIONAL_MODULE_SHEETS and not _legacy_force_disabled(dep):
                auto.add(dep)
    return enabled | auto


def _legacy_module_enabled(c, key):
    if _legacy_force_disabled(key):
        return False
    if _legacy_base_enabled(c, key):
        return True
    eff = _legacy_effective(c)
    k = str(key).strip().lower()
    return key in eff or any(str(e).strip().lower() == k for e in eff)


def _legacy(c, key):
    """What the pre-WP1.2 code answered for ``key``: the plan-flag accessor for
    a plan flag, ``module_enabled`` for everything else."""
    if key in FLAG_KEYS:
        return _legacy_plan_flag_enabled(c, key)
    return _legacy_module_enabled(c, key)


# ── Scenarios ────────────────────────────────────────────────────────────────

def _flags(**on):
    return {LEGACY_FLAG_CONFIG_KEY[k]: v for k, v in on.items()}


def _named_configs():
    all_on = {k: True for k in OPTIONAL_TOGGLES}
    all_off = {k: False for k in OPTIONAL_TOGGLES}
    flags_off = _flags(**{k: False for k in FLAG_KEYS})
    flags_on = _flags(**{k: True for k in FLAG_KEYS})
    return {
        "absent_everything": {},
        "opt_empty": {"opt": {}},
        "opt_none": {"opt": None},
        "all_toggles_on": {"opt": dict(all_on)},
        "all_toggles_off": {"opt": dict(all_off)},
        "all_off_flags_off": {"opt": dict(all_off), **flags_off},
        "all_off_flags_on": {"opt": dict(all_off), **flags_on},
        "flags_on_opt_absent": dict(flags_on),
        "daf_on_qcd_off": {**flags_off, **_flags(daf_giving=True)},
        "qcd_on_daf_off": {**flags_off, **_flags(qcd_giving=True)},
        # One sibling flag stored, the other absent: absent reads off.
        "daf_only_stored_off": _flags(daf_giving=False),
        "qcd_only_stored_on": _flags(qcd_giving=True),
        # Charitable Giving's own (orphan) toggle row is ignored once a flag
        # is stored, and honoured when none is.
        "charitable_row_off_flags_absent": {"opt": {"charitable_giving": False}},
        "charitable_row_off_daf_on": {"opt": {"charitable_giving": False}, **_flags(daf_giving=True)},
        # Bundle parent off: members follow it whatever their own rows say.
        "parent_off": {"opt": {"spending_tracker_ytd": False}},
        "parent_off_members_on": {"opt": {"spending_tracker_ytd": False,
                                          "spending_summary": True,
                                          "account_reconciliation": True}},
        "parent_on_members_off": {"opt": {"spending_tracker_ytd": True,
                                          "spending_summary": False,
                                          "account_reconciliation": False}},
        # Prerequisite auto-selection: survivor off but Life Insurance Need on.
        "prereq_pulled_in": {"opt": {**all_off, "life_insurance_need": True}},
        "prereq_not_needed": {"opt": {**all_off, "survivor_stress_test": False}},
        "tax_capacity_pulls_lifetime_tax": {"opt": {**all_off, "tax_capacity": True}},
        # Case-insensitive toggle row.
        "case_variant_row": {"opt": {"Market_Luck_Stress_Test": False, " GLOSSARY ": False}},
        # A core module given a row anyway (nothing should write one).
        "core_row_off": {"opt": {"net_worth": False, "asset_allocation": False}},
    }


def _random_configs(n=60, seed=1202):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        opt = {k: rng.choice([True, False]) for k in OPTIONAL_TOGGLES if rng.random() < 0.7}
        c = {"opt": opt}
        for f in FLAG_KEYS:
            if rng.random() < 0.6:
                c[LEGACY_FLAG_CONFIG_KEY[f]] = rng.choice([True, False])
        out.append(c)
    return out


ENV_CASES = {
    "no_env": {},
    "force_disable_parent_and_prereq": {
        "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES": "spending_tracker_ytd, survivor_stress_test,HELOC"},
    "force_disable_member": {
        "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES": "account_reconciliation,charitable_giving"},
    "force_enable_some": {
        "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES": "divorce_qdro,Spending_Summary,daf_giving,charitable_giving"},
    "force_enable_and_disable_same": {
        "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES": "equity_compensation",
        "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES": "equity_compensation"},
    "force_all": {"RETIREMENT_SYSTEM_FORCE_ALL_MODULES": "1"},
    "force_all_with_disable": {"RETIREMENT_SYSTEM_FORCE_ALL_MODULES": "1",
                               "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES": "market_luck_stress_test"},
}


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _set_env(mp, env):
    for name in ENV_VARS:
        mp.delenv(name, raising=False)
    for name, value in env.items():
        mp.setenv(name, value)


def _assert_agrees(c, label):
    for key in mc.CATALOG:
        want = _legacy(c, key)
        got = mc.feature_enabled(c, key)
        assert got == want, f"{label}: feature_enabled(c, {key!r}) = {got}, legacy {want}"
        if key in FLAG_KEYS:
            assert mc.plan_flag_enabled(c, key) == got, f"{label}: plan_flag_enabled({key!r})"
        else:
            assert mc.module_enabled(c, key) == got, f"{label}: module_enabled({key!r})"


# ── Agreement with the legacy accessors ──────────────────────────────────────

@pytest.mark.parametrize("env_name", list(ENV_CASES))
def test_feature_enabled_agrees_with_legacy_on_named_scenarios(clean_env, env_name):
    _set_env(clean_env, ENV_CASES[env_name])
    for label, c in _named_configs().items():
        _assert_agrees(c, f"{env_name}/{label}")


@pytest.mark.parametrize("env_name", ["no_env", "force_disable_parent_and_prereq", "force_enable_some"])
def test_feature_enabled_agrees_with_legacy_on_random_mixes(clean_env, env_name):
    _set_env(clean_env, ENV_CASES[env_name])
    for i, c in enumerate(_random_configs()):
        _assert_agrees(c, f"{env_name}/random#{i}")


@pytest.mark.parametrize("fixture", ["sample_frozen", "demo"])
def test_feature_enabled_agrees_with_legacy_on_real_plans(clean_env, tmp_path, fixture):
    c = make_plan(tmp_path, fixture).config(skip_live_pricing=True)
    for env_name, env in ENV_CASES.items():
        _set_env(clean_env, env)
        _assert_agrees(c, f"{fixture}/{env_name}")


def test_unknown_key_reads_like_a_module_toggle(clean_env):
    assert mc.feature_enabled({}, "not_a_module") is True
    assert mc.feature_enabled({"opt": {"not_a_module": False}}, "not_a_module") is False
    assert mc.module_enabled({"opt": {"Not_A_Module": False}}, "not_a_module") is False


def test_module_status_enabled_is_feature_enabled(clean_env):
    for c in list(_named_configs().values())[:8]:
        status = mc.module_status(c)
        for key, row in status.items():
            assert row["enabled"] == mc.feature_enabled(c, key)


# ── set_feature ─────────────────────────────────────────────────────────────

def _own_switch_keys():
    return [k for k, m in mc.CATALOG.items()
            if not m.gated_by and not m.gated_by_any_flag
            and (m.optional or m.gate_kind == mc.GATE_PLAN_FLAG)]


def _all_off_config():
    c = {"opt": {k: False for k in OPTIONAL_TOGGLES}}
    c.update(_flags(**{k: False for k in FLAG_KEYS}))
    return c


@pytest.mark.parametrize("key", _own_switch_keys())
def test_set_feature_round_trip(clean_env, key):
    c = _all_off_config()
    for on in (True, False, True):
        before = {k: mc.feature_enabled(c, k) for k in mc.CATALOG if k != key}
        mc.set_feature(c, key, on)
        assert mc.feature_enabled(c, key) is on
        # Stored where the legacy readers look.
        if key in FLAG_KEYS:
            assert c[LEGACY_FLAG_CONFIG_KEY[key]] is on
            assert _legacy_plan_flag_enabled(c, key) is on
        else:
            assert c["opt"][key] is on
            assert _legacy_module_enabled(c, key) is on
        if not on:
            # Turning one switch off never turns another feature on.
            after = {k: mc.feature_enabled(c, k) for k in before}
            assert not [k for k in before if after[k] and not before[k]]


def test_set_feature_creates_storage_when_absent(clean_env):
    c = {}
    mc.set_feature(c, "market_luck_stress_test", False)
    assert c == {"opt": {"market_luck_stress_test": False}}
    c = {"opt": None}
    mc.set_feature(c, "glossary", False)
    assert c == {"opt": {"glossary": False}}
    c = {}
    mc.set_feature(c, "heloc", True)
    assert c == {"heloc_enabled": True}
    assert mc.feature_enabled(c, "heloc") is True


def test_set_feature_on_member_drives_nothing_and_raises(clean_env):
    for key in ("spending_summary", "account_reconciliation", "charitable_giving"):
        with pytest.raises(ValueError):
            mc.set_feature({}, key, False)
    with pytest.raises(ValueError):
        mc.set_feature({}, "net_worth", False)
    with pytest.raises(KeyError):
        mc.set_feature({}, "not_a_module", False)


def test_set_feature_does_not_bypass_higher_tiers(clean_env):
    c = _all_off_config()
    mc.set_feature(c, "life_insurance_need", True)
    mc.set_feature(c, "survivor_stress_test", False)
    # Stored off, still on: auto-selected as Life Insurance Need's prerequisite.
    assert c["opt"]["survivor_stress_test"] is False
    assert mc.feature_enabled(c, "survivor_stress_test") is True
    clean_env.setenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", "glossary")
    mc.set_feature(c, "glossary", True)
    assert mc.feature_enabled(c, "glossary") is False


def test_set_feature_writes_through_one_private_writer(clean_env, monkeypatch):
    calls = []
    real = mc._write_switch
    monkeypatch.setattr(mc, "_write_switch", lambda c, m, on: (calls.append(m.key), real(c, m, on)))
    mc.set_feature({}, "heloc", True)
    mc.set_feature({}, "divorce_qdro", True)
    assert calls == ["heloc", "divorce_qdro"]


# ── Catalog metadata: tier / nav_group / default_on ─────────────────────────

def test_every_module_has_valid_profile_metadata():
    for key, m in mc.CATALOG.items():
        assert m.tier in mc.TIERS, key
        assert m.nav_group in mc.DOMAINS, key
        assert m.nav_group == m.domain, f"{key}: nav_group defaults to domain"
        assert isinstance(m.default_on, bool), key


def test_default_on_matches_legacy_absent_key_behavior(clean_env):
    """default_on is exactly what each legacy reader returned for an absent key."""
    for key, m in mc.CATALOG.items():
        if m.gated_by or m.gated_by_any_flag:
            continue
        assert m.default_on is _legacy({}, key), key
    assert {k for k, m in mc.CATALOG.items() if not m.default_on} == set(FLAG_KEYS)


@pytest.mark.parametrize("key,tier", [
    ("roth_conversion_plan", mc.SIMPLE), ("market_luck_stress_test", mc.SIMPLE),
    ("lifetime_tax_projection", mc.SIMPLE), ("charts_dashboard", mc.SIMPLE),
    ("net_worth", mc.SIMPLE), ("glossary", mc.SIMPLE),
    ("estate_legacy_plan", mc.STANDARD), ("social_security_timing", mc.STANDARD),
    ("survivor_stress_test", mc.STANDARD), ("hybrid_ltc_policy", mc.STANDARD),
    ("education_funding_529", mc.STANDARD), ("asset_allocation", mc.STANDARD),
    ("charitable_giving", mc.ADVANCED), ("heloc", mc.ADVANCED),
    ("what_if_analysis", mc.ADVANCED), ("housing_location_search", mc.ADVANCED),
    ("spending_tracker_ytd", mc.ADVANCED), ("tax_capacity", mc.ADVANCED),
    ("equity_compensation", mc.EXPERT), ("divorce_qdro", mc.EXPERT),
    ("rmd_audit", mc.EXPERT), ("account_reconciliation", mc.EXPERT),
    ("property_casualty_umbrella", mc.EXPERT), ("scorp_vs_llc", mc.EXPERT),
])
def test_tier_assignments_follow_the_design_table(key, tier):
    assert mc.CATALOG[key].tier == tier


@pytest.mark.parametrize("field,value", [
    ("tier", "bogus"), ("tier", None), ("nav_group", "Workbench"), ("default_on", "yes"),
])
def test_validate_rejects_bad_profile_metadata(monkeypatch, field, value):
    bad = replace(mc.CATALOG["glossary"], **{field: value})
    monkeypatch.setitem(mc.CATALOG, "glossary", bad)
    with pytest.raises(AssertionError):
        mc.validate()


def test_validate_rejects_plan_flag_without_config_key(monkeypatch):
    monkeypatch.setitem(mc.CATALOG, "heloc", replace(mc.CATALOG["heloc"], gate_config_key=None))
    with pytest.raises(AssertionError):
        mc.validate()


def test_validate_rejects_prerequisite_from_a_higher_tier(monkeypatch):
    monkeypatch.setitem(mc.CATALOG, "survivor_stress_test",
                        replace(mc.CATALOG["survivor_stress_test"], tier=mc.EXPERT))
    with pytest.raises(AssertionError):
        mc.validate()


def test_nav_group_override_is_kept():
    m = replace(mc.CATALOG["glossary"], nav_group=mc.TAXES)
    assert m.nav_group == mc.TAXES


def test_taxonomy_payload_carries_profile_metadata():
    from src.server_services.config_service import ConfigService
    tax = ConfigService._module_taxonomy()
    assert tax["tiers"] == list(mc.TIERS)
    for key, m in mc.CATALOG.items():
        row = tax["modules"][key]
        assert (row["tier"], row["nav_group"], row["default_on"]) == (m.tier, m.nav_group, m.default_on)
