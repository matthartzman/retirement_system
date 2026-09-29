"""WI-309 / FIN-012: heir other taxable income stacks under inherited-IRA slices."""
from src.after_tax import (DEFAULT_HEIR_OTHER_TAXABLE_INCOME, effective_heir_ten_year_rate,
                           resolve_heir_ordinary_rate)

BASE = {"plan_start": 2026, "plan_end": 2060, "roth_heir_filing_status": "Single", "brk_inf": 0.02}


def _rate(baseline):
    c = dict(BASE)
    if baseline is not None:
        c["roth_heir_other_taxable_income"] = baseline
    return effective_heir_ten_year_rate(c, 1_500_000)


def test_baseline_raises_derived_heir_rate():
    r0, r150 = _rate(0), _rate(150_000)
    assert r150 > r0 + 0.02


def test_blank_uses_default_and_zero_is_honored():
    assert _rate(None) == _rate(DEFAULT_HEIR_OTHER_TAXABLE_INCOME)
    assert _rate(0) < _rate(None)


def test_roth_legacy_rate_responds_and_explicit_override_wins():
    lo = resolve_heir_ordinary_rate({**BASE, "roth_heir_other_taxable_income": 0}, 1_500_000, 2060)
    hi = resolve_heir_ordinary_rate({**BASE, "roth_heir_other_taxable_income": 150_000}, 1_500_000, 2060)
    assert hi > lo
    assert resolve_heir_ordinary_rate(
        {**BASE, "roth_heir_ordinary_tax_rate_assumption": 0.30}, 1_500_000, 2060) == 0.30
