# Rental Properties sheet preview (WP12.7)

Generated from the fixture case "Condo (loss-making) + Duplex for sale (profitable, sold 2035) + Our house (converted home, sold 2029)" with `rental_property_income` on, married filing jointly, sample plan. Rows that expand (sections B, C, D) are shown collapsed as in the workbook; section A shows every year. Stable sheet name `40. Rental Properties`; in a workbook it takes the next letter after Balance Sheet (here `1E`). With the feature off the sheet does not exist and no other sheet changes.

## The sheet

### 1E. Rental Properties

#### RENTAL PROPERTIES

> Tax rules verified 2026-10-13 against 2025 law. See section G for every simplification and exclusion.

#### A. SUMMARY BY YEAR (all properties)

> Net cash flow = rent collected - operating expenses - debt service - improvements and purchase cash. Taxes are produced by the plan's tax stages; "Estimated tax effect" is Schedule E added to AGI times the year's effective marginal rate (federal, Social Security inclusion and NIIT; state tax not included). Positive = more tax, negative = a tax saving.

| Year | Gross rent | Vacancy loss | Operating expenses | Mortgage interest | Depreciation | Net Schedule E (before passive limit) | Passive loss allowed | Suspended loss (year end) | Schedule E added to AGI | Estimated tax effect | Debt service (interest + principal) | Improvements and purchase cash | Net cash flow | Sale proceeds deposited |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 54,000 | 1,500 | 20,700 | 35,743 | 25,307 | (29,250) | - | 29,250 | - | - | 46,306 | - | (14,506) | - |
| 2027 | 89,175 | 2,890 | 33,655 | 37,755 | 35,311 | (20,437) | - | 49,687 | - | - | 64,306 | - | (11,676) | - |
| 2028 | 126,075 | 4,350 | 47,245 | 39,119 | 47,581 | (12,220) | - | 61,907 | - | - | 82,306 | 27,500 | (35,325) | - |
| 2029 | 99,612 | 3,274 | 26,230 | 36,197 | 38,126 | (4,214) | 66,122 | - | (66,122) | (15,869) | 67,306 | - | 2,803 | - |
| 2030 | 59,606 | 1,656 | 22,849 | 33,204 | 26,306 | (24,409) | - | 24,409 | - | - | 46,306 | - | (11,204) | - |
| 2031 | 61,096 | 1,697 | 23,420 | 32,471 | 26,309 | (22,801) | - | 47,210 | - | - | 46,306 | - | (10,327) | - |
| 2032 | 62,623 | 1,740 | 24,006 | 31,694 | 26,306 | (21,122) | - | 68,332 | - | - | 46,306 | - | (9,427) | - |
| 2033 | 64,189 | 1,783 | 24,606 | 30,870 | 26,313 | (19,383) | - | 87,715 | - | - | 46,306 | - | (8,505) | - |
| 2034 | 65,794 | 1,828 | 25,221 | 29,995 | 26,306 | (17,557) | - | 105,272 | - | - | 46,306 | - | (7,560) | - |
| 2035 | 39,339 | 468 | 17,628 | 25,056 | 17,229 | (21,042) | 126,313 | - | (126,313) | (30,315) | 36,042 | - | (14,799) | 415,419 |
| 2036 | 30,722 | - | 15,259 | 23,030 | 14,835 | (22,402) | - | 22,402 | - | - | 32,621 | - | (17,158) | - |
| 2037 | 31,490 | - | 15,640 | 22,337 | 14,839 | (21,326) | - | 43,728 | - | - | 32,621 | - | (16,771) | - |
| 2038 | 32,277 | - | 16,031 | 21,594 | 14,835 | (20,182) | - | 63,910 | - | - | 32,621 | - | (16,375) | - |
| 2039 | 33,084 | - | 16,432 | 20,796 | 14,839 | (18,983) | - | 82,893 | - | - | 32,621 | - | (15,969) | - |
| 2040 | 19,782 | - | 9,825 | 11,740 | 8,036 | (9,819) | 92,712 | - | (92,712) | (22,251) | 19,029 | - | (9,072) | 456,025 |
| Plan total | 868,865 | 21,185 | 338,746 | 431,601 | 362,480 | (285,147) | 285,147 | - | (285,147) | (68,435) | 677,306 | 27,500 | (195,872) | 871,445 |

> No rental activity after 2040; later years are not listed.

#### B. BY PROPERTY AND YEAR (expand a property to see its years)

> Same columns as section A, one block per property. Schedule E added to AGI is the property's Schedule E net less its opening suspended loss plus its closing suspended loss.

| Property / Year | Gross rent | Vacancy loss | Operating expenses | Mortgage interest | Depreciation | Net Schedule E (before passive limit) | Passive loss allowed | Suspended loss (year end) | Schedule E added to AGI | Estimated tax effect | Debt service (interest + principal) | Improvements and purchase cash | Net cash flow | Sale proceeds deposited |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Condo | 416,237 | - | 206,731 | 359,054 | 215,740 | (365,289) | 365,289 | - | (365,289) | (87,669) | 475,726 | - | (266,220) | 456,025 |
| Duplex for sale | 308,002 | 15,400 | 90,142 | 63,080 | 103,105 | 36,275 | - | - | 36,275 | 8,706 | 126,580 | 27,500 | 48,380 | 415,419 |
| Our house | 144,627 | 5,785 | 41,873 | 9,466 | 43,635 | 43,867 | - | - | 43,867 | 10,528 | 75,000 | - | 21,968 | - |

#### C. DEPRECIATION SCHEDULE

> Straight line over the recovery period with the mid-month convention (IRS Publication 946 Table A-6). Adjusted basis = purchase price and closing costs (for a converted home, the home's adjusted basis) + improvements - accumulated depreciation; in a sale year it is the sale's adjusted basis. Depreciation accrues in loss years too.

| Property / Year | Depreciable basis (building + improvements) | Land (not depreciable) | Depreciation this year | Accumulated depreciation | Adjusted basis (year end) |
|---|---:|---:|---:|---:|---:|
| Condo | 408,000 | 102,000 | 215,740 | 242,321 | 267,679 |
| Duplex for sale | 315,500 | 72,000 | 103,105 | 182,080 | 205,420 |
| Our house | 600,000 | 200,000 | 43,635 | 43,635 | 756,365 |

#### D. PASSIVE-LOSS LEDGER

> A rental loss first offsets passive income; the rest is allowed up to the special allowance, which shrinks as income (MAGI computed before passive losses) rises. Whatever is not allowed is suspended and carried forward by property, and is released in full when the property is sold.

| Year | MAGI used for the limit | Special allowance available | Special allowance used | Net Schedule E (before limit) | Schedule E added to AGI | Released at sale | Suspended loss (year end) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 454,235 | - | - | (29,250) | - | - | 29,250 |
| 2027 | 263,604 | - | - | (20,437) | - | - | 49,687 |
| 2028 | 264,073 | - | - | (12,220) | - | - | 61,907 |
| 2029 | 652,163 | - | - | (4,214) | (66,122) | - | - |
| 2030 | 220,831 | - | - | (24,409) | - | - | 24,409 |
| 2031 | 188,969 | - | - | (22,801) | - | - | 47,210 |
| 2032 | 176,384 | - | - | (21,122) | - | - | 68,332 |
| 2033 | 175,373 | - | - | (19,383) | - | - | 87,715 |
| 2034 | 174,283 | - | - | (17,557) | - | - | 105,272 |
| 2035 | 505,127 | - | - | (21,042) | (126,313) | - | - |
| 2036 | 171,370 | - | - | (22,402) | - | - | 22,402 |
| 2037 | 283,814 | - | - | (21,326) | - | - | 43,728 |
| 2038 | 290,293 | - | - | (20,182) | - | - | 63,910 |
| 2039 | 296,638 | - | - | (18,983) | - | - | 82,893 |
| 2040 | 784,664 | - | - | (9,819) | (92,712) | - | - |

| Property / Year | Opening carryforward | Current-year loss | Used within the limits | Released at sale | Closing carryforward |
|---|---:|---:|---:|---:|---:|
| Condo | - | 365,289 | 272,577 | 92,712 | - |
| Duplex for sale | - | - | - | - | - |
| Our house | - | - | - | - | - |

#### E. SALE ANALYSIS

> Gain = price - selling costs - adjusted basis. Unrecaptured section 1250 gain (up to the depreciation taken) is taxed at ordinary rates capped at 25%; the rest is long-term capital gain. For a converted home the section 121 exclusion applies first, only when the home passes the two-of-five-year test, and never to the depreciation. The tax lines are estimates: the federal long-term tax and the state tax on the long-term part come from the plan's tax stages; the tax on the 1250 gain is the gain times the lesser of the year's marginal rate and 25%. When several sales fall in one year the year's tax is shared by taxable gain.

| Item | Our house (2029) | Duplex for sale (2035) | Condo (2040) |
|---|---:|---:|---:|
| Sale price | 1,750,000 | 587,148 | 786,547 |
| Selling costs | 105,000 | 35,229 | 47,193 |
| Mortgage paid off | 198,313 | 136,500 | 283,328 |
| Adjusted basis (cost + improvements - depreciation) | 756,365 | 205,420 | 267,679 |
|    of which accumulated depreciation | 43,635 | 182,080 | 242,321 |
| Gain or (loss) | 888,635 | 346,499 | 471,675 |
| Unrecaptured section 1250 gain (taxed at ordinary rates, 25% cap) | 43,635 | 182,080 | 242,321 |
| Long-term capital gain taxed | 345,000 | 164,419 | 229,354 |
| Section 121 two-of-five-year test (converted home) | Passes | n/a | n/a |
| Section 121 exclusion applied | 500,000 | - | - |
| Federal tax on the long-term gain | 51,750 | 24,663 | 34,403 |
| State tax on the long-term gain | - | 8,139 | 11,353 |
| Estimated tax on the 1250 gain | 10,472 | 43,699 | 58,157 |
| Estimated tax at sale | 62,222 | 76,501 | 103,913 |
| Net proceeds before tax (price - costs - mortgage) | 1,446,687 | 415,419 | 456,025 |
| Net proceeds after estimated tax | 1,384,465 | 338,919 | 352,112 |

#### F. METRICS

> Measured in the first full year of rent. Cap rate = (rent collected - operating expenses) / property value. Net yield on value = (rent collected - operating expenses - mortgage interest) / value. Cash-on-cash = (rent collected - operating expenses - debt service) / equity (value - mortgage). After-tax hold-to-sale return = the yearly rate of return on the owner's cash: equity at the plan start, each year's net cash flow after the estimated tax effect, and either the after-tax sale proceeds or, held to the plan end, the equity then (no selling costs or tax). Not computed for a converted home (its mortgage belongs to the home).

| Property | Reference year | Property value | Net operating income | Cap rate | Net yield on value | Cash-on-cash | After-tax hold-to-sale return | Held until |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Condo | 2026 | 535,600 | 12,080 | 2.3% | -2.9% | -14.6% | 1.5% | sale in 2040 |
| Duplex for sale | 2026 | 463,500 | 19,720 | 4.3% | 2.6% | 2.2% | 4.4% | sale in 2035 |
| Our house | 2028 | 1,372,526 | 41,070 | 3.0% | 2.7% | n/a | n/a | n/a (converted home: see the sale analysis) |

#### G. ASSUMPTIONS AND WARNINGS

**Tax rules verification**

> - Verified by the household's tax preparer on 2026-10-13, against tax year 2025 rules (not 2026). The 2026 values are re-checked at the next annual tax update.

**How the numbers are built**

> - Schedule E: rent after vacancy, less operating expenses, mortgage interest and depreciation. A negative result is a loss.

> - Depreciation: straight line over 27.5 years with the mid-month convention (IRS Publication 946 Table A-6). Basis is (purchase price + closing costs) x (1 - land share); a converted home uses the lesser of its value and its adjusted basis at conversion. Capital improvements are depreciated separately from the month they are placed in service.

> - A rental loss first offsets passive income. Whatever is left is allowed up to a special allowance of $25,000 (you must actively participate), which is cut by 50% of the amount your income (MAGI, computed before passive losses) exceeds $100,000 and is gone when it reaches the end of that range. The rest is suspended, carried forward by property, and released when the property is sold in full. (Figures shown are for the first plan year and the first year's filing status, MFJ.)

> - Net rental income adds to AGI, to the MAGI used for IRMAA and the ACA credit, and to the net investment income base for NIIT (real-estate-professional status is not modelled).

> - Sale: amount realized = price - selling costs. Adjusted basis = cost basis + improvements - accumulated depreciation. Unrecaptured section 1250 gain (up to the depreciation taken) is taxed at ordinary rates capped at 25%; the rest is long-term capital gain. State tax treats the whole gain as ordinary income.

> - Converted homes only: the section 121 exclusion ($500,000 for the first-year filing status) applies when the home was owned and used as the principal residence for at least 730 days in the 5 years before the sale, and never to depreciation taken. Failing the test, the whole gain is taxable. Every other home sale in the plan is computed as before.

> - Converted homes: from the conversion, the rented share of the home's carrying costs (mortgage payment, real estate tax, utilities, maintenance and other housing budget lines) moves from spending to Schedule E, so nothing is counted twice; the principal part of the payment stays a financing flow.

**Defaults and simplifications**

> - Months: an improvement, a sale or a conversion entered without a month is placed in July (mid-year). Purchase and placed-in-service months default the same way.

> - Married filing separately: if the spouses' living-apart status is not entered, they are assumed to have lived together all year, so the special allowance is $0 (a household input can change this).

> - The MAGI for the passive-loss limit is the first-pass AGI before the withdrawal cascade, like the plan's other AGI-dependent deductions. Roth conversions are sized with the MAGI before the conversion; the final tax uses the actual MAGI and the difference is logged.

> - A converted home uses one land share for both its value and its basis. Its residence start defaults to January five years before the conversion, conversion and sale dates are the 1st of the month, and its sale year and price are the plan's home sale year and price.

> - At the first death the converted home's sale uses the stepped-up basis for gain; the loss basis is not stepped up. An estate sale after conversion keeps the step-up (no gain) and drops suspended losses.

> - Depreciation uses the published Table A-6 percentages rounded to three decimals, straight line only (no section 1250 'additional depreciation' taxed as ordinary income). All depreciation is treated as taken after 6 May 1997.

> - A section 1231 loss on a sale is treated as ordinary in the sale year; the five-year lookback and netting with other section 1231 gains are not modelled.

> - Only a sale of the whole property, fully taxable and to an unrelated buyer, releases suspended losses.

> - Other passive activities (such as K-1 income or losses) are not modelled. Amounts are not rounded to whole dollars.

> - Property values, rents and expenses grow by the rates entered (default: the plan's inflation and home appreciation); a property bought in a plan year uses the purchase month for its first-year rent and expenses.

> - The estimated tax effect and the estimated tax at sale are approximations built from the year's effective marginal rate; the exact tax is in the plan's tax stages (Lifetime Taxes). The state tax on the section 1250 part of a sale sits in that year's ordinary state tax and is not separated.

**Not modelled**

> - Like-kind (section 1031) exchanges, the qualified business income (QBI) deduction, real-estate-professional status, short-term rentals (average stay of 7 days or less) and personal use of a dwelling unit (section 280A).

> - Refinancing events, entity (LLC or partnership) ownership, state-specific passive-loss rules, tenant-level detail.

> - Splitting a property between the spouses, death handling beyond the step-up above, and turning a rental back into a personal home.

> - Partial, installment and related-party sales, gifts, linking a loan to an existing liability row, and splitting sale proceeds across accounts.

> - Section 121 refinements: the once-in-two-years rule, reduced exclusions for unforeseen circumstances, military or other suspensions of the five-year period, a check that both spouses used the home, and any non-qualified-use proration.

**Warnings for this plan**

> - The passive-activity loss limit suspends rental losses in 12 year(s) (peak carryforward $105,272). A suspended loss only reduces tax in a later year with enough rental or other passive income, or when the property is sold.

> - Our house: the home passes the two-of-five-year test at its 2029 sale. The exclusion never covers the depreciation taken, which is taxed as unrecaptured section 1250 gain.


## One property expanded (section B, Condo)

### Condo, first four years and the sale year

| Property / Year | Gross rent | Vacancy loss | Operating expenses | Mortgage interest | Depreciation | Net Schedule E (before passive limit) | Passive loss allowed | Suspended loss (year end) | Schedule E added to AGI | Estimated tax effect | Debt service (interest + principal) | Improvements and purchase cash | Net cash flow | Sale proceeds deposited |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Condo | 416,237 | - | 206,731 | 359,054 | 215,740 | (365,289) | 365,289 | - | (365,289) | (87,669) | 475,726 | - | (266,220) | 456,025 |
|     2026 | 24,000 | - | 11,920 | 27,849 | 14,835 | (30,604) | 1,354 | 29,250 | (1,354) | (325) | 32,621 | - | (20,541) | - |
|     2027 | 24,600 | - | 12,218 | 27,504 | 14,835 | (29,957) | 9,519 | 49,687 | (9,519) | (2,285) | 32,621 | - | (20,239) | - |
|     2028 | 25,215 | - | 12,523 | 27,134 | 14,835 | (29,277) | 17,057 | 61,907 | (17,057) | (4,094) | 32,621 | - | (19,930) | - |
|     2029 | 25,845 | - | 12,837 | 26,737 | 14,835 | (28,563) | 90,470 | - | (90,470) | (21,713) | 32,621 | - | (19,612) | - |
|     2039 | 33,084 | - | 16,432 | 20,796 | 14,839 | (18,983) | - | 82,893 | - | - | 32,621 | - | (15,969) | - |
|     2040 | 19,782 | - | 9,825 | 11,740 | 8,036 | (9,819) | 92,712 | - | (92,712) | (22,251) | 19,029 | - | (9,072) | 456,025 |


## Rental lines added to the other sheets

**Executive Summary** (new block after Forward-Looking Metrics)

| Line | Value |
|---|---:|
| Rental net cash flow, lifetime (after expenses and debt service) | (195,872) |
| Rental Schedule E added to AGI, lifetime (after the passive-loss limit) | (285,147) |
| Rental depreciation, lifetime | 362,480 |
| Rental sale net proceeds deposited, lifetime | 871,445 |
| Rental equity at plan end | - |
| Suspended passive loss carried at plan end | - |

> Detail by year and property, depreciation, the passive-loss ledger and every assumption are on sheet 40. Rental Properties.

**Balance Sheet** (Rental Properties joins Other Assets; its mortgages join Liabilities; the net-worth check against the projection passes)

| Line | Value | Note |
|---|---:|---|
| Primary Residence | 1,352,390 | Gross home value; mortgage shown in Liabilities |
| Rental Properties | 999,100 | Gross value at the end of 2026; mortgages shown in Liabilities. A home converted to a rental stays under Primary Residence. |
| Total Other Assets | 2,880,844 |  |
| Mortgage | 290,769 | Offsets Primary Residence gross value; not double-counted as Home Equity |
| Rental Property Mortgages | 589,438 | Offsets Rental Properties gross value |
| Total Liabilities | 880,207 |  |
| NET WORTH | 7,078,124 |  |

**Cash Flow** (columns added: Rental Cash (net) in the income group, Rental Sale Tax in the tax group; the bridge now foots)

| Year | RMD Dist | Rental Cash (net) | Σ Income | LTCG Tax | Rental Sale Tax | Total Taxes | Reinvested Surplus (forced income > need) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026 | - | (14,506) | 398,293 | - | - | 97,367 | (29,928) |
| 2027 | - | (11,676) | 84,281 | 12,690 | - | 59,811 | - |
| 2029 | - | 2,803 | 148,663 | 52,202 | - | 104,902 | - |
| 2035 | - | (14,799) | 181,377 | 476 | 32,802 | 100,363 | - |

**Net Worth** (column added: Rental Equity = property value less its mortgage)

| Year | Home Equity | Cash | Rental Equity | Σ Other | TOTAL NW |
|---|---:|---:|---:|---:|---:|
| 2026 | 1,061,621 | - | 409,662 | 2,000,637 | 7,078,124 |
| 2027 | 1,132,406 | - | 450,778 | 2,047,208 | 7,442,551 |
| 2029 | - | - | 537,618 | 870,983 | 7,902,579 |
| 2035 | - | - | 365,492 | 365,492 | 8,970,126 |

**Lifetime Taxes** (columns added at the right; two total lines under the lifetime totals)

| Year | AGI | Total Tax | Rental Schedule E in AGI | Rental Sale Tax |
|---|---:|---:|---:|---:|
| 2026 | 454,235 | 97,367 | - | - |
| 2027 | 280,007 | 59,811 | - | - |
| 2029 | 296,000 | 104,902 | (66,122) | - |
| 2035 | 342,000 | 100,363 | (126,313) | 32,802 |

**Charts**: the Income & Portfolio Draws chart gains a "Rental Cash" series, the Spending & Taxes chart gains "Rental Net Cost" and "Rental Sale Tax", and a new "Rental Properties — Cash Flow, Schedule E and Equity" chart (bars: net cash flow and Schedule E added to AGI; line on the right axis: equity) is added at the bottom.

