# Model changes of 19-20 October 2026 (tax-correctness engine changes, WI-023 to WI-025)

Plain-language record of changes that can move your results. If your numbers
change after updating and you have not edited your own data, look here first.
The technical record (with the exact pinned figures) is
`../GOLDEN_MASTER_CHANGELOG.md`; the sale-gain rules are in
`../CAPITAL_GAINS_IN_AGI.md`.

## Changes that can move your results

| Change | What you may notice | Inputs affected | Direction |
|---|---|---|---|
| **Senior bonus deduction kept when you itemize** (363p, 19 Oct) | The extra deduction for people 65 and over (OBBBA "senior bonus") was lost in years you itemized. It is now included in the itemized total. | Itemized deductions, ages 65+, MFJ or other eligible filing status | Slightly lower tax in itemizing years. Frozen sample plan: lifetime tax -$42, terminal net worth +$209. |
| **Qualified dividends taxed at the preferential rates, stacked with your gains** (WI-023) | Qualified dividends are taxed at 0/15/20%, stacked above ordinary income and below realized gains, instead of at ordinary rates. The 0% and 15% bands now use the verified 2026 figures (married 98,900 / 613,700) and the filing status in force each year (Single in survivor years). Dividends still count toward the 3.8% investment-income tax. | Taxable-account dividends, realized gains, filing status | Lower tax for most households with taxable portfolios. |
| **Brokerage sale gains count in more income tests** (WI-024) | The net gain from selling investments in taxable accounts now counts in Medicare IRMAA income (two years later), in the 3.8% investment-income tax test, and, where it applies, in the ACA subsidy income and Social Security taxation. | Withdrawals from taxable accounts, Medicare-age years, bridge years before Medicare | Higher tax or surcharges in gain years; offsets part of the dividend change above. |
| **Roth conversion capital-gains cap measured after the standard deduction** (WI-023b) | The cap that keeps Roth conversions from pushing gains into a higher rate band now starts from income less the standard deduction. | Roth conversion plans with taxable gains | Larger conversions in the early years (frozen plan: +$143k converted, mostly 2027 to 2029). |
| **Home and rental sale gains in AGI** (H1, 13 Oct) | The taxable gain on a home or rental sale now appears in AGI, the 3.8% test and IRMAA income (two years later). | A home or rental sale in the plan | Higher AGI, possibly NIIT and a higher IRMAA tier two years after the sale. No effect without a sale. |
| **Social Security taxable-share setting removed** (WI-028) | The "Social Security taxable fraction" setting on the Tax Assumptions page and its Summary row are gone. It never changed your tax: the engine always used the statutory IRC 86 phase-in. Saved plans drop the old value automatically. | None; no result changes. |
| **Symmetric survivor step-up** (WI-025) | A jointly owned account gets the same 50% basis step-up whichever spouse dies first. Before, the result depended on the death order. | Joint taxable accounts, survivor years | Smaller gain on a later sale in the case that was previously under-stepped. No change on the frozen plan. |

Combined effect on the frozen sample plan across WI-023 to WI-024: terminal net
worth about 5.300M to 5.382M and lifetime tax about 1.270M to 1.237M (full
detail in the changelog).

## Rental and housing changes (Tier 3, H2 to H6, 13 Oct)

These apply only when the rental feature is on (it is off by default), so plans
that do not use it are unchanged. No golden-master pin moved. Rules are in
`../RENTAL_TAX_RULES.md` sections 9 to 13.

| Change | What you may notice | Direction |
|---|---|---|
| **Rental loan linked to a Liabilities row** (H2) | A rental's loan entered both on the property and in Liabilities was counted twice in net worth and cash need. You can now link them, and a loan on a converted home flows to rental interest instead of staying personal debt. | Lower debt and cash need where the loan was double counted. |
| **Moving back into a rented home** (H3) | Years you move back in count toward the home-sale exclusion, depreciation stops on the move-back date, and earlier rental years are treated as nonqualified use. | A more accurate gain on a later sale. |
| **Rental owner and proceeds split** (H4) | Each property records an owner (joint or one spouse, with a share). Sale proceeds are split by ownership. A property with no owner set behaves as before. | Where proceeds land; no change to a joint return's tax. |
| **Rental at death** (H5) | The deceased owner's share gets a basis step-up, depreciation restarts for the survivor, and suspended rental losses are used on the final return instead of lapsing. | Lower tax after a death with a rental. |
| **"Rent out, then sell" in the housing optimizer** (H6) | The optimizer can convert the current home to a rental and sell it in a later year, alongside sell, keep and keep-and-rent. | New option; may change the recommended housing plan. |

## Earlier September engine changes (also covered in the 24-25 September note)

| Change | What you may notice | Direction |
|---|---|---|
| **Social Security paid in arrears** (4 and 8 Sep) | First-year benefits and annuity or pension income pay only the months actually received (a June 1 start pays 7 months, not 12; SSA pays a month later). | Lower first-year income. |
| **2025 standard deductions corrected, 2026 tax rows added** (WI-301, 29 Sep) | Higher deductions and wider 2026 brackets. All new 2026 values are marked unverified planning assumptions. | Lower tax, about $130 a year on the sample plan. |
| **Large Discretionary inflated from plan-start dollars** (WI-310) | Future big-ticket items cost more in nominal dollars. | Lower net worth. |
| **Survivor Social Security and deductions** (WI-103/104, 28 Sep) | Survivor benefit now gets COLA, an age-60 gate and early-claim reduction; the deceased spouse's age-65 add-on and senior bonus are no longer double-counted. | Mixed; survivor years only. |
| **Roth fill-to-bracket headroom** (WI-105, 28 Sep) | Conversions fill the bracket after the standard deduction. | Larger conversions. |
| **IRMAA lookback** (WI-304, 29 Sep) and **RMD age-83 divisor** (WI-303) and **2026 IRMAA tier-4 surcharge** (29 Sep) | Survivor years assessed on the joint table for two years; tiny RMD and surcharge corrections. | Small. |

## Changelog entries without a user-visible change

Every entry in `../GOLDEN_MASTER_CHANGELOG.md` since September 2026 is listed
with its note in `index.md` (section "Golden-master changelog map").
