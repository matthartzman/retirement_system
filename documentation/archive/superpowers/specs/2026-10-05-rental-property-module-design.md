# Rental Properties module — design (DRAFT for review)

Status: draft for owner review. **Nothing here is built.** Sequencing and staffing live in `2026-10-05-master-plan-tiers-and-file-elimination.md` (WP12).
Builds on: the housing refinement design §13 "Phase 2 — keep and rent out" (`2026-09-16-housing-optimizer-refinement-design.md`), which already lists what a rental channel needs; the engine today has none of it (`src/housing/__init__.py` states "no rental income is modelled").

## 1. Decisions (owner, 2026-10-05)

| # | Decision |
|---|---|
| 1 | **Tax depth: Standard.** Rent and operating expenses net on Schedule E into AGI; mortgage interest; 27.5-year depreciation; passive-activity loss limits with the active-participation allowance and suspended-loss carryforward; NIIT; state tax; sale with §1250 recapture and LTCG. Excluded: 1031 exchanges, QBI, real-estate-professional status, short-term-rental rules. |
| 2 | **Home conversion is included now.** A current or future home can be converted to a rental ("keep and rent out"), and the housing optimizer can propose it. |
| 3 | **UI:** a new **Rental Properties** page under *Investments & Property*, a switchable feature in the Advanced tier. |
| 4 | **Build order:** engine first (behind the feature switch, default off), UI, data and workbook after the storage work (see master plan WP12). |

**Reconciling 1 and 2 (my interpretation — confirm):** home conversion needs part of §121, but the decision to keep Standard depth rules out a global §121 change. So the two-of-five-year ownership-and-use test applies **only to homes converted to rentals**; every other home sale in a plan is computed exactly as today, so existing plans and golden numbers do not move. The non-qualified-use ratio is not needed: it only bites when rental use comes *before* residence use, which this module does not model. Hardening §121 for every sale stays a separate, later change.

## 2. Goals and non-goals

Goals: model rent as an income stream with its real tax treatment; keep cash flow, AGI, NIIT, IRMAA/ACA MAGI, net worth, balance sheet and the sale consistent; show it in the workbook and the UI; let the household convert a home into a rental.
Non-goals: 1031 exchanges, QBI, real-estate-professional status, short-term rentals, refinancing events, entity (LLC/partnership) ownership, state-specific passive-loss rules, tenant-level detail.

## 3. Data model

One **property** per record; a plan holds any number (practical UI limit 20, the same as Other Assets).

| Group | Fields |
|---|---|
| Identity | name; kind (`Standalone` or `Converted home`); owner split (member 1 / member 2 / joint) |
| Basics | purchase date; purchase price; land share of basis (default 20%); closing costs added to basis; current value and as-of date; annual appreciation |
| Converted home only | link to the plan's home; conversion year; value at conversion; basis and depreciation start = lesser of value at conversion and adjusted basis |
| Income | monthly rent; vacancy %; annual rent growth; rental start and end year |
| Expenses | property tax (and growth); insurance; maintenance % of rent; management % of rent; HOA; utilities; other; expense growth |
| Financing | either a link to an existing liability row, or loan terms (balance, rate, payment or term); interest and principal come from the amortization |
| Tax | placed-in-service month; capital-improvement list (added to basis, depreciated over 27.5 years from the year placed); passive-loss options (active participation yes/no) |
| Sale | sale year; sale price (appreciated value or typed); selling cost % |
| Overrides | per-year grid for rent, expenses and one-off items, for years that differ from the formulas |

Storage (after the storage work): typed tables `rental_properties`, `rental_improvements`, `rental_year_overrides` in `plan.db`; the carried passive losses and accumulated depreciation are computed by the engine, never stored as inputs.

## 4. Tax and projection design

All thresholds and rates come from the tax-law reference data (added to `tax_law` in `reference_data/` now, carried into `reference.db` by master plan WP3.2), never hard-coded.

1. **Schedule E.** Per property and year: gross rent × (1 − vacancy) − operating expenses − mortgage interest − depreciation = net rental income or loss.
2. **Depreciation.** Residential, straight-line over 27.5 years, mid-month convention (IRS Publication 946 Table A-6 percentages). Depreciable basis = (price + closing costs) × (1 − land share), plus improvements from their placed-in-service year. For a converted home the basis is the lesser of value at conversion and adjusted basis, excluding land. Depreciation is "allowed or allowable", so it accrues even in years with a loss.
3. **Passive-activity loss limit.** A net loss offsets other passive income first. Remaining loss is allowed up to the **$25,000 active-participation allowance**, reduced by 50% of MAGI above **$100,000** and gone at **$150,000** (married filing separately: the rule's own thresholds, from reference data). Disallowed loss is suspended and carried forward per property, and released when the property is fully sold. MAGI for the limit is computed before passive losses.
4. **AGI, NIIT and MAGI.** Net rental income enters AGI, MAGI for IRMAA and ACA, and the net investment income base for NIIT (rental income is NII unless the owner is a real-estate professional, which is out of scope).
5. **Cash flow.** Cash flow = rent received − operating expenses − debt service (interest and principal) − improvements; taxes are produced by the existing tax stages. For a converted home, the carrying costs the engine counts as spending today (`spending_and_rmd.py:347-355`) move to Schedule E from the conversion year, so nothing is counted twice; the principal part of the payment stays a financing flow.
6. **Net worth and balance sheet.** Property value and mortgage appear as their own lines; a standalone property must not also be entered under Other Assets (the page warns on a name or value match).
7. **Sale.** Net proceeds = price − selling costs. Adjusted basis = basis + improvements − accumulated depreciation. Gain = net proceeds − adjusted basis. **Unrecaptured §1250 gain** = min(gain, accumulated depreciation), taxed at ordinary rates capped at 25%; the remainder is LTCG. Released suspended passive losses offset the year's income. State tax treats all of it as ordinary.
8. **§121 for converted homes.** The exclusion ($250,000 single / $500,000 married filing jointly) applies only if the home was owned and used as the principal residence for at least two of the five years before sale; depreciation taken is never excluded. Failing the test, the full gain is taxable. All other home sales are unchanged.

**Roth conversion interaction.** The passive-loss allowance depends on MAGI, which includes any Roth conversion, which is itself sized from AGI. Resolution: the conversion sizing uses MAGI before conversion for the allowance; the final tax stage uses the actual MAGI; the difference is logged and bounded (the existing guardrail panel is unaffected because rental income is a known input, not a choice). The engine agent confirms this with a test that converts under a loss-making rental.

## 5. Feature registration

| Item | Value |
|---|---|
| Key / name | `rental_property_income` / Rental Properties |
| Kind, domain, demand | PROJECTION, Housing & Property, MEDIUM |
| Switch | module toggle, default off; tier **Advanced** (advanced fields: Expert); `engine_participation=True` |
| Nav | page `rental_properties` in *Investments & Property* |
| Workbook | new sheet in section 1 (Reports), placed after Balance Sheet (adjustable) |
| Soft dependents | Executive Summary, Cash Flow, Net Worth, Balance Sheet, Lifetime Taxes, Charts each add rental lines only when on |
| Off | no rental rows or sheet; data kept ("Off · N rows entered"); the engine ignores it and the switch states that |

## 6. UI screens

1. **Rental Properties page.** Summary strip (annual net cash flow, taxable rental income, suspended losses carried, total equity); property table (name, kind, value, rent, net yield, sale year) with add, duplicate, remove; warnings (possible double count with Other Assets, loss limited by the passive rule, converted home failing the §121 test).
2. **Property detail** (tabs, mobile-friendly cards): Basics · Income · Expenses · Financing · Tax · Sale · Overrides. Standard fields are visible when the feature is on; passive-loss options, improvements, depreciation detail and the override grid are Expert-tier ("Show advanced").
3. **Convert my home** action on the property page (and a matching choice in Next Housing Move / Housing Comparison): pre-fills the converted-home fields from the plan's home.
4. **Interview question** (master plan 5.3): "Do you own, or plan to own, rental property?" turns the feature on.
5. A mockup is reviewed by the owner before the page is built (WP12.5), following the pattern used for the Roth guardrail panel.

## 7. Workbook output

New sheet **Rental Properties** (stable name `40. Rental Properties`), sections:
- **A. Summary by year:** gross rent, vacancy, operating expenses, interest, depreciation, net Schedule E, passive loss allowed and suspended, estimated tax effect, debt service, net cash flow.
- **B. By property and year:** the same columns per property (collapsible outline like Spending Summary).
- **C. Depreciation schedule:** basis, land, annual and accumulated depreciation, adjusted basis.
- **D. Passive-loss ledger:** opening carryforward, current loss, allowance used, closing carryforward, release at sale.
- **E. Sale analysis:** price, selling costs, adjusted basis, §1250 recapture, LTCG, §121 result for converted homes, tax at sale, net proceeds.
- **F. Metrics:** cap rate, net yield on value, cash-on-cash, after-tax hold-to-sale return.
- **G. Assumptions and warnings:** the rules above in plain words, and every limitation in section 2.

Also: a rental line in Executive Summary, Cash Flow, Net Worth, Balance Sheet and Lifetime Taxes, and a rental series in Charts, each present only when the feature is on.

## 8. Engine integration points

`src/projection_stages/income.py` (rental net into the income stage), `roth_conversion_and_agi_tax.py` (AGI, MAGI, NIIT base; passive-loss allowance), `spending_and_rmd.py:347-355` (carrying-cost shift), `home_sale.py:53-72` (`_compute_home_sale_economics`: recapture, converted-home §121 test), `portfolio_growth_and_net_worth.py` (property equity), `cashflow_breakdown.py`, `deterministic_engine.py` (orchestration and result-row fields), `housing/` (`rent_out` disposition, dual-ownership predicate, candidate notes, removal of the Phase 1 disclosure text), `module_catalog.py`, `data_io.py` (one parse boundary producing `c['rental_properties']`), workbook builders and `result_contract.py`.

## 9. Testing

- **Tax core:** unit tests from IRS-style examples (the repository already keeps `tests/fixtures/irs_style_examples.json`): depreciation percentages by placed-in-service month, allowance phase-out at the thresholds, recapture versus LTCG split, suspended-loss release.
- **No change when off:** the golden equality test stays green with the feature off.
- **On:** new sanctioned golden cases (loss-making rental, profitable rental, converted home that passes and fails the two-of-five test, sale with recapture, MFS and single filers).
- **Cross-checks:** a tax-preparation-style worksheet reconciliation per case; double-count guard; Roth conversion under a passive-loss limit.
- **UI and workbook:** frontend tests for the page, Playwright end-to-end, workbook snapshot expectations for the new sheet.

## 10. Risks and checkpoints

- **Tax-rule accuracy:** the owner (or the owner's tax preparer) reviews the rule section and the worked examples before the engine merges (checkpoint at WP12.1).
- **Double counting** with Other Assets and with the home's carrying costs: tested and warned.
- **MAGI circularity** with Roth conversions (section 4).
- **Scope creep** into excluded features: the "Assumptions and warnings" section lists each limitation so it is visible to users.
- **Housing integration** is the most coupled part and is its own PR (WP12.8).
