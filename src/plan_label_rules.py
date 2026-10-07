"""The label rules every plan reader and importer applies to a plan row (single source).

Two rules lived in several copies (``data_io``, the retired ``config_backend`` loader,
``csv_exchange``, ``active_plan``, conversion step C3) and had to be kept equal by a test.
This module is the one definition:

* **Year-stamped labels** (``annual_spending_2026``) are stored and read under a canonical
  name (``annual_spending_base_year``): :func:`canonical_label`.
* **Retired ``Scenarios / Sell Home`` home-value labels**: the Sell Home scenario once
  carried its own copy of the home's value and basis; the current model reads them from
  Other Assets, and the legacy loader dropped them at every load:
  :func:`is_retired_scenario_home_row`.

Pure, no imports beyond ``re``.
"""
from __future__ import annotations

import re

YEAR_LABEL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^annual_401k_limit_\d{4}$"), "annual_401k_limit_base_year"),
    (re.compile(r"^annual_spending_\d{4}$"), "annual_spending_base_year"),
    (re.compile(r"^balance_\d{1,2}_\d{1,2}_\d{4}$"), "balance_as_of_plan_start"),
    (re.compile(r"^value_\d{1,2}_\d{1,2}_\d{4}$"), "value_as_of_plan_start"),
    (re.compile(r"^family_annual_limit_\d{4}$"), "family_annual_limit_base_year"),
    (re.compile(r"^self_only_annual_limit_\d{4}$"), "self_only_annual_limit_base_year"),
    (re.compile(r"^coverage_\d{4}_family_months$"), "coverage_base_year_family_months"),
    (re.compile(r"^coverage_\d{4}_self_only_months$"), "coverage_base_year_self_only_months"),
    (re.compile(r"^ss_wage_base_\d{4}$"), "ss_wage_base_base_year"),
    (re.compile(r"^ltcg_0pct_top_mfj_\d{4}$"), "ltcg_0pct_top_mfj_base_year"),
    (re.compile(r"^ltcg_15pct_top_mfj_\d{4}$"), "ltcg_15pct_top_mfj_base_year"),
    (re.compile(r"^part_b_premium_\d{4}$"), "part_b_base_premium_monthly"),
    (re.compile(r"^part_d_premium_\d{4}$"), "part_d_base_premium_monthly"),
    (re.compile(r"^annual_premium_\d{4}$"), "annual_premium_base_year"),
)

RETIRED_SCENARIO_HOME_LABELS = frozenset({
    "home_sale_price", "home_basis", "home_value", "house_value", "value_as_of_plan_start",
    "current_home_value", "current_value", "market_value",
})


def canonical_label(label: object) -> str:
    """Strip a label and map a year-stamped one to its canonical name."""
    text = str(label or "").strip()
    for pattern, replacement in YEAR_LABEL_PATTERNS:
        if pattern.match(text):
            return replacement
    return text


def is_retired_scenario_home_row(section: str, subsection: str, label: str) -> bool:
    """``True`` for a ``Scenarios / Sell Home`` row the current model no longer reads."""
    return section == "Scenarios" and subsection == "Sell Home" and label in RETIRED_SCENARIO_HOME_LABELS
