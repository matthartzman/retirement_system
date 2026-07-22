"""Canonical financial/planning-term glossary (system review 2026-07-21, D3).

Single source of truth for plain-language term definitions consumed by both
the front end (via GET /api/glossary, fetched once on load and merged over
frontend/js/dashboard.js's local ACRONYM_DEFINITIONS fallback) and the
workbook's Glossary sheet (src/reporting/sheets_qc_reference.py:build_sheet22).
Before this module, the two carried independently-maintained lists that had
already drifted (divergent IRMAA wording); reconciled here using the fuller
of the two wordings.

Deliberately excludes purely technical/app-internal terms (API, CSV, JSON,
YAML, SQLite, UI, the FMP data-provider name) that make sense in an in-app
help panel but not in a client-facing financial-plan glossary -- those stay
local to dashboard.js's ACRONYM_DEFINITIONS.
"""
from __future__ import annotations

from .core import salt_cap, TAX_BASE_YEAR
from .taxes import SALT_REVERSION_YEAR

GLOSSARY: dict[str, str] = {
    "DOB": "Date of birth",
    "RMD": "Required Minimum Distribution — mandatory annual withdrawals from tax-deferred accounts starting at age 72, 73, or 75 depending on birth year per SECURE 2.0",
    "NIIT": "Net Investment Income Tax — a 3.8% surtax on investment income above MAGI thresholds",
    "SS": "Social Security",
    "MFJ": "Married filing jointly",
    "IRMAA": "Income-Related Monthly Adjustment Amount — a Medicare Part B/D premium surcharge for higher-income beneficiaries, based on MAGI from two years prior",
    "LTCG": "Long-Term Capital Gain — gain on assets held more than one year, taxed at preferential rates",
    "PCT": "Percent",
    "HSA": "Health savings account",
    "DAF": "Donor Advised Fund — a charitable giving vehicle allowing an immediate deduction with delayed grant-making",
    "LTC": "Long-term care",
    "QCD": "Qualified Charitable Distribution — an IRA distribution sent directly to charity, excluded from AGI",
    "QBI": "Qualified business income",
    "W-2": "Wage and Tax Statement",
    "S-Corp": "S corporation",
    "SDI": "State disability insurance",
    "SSDI": "Social Security Disability Insurance",
    "SSI": "Supplemental Security Income",
    "ABLE": "Achieving a Better Life Experience (a tax-advantaged savings account for disability-related expenses)",
    "QTIP": "Qualified Terminable Interest Property trust — provides income to a surviving spouse while preserving remainder control",
    "IRA": "Individual retirement account",
    "Roth": "Roth retirement account",
    "Roth Conversion": "Transfer from a pre-tax IRA to a Roth IRA, triggering ordinary income tax in the conversion year",
    "PV": "Present value",
    "AGI": "Adjusted Gross Income — gross income minus above-the-line deductions",
    "MAGI": "Modified Adjusted Gross Income — AGI with certain deductions added back",
    "CPI": "Consumer Price Index",
    "COLA": "Cost-of-living adjustment",
    "ETF": "Exchange-traded fund",
    "REIT": "Real estate investment trust",
    "REITs": "Real estate investment trusts",
    "TIPS": "Treasury Inflation-Protected Securities",
    "Monte Carlo": "Statistical simulation using repeated random scenarios to model a range of outcomes",
    "OOP": "Out-of-pocket",
    "SEHI": "Self-employed health insurance",
    "PDIA": "Participating deferred income annuity",
    "PIA": "Primary Insurance Amount — Social Security's base monthly benefit at Full Retirement Age before early-claiming reductions or delayed-retirement credits",
    "FRA": "Full Retirement Age — the Social Security age when the unreduced base benefit is available",
    "HELOC": "Home equity line of credit",
    "QSS": "Qualifying Surviving Spouse — the filing status available to a surviving spouse with a dependent for up to two years after the year of death, using MFJ tax brackets",
    "CST": "Credit-Shelter Trust — an estate-planning trust that shelters up to the deceased spouse's federal exemption from estate tax at the survivor's later death",
    "Credit-Shelter Trust": "A trust designed to use a decedent's estate tax exemption, sheltering assets from tax at the survivor's later death",
    "Sharpe": "Sharpe ratio — a measure of risk-adjusted return: how much extra return a portfolio earns per unit of volatility risk taken",
    "tangency": "Tangency portfolio — the single asset mix that maximizes the Sharpe ratio, with no additional risk-limit constraint applied",
    "Basis": "The original cost of an asset, used to figure capital gain or loss when it's sold",
    "ILIT": "Irrevocable Life Insurance Trust — removes life insurance proceeds from the taxable estate",
    "Joint-and-Survivor": "An annuity or pension feature (J&S) that pays a reduced benefit to a surviving spouse after the primary annuitant's death",
    "Percentile Band": "The value at or below which a given share of Monte Carlo simulation results fall",
    "Sec. 121 Exclusion": "Up to $500,000 (MFJ) of home-sale gain excluded from federal income tax",
    "Sequence-of-Returns Risk": "The risk that poor investment returns early in retirement permanently impair a portfolio, even when average returns are fine over the full horizon",
    "Spousal Rollover": "A surviving spouse's option to inherit a deceased spouse's IRA as their own, deferring RMDs to their own age",
    "Standard Deduction": "The tax-reference-year MFJ base plus over-65 add-ons; inflated annually",
    "Step-Up in Basis": "Reset of an asset's cost basis to fair market value at death for non-retirement assets, erasing built-in gain for the heir",
}


def _salt_cap_definition(tax_year: int) -> str:
    cap_now = int(salt_cap(tax_year, 0))
    revert_year = SALT_REVERSION_YEAR
    return (
        f"A federal limit on how much state and local tax (income and property tax combined) a "
        f"household can deduct on its federal return. For {tax_year}, the cap is "
        f"${cap_now:,} — it shrinks for very high incomes and is currently scheduled to "
        f"drop back to $10,000 starting in {revert_year}. This figure changes by tax year."
    )


def build_glossary(tax_year: int = TAX_BASE_YEAR) -> dict[str, str]:
    """Return the full canonical glossary, including the tax-year-dependent
    SALT Cap definition computed fresh for ``tax_year``."""
    terms = dict(GLOSSARY)
    terms["SALT Cap"] = _salt_cap_definition(tax_year)
    return terms
