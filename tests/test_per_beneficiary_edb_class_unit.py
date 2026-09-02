"""Wave 3 item 3.3 (system review 2026-08-31, finding F4, Options 1 + 3):
per_beneficiary_ten_year_drawdown treated every non-spouse beneficiary as
subject to the SECURE Act 10-year rule, with no branch for an eligible
designated beneficiary (EDB) -- legally incorrect, not merely conservative,
for a minor child, a disabled or chronically ill beneficiary, or one less
than ten years younger than the decedent. It was also federal-only (no
state tax) and taxed each distribution slice as the heir's only income (no
baseline-income stacking).

This adds a per-account beneficiary_class/age/state/baseline_income (all
new, all defaulting to '', 0, '', 0.0 -- the exact prior behavior) so an
EDB account gets its own life-expectancy stretch instead of the 10-year
rule, and every account's slice tax now stacks on a configurable baseline
income and adds state tax when a supported state is named.

Option 2 (showing the Roth optimizer's own point-estimate heir rate,
effective_heir_ten_year_rate, at three assumptions) is NOT covered here --
that rate is a single household-level estimate, not per-account/
per-beneficiary, and is deferred as separately-scoped presentation work.
"""
from src.after_tax import (
    EDB_BENEFICIARY_CLASSES,
    _account_stretch_schedule,
    _edb_stretch_years,
    per_beneficiary_ten_year_drawdown,
)


def _rows_and_config(pretax_balance=200_000.0, ret=0.0):
    second_death_yr = 2050
    rows = [
        {"year": second_death_yr, "_account_balances": {"INHERITED_IRA": pretax_balance}},
    ]
    c = {
        "h_death_yr": second_death_yr - 2,
        "w_death_yr": second_death_yr,
        "h_dob_yr": 1955,
        "w_dob_yr": 1958,
        "h_rmd_start_age": 75,
        "w_rmd_start_age": 75,
        "ret": ret,
        "account_registry": [{"id": "INHERITED_IRA", "tax": "pre_tax", "label": "Inherited IRA"}],
        "roth_heir_filing_status": "Single",
    }
    return c, rows


def test_default_beneficiary_class_is_the_unchanged_ten_year_rule():
    c, rows = _rows_and_config()
    c["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A"}}
    result = per_beneficiary_ten_year_drawdown(c, rows)
    assert result["available"]
    account = result["beneficiaries"][0]["accounts"][0]
    assert account["beneficiary_class"] == "DESIGNATED"
    assert len(account["annual_schedule"]) == 10


def test_edb_class_uses_its_own_stretch_length_not_ten_years():
    c, rows = _rows_and_config()
    c["account_titling"] = {"INHERITED_IRA": {
        "primary_beneficiary": "Child A", "beneficiary_class": "EDB_DISABLED", "beneficiary_age": 40,
    }}
    result = per_beneficiary_ten_year_drawdown(c, rows)
    account = result["beneficiaries"][0]["accounts"][0]
    assert account["beneficiary_class"] == "EDB_DISABLED"
    assert len(account["annual_schedule"]) == _edb_stretch_years(40)
    assert len(account["annual_schedule"]) != 10


def test_every_edb_class_is_recognized():
    for cls in EDB_BENEFICIARY_CLASSES:
        c, rows = _rows_and_config()
        c["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "X", "beneficiary_class": cls}}
        result = per_beneficiary_ten_year_drawdown(c, rows)
        assert len(result["beneficiaries"][0]["accounts"][0]["annual_schedule"]) != 10, cls


def test_baseline_income_reduces_after_tax_proceeds_via_marginal_stacking():
    c_low, rows_low = _rows_and_config()
    c_low["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A", "beneficiary_baseline_income": 0.0}}
    low = per_beneficiary_ten_year_drawdown(c_low, rows_low)["beneficiaries"][0]["after_tax_total"]

    c_high, rows_high = _rows_and_config()
    c_high["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A", "beneficiary_baseline_income": 150_000.0}}
    high = per_beneficiary_ten_year_drawdown(c_high, rows_high)["beneficiaries"][0]["after_tax_total"]

    # A heir who already has substantial ordinary income pushes each slice
    # into a higher marginal bracket -- after-tax proceeds must be lower,
    # never equal (equal would mean baseline_income is silently ignored).
    assert high < low


def test_state_tax_reduces_after_tax_proceeds_when_a_supported_state_is_named():
    c_none, rows_none = _rows_and_config()
    c_none["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A", "beneficiary_state": ""}}
    no_state = per_beneficiary_ten_year_drawdown(c_none, rows_none)["beneficiaries"][0]["after_tax_total"]

    c_il, rows_il = _rows_and_config()
    c_il["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A", "beneficiary_state": "Illinois"}}
    with_state = per_beneficiary_ten_year_drawdown(c_il, rows_il)["beneficiaries"][0]["after_tax_total"]

    assert with_state < no_state


def test_unsupported_state_falls_back_to_federal_only_without_raising():
    c, rows = _rows_and_config()
    c["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A", "beneficiary_state": "Atlantis"}}
    result = per_beneficiary_ten_year_drawdown(c, rows)  # must not raise
    assert result["available"]


def test_account_stretch_schedule_fully_depletes_the_balance_with_no_growth():
    schedule = _account_stretch_schedule(100_000.0, 5, annual_growth_rate=0.0)
    assert len(schedule) == 5
    assert sum(schedule) == 100_000.0


def test_edb_stretch_years_is_bounded_and_uses_a_flat_default_with_no_age():
    from src.after_tax import DEFAULT_EDB_STRETCH_YEARS
    assert _edb_stretch_years(0) == DEFAULT_EDB_STRETCH_YEARS
    assert _edb_stretch_years(None) == DEFAULT_EDB_STRETCH_YEARS
    assert 10 <= _edb_stretch_years(85) <= 40
    assert 10 <= _edb_stretch_years(5) <= 40


def test_qss_dependent_infers_edb_minor_child_when_class_is_blank():
    # Acceptance criterion (system review Wave 3 table, item 3.3): beneficiary
    # class must default to a class INFERRED from existing data where
    # present, not silently stay DESIGNATED for every existing plan.
    # qss_dependent (Household, survivor_has_dependent) is the one existing
    # signal this codebase already carries for "there is a dependent child".
    c, rows = _rows_and_config()
    c["qss_dependent"] = True
    c["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A"}}
    result = per_beneficiary_ten_year_drawdown(c, rows)
    account = result["beneficiaries"][0]["accounts"][0]
    assert account["beneficiary_class"] == "EDB_MINOR_CHILD"
    assert account["class_was_inferred"] is True
    assert len(account["annual_schedule"]) != 10


def test_explicit_beneficiary_class_overrides_the_qss_dependent_inference():
    c, rows = _rows_and_config()
    c["qss_dependent"] = True
    c["account_titling"] = {"INHERITED_IRA": {
        "primary_beneficiary": "Child A", "beneficiary_class": "EDB_DISABLED",
    }}
    result = per_beneficiary_ten_year_drawdown(c, rows)
    account = result["beneficiaries"][0]["accounts"][0]
    assert account["beneficiary_class"] == "EDB_DISABLED"
    assert account["class_was_inferred"] is False


def test_no_qss_dependent_and_no_explicit_class_stays_designated():
    c, rows = _rows_and_config()
    c["qss_dependent"] = False
    c["account_titling"] = {"INHERITED_IRA": {"primary_beneficiary": "Child A"}}
    result = per_beneficiary_ten_year_drawdown(c, rows)
    account = result["beneficiaries"][0]["accounts"][0]
    assert account["beneficiary_class"] == "DESIGNATED"
    assert account["class_was_inferred"] is False
