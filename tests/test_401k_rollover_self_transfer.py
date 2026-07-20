"""Regression: the workplace-plan rollover must never misplace the 401(k).

The engine rolls member 1's workplace plan into member 1's traditional IRA at
``rollover_401k_yr``. When that member has no traditional IRA the destination
lookup used to degrade in two ways, both destructive:

* ``first_account(..., acct_type='traditional_ira')`` returns ``all_acct_ids[0]``
  — an arbitrary account of *any* tax type — when nothing matches. In the
  fixture below that is a checking account, so the entire pre-tax balance was
  transferred into cash, untaxed, and vanished from ``pretax_nw``.
* The ``or first_pretax(...)`` fallback resolves to the 401(k) itself (a 401(k)
  is pre-tax), so the transfer credited and immediately zeroed the same
  account, destroying the balance outright.

Either way the pre-tax position disappeared in the rollover year, suppressing
every downstream RMD and Roth conversion.

A household with a 401(k) and no IRA is ordinary, so this is pinned here rather
than worked around in the fixtures. See tests/synthetic_plans.py, whose standard
account set gives member 1 both accounts for a different reason (keeping the
rollover a *real* transfer so the golden master exercises it).
"""
from __future__ import annotations

import copy
import os
import unittest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from tests.synthetic_plans import PLAN_START, base_plan


def _plan_401k_only() -> dict:
    """The synthetic baseline, with member 1's traditional IRA removed.

    Member 1's only pre-tax account is now the 401(k), which is exactly the
    shape that made the destination lookup resolve back to the source.
    """
    plan = copy.deepcopy(base_plan())
    plan["accounts"] = [a for a in plan["accounts"] if a["id"] != "Member_1_IRA"]
    return plan


def _build(rollover_year: int) -> dict:
    c = build_plan_from_json(_plan_401k_only(), "")
    c = ensure_engine_config(c, source="rollover_regression")
    c["rollover_401k_yr"] = rollover_year
    # Roth conversions are left at the plan's own policy: a wiped pre-tax
    # balance would silently zero them, so they are part of what is asserted.
    return c


class WorkplaceRolloverSelfTransferTests(unittest.TestCase):

    def test_pretax_balance_survives_the_rollover_year(self):
        rollover_year = PLAN_START + 4
        rows = {int(r["year"]): r for r in project(_build(rollover_year))}

        before = float(rows[rollover_year - 1].get("pretax_nw", 0) or 0)
        during = float(rows[rollover_year].get("pretax_nw", 0) or 0)

        self.assertGreater(before, 0.0, "fixture must hold a pre-tax balance")
        # Growth, contributions, withdrawals and conversions all move this
        # year over year; a self-transfer bug removes member 1's entire 401(k)
        # at once. Anything within a normal year's drift clears this bound.
        self.assertGreater(
            during, before * 0.80,
            f"pre-tax balance collapsed across the rollover year: "
            f"{before:,.0f} -> {during:,.0f}",
        )

    def test_no_rollover_is_reported_when_there_is_no_destination(self):
        rollover_year = PLAN_START + 4
        rows = {int(r["year"]): r for r in project(_build(rollover_year))}
        self.assertEqual(
            0.0, float(rows[rollover_year].get("k401_rollover", 0) or 0),
            "a household with no owner-0 IRA has nothing to roll into",
        )

    def test_rollover_year_does_not_change_the_projection(self):
        """With no destination the rollover is inert, so moving it is a no-op.

        This catches a partial fix that leaves the source account short by any
        amount, not just one that zeroes it outright.
        """
        early = project(_build(PLAN_START + 4))[-1]
        late = project(_build(PLAN_START + 9))[-1]
        self.assertAlmostEqual(
            float(early.get("total_nw", 0) or 0),
            float(late.get("total_nw", 0) or 0),
            places=2,
        )

    def test_no_balance_is_transferred_into_a_non_pretax_account(self):
        """The destination must never be cash/Roth/HSA picked by the id fallback.

        ``pretax_nw`` collapsing while ``total_nw`` held up was the signature of
        the original failure: the money was still in the plan, but it had been
        moved into checking and was no longer taxable on the way out.
        """
        rollover_year = PLAN_START + 4
        rows = {int(r["year"]): r for r in project(_build(rollover_year))}
        row = rows[rollover_year]
        for acct_id, amt in (row.get("_account_transfers_in") or {}).items():
            self.assertEqual(
                0.0, float(amt or 0),
                f"rollover year moved {amt:,.0f} into {acct_id}; "
                f"there is no valid destination in this household",
            )

    def test_rollover_still_transfers_when_an_ira_destination_exists(self):
        """The fix must not disable the real rollover path."""
        rollover_year = PLAN_START + 4
        c = build_plan_from_json(copy.deepcopy(base_plan()), "")
        c = ensure_engine_config(c, source="rollover_regression")
        c["rollover_401k_yr"] = rollover_year
        rows = {int(r["year"]): r for r in project(c)}
        self.assertEqual(
            1.0, float(rows[rollover_year].get("k401_rollover", 0) or 0),
            "member 1 owns both a 401(k) and an IRA here, so the rollover runs",
        )


if __name__ == "__main__":
    unittest.main()
