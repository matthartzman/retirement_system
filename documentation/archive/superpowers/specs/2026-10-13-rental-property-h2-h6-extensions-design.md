# Rental property extensions H2 to H6 (design as built)

Status: implemented

Moved from sections 9 to 13 of `documentation/reference/RENTAL_TAX_RULES.md` on 2026-11-12 because it is built design material, not a living rule set. Section numbers below are the original ones, so older citations ("RENTAL_TAX_RULES.md section 12") map directly. The living rules, constants and worked examples R01 to R24 stay in `RENTAL_TAX_RULES.md`.

## 9. H2: link a rental to an existing liability (built; owner answered yes to the three questions 2026-10-13)

Status: built. The worked examples below are pinned by `tests/test_rental_loan_link_functional.py`. Rental stays default OFF; with the feature off the link
is ignored and every number is as today.

### 9.1 Problem
A rented property's loan can be entered twice: once on the property (`loan_balance`, `loan_rate`,
`loan_monthly_payment`) and once as a row in Liabilities (`client_liabilities`, type `other`/`heloc`). The
engine then counts the debt twice in net worth (the property's loan inside rental equity, the liability row in
`additional_liabilities`) and the payment twice in the cash need. A converted home has the opposite gap: a
loan on the home that sits in Liabilities (for example a HELOC or a cash-out second loan) keeps being treated
as personal debt after the conversion, so its interest never reaches Schedule E.

### 9.2 Data model
One new optional text column on the rental table: `loan_liability_id` (matches `liability_id` in Liabilities).
Added to `rental_repo` columns, `parsing/rental_properties` (`RentalSpec.loan_liability_id`), the rental
service field list and the editor. Plan file schema v10 (forward-only `ALTER TABLE rental_properties ADD COLUMN
loan_liability_id TEXT NOT NULL DEFAULT ''`; blank for every existing row). The CSV exchange template gains the
column after `notes`. The editor's Loan block lists the Liabilities rows (`liability_options` in the page payload);
link warnings show with the page warnings and in the row as `rental_loan_link_warnings`.

### 9.3 Rule
| Case | Behaviour |
|---|---|
| Standalone property, link set, liability found, feature on | The liability is the single source of the loan: balance (at `loan_balance_year`, default the liability `start_year` or the plan start), `interest_rate`, `monthly_payment` (or level payment to `payoff_year` when blank). The property's own loan fields are ignored. The rental book amortizes the loan (interest to Schedule E, principal to cash, balance inside rental equity). The liability row is skipped by the general liability loop and by the opening balance sum, so nothing counts twice. |
| Converted home, link set | Balance and payment stay in the liability loop exactly as today (cash and net worth unchanged: the rental row keeps loan 0, as for the home mortgage). From the conversion date the linked liability's interest is deducted on Schedule E at the same rented share as the home mortgage interest (`converted_home_share`: 0.5 in the conversion year when converted in July, 1.0 after). It joins the passive-loss limit with the rest of Schedule E. |
| Link set, id not found | Warning on the rental row and in the build notes; the property's own loan fields are used; the liability (if any exists under another id) is untouched. |
| Two properties link the same liability | First wins; the second gets a warning and uses its own fields. |
| Link to a `student_loan` row | Rejected with a warning (not a property loan). |
| Property sold while linked | Payoff is the linked balance at the sale month (reduces net proceeds); the liability is not paid again afterwards. Converted home: payoff of the linked balance from home-sale proceeds is **not** modeled today for any liability; unchanged and listed as a limitation. |
| Feature off | Link column ignored; liabilities behave as today. |

### 9.4 Worked examples (engine arithmetic: monthly level payment, monthly interest)
| # | Inputs | Today | With link | Rule |
|---|---|---|---|---|
| L1 | Duplex loan 200,000 at 4%, 22 years (payment 1,140.36 a month, 13,684.34 a year), entered on the property **and** as a Liabilities row | Debt counted twice: net worth 200,000 too low at start; cash payments 27,368.68 a year; Schedule E interest year 1 = 7,894.62 | Debt once: balance 200,000, payment 13,684.34, Schedule E interest 7,894.62, principal 5,789.72, end balance 194,210.28 | single source of the loan |
| L2 | Same loan only in Liabilities, link set on the property, property loan fields blank | Property shows no interest (Schedule E too high by 7,894.62); liability payment in the cash need | Interest 7,894.62 on Schedule E; payment moves from the liability loop into rental cash (cash need unchanged) | link supplies the property loan |
| L3 | Converted home (July 2027), HELOC liability 100,000 at 7%, interest-only | Interest 7,000 a year stays personal (no deduction) | 2027 Schedule E interest 3,500 (share 0.5); 2028 onward 7,000 (share 1.0); cash and net worth unchanged | Schedule E interest at the rented share |
| L4 | Link id typo "heloc-1" (liability is "heloc1") | n/a | warning; property's own loan fields used; liability stays personal | not found |
| L5 | Two rentals both link "mtg-a" | n/a | first uses it; second warns, uses own fields | first wins |

### 9.5 UI mock (rental property editor, Loan block)
```
Loan
  Existing loan   [ None (enter a loan below)            v ]
                  [ mtg-a  Duplex mortgage   $200,000 4.0% ]
                  [ heloc1 Home HELOC        $100,000 7.0% ]
  -- when one is chosen --------------------------------------
  Balance         $200,000     (from Liabilities, read only)
  Rate            4.0%         (from Liabilities, read only)
  Monthly payment $1,140.36    (from Liabilities, read only)
  Note: "This loan is counted once. It is taken out of the general
         Liabilities totals while this property uses it."
  -- when None -----------------------------------------------
  Balance / Rate / Payment / Term years   (as today, editable)
Warning strip (only when a link is broken): "Loan 'heloc-1' not found.
  Using the loan fields on this property."
```
Liabilities page: a linked row shows the badge "Used by rental: Duplex" (read only, no delete while linked).

### 9.6 Questions for the owner
1. Standalone: is "the liability is the source, the property fields are ignored" the right direction? (Alternative: the property wins and the liability row is hidden from totals.)
2. Converted home: only Schedule E interest moves; do you also want the linked loan's balance shown on the property? (Default: no.)
3. OK to leave "payoff of other liabilities at home sale" as a stated limitation?

## 10. H3: personal-use reversion (rent, then move back in) (built; owner and tax preparer approved 2026-10-13)

Status: built. T1 to T3 are pinned by `tests/test_rental_reversion_functional.py`. Rental stays default OFF.

### 10.1 Problem
A converted home today is rented from the conversion date to `rental_end_year`; after that the engine counts **no
residence use**, so a later sale fails the two-of-five test even when the household moved back in. It also
treats the whole end year as rented and takes a full year of depreciation. Real moves back in need three
rules the module skips: the move-back counts as residence for the 121 clock, depreciation stops at the move-back
date, and rental use that sits *before* the last residence date is **nonqualified use** (IRC 121(b)(5)).

### 10.2 Data model (plan schema v11, forward-only `ALTER TABLE ... ADD COLUMN`, converted-home rows only; the editor shows both fields next to Rental end year)
| Column | Meaning |
|---|---|
| `moves_back_in` | yes/no, default no (today's behaviour, byte-identical). |
| `reversion_month` | month of `rental_end_year` the household moves back in (default 7, mid-year, as the other months). |

`rental_end_year` + `reversion_month` = the move-back date (1st of the month). Rented months in the end year:
January to the month before; depreciation runs to that month (mid-month disposal convention, as for a sale).
From the move-back date the home's carrying costs return to personal spending (the existing rented share, now
partial in the end year). One rental period per home (a second conversion is out of scope).

### 10.3 Rules
| Rule | Behaviour |
|---|---|
| Section 121 clock | residence periods = `[owned_from, conversion)` and `[move-back, sale)`; passes when residence days in the 5 years before the sale >= 730 and ownership days >= 730 (existing `section_121_two_of_five`). Without `moves_back_in`: only the first period, as today. |
| Depreciation taken | `accumulated = sum of depreciation through the move-back month`; no depreciation afterwards; it stays in the basis reduction at the later sale and is unrecaptured 1250 gain (IRC 121(d)(6)), never excluded. |
| Nonqualified use | rental days (conversion to move-back) / ownership days (`owned_from` to sale). Applies only when the household moves back in (rental *after* the last residence date is exempt, 121(b)(5)(C)(ii)(I)); applies only to periods after 2008 (all conversions in the plan are). Allocated to the gain that is left after the 1250 split: `nonqualified gain = (gain - 1250 gain) x ratio` is taxable LTCG; the exclusion applies to the rest. |
| Passive losses | moving back in is not a disposition: suspended losses stay suspended (they can still offset other passive income) and are released by the later fully taxable sale of the home, as for today's converted-home sale. Open question for the tax preparer, see 10.6. |
| Sold while rented, or no move-back | exactly as today (no nonqualified use, no residence credit after conversion). |
| Feature off | ignored. |

### 10.4 Worked examples (MFJ exclusion 500,000; owned and lived in from 1 Jan 2015; converted 1 Jul 2027; depreciable basis 400,000 so depreciation is 6,668 in 2027, 14,544 in 2028 and 7,878 in 2029 to the move-back; 27.5 years, mid-month)
| # | Inputs | Today | With reversion | Rule |
|---|---|---|---|---|
| T1 | Moves back 1 Jul 2029, sold 1 Jul 2031, gain (after depreciation) 400,000 | Residence days 365 in the window, test **fails**: excluded 0; 1250 gain 35,756 (a full year of 2029 depreciation); LTCG 364,244 | Residence 365 + 730 = 1,095 days, **passes**. 1250 gain 29,090. Rest 370,910. Nonqualified ratio 731 / 6,025 = 12.133%, so LTCG 45,001.69. Excluded 325,908.31. | 121(a), (b)(5), (d)(6) |
| T2 | Same, gain 900,000 | fails: LTCG 864,244, 1250 gain 35,756 | 1250 gain 29,090; rest 870,910; nonqualified 105,665.60; eligible 765,244.40; excluded capped at 500,000; LTCG 370,910.00 | exclusion cap |
| T3 | Moves back 1 Jul 2029, sold 1 Dec 2029, gain 400,000 | fails | residence 942 + 153 = 1,095 days passes. Ratio 731 / 5,448 = 13.418%. LTCG 49,767.84, excluded 321,142.16, 1250 gain 29,090 | same |
| T4 | Sold 1 Jul 2029 while still rented (no move-back) | as today | as today (rental after the last residence date is not nonqualified use) | 121(b)(5)(C)(ii)(I) |
| T5 | `moves_back_in` = no | as today | as today, byte-identical | default |

### 10.5 UI mock (converted-home row, Basics tab; the estimate sits on the Sale tab)
```
Rental period
  Rental end     [ 2029 - 07 ]            Move back in on that date  [ Yes v ]
  Hint: "Moving back in starts a new residence period for the 2-of-5-year test,
         stops depreciation, and makes the rental months nonqualified use."
Sale tab, "Section 121 estimate (home sale year 2031)"   (read only, estimate)
  Residence days in the last 5 years   1,095 of 730 needed   passes
  Depreciation taken (recaptured)      $29,090
  Nonqualified use                     12.1% of 6,025 ownership days
  Taxable part of the gain             $45,002 LTCG + $29,090 recapture
  Excluded                             $325,908
```

### 10.6 Questions
1. Owner: default `reversion_month` 7 and the one-rental-period limit OK?
2. Tax preparer: (a) nonqualified use applied to the gain left after the 1250 split (as Pub. 523 orders them); (b) suspended passive losses stay suspended on the move-back and release at the later sale; (c) the end-year depreciation uses the mid-month disposal convention at the move-back month.

## 11. H4: owner split between spouses and sale proceeds split (built; owner approved 2026-10-13)

Status: built (plan schema v12). Pinned by `tests/test_rental_owner_split_functional.py`. Rental stays default OFF. An owner left **Not set** keeps today's single default account (so existing rental plans do not move); the workbook Owner column is not built: the owner is in the row data (`rental_by_property`) and the editor.

### 11.1 Problem
Each property already stores `owner` (Joint / Member 1 / Member 2), but nothing reads it. A jointly titled
property's sale proceeds are deposited to one account (`home_sale_acct`, else the first taxable account), and
the rental views show no owner. On a joint return the income tax is the same whoever owns the property, so the
split matters for where proceeds land, for what each spouse owns after a death (H5 reads it for the step-up),
and for reporting.

### 11.2 Data model (plan schema v12, forward-only)
One new optional column `member_1_share` (0 to 1) on the rental table, used only with `owner` = Joint.
Blank means 50% for Joint, 100% for Member 1, 0% for Member 2. A share with an owner other than Joint is an
input error ("use Joint for a split"). Applies to the converted home as well (its `owner` and share).

### 11.3 Rules
| Rule | Behaviour |
|---|---|
| Income tax on a joint return | unchanged: Schedule E, depreciation, passive-loss limit and gain use the one return; the golden numbers do not move. Owner **Not set** (blank): proceeds go to the single default account as before. |
| Sale proceeds | Positive net proceeds of a rental sale (and of a converted-home sale that is not already split by `home_sale_splits`) are deposited `member_1_share` to the first taxable account of member 1 and the rest to member 2's (`first_taxable(c, owner_idx)`). A member with no taxable account: that member's part goes to the other member's account; none at all: the household default account as today. The deposit is basis-free cash (gain taxed in the sale year), as today. |
| Existing `home_sale_splits` | win for the plan's home, unchanged. |
| An owner who died before the sale | the deceased member's part goes to the survivor's account (all of it to the survivor; estate transfers are H5). |
| Reporting | `rental_by_property` rows carry `owner` and `member_1_share`; the Rental Properties sheet gets an Owner column and the sale proceeds by account. |
| Death | no new tax effect in H4; H5 reads the stored share for the step-up (decedent's share). |
| MFS | the plan models one return; Schedule E is not split between two separate returns (stated limitation; the MFS lived-apart allowance stays as built). |
| Feature off | ignored. |

### 11.4 Worked examples (net sale proceeds 200,000; accounts Member_1_Trust and Member_2_Trust)
| # | Inputs | Today | With H4 | Rule |
|---|---|---|---|---|
| O1 | Owner Joint, blank share (50%) | 200,000 to the default account | 100,000 to Member_1_Trust, 100,000 to Member_2_Trust | 50% each |
| O2 | Owner Joint, member_1_share 60% | all to the default account | 120,000 to Member 1, 80,000 to Member 2 | share |
| O3 | Owner Member 1 | default account | 200,000 to Member 1 | 100% |
| O4 | Owner Joint, Member 2 has no taxable account | default | 100,000 to Member 1 and 100,000 more to Member 1's account (all 200,000 to Member 1) | fallback |
| O5 | Joint 50/50, Member 2 died two years before the sale | default | all 200,000 to the survivor (Member 1) | survivor |
| O6 | Owner Member 1, share 60% entered | n/a | input error: "member_1_share applies only to Joint ownership" | validation |
| O7 | Joint return, any owner | tax as today | identical rental tax items (Schedule E, gain, passive limit); only where the cash is deposited differs, so later investment income in those accounts can differ slightly | MFJ |

### 11.5 UI mock (property editor, Identity group; the split preview sits on the Sale tab)
```
Identity
  Owner         [ Joint v ]            (Joint | Member 1 | Member 2)
  Member 1 owns [ 50 ] %               Member 2 owns 50 %      (only shown for Joint)
Sale tab, "Where the proceeds go"        (read only, estimate)
  Net proceeds after costs and loan     $200,000
  Member 1 (Member_1_Trust)             $100,000
  Member 2 (Member_2_Trust)             $100,000
  Note: "Income tax is the same on a joint return whoever owns the property."
```

### 11.6 Questions for the owner
1. Is "derive the split from ownership (Joint 50/50 by default)" right, or do you want an explicit split table like the home-sale splits?
2. OK that MFS households keep the one-return model (no per-return Schedule E split), listed as a limitation?
3. OK that a deceased owner's part goes to the survivor's account until H5 defines estate transfers?

## 12. H5: death handling (built; tax preparer approved the examples 2026-10-13)

Status: built (no schema change). Pinned by `tests/test_rental_death_functional.py`. Rental stays default OFF. Reads the H4 `owner` and
`member_1_share`; applies only to properties with an owner set (unset owner = today's behaviour, so existing
rental plans do not move).

### 12.1 Problem
The module has no death handling. A first death changes nothing for a rental; at the second death the converted
home's estate sale keeps the step-up (no gain) but every suspended passive loss simply lapses
(`RENTAL_TAX_RULES.md` section 7). The law gives three things: a basis step-up (IRC 1014), loss of the
depreciation recapture on the stepped-up part, and a deduction on the decedent's final return for suspended
losses that exceed the step-up (IRC 469(g)(2)).

### 12.2 Rules
| # | Rule | Behaviour |
|---|---|---|
| 1 | Decedent's share | Sole owner who dies: 100%. Sole owner who survives: 0%. Joint: the decedent's ownership share, 50% unless `member_1_share` says otherwise (spouses' qualified joint interest, IRC 2040(b)); 100% in a community-property regime (IRC 1014(b)(6)); the plan's existing regime flag (`_basis_stepup_fraction`) decides, as for the home. |
| 2 | Step-up (or down) at the date of death | the decedent's share of the adjusted basis (cost + improvements - accumulated depreciation) becomes its share of fair market value at death (`value path` at the death month). The change is `delta B` (negative = step-down). |
| 3 | Depreciation | the stepped share is a new asset placed in service at the date of death (27.5 years, mid-month) on FMV x (1 - land share); its old accumulated depreciation is erased (no 1250 recapture on it). The survivor's share keeps its original schedule and its accumulated depreciation. |
| 4 | Suspended losses at death | the decedent's share of the suspended loss `S` is allowed on the final (death-year) return only to the extent it exceeds the increase: `allowed = max(0, S - max(0, delta B))`, deducted against ordinary income in the death year (joint return); the rest is permanently lost. The survivor's share stays suspended. |
| 5 | Second death | the same on the whole remaining share; the property is stepped to FMV at that date. For the converted home's estate sale this replaces "all suspended losses lapse" by rule 4 (`allowed` released in the final year). |
| 6 | Not set owner / feature off | unchanged from today. |
Limitations: the converted home's first-death step-up of the plan's home stays as built (home sale stage); its depreciation restart is not modelled. Rental income taxed to the estate or heirs after the second death is not modelled.

### 12.3 Worked examples
Property: cost 400,000 (land 20%: building 320,000), accumulated depreciation 100,000 so adjusted basis 300,000; FMV at death 500,000.
| # | Inputs | Today | With H5 | Rule |
|---|---|---|---|---|
| D1 | Joint 50/50, common-law, first death | nothing happens; later sale at 500,000: gain 200,000, of which 1250 gain 100,000 | decedent half: basis 150,000 to 250,000 (`delta B` 100,000); new building basis 250,000 x 80% = 200,000, 7,272.73 a year from the death date; survivor half keeps 160,000 building at 5,818.18 a year and 50,000 accumulated. Later sale at 500,000: gain 100,000, of which 1250 gain 50,000 | 1014, 2040(b) |
| D2 | Same, suspended loss 40,000 | stays suspended | decedent share 20,000; `delta B` 100,000 so allowed = max(0, 20,000 - 100,000) = 0, all 20,000 lost; survivor's 20,000 stays suspended | 469(g)(2) |
| D3 | Sole owner dies, suspended loss 120,000, `delta B` 50,000 | stays suspended | allowed = 70,000 on the final return; 50,000 lost | 469(g)(2) |
| D4 | Second death, suspended 60,000, FMV 700,000, adjusted basis 450,000 (`delta B` 250,000) | lapses | allowed = max(0, 60,000 - 250,000) = 0 (same as today) | 469(g)(2) |
| D5 | Second death, suspended 300,000, same property | lapses (0) | allowed = 300,000 - 250,000 = 50,000 deducted on the final return | 469(g)(2) |
| D6 | First death, FMV 250,000 (below the 300,000 adjusted basis), suspended 30,000 | stays | step-down: no increase, so the decedent's share of the loss is allowed in full (15,000 if joint 50/50); basis steps down | 1014, 469(g)(2) |
| D7 | Community property, first death | n/a | 100% of the property is stepped up (`delta B` 200,000); decedent share of losses is the whole loss | 1014(b)(6) |

### 12.4 Questions for the tax preparer (please confirm each)
1. Decedent's share by owner: sole 100%/0%, joint 50% common-law, 100% community property.
2. The stepped share restarts 27.5-year mid-month depreciation from the date of death on FMV x (1 - land share); its accumulated depreciation is erased.
3. Suspended-loss release on the final return is `max(0, S - increase)` for the decedent's share only, deducted in the death year on the joint return; the rest is lost.
4. At the second death the same applies to the remaining share and the estate sale keeps the step-up.
5. FMV at death = the engine's value path at the death month.
6. Owner: OK that an unset owner keeps today's behaviour (no death handling)?

### 12.5 As built
- `RentalBook` reads the household's deaths (`h_death_yr`, `w_death_yr`, couple flag, `basis_step_up_property_regime`). A first death exists only for a couple dying in different years; a single death or two deaths in one year is the second-death case (fraction 1).
- Death month is 7; fair market value is the property's value path at mid-year; improvements before the death are inside the stepped basis.
- Standalone properties with an owner: depreciation slices (`_Seg`), the stepped basis (`_sale_basis`) and the depreciation still on the books at a later sale (`_accumulated`) follow the rules above. Row fields: `rental_by_property[].death_suspended_removed / death_loss_released / death_loss_lost / death_basis_change` and `rental_death_loss_released / lost / basis_change` (present in a death year only). The released loss is an ordinary deduction in the death year (`ordinary_income`).
- Converted home: only the second-death estate year (the last rented year) releases the excess suspended loss; its first-death step-up and depreciation restart are not modelled (the plan home's basis step-up in the home-sale stage is as before). Its value path uses the plan's home appreciation.
- The passive ledger drops the decedent's share in the death year; the survivor's share stays suspended.

## 13. H6: optimizer search "rent out, then sell in year X" (built; owner approved the comparison 2026-10-13)

Status: built behind the rental feature (default OFF, so off the housing optimizer is unchanged).
Pinned by `tests/test_housing_rent_then_sell_functional.py`. The sale window is shared with Sell; cash-on-sale and sale-year tax stay in the notes.

### 13.1 What it is
A fourth disposition of the current home, `rent_then_sell` ("Rent out, then sell"), searched next to
sell, keep and keep-and-rent-out when the Housing optimizer's Disposition is Auto (or chosen alone).
It converts the home to a rental in move 1's acquisition year (as `rent_out` does) and sells it in a
searched year X from the request's sale window, with X after the conversion year. The engine does the rest
with what H1 to H3 built: carrying costs move to Schedule E, depreciation runs, the sale in X uses the
converted-home rules (recapture, two-of-five test, dual basis), and the taxable gain is in X's AGI and in
the IRMAA lookback two years later (H1).

### 13.2 Rules
| Rule | Behaviour |
|---|---|
| Candidates | one per (location, acquisition year, sale year X > acquisition year); owning two homes is allowed (the home is rented), as for `rent_out`. |
| Rent | never invented: typed rent, else the plan's converted-home rent; with neither, not searched (as `rent_out`). |
| Scoring | the same net worth and lifetime cost as the other dispositions: housing cost less sale gain plus the sale's tax, with the rental's after-tax net cash in place of the moved carrying costs. The tax on the rent is the estimate in Pass 1 and the engine's exact delta for the shortlist; the exact delta leaves the sale's own tax out (it is counted once, with the sale). |
| Notes on each row | `rented out from Y, sold in X`; whether the section 121 test is met for X (and the last year it would be); the depreciation recaptured in X; the sale gain in X's AGI and the IRMAA tier two years later. |
| Off | `rent_then_sell` is an unknown disposition; nothing else changes. |

### 13.3 Comparison (frozen sample plan, move 1 buys in 2028, rent 5,500 a month; objective net worth; one location)
The Disposition column is what the Current home cell shows; Sell is the best plain sale in the window.
| Current home | Net worth at plan end | Lifetime housing cost | Section 121 for the sale | Notes |
|---|---|---|---|---|
| Sell 2029 | 10,065,402 | 1,073,227 | n/a (home not rented) | dual ownership 2028-2029 |
| Keep and rent out | 12,422,678 | 252,206 | exclusion only if sold by 2031 | keeps the home; recapture on a later sale |
| Rent out, sell 2029 | 10,425,797 | 966,560 | met | |
| Rent out, sell 2030 | 10,390,135 | 910,450 | met | sale gain 345,000 in 2030 AGI; IRMAA tier 4 in 2032 |
| Rent out, sell 2031 | 10,444,554 | 880,199 | met (last year) | gain 345,000; IRMAA tier 4 in 2033 |
| Rent out, sell 2032 | 10,126,789 | 870,219 | NOT met | gain 845,000 in AGI; IRMAA tier 5 in 2034 |
| Rent out, sell 2034 | 10,363,394 | 724,283 | NOT met | recapture 139,626 |
| Rent out, sell 2036 | 10,376,475 | 576,660 | NOT met | lowest lifetime cost in the window |
Reading it: selling by 2031 keeps the 500,000 exclusion; one year later the whole gain is taxable, which also lifts the
IRMAA tier two years on. Net worth is highest for a 2031 sale; lifetime cost keeps falling as more rent is collected before
the sale. Keep-and-rent-out is not comparable on net worth because it never sells (the home stays in net worth).

### 13.4 UI mock (Housing optimizer, step 2 "Current home")
```
Disposition   [ Auto (search all) v ]      options: Sell | Keep | Keep and rent out | Rent out, then sell
Sale window   Earliest [ 2029 ]  Latest [ 2036 ]          (used by Sell and Rent out, then sell)
Monthly rent  [ 5,500 ]  (today's dollars)                  (rent options)
Results row:  Current home: "Rent out, sell 2031"      Notes: rented out from 2028, sold in 2031; §121 met ...;
              §1250 recapture ...; sale gain ... in 2031 AGI; IRMAA tier 4 in 2033   [Convert my home]
```

### 13.5 Questions for the owner
1. Is this comparison (net worth and lifetime cost per sale year, with the section 121 / recapture / IRMAA notes) what you want to see?
2. Should the results also show, for each rent-then-sell row, the cash on the sale and the sale-year tax as their own columns? (Not built: they are in the notes today.)
3. Keep the sale window shared with Sell (X after the conversion year), or give Rent out, then sell its own window?
