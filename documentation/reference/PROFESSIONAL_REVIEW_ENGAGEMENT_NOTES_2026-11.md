# Professional review engagement notes (from the 2026-11-10 system review)

Prepared in Wave 1 (item W1-07). Starting these engagements is the plan owner's task; Claude cannot do it.
Source findings are in `documentation/archive/reports/SYSTEM_REVIEW_2026-11-10.md` (grep the finding id).
Give the professionals the rule and the question only. Do not send plan files or account numbers.

Start both engagements now. Waves 2 and 3 run in parallel with the waiting time, and the Wave 3 engine changes
(FIN-001, 002, 003, 008) and the Illinois estate-tax rewrite (FIN-004) are gated on the answers.

## 1. One CPA engagement (batch FIN-001, FIN-002, FIN-003, FIN-008, FIN-011, wash-sale W1, optional FIN-006)

| Id | What the engine does today | Question for the CPA |
|---|---|---|
| FIN-001 | QBI deduction is a flat 20% of business income, with no taxable-income cap, threshold, SSTB test or W-2 wage / UBIA limit. | Confirm the 2026 threshold and phase-in values, and whether the household business is an SSTB. Is the plan to model the 20% of (taxable income less net capital gain) cap and the W-2 wage limit correct? |
| FIN-002 | The OBBBA senior deduction phase-out is applied once to the couple's combined $12,000. | Is the $6,000 deduction and its 6% phase-out per person, so that each qualifying spouse is reduced separately? Confirm the MAGI threshold for joint filers. |
| FIN-003 | SALT deduction uses AGI x the flat state rate, which counts income Illinois does not tax. | Should SALT come from the actual state tax computed (retirement income and Social Security excluded), or from the prior-year amount paid, given cash-basis timing? |
| FIN-008 | Illinois 1.5% S-corp replacement tax is not modeled, and a code comment wrongly says it is. | Confirm the base for the replacement tax and how a pass-through entity tax election would interact. The plan will note that PTE elections are not modeled. |
| FIN-011 | Reference tables stop at 2026 and the 2027 plan year is close. | Verify the 2027 rows and the state-tax rows (the dashboard marks states as review required) when the Rev. Proc. and CMS sheet are published. |
| Wash-sale W1 | A purchase made with shares sold in the same sale is not treated as a replacement (`2026-11-09-sales-ledger-v3-design.md`, line 265). | Confirm rule W1 before release. |
| FIN-006 (optional) | Self-employed health insurance deduction is also counted as itemized medical and is not reduced by the ACA premium credit. | Confirm the Rev. Proc. 2014-41 iterative method and that SEHI should be netted out of itemized medical. |

## 2. Estate attorney (or Illinois Attorney General calculator comparison): FIN-004, FIN-007

| Id | What the engine does today | Question |
|---|---|---|
| FIN-004 | Illinois estate tax applies the old state death tax credit table to the whole estate, with no $60,000 adjustment and no limit at the federal tax over a $4M exclusion. | Confirm the Illinois method: adjusted taxable estate = taxable estate - $60,000; credit = lesser of the table amount and the tentative federal tax with a $4M exclusion; and the interrelated deduction. A quicker first step is to run the Illinois Attorney General estate tax calculator at $4.05M, $4.5M, $5M and $10M and record the results as test points. |
| FIN-007 | After the first death, the deceased spouse's unused federal exemption keeps inflating. | Confirm the portability treatment: freeze the DSUE at the first-death year's indexed amount, index only the survivor's own exclusion, assume a timely election, and say how IRC 2058 applies to the state-tax deduction. |

## 3. Questions still open with the CPA (added 2026-11-11, after the first answers)

Send the rule and the question only. The owner fills the bracketed facts; they are not stored in this file.

**QBI: is the household business a specified service trade or business (SSTB)? (sets `qbi_sstb`)**

> Our S-corporation [one-sentence description of what the business sells and who it sells to] is owned [percent] by [owner]. Under IRC 199A(d)(2) and Treas. Reg. 1.199A-5, is it an SSTB, taking into account the "reputation or skill" catch-all and the de minimis rule (10% of gross receipts when receipts are $25 million or less)?
> If we are not an SSTB today, would anything we expect to change in 2027 or later (a new service line, a change in how clients are billed, a second entity) make us one?
> For the 2026 plan year our projected taxable income before the QBI deduction is about [amount]. The 2026 threshold is $403,500 (joint) and the phase-in range ends at $553,500. Does SSTB status change our deduction at that income, or only above the threshold?
> If W-2 wages are the limiting factor, are the wages paid to the owner-employee the only wages counted, and should the plan treat the owner's S-corporation salary as the full W-2 wage base?

Why we ask: the engine only needs a yes or no (`qbi_sstb`) plus the wage and property inputs. Above the threshold a "yes" scales the deduction down to zero across the phase-in range; below it the answer changes nothing today, but the plan projects forward and income can cross the threshold in later years.

**PTE election: timing for the plan year (see `pte_election`)**

> The Illinois pass-through entity tax election was not made for 2026. (a) Confirm that it therefore cannot apply to 2026. (b) For 2027, when and how must the election be made (on a timely filed entity return, or earlier by estimated payment), and what is the deadline? (c) Is the election annual, or does it carry forward until revoked? (d) Confirm the rate and that the owner's Illinois credit equals the tax paid.

### Answers received 2026-11-11 (relayed by the plan owner, not yet in writing from the CPA)

| # | Question | Answer |
|---|---|---|
| 1 | Business is an SSTB (and would anything make it one later) | Yes: it is an SSTB today (owner confirmed 2026-11-11) |
| 2 | Does SSTB status change the deduction at projected income | No (income is below the threshold, so it does not bind today) |
| 3 | Owner S-corp salary is the full W-2 wage base | Yes |
| 4 | PTE election cannot apply to 2026 | Correct |
| 5 | Election made on the timely-filed entity return; deadline | Yes, April 15 |
| 6 | Election is annual, not carried forward | Annual |
| 7 | 4.95% rate and owner credit equals tax paid | Yes |
| 8 | Elect PTE for 2027 | No |
| 9 | Non-itemizer charitable deduction (IRC 170(p)) as modeled | Yes |
| 10 | SEHI iterative method differs materially / premiums out of itemized medical | No change needed: keep the one-pass approximation and the itemized-medical netting as built (owner confirmed 2026-11-11) |
| 11 | Wash-sale rule W1 | Yes |

Consequences: `qbi_sstb` TRUE (set it in the app: Plan inputs, QBI); `pte_election` stays off for the 2027 plan year, and the election is an annual choice, so the plan should treat it as made year by year, not carried forward.

## Status

- [ ] CPA engaged (date, firm): ____
- [ ] Attorney or AG-calculator comparison started (date): ____
- [ ] Answers recorded and Wave 3 items unblocked: ____

The matching rows are in `documentation/reference/BACKLOG.md`.
