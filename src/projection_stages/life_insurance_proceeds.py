"""In-force life-insurance death benefits (FIN-005 option A).

Behind the Existing Life Insurance module switch, a death in the projection
pays each in-force policy on the decedent's life. Premiums are not modelled in
the projection cash flow, so there is nothing to stop; only the benefit is
added.

Routing (assumptions the planner reviews):
* Policy not owned by an ILIT: the face amount is paid into the survivor's
  taxable account (cash if none) at a first death, or into the estate account
  at the last death. Because it lands in a balance it is part of the estate
  base automatically.
* Policy owned by an ILIT: proceeds go to the trust, outside the survivor's
  estate, so no balance is credited. The amount is returned for reporting.
* A term policy pays only when the death year is within term_end_year (when set).
"""
from __future__ import annotations

from typing import Any

from .. import core as _aa
from .. import core as _ar


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def policy_insured_idx(c: dict[str, Any], policy: dict[str, Any]) -> int | None:
    """0 / 1 for the member a policy insures, None when it cannot be matched."""
    insured = _norm(policy.get('insured'))
    if not insured:
        return None
    labels = {
        0: {_norm(c.get('h_name')), _norm(c.get('h_nick')), 'member 1', 'member_1', 'h', 'husband'},
        1: {_norm(c.get('w_name')), _norm(c.get('w_nick')), 'member 2', 'member_2', 'w', 'wife'},
    }
    for idx, names in labels.items():
        if insured in {n for n in names if n}:
            return idx
    return None


def life_insurance_enabled(c: dict[str, Any]) -> bool:
    return bool((c.get('opt') or {}).get('existing_life_insurance')) and bool(c.get('life_policies'))


def apply_life_insurance_proceeds(
    c: dict[str, Any],
    *,
    year: int,
    inher: Any,
    bal: dict[str, float],
    account_transfers_in: dict[str, float],
) -> tuple[float, float]:
    """Pay death benefits for the member whose death this year's transition just handled.

    Returns ``(paid_to_estate_or_survivor, paid_to_ilit)`` for the year.
    """
    if not life_insurance_enabled(c) or not getattr(inher, 'description', ''):
        return 0.0, 0.0
    deceased = inher.deceased_owner_idx          # None for a simultaneous death
    death_year = int(year)
    second_death = inher.survivor_owner_idx is None
    paid = ilit = 0.0
    target = None
    for policy in c['life_policies']:
        insured_idx = policy_insured_idx(c, policy)
        if insured_idx is None or (deceased is not None and insured_idx != deceased):
            continue
        term_end = int(policy.get('term_end_year') or 0)
        if term_end and death_year > term_end:
            continue
        face = max(0.0, float(policy.get('face_amount') or 0.0))
        if face <= 0:
            continue
        if policy.get('owned_by_ilit'):
            ilit += face
            continue
        if target is None:
            target = _proceeds_account(c, inher, second_death)
        if not target:
            continue
        bal[target] = float(bal.get(target, 0.0) or 0.0) + face
        account_transfers_in[target] = account_transfers_in.get(target, 0.0) + face
        paid += face
    return paid, ilit


def _proceeds_account(c: dict[str, Any], inher: Any, second_death: bool) -> str | None:
    if second_death:
        return inher.estate_account or _aa.first_taxable(c) or None
    registry = c.get('account_registry', [])
    survivor = inher.survivor_owner_idx
    try:
        taxable = _ar.ids_by_tax(registry, 'taxable', survivor)
    except Exception:
        taxable = list(c.get('taxable_ids', []))
    if taxable:
        return taxable[0]
    cash = list(c.get('cash_ids', []))
    return cash[0] if cash else (inher.estate_account or None)
