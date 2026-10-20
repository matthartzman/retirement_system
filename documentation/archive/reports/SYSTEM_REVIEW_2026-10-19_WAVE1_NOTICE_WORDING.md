# System Review 2026-10-19 — Wave 1 Notice Wording (WI-010, WI-010a)

Wording approved by the repository owner on 2026-10-20. Companion to `SYSTEM_REVIEW_2026-10-19.md` section 9 (Wave 1). Notices change no calculation. Each has a retirement trigger; remove the notice when the trigger is met. Surfaces for every notice: preflight, Tax Assumptions page, workbook and advisor report, for affected plans only.

## WI-010a — interim notices

| ID | Finding | Severity | Shown when | Removed when |
|---|---|---|---|---|
| N1 | FIN-001 | warning | Plan sells taxable holdings at a gain | Phase 1 (IRMAA) ships: update wording. Phase 2 (NIIT, ACA, Social Security) ships: remove |
| N2 | FIN-003 | info | Plan has taxable equity holdings | Qualified-dividend stacking fix ships |
| N3 | FIN-004 | warning | Plan has pre-tax draws before age 59½ | Early-withdrawal tax is modeled |
| N4 | FIN-010 | info | Plan has joint taxable accounts | Symmetric step-up fix ships |

**N1.** Gains from selling taxable investments are not yet counted as income in the Medicare (IRMAA), net investment income tax, ACA subsidy and Social Security taxation calculations. Federal income tax on those gains is calculated. Results may be optimistic for plans that fund spending from appreciated taxable holdings.

**N2.** Qualified dividends are currently taxed at ordinary rates instead of the lower 0%, 15% and 20% rates. Estimated federal tax is overstated (conservative) for plans with taxable stock holdings.

**N3.** Withdrawals from IRAs and 401(k)s before age 59½ may carry a 10% additional tax unless an exception applies. This version does not calculate that tax, so plans that draw from pre-tax accounts before 59½ may look more sustainable than they are.

**N4.** When the spouse who does not own a joint taxable account dies first, the survivor's step-up in cost basis is not modeled. Later capital gains tax may be overstated in that case.

## WI-010 — decision-dependent notices

| ID | Finding | Severity | Shown when | Removed when |
|---|---|---|---|---|
| N5 | FIN-007 | warning | Claim age is before full retirement age and wages continue | Earnings test is modeled |
| N6 | FIN-009 | warning | Household has one member | Exemption is derived from the household |
| N7 | FIN-005, FIN-006 | info | Always (data status) | A data family is updated and verified: change its status |

**N5.** The Social Security earnings test is not modeled. If you claim before full retirement age while still earning wages, some benefits may be temporarily withheld, and this plan does not reflect that.

**N6.** The estate tax calculation uses a default exemption sized for a married couple using portability. For a one-person household the exemption is lower, so estimated federal estate tax may be understated.

**N7.** Shown as a per-family status list (verified / assumption / unreviewed) for: federal tables, AMT, state income tax, state estate tax, mortality, Part D. Status values are taken from the dataset and must not read "verified" for a family whose values have not been updated and checked. Exact status strings are to be set from the reference-data status vocabulary during implementation.

## Implementation notes

- Planner reviews the final rendered text before release; wording above is approved as the source text.
- Each notice needs a preflight unit test and a retirement check that it is removed when its trigger ships.
- N7 is not yet implementable as a single status until the AMT and state values are actually updated; until then those families show "assumption" or "unreviewed".
