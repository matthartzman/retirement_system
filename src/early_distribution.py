"""Additional 10% tax on early retirement-account distributions (WI-039, FIN-004; IRC 72(t)).

A pure kernel. Taxable distributions from pre-tax accounts (traditional IRA, 401(k), 403(b),
SEP IRA) taken before the owner reaches 59½ carry a 10% additional tax unless an exception
applies. Scope (owner and CPA accepted, 2026-10-20):

* age 59½ and later: no tax; in the year 59½ is reached only the months before the birthday
  count (draws are assumed even through the year);
* rule of 55: separation from service in or after the year the owner turns 55 exempts that
  owner's employer-plan accounts (401(k), 403(b)) from the separation year on;
* disability: from the start year, all of that owner's pre-tax distributions are exempt;
* substantially equal periodic payments (SEPP): from the start year, up to the user-entered
  annual amount of that owner's pre-tax distributions is exempt (the schedule is entered, never
  computed, and a modified schedule is not modeled);
* death: a deceased owner has no draws.

Not modeled: higher-education, first-home, birth/adoption, medical, QDRO, levy and the other
72(t) exceptions; the Roth-conversion five-year rule (Roth withdrawals are treated as
exempt); state-level additional taxes. Roth conversions are not distributions here.
"""
from __future__ import annotations

from typing import Any, Mapping

EARLY_AGE_MONTHS = 59 * 12 + 6          # 59½
RULE_OF_55_AGE = 55
EMPLOYER_PLAN_TYPES = ("401k", "403b")
PRETAX_TYPES = ("traditional_ira", "401k", "403b", "sep_ira")


def early_fraction(year: int, dob_year: int, dob_month: int) -> float:
    """Share of ``year`` in which the owner is under 59½ (1 before, 0 after, partial in the year)."""
    idx = int(dob_year) * 12 + (int(dob_month or 1) - 1) + EARLY_AGE_MONTHS
    turn_year, turn_month = idx // 12, idx % 12
    if year < turn_year:
        return 1.0
    if year > turn_year:
        return 0.0
    return turn_month / 12.0


def early_distribution_tax(rate: float, year: int, draws_by_account: Mapping[str, float],
                           registry: list[Mapping[str, Any]], members: list[Mapping[str, Any]],
                           exceptions: Mapping[int, Mapping[str, Any]]) -> tuple[float, float]:
    """(tax, penalized_base) on this year's pre-tax draws.

    ``members``: dicts with ``dob_yr`` / ``dob_month`` (index = owner_idx). ``exceptions``: per
    owner index, optional ``separation_year``, ``disability_year``, ``sepp_year``, ``sepp_amount``.
    """
    if not draws_by_account:
        return 0.0, 0.0
    by_id = {a["id"]: a for a in registry}
    per_owner: dict[int, list[tuple[str, float]]] = {}
    for acct_id, amount in draws_by_account.items():
        acct = by_id.get(acct_id)
        if not acct or acct.get("acct_type") not in PRETAX_TYPES or float(amount or 0.0) <= 0.0:
            continue
        per_owner.setdefault(int(acct.get("owner_idx", 0)), []).append((acct["acct_type"], float(amount)))
    base = 0.0
    for owner, draws in per_owner.items():
        if owner >= len(members):
            continue
        m = members[owner]
        frac = early_fraction(year, m["dob_yr"], m.get("dob_month") or 1)
        if frac <= 0.0:
            continue
        ex = exceptions.get(owner) or {}
        dis = int(ex.get("disability_year") or 0)
        if dis and year >= dis:
            continue
        sep = int(ex.get("separation_year") or 0)
        rule55 = bool(sep and year >= sep and sep - int(m["dob_yr"]) >= RULE_OF_55_AGE)
        total = 0.0
        for acct_type, amount in draws:
            if rule55 and acct_type in EMPLOYER_PLAN_TYPES:
                continue
            total += amount
        sepp = int(ex.get("sepp_year") or 0)
        if sepp and year >= sepp:
            total = max(0.0, total - float(ex.get("sepp_amount") or 0.0))
        base += total * frac
    return rate * base, base
