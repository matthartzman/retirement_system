# Rental property tax rules (WP12.1)

> **Verification:** Verified by the household's tax preparer on 2026-10-13, against tax year 2025 rules (not 2026). The 14 constants, the Table A-6 percentages and examples R01-R24 are covered. The 2026 values (the app's reference tax year) must be re-checked at the next annual tax update (see `ANNUAL_MAINTENANCE_RUNBOOK.md`). The feature stays default OFF.

Status: **for owner / tax-preparer review** (checkpoint before the engine integration, WP12.2).
Design: `docs/superpowers/specs/2026-10-05-rental-property-module-design.md` sections 1, 2 and 4.

| What | Where |
|---|---|
| Pure functions (no I/O, no engine imports) | `src/rental_tax.py` |
| Constants (dated rows, `status` = `legislated`) | `reference_src/tax_law_v10.json`, carried into `src/reference/reference.db` |
| Worked examples (inputs and expected outputs) | `tests/fixtures/irs_style_examples.json` -> `rental_property_examples` |
| Tests | `tests/test_rental_tax_core_unit.py` (every example ID below must appear in this file) |

Nothing here is wired into the projection yet: the engine integration is WP12.2, the parse boundary and
home-conversion hooks WP12.3. Amounts are unrounded dollars (tax forms round to whole dollars).

## 1. Constants

All read through `rental_tax_constants(dataset, year, filing_status, mfs_lived_apart_all_year=...)` from the
tax-law dataset. A filing status without its own row uses the MFJ row (the dataset's lookup rule).

| Row name | MFJ | Single / HOH | MFS | Law |
|---|---|---|---|---|
| `residential_rental_recovery_years` | 27.5 | (MFJ row) | (MFJ row) | IRC 168(c); Pub. 946 Table A-6 |
| `passive_rental_special_allowance` | 25,000 | (MFJ row) | 12,500 (lived apart all year) | IRC 469(i)(2), (5)(A) |
| `passive_rental_special_allowance_mfs_not_living_apart` | - | - | 0 | IRC 469(i)(5)(B) |
| `passive_rental_phaseout_start` | 100,000 | (MFJ row) | 50,000 | IRC 469(i)(3)(A), (5)(A) |
| `passive_rental_phaseout_rate` | 0.5 | (MFJ row) | (MFJ row) | IRC 469(i)(3)(A) |
| `unrecaptured_1250_max_rate` | 0.25 | (MFJ row) | (MFJ row) | IRC 1(h)(1)(E), 1(h)(6) |
| `section_121_exclusion` | 500,000 | 250,000 | 250,000 | IRC 121(b) |
| `section_121_required_days` | 730 | (MFJ row) | (MFJ row) | IRC 121(a); Reg. 1.121-1(c)(1) |
| `section_121_lookback_years` | 5 | (MFJ row) | (MFJ row) | IRC 121(a) |

The values are statutory and not indexed for inflation. They were entered from the statute as recalled, not
re-checked against the primary source; each row's `source` says so.

## 2. Rules

**Depreciation (`macrs_mid_month_percentages`, `annual_depreciation`, `accumulated_depreciation`).**
Residential rental property is depreciated straight line over 27.5 years with the mid-month convention: it is
treated as placed in service, and as sold, in the middle of the month. The function rebuilds the
Pub. 946 Table A-6 column for the placed-in-service month: year 1 = (12 - month + 0.5) / 12 / 27.5, and
each later year = unrecovered percentage / remaining recovery period, rounded to 3 decimals. This gives the
published table exactly: 3.636% in years 2-9, 3.637% and 3.636% alternating from year 10, and a short last
year (year 28 for months 1-6, year 29 for months 7-12). Each column sums to 100%. Basis x percentage gives
the deduction. In the **sale year** the deduction is the full-year amount x (sale month - 0.5) / 12. In the
final, already short, year it is capped at that year's table amount. If the property is sold in the year it
was placed in service, the deduction is (sale month - placed month) / 12 of a full year. Each **capital
improvement** is its own asset, depreciated from its own placed-in-service year and month
(`DepreciableAsset`, `property_depreciation`). Depreciation is "allowed or allowable", so it accrues in loss
years too.

**Depreciable basis.** Purchased: (price + capitalized closing costs) x (1 - land share). Converted home:
lesser of fair market value and adjusted basis on the conversion date, x (1 - land share).

**Schedule E (`schedule_e_net`).** Gross rent x (1 - vacancy) - operating expenses - mortgage interest -
depreciation. A negative result is a loss.

**Passive-activity loss limit (`special_allowance`, `apply_passive_loss_limits`).** This follows the
Form 8582 order:
1. Each property's overall result = this year's Schedule E net + gain on its sale this year - loss carried in.
2. A property sold in full (fully taxable, unrelated buyer) with an overall loss: the whole loss, including
   the carryforward, is allowed (released, IRC 469(g)).
3. A property with an overall gain: all its own losses are allowed, and its net gain is passive income. A sale
   gain counts as passive income here only. It still reaches AGI through the capital-gain path.
4. Overall losses are allowed up to passive income plus the **special allowance**. The allowance is
   25,000 - 50% x (MAGI - 100,000), never below 0, so it is 0 at MAGI 150,000. It needs active participation.
   It is limited to the net loss of the active-participation properties and to the overall net loss
   (Form 8582 line 4).
   For **married filing separately** the figures are 12,500 and 50,000 (0 at 75,000), but only if the spouses
   lived apart all year. Otherwise the allowance is 0.
5. The allowance used is shared among active-participation loss properties in proportion to their losses
   (Worksheet 4). Passive income is then shared among all loss properties in proportion to their remaining
   loss (Worksheet 5). Whatever is not allowed is **suspended** and carried forward per property.
The caller supplies MAGI for this rule. It must be computed before passive losses: AGI without passive
losses, taxable Social Security, IRA deductions and similar items (Pub. 925).

**Sale (`rental_sale`, `split_sale_gain`, `unrecaptured_1250_tax`).** Amount realized = price - selling
costs. Adjusted basis = cost basis (land included) + improvements - accumulated depreciation. Gain = amount
realized - adjusted basis. **Unrecaptured section 1250 gain** = min(gain, accumulated depreciation). It is
taxed at ordinary rates, capped at 25%: stacked on top of ordinary taxable income, each dollar is taxed at the
lower of its bracket rate and 25%. The rest of the gain is section 1231 gain, treated as long-term capital
gain. A loss is a section 1231 loss, which is ordinary.
**Converted home with a loss:** the loss is measured from the lesser of value and adjusted basis on the
conversion date (dual basis). A sale price between the two bases gives neither gain nor loss.

**Section 121 for converted homes only (`section_121_two_of_five`, `section_121_converted_home`).** The home
qualifies if it was owned for at least 730 days and used as the principal residence for at least 730 days
within the 5 years ending on the sale date. The two periods do not have to overlap. Gain equal to the
depreciation taken is never excluded: it is unrecaptured 1250 gain. The exclusion (250,000; 500,000 MFJ)
applies to the rest of the gain, and any gain above that is long-term capital gain. If the test fails, the
whole gain is taxable. Nonqualified use does not apply, because rental use after the last residence use is
not nonqualified use (IRC 121(b)(5)(C)(ii)(I)). Every other home sale in a plan is computed as today.

## 3. Worked examples

Inputs and expected outputs are the fixture cases, and the tests assert every one. "MFJ 2026" means the 2026
constants above.

| ID | Rule | Inputs | Expected | Source |
|---|---|---|---|---|
| R01 | Table A-6 year 1 | placed month 1 / 2 / 3 / 4 / 5 / 6 / 7 / 8 / 9 / 10 / 11 / 12 | 3.485 / 3.182 / 2.879 / 2.576 / 2.273 / 1.970 / 1.667 / 1.364 / 1.061 / 0.758 / 0.455 / 0.152 % | Pub. 946 Table A-6 |
| R02 | Table A-6 later years | (month, year): (1,2) (12,9) (1,10) (6,10) (7,10) (12,10) (1,11) (7,11) (1,28) (6,28) (7,28) (12,28) (7,29) (12,29) | 3.636, 3.636, 3.637, 3.637, 3.636, 3.636, 3.636, 3.637, 1.970, 3.485, 3.636, 3.636, 0.152, 1.667 % | Pub. 946 Table A-6 |
| R03 | Building depreciation | basis 288,000, placed June 2026; years 2026, 2027 | 5,673.60 (1.970%); 10,471.68 (3.636%) | Pub. 946 Table A-6 |
| R04 | Improvement from its own year | roof 27,500 placed Oct 2028; year 2028 | 208.45 (0.758%); building + roof 2028 = 10,680.13 | Pub. 527 ch. 4; Pub. 946 Table A-6 |
| R05 | Sale-year depreciation | R03 building sold March 2031 (recovery year 6) | 2031: 288,000 x 3.636% x 2.5/12 = 2,181.60; accumulated 2026-2031 = 49,741.92 | Pub. 946 ch. 4 "Dispositions" |
| R06 | End of recovery | basis 100,000 placed Jan 2026; years 2053, 2054 | 1,970.00 (year 28); 0 (fully recovered) | Pub. 946 Table A-6 |
| R07 | Schedule E | rent 30,000, vacancy 5%, opex 9,000, interest 12,000, depreciation 10,471.68 | -2,971.68 (loss) | Pub. 527 ch. 3-4; Schedule E |
| R08 | Purchased basis | price 350,000 + closing 10,000, land 20% | 288,000 | Pub. 527 ch. 4; Pub. 551 |
| R09 | Converted-home basis | adjusted basis 340,000, land 25%; value 320,000 / value 450,000 | 240,000 (value lower) / 255,000 (adjusted basis lower) | Pub. 527 ch. 4 "Property Changed to Rental Use"; Reg. 1.168(i)-4(b) |
| R10 | Allowance phase-out | MFJ MAGI 90k / 100k / 125k / 130k / 150k / 175k; Single 125k | 25,000 / 25,000 / 12,500 / 10,000 / 0 / 0; 12,500 | IRC 469(i)(2)-(3); Form 8582 lines 5-8 |
| R11 | MFS allowance | lived apart, MAGI 50k / 60k / 75k; lived together, MAGI 40k | 12,500 / 7,500 / 0; 0 | IRC 469(i)(5) |
| R12 | Loss limit, one property | loss 20,000, MFJ MAGI 100k / 125k / 150k | allowed 20,000 / 12,500 / 0; suspended 0 / 7,500 / 20,000 | IRC 469(i); Form 8582 |
| R13 | Loss limit, MFS | loss 20,000; lived apart MAGI 60k; lived together MAGI 40k | allowed 7,500, suspended 12,500; allowed 0, suspended 20,000 | IRC 469(i)(5); Form 8582 |
| R14 | Passive income first, then allowance | A loss 30,000, B income 10,000, MFJ MAGI 130k | allowance 10,000; A allowed 20,000, suspended 10,000; net to AGI -10,000 | Form 8582 lines 1-10, 15-16 |
| R15 | Carryforward vs own income | A income 4,000, carried 10,000, MAGI 160k | Schedule E to AGI 0; suspended 6,000 | IRC 469(b); Form 8582 Worksheet 1 col. (c) |
| R16 | Release at full sale | A loss 2,000 + carried 18,000, sold in full, MAGI 200k | allowed 20,000 (released), suspended 0 | IRC 469(g)(1)(A); Pub. 925 |
| R17 | Sale gain is passive income | A sold: gain 50,000, loss 2,000, carried 18,000; C loss 12,000; MAGI 200k | A Schedule E -20,000; C allowed 12,000; nothing suspended; net to AGI -32,000 | Reg. 1.469-2T(c)(2); Form 8582 line 1a |
| R18 | Gain above depreciation | price 500,000, selling 30,000, cost 360,000, improvements 27,500, depreciation 60,000 | realized 470,000; adjusted basis 327,500; gain 142,500 = 1250 gain 60,000 + LTCG 82,500 | IRC 1001, 1016, 1(h)(6); Pub. 544 ch. 3; Form 4797 |
| R19 | Gain below depreciation | same, price 380,000, selling 22,800 | gain 29,700 = 1250 gain 29,700, LTCG 0 | IRC 1(h)(6) |
| R20 | Loss | same, price 320,000, selling 20,000 | loss 27,500, section 1231 ordinary | IRC 1231(a)(2); Pub. 544 ch. 3 |
| R21 | Converted home, dual basis | cost 340,000, loss basis 320,000, depreciation 20,000; realized 310,000 / 280,000 | 0 (between the bases) / loss 20,000 | Reg. 1.165-9(b)(2); Pub. 551 |
| R22 | Tax on 1250 gain (MFJ 2026 brackets) | 60,000 on top of 380,000; 20,000 on top of 90,000 | 23,550 x 24% + 36,450 x 25% = 14,764.50; 10,800 x 12% + 9,200 x 22% = 3,320 | IRC 1(h)(1)(E); Schedule D Tax Worksheet |
| R23 | Two-of-five test | owned and lived in 1 Jan 2015 - 1 Jan 2024; sold 30 Jun 2026 / 30 Jun 2027 / 1 Jan 2027 / 2 Jan 2027 | passes (915 days) / fails (550) / passes (730) / fails (729) | IRC 121(a); Reg. 1.121-1(c)(1); Pub. 523 |
| R24 | 121 with depreciation | gain 300,000, depreciation 25,000; MFJ passes / Single passes / fails | 1250 gain 25,000 in each case; excluded 275,000, LTCG 0 / excluded 250,000, LTCG 25,000 / excluded 0, LTCG 275,000 | IRC 121(b), 121(d)(6); Pub. 523 |

The examples are IRS-style: they apply the cited rules to round numbers. They are not copied from IRS
publications. The Table A-6 cells (R01, R02, R06) are the published percentages.

## 4. Assumptions and simplifications

1. Tables, not a formula: depreciation uses the Table A-6 percentages, rounded to 3 decimals as published.
   The unrounded formula would differ by under $1 a year on a $300,000 basis.
2. The sale month and the improvement placed-in-service months come from the caller. The data model has no
   month for improvements yet (WP12.3 decides the default).
3. One land share is used for both the value and the adjusted basis of a converted home. The land part of
   fair market value and of cost are not separated.
4. Only a sale of the whole property, fully taxable to an unrelated buyer, releases suspended losses. There
   are no partial sales, installment sales, related-party sales, gifts, deaths or 1031 exchanges.
5. Other passive activities are not modeled, except as an optional amount of other passive income (no other
   passive losses). Passive credits, the commercial revitalization deduction and former passive activities
   are out of scope.
6. Active participation is a yes/no input per property. Real-estate-professional status, short-term rentals
   (average stay of 7 days or less) and personal use of a dwelling unit (IRC 280A) are out of scope.
7. MAGI for the allowance is a caller input. The Roth-conversion circularity is handled in WP12.2 (design
   section 4).
8. All depreciation is treated as taken after 6 May 1997 (relevant to 121(d)(6)). Only straight line, so there
   is no section 1250 "additional depreciation" recaptured as ordinary income.
9. A section 1231 loss is treated as ordinary in the sale year. The 5-year section 1231 loss lookback
   (1231(c)) and netting with other 1231 gains are not modeled.
10. Section 121 for converted homes: MFJ gets 500,000 when the home qualifies. This does not check that both
    spouses used the home, that either spouse owned it, or the once-in-two-years rule. Reduced exclusions for
    unforeseen circumstances and military or other suspensions of the 5-year period are not modeled. There is
    no nonqualified-use proration, because no rental use before residence use is modeled.
11. State tax follows the design: all of the sale gain is ordinary for state purposes (WP12.2). No
    state-specific passive rules.
12. Amounts are not rounded to whole dollars.

## 5. Open questions for the owner / tax preparer

1. **MFS default:** if a plan says MFS but not whether the spouses lived apart all year, the code assumes
   they lived together, so the allowance is 0. Is that the right default, or should it be a plan field?
2. **Improvement month:** improvements have no month in the data model. Which default: mid-year (July),
   January, or a new field?
3. **Sale month:** which month should the engine assume for a sale year (design R section 3 has only a sale
   year)? It sets the sale-year depreciation and the two-of-five window.
4. **Converted home dates:** for the two-of-five test, should the engine take move-out as 1 January of the
   conversion year and the sale as the assumed sale month? (R23 shows a home converted 1 Jan 2024 passes if
   sold by 1 Jan 2027.)
5. **Land share at conversion:** is one land share good enough, or should the value at conversion carry its
   own land value?
6. **Passive income from other sources:** does the household have other passive activities (K-1s) that
   should feed `other_passive_income`?
7. **Constants check:** please confirm the statutory figures in section 1 against the current IRC, Form 8582
   instructions and Pub. 527 / 925 / 946 / 523. (Done: see the verification record at the top.)

## 6. Owner decisions (2026-10-13)
1. MFS with unknown living-apart status: assume lived together, allowance $0; a household input is added in 12.4.
2. Improvements, sale and conversion without a month: mid-year (month 7) until 12.4 adds month fields; disclose in the UI later.
3. Converted home: one land share for both value and basis.
4. Reference goldens may be re-recorded for additions-only changes, reviewed in the PR.
5. Verified by the household's tax preparer on 2026-10-13, against tax year 2025 rules (not 2026). A correction lands as a small commit.

## 7. Added in 12.3 (simplifications)
- Converted home: ownership/residence start defaults to January, five years before the conversion; conversion and sale dates are the 1st of the month.
- Converted-home sale year and price are the plan's `home_sale_yr` / `home_sale_px`.
- First-death step-up: the converted sale uses the stepped-up gain basis; the loss basis is not stepped up.
- Estate sale after conversion keeps the step-up (no gain) and drops suspended losses (IRC 469(g)(2) would allow part).
- Shifted carrying costs: mortgage payment, real-estate tax, budget utilities/maintenance/other. Improvement lumps stay personal.
- Not modelled: owner split, death handling, sale-proceeds split across accounts. (Back to personal use: built in H3, section 10.) (Loan link to a Liabilities row: built in H2, section 9.)

## 8. Workbook (12.7)
New sheet `40. Rental Properties` (section 1 Reports, after Balance Sheet; letter computed per build, `1E` when on), present **only while `rental_property_income` is on**. Sections: A summary by year; B by property and year (collapsible rows); C depreciation schedule; D passive-loss ledger; E sale analysis; F metrics; G assumptions and warnings (this document's sections 4-7 in plain words, constants quoted from the reference data in force). Code: `src/reporting/rental_report_data.py` (figures), `src/reporting/sheets_rental.py` (layout).
- Rental lines (also only when on): Executive Summary block; Cash Flow columns `Rental Cash (net)` (income group) and `Rental Sale Tax` (tax group), so Σ Income and the cash bridge foot; Net Worth `Rental Equity`; Balance Sheet rental value (assets) and rental mortgages (liabilities); Lifetime Taxes columns `Rental Schedule E in AGI` and `Rental Sale Tax`; Charts: `Rental Cash` income series, `Rental Net Cost` and `Rental Sale Tax` spending series, and a Rental Properties chart (net cash flow, Schedule E added to AGI, equity).
- Per-property Schedule E after the passive limit = net Schedule E - opening carryforward + closing carryforward (sums to the plan figure). Accumulated depreciation before the plan start is recomputed from the placed-in-service dates.
- Estimates (labelled on the sheet): estimated tax effect = Schedule E added to AGI x the year's `effective_marginal_rate` (federal, Social Security inclusion, NIIT; no state); tax on the 1250 gain at a sale = gain x the lesser of that rate and 25%; federal and state tax on the long-term part come from the tax stages. The after-tax hold-to-sale return is an annual IRR (not for a converted home). Years after the last rental activity are not listed.
- The plan-file revision (`PlanStore.revision()`), the plan state and the build input fingerprint include the rental tables, so editing a rental marks the last build stale; a plan with no rental keeps its old revision.


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
