# Cash pair-status tax floor: worked example for owner approval

Date: 2026-11-03.

Status: implemented, default OFF; mechanism approved by the owner 2026-11-03, turn-on not approved. Synthetic frozen sample plan only (the golden-master fixture); no real data.

## What was built (behind `Cashflow / Cash Tracking / cash_pair_status_tax`, default FALSE)

The "floor" mechanism you chose. For the plan's first year only, cash the ledger reports as an `external_withdrawal` from a **pre-tax** account is forced out of that account and taxed as ordinary income exactly like an RMD (it is added to `rmd_taxable_total`, which both taxes it and counts it as cash toward spending). Internal pairs, `unmatched` rows and `excess_return` add nothing. Taxable, Roth and HSA accounts are **not** wired: they need lot basis or qualified-withdrawal rules, so they are still report-only. Code: `src/cash_tax_floor.py`, one seam in `spending_and_rmd.py`, fed in `report_compute.run_projection_artifacts`.

**Off:** engine output is byte-identical (`measure` MATCH, delta 0.00; test compares full projection rows). The setting has no UI row yet; turning it on means adding the plan-data row.

## Numbers (sample plan, plan start 2026; `Member_2_IRA` balance 465,649)

Baseline year 1: draws only from the two Trust accounts (1,621 and 2,601), total tax 98,956.

| Reported external withdrawal from Member_2_IRA | Year-1 draws | Year-1 tax | Lifetime tax | Terminal NW |
|---|---|---|---|---|
| none (baseline / setting OFF) | Trusts 4,222 | 98,956 | 1,239,362 | 5,376,101 |
| 8,000 | IRA 8,000, Trusts 0 | 98,832 (-124) | 1,234,749 (-4,613) | 5,384,322 (+8,221) |
| 30,000 | IRA 30,000, Trusts 0 | 104,139 (+5,183) | 1,229,650 (-9,712) | 5,377,248 (+1,147) |

Reading it: the IRA dollars are taxed as ordinary income, but they also cover the spending the Trusts would otherwise fund, so the Trust gains are no longer realised and year-1 tax can fall for a small draw. Lifetime tax falls in both cases because the draw moves money out of a pre-tax account early at a low bracket. This is the mechanism working as designed, but it is a **behaviour change, not a pure floor**: the forced draw displaces planned Trust draws rather than adding to them.

`excess_return`: untaxed, no engine path (the engine never sees contributions), so nothing changes; the Cash panel still flags the user to enter the taxable earnings. CASH-lot per-class treatment: the audit (cash plan section 10) found no inconsistency, so no engine change; the one hazard is a hand-entered CASH lot with blank `purchase_price` in a taxable account.

## Decisions needed from you

1. Is "forced draw credited as cash, displacing planned draws" the behaviour you want, or should reported draws be *added on top* of the plan's draws (a strict floor per account)?
2. Approve extending to taxable / Roth / HSA accounts later (needs basis and qualified-withdrawal rules)?
3. Only after a yes: add the setting row and test on real data. No golden-master pin changes anywhere in this work.

## Owner answers (2026-11-03)

1. Mechanism: **displace, as built** (approved).
2. Scope: extend later to taxable, Roth and HSA. Not built: each needs its own rules (taxable: lot basis and gain; Roth: contributions-first, age and 5-year tests; HSA: qualified medical vs not) and will be designed and reviewed as separate steps, still behind the same OFF setting.
3. Rollout: the setting row now exists (`Cashflow / Cash Tracking / cash_pair_status_tax`, default FALSE). Test on real data before turning it on; no pin changes.

## HSA extension (owner choice 2026-11-03: bank-capped, income tax only)

Engine facts found first: every HSA draw the cascade makes is treated as qualified; `withdraw_hsa_window` computes `taxable_amount` and a 20% pre-65 `penalty` but no caller feeds them into tax; a blank `hsa_expense_bank` means unlimited in `hsa_available_to_draw` but starts at 0 in the projection loop.

Built (still behind `cash_pair_status_tax`, default OFF): a reported HSA `external_withdrawal` is qualified up to the entered bank (blank bank = all qualified); only the excess is drawn from the HSA in the first year and taxed as ordinary income through the same RMD-style channel. The qualified part is left to the cascade. **Not fed:** the 20% pre-65 penalty (no insertion point in that stage).

Sample plan (Member_1_HSA 72,730, owner age 64), reported HSA withdrawal 6,000:

| Expense bank | Forced HSA draw | Year-1 tax | Lifetime tax | Terminal NW |
|---|---|---|---|---|
| 1,000 (OFF) | none | 98,956 | 1,239,362 | 5,376,101 |
| 1,000 (ON) | 5,000 | 98,109 (-847) | 1,237,617 (-1,745) | 5,378,526 (+2,425) |
| 6,000 (ON) | none (all qualified) | 98,956 | 1,239,362 | 5,376,101 |

The 5,000 excess would carry a 20% penalty of 1,000 at age 64; that is **not** in these numbers. As with the pre-tax floor, the forced draw displaces planned Trust draws, so year-1 tax can fall. Taxable and Roth are still report-only.
