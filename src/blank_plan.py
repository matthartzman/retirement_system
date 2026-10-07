"""Start New Plan on plan rows (WP4.5): which values a blank plan clears.

A new plan keeps every row (so the structure, units, notes and the policy settings stay) and
clears the household's own facts. The rules are those of the retired CSV templates:

* the policy and settings sections (``KEPT_SECTIONS``, the sections the old
  ``client_policy.csv``, ``client_optional_functions.csv`` and the optimizer controls file
  held, plus two HSA contribution flags that file carried) keep their values;
* a few rows are system defaults the input package curates, not facts about a household
  (``PRESERVED_SYSTEM_DEFAULT_KEYS``: inflation, COLA, annuity fallbacks, the Social Security
  funding-discount stress, the business valuation fallback); they keep their values too;
* every other row's value is cleared.

The row's own notes already say what a blank means ("blank = none"), which is the point of
clearing rather than deleting.
"""
from __future__ import annotations

from typing import Any

from .csv_exchange import PART_FILE_SECTIONS

# Rows a blank plan must still start from, because they are SYSTEM DEFAULTS that the input
# package curates -- not facts about a household. Blanking them does not give a new plan "no
# opinion"; it drops the engine onto whatever hardcoded fallback happens to exist in code,
# which is a different and undocumented number. The test is what the row's own notes claim:
# "Default 2032" and "default annual growth applied when an entity omits its own rate" are
# defaults and are preserved. Deliberately NOT preserved, because their notes show the stored
# value was a client OVERRIDE rather than the default:
#   Liquidity Buffer/years_of_expenses  -- "default is 0", stored 2
#   HSA Policy/hsa_withdrawal_mode      -- "default spend_as_needed", stored smooth_window
PRESERVED_SYSTEM_DEFAULT_KEYS = frozenset({
    # Economic and tax assumptions.
    ("Economic Assumptions", "", "inflation_general"),
    ("Economic Assumptions", "", "social_security_cola"),
    ("Economic Assumptions", "", "portfolio_nominal_return"),
    ("Economic Assumptions", "", "fed_tax_bracket_inflator"),
    ("Economic Assumptions", "", "social_security_taxable_fraction"),
    # Annuity fallbacks: apply ONLY to streams with no explicit rate of their own.
    ("Economic Assumptions", "", "annuity_default_dividend_rate"),
    ("Economic Assumptions", "", "annuity_default_additional_income_pct"),
    # Global dividend-reinvestment policy switch.
    ("Economic Assumptions", "", "reinvest_dividends_default"),
    # Social Security trust-fund underfunding stress (statutory-style defaults).
    ("Social Security", "Funding Discount", "ss_funding_discount_year"),
    ("Social Security", "Funding Discount", "ss_funding_discount_pct"),
    # Business-succession valuation fallback.
    ("Business Succession", "Policy", "valuation_growth_default"),
})

# Sections whose values a blank plan keeps: the old policy / optional-functions / optimizer
# controls files. ``HSA Policy`` was split: its rows were in the blanked assets file except
# these two flags, which the policy file held.
KEPT_SECTIONS = frozenset(
    set(PART_FILE_SECTIONS["client_policy.csv"])
    | set(PART_FILE_SECTIONS["client_optional_functions.csv"])
    | set(PART_FILE_SECTIONS["asset_class_optimizer_controls.csv"])
) - {"HSA Policy"} | {"Plan Settings"}  # Plan Settings: the plan tier row
KEPT_KEYS = frozenset({
    ("HSA Policy", "Contributions", "index_hsa_limit"),
    ("HSA Policy", "Contributions", "requires_hdhp"),
})


def keeps_value(section: str, subsection: str, label: str) -> bool:
    return (section in KEPT_SECTIONS or (section, subsection, label) in KEPT_KEYS
            or (section, subsection, label) in PRESERVED_SYSTEM_DEFAULT_KEYS)


def blank_plan_rows(store: Any, *, ytd_blend_enabled: bool | None = None) -> int:
    """Clear the household facts of the open plan's rows (inside the caller's transaction)
    and stamp ``Cashflow / Spending / ytd_blend_enabled`` when a choice is given. Returns the
    number of values cleared."""
    cleared = 0
    for row in store.all_rows():
        if row["value"] != "" and not keeps_value(row["section"], row["subsection"], row["label"]):
            store.set_row(row["row_id"], value="")
            cleared += 1
    if ytd_blend_enabled is not None:
        for row in store.find_rows("Cashflow", "Spending", "ytd_blend_enabled"):
            store.set_row(row["row_id"], value="TRUE" if ytd_blend_enabled else "FALSE")
    return cleared
