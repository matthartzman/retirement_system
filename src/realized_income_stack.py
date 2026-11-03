"""The year's ordinary-income stack that realized gains are priced on (sales ledger plan 7.1 / 7.2, gap (a)).

Built from the Planner's config for one tax year without running the projection: the first earner's earned income
(``realized_tax.plan_ordinary_income``), the pension and annuity streams (``core.annuity_cash_income`` on copies, as that
function keeps a payment cache on the stream), Social Security with its taxable part from
``core.social_security_taxable_amount``, and rental ordinary income from the ``RentalBook`` walked from plan start
(``rental_property.ordinary_income``). Not included: retirement withdrawals and RMDs (they depend on balances that only
the projection knows), investment income, the standard deduction, and the extra Social Security the gains themselves
make taxable. No I/O.

Social Security here is each living spouse's own benefit: the claim-age table entry, else PIA times the SSA claim factor
(mirrored from the projection's closure, which is not importable), indexed by ``ss_cola`` from the claim year. Spousal
top-up, the earnings test and survivor benefits are left out, so it is an estimate. The result says what it included.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .core import annuity_cash_income, social_security_taxable_amount
from .realized_tax import plan_ordinary_income

_FAR_FUTURE = 9999


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _fra(dob_year: int, override: Any) -> float:
    if _num(override) > 0:
        return float(override)
    if dob_year >= 1960:
        return 67.0
    if dob_year <= 1942:
        return 65.0 + max(0, dob_year - 1937) * (2.0 / 12.0)
    return 66.0 if dob_year <= 1954 else 66.0 + (dob_year - 1954) * (2.0 / 12.0)


def _claim_factor(claim_age: float, dob_year: int, override: Any) -> float:
    """SSA reduction (5/9 of 1% a month for 36 months, 5/12 beyond) or delayed credit (2/3 of 1% a month) vs. PIA."""
    months = int(round((claim_age - _fra(dob_year, override)) * 12))
    if months >= 0:
        return 1.0 + months * (0.08 / 12.0)
    early = -months
    return max(0.0, 1.0 - min(36, early) * (5.0 / 900.0) - max(0, early - 36) * (5.0 / 1200.0))


def _own_ss(c: Mapping[str, Any], who: str, year: int) -> float:
    dob = int(_num(c.get(f"{who}_dob_yr")))
    if not dob:
        return 0.0
    age = max(62, min(70, int(_num(c.get(f"{who}_ss_claim_age", c.get("ss_claim_age", 70))) or 70)))
    claim_year = int(_num(c.get(f"{who}_ss_claim_year")) or dob + age)
    if year < claim_year:
        return 0.0
    table = c.get(f"{who}_ss_benefit_table") or {}
    pia = _num(c.get(f"{who}_ss_pia")) or _num(table.get(67))
    precise = _num(c.get(f"{who}_ss_claim_age_precise")) or age
    monthly = _num(table.get(age)) or pia * _claim_factor(precise, dob, c.get(f"{who}_fra_age"))
    return monthly * 12.0 * (1.0 + _num(c.get("ss_cola"))) ** (year - claim_year)


def _rental_income(c: Mapping[str, Any], year: int, filing: str, other_income: float) -> float:
    from .projection_stages.rental_property import ordinary_income, rental_book_for
    book = rental_book_for(dict(c))
    if book is None:
        return 0.0
    ry = None
    for y in range(min(int(book.plan_start), year), year + 1):   # loan balances carry year to year
        ry = book.year_flows(y)
    return float(ordinary_income(ry, book.passive_result(ry, other_income, filing)))


def _stream(c: Mapping[str, Any], key: str, year: int) -> float:
    s = c.get(key)
    if not isinstance(s, dict) or s.get("enabled") is False:
        return 0.0
    return annuity_cash_income(deepcopy(s), year)


def _pension_and_annuity(c: Mapping[str, Any], year: int, h_alive: bool, w_alive: bool) -> tuple[float, float]:
    """The projection's own alive/survivor rules for the streams (income stage), on copies."""
    pension = _stream(c, "wife_pension", year) if w_alive else 0.0
    js = _num(c.get("js_pct"))
    ann = 0.0
    if w_alive:
        ann += _stream(c, "wife_single", year) + _stream(c, "wife_qlac", year)
    if h_alive:
        ann += _stream(c, "h_single", year) + _stream(c, "h_qlac", year)
    if w_alive or h_alive:
        ann += _stream(c, "wife_joint", year) * (1.0 if w_alive else js)
        ann += _stream(c, "h_joint", year) * (1.0 if h_alive else js)
    return pension, ann


def plan_income_stack(c: Mapping[str, Any], year: int, filing: str | None = None) -> dict[str, Any]:
    """Components of the year's ordinary income from the built plan config, their total (``ordinary_income``) and the
    ``included`` names and ``label`` for the estimate note. Each piece fails to zero on its own so a partial plan still prices."""
    year = int(year)
    filing = str(filing or c.get("filing_status", "MFJ") or "MFJ")
    h_alive = year <= int(_num(c.get("h_death_yr")) or _FAR_FUTURE)
    w_alive = year <= int(_num(c.get("w_death_yr")) or _FAR_FUTURE)
    earned = plan_ordinary_income(c, year)
    try:
        pension, annuity = _pension_and_annuity(c, year, h_alive, w_alive)
    except Exception:  # noqa: BLE001
        pension = annuity = 0.0
    try:
        gross_ss = (_own_ss(c, "h", year) if h_alive else 0.0) + (_own_ss(c, "w", year) if w_alive else 0.0)
    except Exception:  # noqa: BLE001
        gross_ss = 0.0
    try:
        rental = _rental_income(c, year, filing, earned + pension + annuity)
    except Exception:  # noqa: BLE001
        rental = 0.0
    other = max(0.0, earned + pension + annuity + rental)
    ss_taxable = social_security_taxable_amount(gross_ss, other, filing)
    parts = {"earned": earned, "pension": pension, "annuity": annuity, "rental": rental,
             "social_security": gross_ss, "social_security_taxable": ss_taxable}
    names = (("earned income", "earned"), ("pension", "pension"), ("annuity income", "annuity"),
             ("taxable Social Security", "social_security_taxable"), ("rental income", "rental"))
    included = [label for label, key in names if parts[key]]
    return {**{k: round(v, 2) for k, v in parts.items()}, "ordinary_income": round(other + ss_taxable, 2),
            "included": included, "label": income_label(included)}


def income_label(included: list[str]) -> str:
    """Words for the estimate note: what the gains are stacked on and what is left out."""
    base = ", ".join(included) if included else "no other ordinary income"
    return (f"Estimate: gains are stacked on the plan's {base}. Retirement withdrawals and required minimum "
            "distributions are not included.")
