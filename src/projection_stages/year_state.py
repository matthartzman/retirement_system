from __future__ import annotations

"""Mutable per-run/year state separated from immutable run configuration.

The deterministic legacy math mutates account balances, mortality state, and
intermediate balances by year.  v10 keeps that mutability in this explicit state
container so configuration objects can remain immutable at the run boundary.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class MutableYearState:
    balances: dict[str, float] = field(default_factory=dict)
    basis_free_balances: dict[str, float] = field(default_factory=dict)
    home_value: float = 0.0
    autos_value: float = 0.0
    startup_value: float = 0.0
    note_balance: float = 0.0
    filing_status: str = "MFJ"
    first_death_done: bool = False
    cst_funded_total: float = 0.0
    cst_balance: float = 0.0
    # Net capital-loss carryforward (magnitude, >= 0) rolled between years:
    # harvested/realized losses beyond current-year gains + the $3k ordinary
    # offset accumulate here and offset future gains first.
    cap_loss_carryforward: float = 0.0


def create_initial_year_state(config: Mapping[str, Any]) -> MutableYearState:
    balances = {str(k): float(v or 0.0) for k, v in dict(config.get("balances", {}) or {}).items()}
    for acct_id in config.get("all_acct_ids", []) or []:
        balances.setdefault(str(acct_id), 0.0)
    return MutableYearState(
        balances=balances,
        basis_free_balances={str(aid): 0.0 for aid in config.get("taxable_ids", []) or []},
        home_value=float(config.get("home_val", 0.0) or 0.0),
        autos_value=float(config.get("autos", 0.0) or 0.0),
        startup_value=float(config.get("startup_eq", 0.0) or 0.0),
        note_balance=float(config.get("note_face", 0.0) or 0.0),
        filing_status=str(config.get("filing_status", "MFJ") or "MFJ"),
    )
