# Planning assumptions and expert decisions register

Living document. First written 2026-11-11; the "Last updated" line below says when it was last touched.

One list of every decision, direction and assumption in the system that a person with the right authority has made or still has to make: CPA, estate attorney, financial planner, economist or actuary, legal or security adviser, and the owner as software designer. It has three parts:

- **Part 1, expert decisions (sections A to D):** who decided, who approved, when, how often.
- **Part 2, laws, guidance and rates (section L):** each federal and state law, guidance document and rate the engine depends on, with its update frequency, the next expected update and where the update comes from.
- **Part 3, other assumptions needing review (section R):** modeling shortcuts, defaults and data sets that are not law but still need a person to look at them on a schedule.

**Last updated:** 2026-11-12 (added section N, limitation notices).

## Keeping this document current

This file is only useful if it is maintained. The rules:

1. **Owner of the file:** the plan owner. Claude or any maintainer may propose edits; the owner approves the "Approved by" and "Date" cells.
2. **Update it in the same change** that adds, removes or re-decides any item above: a new reference-data row, a new default, a new limitation notice, a CPA or attorney answer, a changed shortcut in the engine. A decision that is not in this file is not recorded.
3. **Annual pass:** each January, while doing the tax-year checklist in `ANNUAL_MAINTENANCE_RUNBOOK.md`, walk section L and update "Last reviewed", "Next expected update" and the value in "Used now". In the same sitting, scan sections A to D and R for rows marked TBA and either get the answer or re-date the question.
4. **Event triggers:** a new IRS Revenue Procedure, a CMS or SSA announcement, a new state budget, or a new federal law means a review of the affected section L rows within 30 days.
5. **Dates:** write ISO dates (YYYY-MM-DD). "Owner-reported" means the proof is outside the repository. Never invent an approval; use TBA.
6. **Do not put account numbers, balances or other household facts here.** Defaults and rules only.
7. Update the "Last updated" line above and add a one-line entry to the change log at the bottom.

## How to read this

- **Built-in assumption** is what the system does today, taken from the code, the reference data or the schema defaults.
- **Who decides** is the role that should own the call. **Approved by / source** names who actually approved it and where that is recorded. **Date** is the recorded approval date, or **TBA** when none is recorded in the repository.
- **Owner-reported** means the owner told Claude, and the proof (a table, an email) is kept outside the repository. Nothing is invented: where a sign-off is not on file, the row says TBA.
- **Frequency**: *Annual* (each tax year), *Law change* (re-check only when statute or a published notice changes), *Once* (decide and record), *Per plan* (a household fact), *Per release*.
- **Impact**: High moves projected net worth, tax or estate tax in a way a user would act on; Medium moves numbers or disclosures a reader could rely on; Low is wording, workflow or housekeeping.
- Related ids point to other rows in this file. `FIN-`, `QA-`, `ARC-`, `W-` ids point to `SYSTEM_REVIEW_2026-11-10.md`; `N1`-`N10` are the limitation notices in `src/limitation_notices.py`, listed in section N below.

## Coverage and limits (read before relying on this)

Sources searched: `reference_src/` (tax law, state tax, capital-market, mortality, dashboard), `reference_src/schema.csv` defaults, `src/limitation_notices.py`, `ANNUAL_MAINTENANCE_RUNBOOK.md`, `BACKLOG.md`, `RENTAL_TAX_RULES.md`, `CAPITAL_GAINS_IN_AGI.md`, the 2026-11-10 system review and its findings file, the Wave 0 decision record, the notice wording files, the engagement notes, and the "open questions" and "decisions" sections of the design specs under `documentation/future/` and `documentation/archive/superpowers/`. Code was searched for "assumption" and "simplification" comments in `src/projection_stages/`.

Not covered line by line: the 3,000-line golden-master changelog, the older archived system reviews, `src/module_catalog.py`, the frontend files and the roughly 190 "Other Assets" schema rows. The rows drawn from spec open questions (C14 to C18) come from older design documents; Claude did not check each one against the current code, so **status "unknown" means unchecked, not open**. Treat this as the first complete pass, not a certified inventory.

Dates: 2026-11-11 CPA answers were relayed by the owner in chat; the CPA has not put them in writing.

---

## A. Federal and state income tax (CPA)

| ID | Decision / assumption | Built-in assumption today | Who decides | Approved by / source | Date | Frequency | Impact | Alternatives | Related | Comment |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | Specified service trade or business (SSTB) status for QBI | `qbi_sstb` input; household is an SSTB. Below the income threshold it changes nothing today | CPA | CPA via owner; engagement notes section 3, BACKLOG | 2026-11-11 | Annual (business facts change) | Medium now, High above $403,500 MFJ | Not SSTB (no phase-out above threshold) | A2, A3, A4 | Owner must set `qbi_sstb` TRUE in the live plan; not yet done. Re-ask if services mix changes |
| A2 | QBI method: 20% of QBI, taxable-income cap, W-2 wage / UBIA limit, $400 minimum, one business | Built W3-02; owner salary is the full W-2 wage base (CPA yes) | CPA | CPA, first answers 2026-11 and 2026-11-11; N8 wording | 2026-11-11 | Annual (thresholds) | High | Aggregate several businesses; per-business limits | A1, A16, N8 | N8 stays until planner approves wording. Second entity would break "one business" |
| A3 | QBI thresholds and phase-in widths | $403,500 / $201,750 start; $150,000 / $75,000 width from 2026; indexed after 2026 | CPA (source: Rev. Proc.) | Reference rows, status legislated/verified | Reviewed 2026-09-29 to 2026-10-20 | Annual | Medium | None; statutory | A16, A17 | 2027 rows TBA until Rev. Proc. published |
| A4 | OBBBA senior deduction ($6,000 per person) phase-out threshold for joint filers | Applied per CPA reading: joint threshold; per-person reduction | CPA | CPA, first answers (FIN-002) | 2026-11 (exact day not recorded) | Law change (sunsets after 2028) | Medium | Per-person thresholds | A16 | Re-confirm each year through 2028 |
| A5 | SALT deduction base | State tax computed from the engine (retirement income and Social Security excluded), not AGI x flat rate | CPA | CPA, first answers (FIN-003) | 2026-11 | Once, then law change | Medium | Prior-year amount paid (cash-basis timing) | A6, A7 | CPA settled it; timing of payments not modeled beyond that |
| A6 | SALT cap and phase-down schedule | Cap schedule by absolute year, phase-down at high income | CPA | Reference rows (legislated) | Reviewed 2026-10 | Law change | Medium | None | A5 | Extend the schedule when law changes |
| A7 | Illinois S-corp replacement tax | 1.5% of net income less the $1,000 exemption | CPA | CPA, first answers (FIN-008) | 2026-11 | Law change | Medium | Omit (prior behaviour) | A8 | Prior code comment wrongly said it was already counted |
| A8 | Illinois PTE election | Not modeled for 2026; not elected for 2027; election is annual, made on the timely entity return (April 15); 4.95%; credit equals tax paid | CPA | CPA via owner | 2026-11-11 | Annual | Medium | Elect for 2027 (owner chose No) | A7, A1 | Wave 3 session still to ship the first-year / enable change and the no-carry-forward rule; unverified |
| A9 | Self-employed health insurance with ACA premium credit | One-pass approximation netted against the credit; premiums removed from itemized medical | CPA | CPA via owner ("No change needed") | 2026-11-11 | Law change | Low to Medium | Rev. Proc. 2014-41 iterative method | A10 | Code left as is by owner decision |
| A10 | ACA premium tax credit tables and enhanced-subsidy expiry | Original and enhanced applicable-percentage tables, FPL and benchmark premium are "assumption" rows; enhanced subsidies end after a year field | CPA or enrolled agent | Reference rows; recalled from memory, unverified; owner verified "current ACA enhanced-subsidy law" in WI-003 | 2026-10-19 (owner-reported) | Annual | High for bridge-year households | Zero credit; manual premium entry | A9, A21 | Verify against Rev. Proc. 2025-25; per-row table is held by the owner, not in the repo |
| A11 | Non-itemizer charitable deduction (IRC 170(p)) | $1,000 single / $2,000 joint from 2026, excludes DAF and QCDs, compared against itemizing | CPA | CPA via owner | 2026-11-11 | Annual (confirm no change) | Low to Medium | Ignore the deduction | A16 | Built from secondary commentary until the CPA confirmed |
| A12 | Wash-sale rules W1 to W5 | W1 buys in the same sale are not replacements; W2 oldest-first matching; W3 proportional disallowance; W4 basis add-back (lost in IRA/Roth/HSA); W5 chains | CPA | W1 confirmed by CPA via owner; W2 to W5 not asked | W1 2026-11-11; W2-W5 TBA | Once, then law change | Medium (tax reporting) | Manual disallowance only (today) | A13 | Automatic disallowance is not built (BACKLOG). Ask the CPA W2-W5 before building |
| A13 | Early distributions before 59.5 (IRC 72(t)) | 10% additional tax modeled; SEPP amount input; exceptions limited | CPA | Owner scope decision (WI-002a); CPA review of exceptions | Scope 2026-10-19; exceptions review TBA | Law change | Medium | Model all exceptions | A12 | N3 retired when WI-039 shipped |
| A14 | Social Security earnings test | Modeled (WI-040); annual limits in reference rows | Benefits counselor or CPA | Owner scope decision (WI-002b), reviewed `income.py` | 2026-10-19; professional review TBA | Annual | Medium | Ignore (prior behaviour) | A16 | SSA publishes new limits each autumn |
| A15 | Brokerage-gain MAGI phasing | Phase 1 IRMAA MAGI; Phase 2 NIIT, ACA MAGI and Social Security taxation | Financial planner; CPA for phase 2 | Owner decision (WI-002c); planner sign-off before each golden re-pin | 2026-10-19; phase 2 status unverified | Once | High (plans funded by appreciated assets) | IRMAA only | N1 | Check N1 wording against what has shipped |
| A16 | Federal reference tables (brackets, standard deduction, LTCG, IRMAA, SS wage base, AMT, QLAC/QCD, estate exclusion, earnings test, RMD divisors) | Dated rows; 139 verified, 88 "assumption", 34 legislated, 20 historical; each dashboard row reviewed 2026-09-29 to 2026-10-21 | CPA (or maintainer against primary source) | Maintainer against IRS, CMS and SSA documents; AMT and WI-003 checks owner-reported | 2026-09-29 to 2026-10-21 | Annual (mid to late January) | High | Pull live from an API | A17, A18, A3 | Never overwrite a row, add dated rows. State and AMT are flagged in N7 |
| A17 | 2027 reference rows (FIN-011) | Tables stop at 2026 | CPA; maintainer | BACKLOG row, engagement notes | TBA | Annual | High at 2027 start | Run 2027 on 2026 values with a notice | A16 | Waits on the IRS Rev. Proc. and CMS fact sheet; W2-10 warning is the stop-gap |
| A18 | State income and estate tax rows (IL, FL, TX, TN, NC, AZ, CO, NV, CA, NY, IN, SD, WY) | Rates and exemptions in `state_tax.csv`; dashboard `REVIEW_REQUIRED_BY_STATE`, blocking TRUE | CPA | Owner verified NC, IN, CA, NY and the NY estate exclusion (WI-003); other states unreviewed | 2026-10-19/20 | Each legislative session | High for a moving household | Fewer states supported | B1, B6 | One banner covers all states; no per-row review date |
| A19 | Tax-law scenario and bracket inflator | `current_law`; brackets inflate 2% a year | Financial planner or economist | Defaults, no approval recorded | TBA | Annual | Medium | Higher-rates scenario from a chosen year | C2 | Sunset of laws and chained CPI differ from 2% |
| A20 | Medicare premiums and IRMAA | Part B $185, Part D $55 per person monthly defaults; no reference backing; IRMAA tiers 2-year lookback, tiers 1-5 | Maintainer against CMS | CMS 2026 fact sheet (IRMAA verified), premiums entered per household | IRMAA 2026-09-29 | Annual (September/October) | Medium | Reference-backed premiums | A16, A21 | Nothing flags stale premiums; runbook says update each autumn |
| A21 | Qualified dividend stacking | Taxed at ordinary rates (conservative) per N2 | CPA | Disclosed in N2 | 2026-10-20 | Once | Low to Medium | Use the 0/15/20% stack | N2 | Fix status unverified |
| A22 | Rental property tax rules (14 constants, depreciation tables, 25% recapture cap, passive loss rules) | Constants verified against 2025 rules, not 2026 | Tax preparer | Household tax preparer, `RENTAL_TAX_RULES.md` | 2026-10-13 | Annual re-check, 2026 values due | High for rental owners | Fewer simplifications | A23, B8 | Re-check the 2026 values at the next tax update |
| A23 | Rental simplifications | MFS assumes lived together (allowance $0); improvements, sale and conversion in month 7; one land share; no K-1 passive income unless entered | Owner and tax preparer | Owner decisions section 6 | 2026-10-13 | Once | Low to Medium | Month fields; land value at conversion | A22 | Section 5 questions 5 and 6 (land share, other passive income) have no recorded answer |
| A24 | Home and rental sale gains in AGI (IRMAA, NIIT, ACA lookback) | Home and rental sales only; other AGI-keyed rules unchanged; IRMAA two-year lookback confirmed | Owner and tax preparer | `CAPITAL_GAINS_IN_AGI.md` | 2026-10-13 | Once | Medium | Extend to all gains (see A15) | A15 | Overlaps A15 phase 1 |
| A25 | Rental H3 move-back (nonqualified use order, suspended losses stay, mid-month convention) | Built; one rental period; reversion month 7 | Tax preparer | Header says owner and tax preparer approved; questions 10.6 listed | 2026-10-13 | Once | Low | Allow several periods | A22 | Confirm questions 10.6(a) to (c) have a written answer |
| A26 | Installment-sale gain tax | Note-installment tax design exists | CPA | Not read for this register | TBA | Once | Unknown | | | Add a row once reviewed |

## B. Estate and legal (estate attorney)

| ID | Decision / assumption | Built-in assumption today | Who decides | Approved by / source | Date | Frequency | Impact | Alternatives | Related | Comment |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | Illinois estate tax method (FIN-004) | Adjusted estate = taxable estate - $60,000; credit = lesser of old 2011(b) table and federal tax on a $4M exclusion; interrelated deduction | Estate attorney | Attorney signed off on the method | 2026-11-11 | Law change | High (was $269k vs about $40k at $4.1M) | Illinois AG calculator | B2, B3, A18 | Test values are hand-derived, not matched to the AG calculator. The backlog row still reads "Awaits attorney" and should be updated |
| B2 | DSUE and portability treatment (FIN-007, IRC 2058) | Deceased spouse's unused exemption frozen at first-death year; timely election assumed; `portability_enabled` TRUE | Estate attorney | Illinois part signed off; DSUE and 2058 treatment not recorded | TBA | Once | High after first death | Index DSUE; no portability | B1, B3 | Built in W4-02 before written sign-off. Needs the attorney's yes |
| B3 | Federal exemption derived from the household (WI-002e) | One-person household uses single exemption; couples need a portability election | Estate attorney | Owner decision | 2026-10-19; attorney sign-off TBA | Once | High | Default married exemption | B2, N6 | The credit-shelter arithmetic review is a separate attorney task (WI-003 note) |
| B4 | Basis step-up property regime | `COMMON_LAW` (50% step-up on joint property) vs community property | Estate attorney or CPA | Plan setting; no approval recorded | TBA | Per plan | Medium | Community property | A25, B8 | Matters if the household ever lives in a community-property state |
| B5 | Life insurance proceeds and estate inclusion (FIN-005) | Module toggle default OFF; when on, proceeds pay the survivor and join the estate base | Estate attorney or planner | Owner decision to build W4-04; N10 wording draft | Built 2026-11; wording TBA | Per plan | High for policy owners | Inventory only | N10, B1 | Inclusion depends on ownership and control (IRC 2042), not modeled by owner. Planner wording review pending |
| B6 | Other states' estate tax (NY exclusion $7.35M and others) | Rows in `state_tax.csv` | Estate attorney | Owner verified NY (WI-003) | 2026-10-19/20 | Law change | Medium | | A18 | Same dashboard flag as state income tax |
| B7 | Business succession value in estate | Module toggle; value added to taxable estate when on | Estate attorney and valuation expert | Not recorded | TBA | Per plan | Medium | Remove from estate | | No real inputs yet (BACKLOG) |
| B8 | Rental death handling (H5): decedent share by owner, step-up, depreciation restart, suspended-loss release | Sole 100%/0%, joint 50% (community property 100%); month 7 death | Tax preparer; estate attorney | Tax preparer approved the examples; section 12.4 questions listed | 2026-10-13 | Once | Low | | A22, B4 | Converted-home first-death step-up is not modeled |
| B9 | Heir assumptions for pre-tax inheritance | `heir_filing_status` Single; `heir_other_taxable_income` $200,000; SECURE 10-year rule | Financial planner; estate attorney | Defaults | TBA | Per plan | Medium (Roth optimizer terminal tax) | Per-heir inputs | C13 | Feeds the Roth optimizer objective |
| B10 | HSA beneficiary and consume-by rules | `hsa_beneficiary_type` spouse; consume by second-death 90th percentile | Planner; CPA | Defaults | TBA | Per plan | Low to Medium | Non-spouse (taxable at death) | | |
| B11 | Divorce stress scenario (FIN-009) | Option A: scenario label widened; splits assets, keeps joint filing | Owner (scope); planner | Owner chose option A for FIN-009 | 2026-11-10/11 | Once | Medium | Option B: Single filing, per-member accounts, divorced-spouse SS | C5 | Option B only if divorce planning is in scope |

## C. Financial planning, economics and actuarial assumptions (financial planner, economist, actuary)

| ID | Decision / assumption | Built-in assumption today | Who decides | Approved by / source | Date | Frequency | Impact | Alternatives | Related | Comment |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | Capital-market assumptions: expected return, volatility, correlation, yield by asset class and horizon | CSV presets (conservative etc.); refreshed 2026-06-09; "not a forecast" | Economist or planner | No approval recorded; dashboard row CURRENT_WITHIN_POLICY | 2026-06-09 (refresh) | Annual | High | Vendor CMA set | C2, C3 | Longest-lived assumption with no named approver |
| C2 | Macro defaults | Inflation 2.5%, COLA 2.0%, portfolio return 6%, cash yield 2%, annuity dividend 5% | Planner or economist | Defaults only | TBA | Annual | High | Per-asset path | A19, C1 | Bracket inflator 2% differs from 2.5% inflation; confirm intent |
| C3 | Monte Carlo design | 300 paths, 12% sigma, vectorized "quick" mode default; success floor $0; wellness shocks 3%/year at $150,000 | Planner | Headline "Funded as asked" decided by owner; planner reviews the displayed definition | 2026-10-19 | Once | High | Exact scalar mode; fatter tails | C4 | Vectorized mode reads about 14 to 18 points more optimistic than exact (BACKLOG QA-006) |
| C4 | Success definition and floor | Success = funded as asked with no liquid floor | Planner | Owner decision WI-002d | 2026-10-19 | Once | High | Add a reserve floor | C3 | Secondary "without Roth for extras" figure removed |
| C5 | Social Security | Benefits cut 22% from 2032 (trust-fund shortfall); survivor keeps 100%; spousal top-up approximate | Planner or economist | Defaults; stress scenario suggests about 21% | TBA | Annual | High | No cut; later cut | B11 | Phase 6 design asked whether the cut should phase in; status unknown |
| C6 | Mortality | SSA table; simulated deaths use the male table for member 1 and the female table for member 2 (FIN-012 fixed in W4-03: per-member sex) | Actuary or planner | Owner verified the table (WI-003) | 2026-10-19 | Periodic (new SSA table) | High | Sex-neutral; longevity multiplier | N7 | Per-member sex needs entry for both members |
| C7 | Spending policy | Core spending grows with CPI; spending stops inflating in 2040; 15% of spending inflation-sensitive; real-estate taxes +2.5% a year | Planner | Defaults | TBA | Per plan, annual review | High | Declining real spending; manual growth | C8 | |
| C8 | Healthcare and long-term care | Pre-65 premium input, out-of-pocket cap $10,000, LTC premium classified as an essential tier | Planner; insurance adviser | LTC reclassification spec (2026-08); no approval line | TBA | Annual | Medium | | A20 | |
| C9 | Asset allocation and glide path | 85% equity, 10% commodity, 5% cash defaults; target-date glide; risk score auto | Planner | Defaults | TBA | Per plan | Medium | Static allocation | C1 | |
| C10 | Roth conversion policy | Optimize terminal tax; 22% target bracket; 95% headroom usage; discount rate 6.5%; terminal pre-tax haircut 24%; IRMAA tier 2 target; 10 conversion years | Financial planner | Defaults; planner sign-off before golden re-pins | TBA | Annual | High | Fill-to-bracket; fixed dollar | B9, A16 | Objective weights (1.0 / 0.25) have no recorded rationale |
| C11 | Tax-loss and gain harvesting | Policy off by default; $500 minimum, 5% minimum, 2 bps cost, 50% of replacement sold before death | Planner; CPA | Defaults | TBA | Per plan | Low to Medium | Apply mode | A12 | Interacts with wash-sale rules |
| C12 | RMD age and QCD | Member RMD age 75 override; QCD capped at RMD and the annual limit | CPA | Divisors verified against Pub. 590-B | 2026-09-29 | Law change | Medium | Age 73 | A16 | Birth-year rule differs by member |
| C13 | Withdrawal cascade and HSA draws | Fixed order across account types; HSA draws "spend as needed"; blank bank means unlimited; non-qualified draws blocked | Planner | HSA specs 2026-08; owner chose bank-capped, income tax only (2026-11-03) | 2026-11-03 | Once | Medium | Optimize mode | B10 | Whether the HSA double-dip correction ships ungated was flagged for planner review |
| C14 | Annuity pricing and mortality credit | Five-segment payout curve; 1.29 mortality-credit boost; reserve decay 0.975 | Actuary | None recorded | TBA | Annual | Medium | Quoted prices | | Calibration, not market quotes |
| C15 | Housing assumptions | 6% selling cost; home-equity contingency 20% haircut, 1-year lag; optimizer uses 3BR/2BA default and no forced purchase | Planner; real estate adviser | Housing designs 2026-09 | TBA | Per plan | Medium | | | |
| C16 | Stress scenarios | Spending x1.2, 4.5% inflation, 4% return, $5,000 rent after home sale, delay-retirement and salary overrides | Planner | Phase 6 design (open questions needed sign-off) | TBA | Once | Medium | | B11 | Sign-off on divorce parameters is open |
| C17 | Adaptive spending guardrails and ELTR metric | Design open questions: which guardrail rule, per-household configurable, ELTR discount rate and denominator | Planner | Phase 3 and Phase 5 specs | Status unknown | Once | Medium | Guyton-Klinger full rule set | C10 | Check whether built before answering |
| C18 | Cash pair-status tax floor | Rule built, default OFF; forced draw credited as cash, displaces planned draws; extend to taxable, Roth, HSA later | Owner; CPA | Owner approved mechanism and scope; turn-on not approved | Mechanism 2026-11-03; turn-on TBA | Once | Medium | Add on top (strict floor) | C13 | Test on real data first; no golden change |

## D. Owner as software designer, security and compliance (owner; legal and security advisers where noted)

| ID | Decision / assumption | Built-in assumption today | Who decides | Approved by / source | Date | Frequency | Impact | Alternatives | Related | Comment |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | Limitation notice wording N1 to N7 | Owner-approved text shown in preflight, Tax Assumptions page, workbook, advisor report | Owner; planner reviews rendered text | Owner, `NOTICE_WORDING_2026-10-19` | 2026-10-20 | Per release | High (disclosure) | Legal review of disclaimers | D2 | A legal review of "not advice" wording is not recorded |
| D2 | Notice wording N8 and N10 | Draft | Owner; financial planner | Draft by maintainer | TBA | Per release | Medium | | A2, B5 | Planner wording review pending |
| D3 | Account number protection | Last four digits only; redaction tool built, not run on the live plan | Owner; security adviser | Phase 5 checklist; BACKLOG owner task | TBA | Once | High (privacy) | | D4 | Dry run first, then `--apply` |
| D4 | Public repository and history purge | Remote visibility public; history purged 2026-10-19; GitHub Support request reported complete | Owner; legal adviser if sensitive | Owner decision WI-001 | 2026-10-19 / 2026-10-20 | Once | High | Private repository | D3 | Not independently verified from the repo. Confirm repo stays free of plan data |
| D5 | Hosted use | Hosting needs authentication, Host allow-list, no unauthenticated mode (ARC-001/009) | Owner; security adviser | Owner decision | 2026-10-19 | Once | High | Stay local only | D6 | Required before any hosted deployment |
| D6 | Trends remote access | Remote guests can edit account mappings and start refreshes | Owner | Trends remote-access design | 2026-10-27 | Once | Medium | Read-only guests | D5 | |
| D7 | Vendor naming | Monarch may be named; extraction described vendor-neutral | Owner; legal adviser | Owner decision | 2026-10-19 | Once | Low | | | Vendor terms of service not reviewed (recommend) |
| D8 | Golden-master discipline | Re-pins only via `regen_golden_master.py` with a reason; measure first; hand-check one delta | Owner; planner sign-off | `CLAUDE.md`, runbook | Standing | Per release | High | | A15, C10 | Planner sign-off before each re-pin (WI-002c) |
| D9 | Document status reconciliation | Status lines updated; three rows left for the owner (Roth gap design, modularization designs, housing panel fixes) | Owner | Owner approved the table | 2026-11-11 | Once | Low | | | Three "owner to decide" rows open |
| D10 | Wave scope decisions | FIN-009 and FIN-010 option A only; Concepts Guide as in-app HTML (b); no ceiling raises | Owner | W4-07 and review decisions | 2026-11-10/11 | Once | Medium | Option B for both | B11, C16 | FIN-010 option B (per-member 401(k) limits) deferred |
| D11 | Removal triggers for legacy code | Excel fallback, parse-time migration, `legacy_conversion`, `USER_AGENT` fallback each wait on a trigger | Owner | BACKLOG, W3-11 | TBA | Once | Low | | | Owner must confirm no pre-v10 plans remain before deleting `legacy_conversion` |
| D12 | Sales ledger and broker data | Brokers Fidelity, E*Trade, Vanguard; ledger starts at the current tax year; carryforward entered; trade date = prior business day for Monarch rows; specific-lot only; state tax on gains by residence | Owner; CPA | Owner answers | 2026-10-28 | Once | Medium | Average-cost funds (dropped) | A12 | Fidelity 1099-B parser waits for a real sample about February 2027 |
| D13 | Transfer kind in broker importers | Deferred until a real file shows an in-kind transfer | Owner | Owner | 2026-11-02 | Once | Low | Manual transfers | | |
| D14 | Year-end close rules | Close warns (does not block) if broker files are old; a year with no plan figure can close | Owner | Open questions 1 and 2, "Claude's call" defaults | TBA (owner answer not recorded) | Annual | Low | Block the close | | Confirm these two defaults |
| D15 | Annual maintenance cadence | January household checklist; mid-January tax-year update; September/October SSA and CMS update | Owner | `ANNUAL_MAINTENANCE_RUNBOOK.md` | Standing | Annual | High | Calendar reminders | A16, A20 | Nothing enforces it; the app only flags stale rows |

## L. Laws, guidance and rates the system depends on (Part 2)

"Next expected update" is the usual publication window for that kind of source, not a promise. Rows marked *verify* hold a value I recalled from general knowledge and did not find in the repository: confirm against the primary source before relying on them. "Used now" comes from the dashboard (`reference_src/tax_update_dashboard.csv`) and the reference data. Stored in `reference_src/tax_law_v10.json` unless stated; rebuild `src/reference/reference.db` with `python tools/build_reference_db.py` after any edit.

| ID | Law, guidance or rate | Jurisdiction | Used now | Last reviewed | Frequency | Next expected update | Update source | Stored as / how to update | Impact if stale | Related |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 | Ordinary income brackets and standard deduction (incl. 65+ and OBBBA amounts) | Federal | Rev. Proc. 2025-32 (tax year 2026) | 2026-09-29 | Annual | Oct to Nov 2026 (Rev. Proc. for 2027) | IRS Revenue Procedure | Dated rows, brackets array; never overwrite | High | A16, A17 |
| L2 | Long-term capital gains 0% and 15% thresholds | Federal | Rev. Proc. 2025-32 sec. 4.03 | 2026-09-29 | Annual | Oct to Nov 2026 | IRS Revenue Procedure | Dated rows | High | A16 |
| L3 | Net investment income tax (3.8%, $250,000 joint threshold) | Federal | Statutory, not indexed | Verified in the 2026 review; reconfirm yearly | Law change | Only if Congress changes it | IRC 1411 | `niit_threshold` rows | Medium | A15 |
| L4 | Alternative minimum tax exemption, phase-out, rate break | Federal | Rev. Proc. 2025-32 sec. 4.10 | 2026-10-20 (owner-reported) | Annual | Oct to Nov 2026 | IRS Revenue Procedure | `amt_*` rows, one per filing status | Medium | A16 |
| L5 | Medicare IRMAA tiers (2-year lookback) and Part B / Part D premiums | Federal | CMS 2026 fact sheet dated 2025-11-14; Part D national base premium $38.99 (CMS, 2025-07-28) | 2026-09-29 | Annual | Part D base: late July; Part B and IRMAA: Oct to Nov 2026 | CMS fact sheet | Dated rows for IRMAA; household premiums are Plan Data rows (not reference-backed) | Medium | A20 |
| L6 | Social Security wage base, COLA, earnings-test limits and rates | Federal | SSA 2026 wage base $184,500; earnings test row for 2027 | 2026-10-20 / 2026-10-21 | Annual | Mid-October (COLA release) | SSA COLA fact sheet and wage-base page | Dated rows; household wage base is a separate Plan Data row | Medium | A14, A16 |
| L7 | QLAC premium limit, QCD annual limit, student-loan interest phase-out | Federal | IRS Notice 2025-67 (QLAC $210,000, QCD $111,000); Rev. Proc. 2025-32 sec. 4.29 | 2026-10-20 | Annual | Oct to Nov 2026 (IRS cost-of-living notice) | IRS Notice and Rev. Proc. | Dated rows | Low to Medium | A16, C12 |
| L8 | RMD Uniform Lifetime Table and start-age rules (SECURE 2.0 birth-year ages) | Federal | Pub. 590-B (2025) Table III, effective 2022; member RMD age override 75 | 2026-09-29 | Law change; confirm yearly | Only on a statutory or IRS table change | IRS Pub. 590-B, SECURE 2.0 | RMD divisor table; per-member age in Plan Data | Medium | C12 |
| L9 | Federal estate and gift exclusion; portability; estate rate schedule 2001(c) | Federal | IRC 2010(c)(3) as amended by P.L. 119-21; Rev. Proc. 2025-32 sec. 2.14 | 2026-10-20 | Annual (indexed) | Oct to Nov 2026 | IRS Revenue Procedure; statute | `federal_estate_basic_exclusion` row; rate schedule in `src/core.py` | High at death | B2, B3 |
| L10 | OBBBA senior deduction ($6,000 per person, phase-out) | Federal | CPA reading: joint threshold | 2026-11 | Law change | Scheduled to end after 2028 (*verify*) | P.L. 119-21; IRS guidance | Engine constants and Plan Data | Medium | A4 |
| L11 | SALT cap and phase-down schedule | Federal | Cap schedule keyed to absolute years, 7 rows | 2026-10 | Law change | Next scheduled step each January; reverts under P.L. 119-21 around 2030 (*verify*) | P.L. 119-21; IRS | `salt_cap`, `salt_phasedown_*` rows | Medium | A5, A6 |
| L12 | QBI deduction (IRC 199A): threshold, phase-in width, $400 minimum | Federal | Threshold $403,500 joint / $201,750 other for 2026; width $150,000 / $75,000 from 2026 | 2026-11-11 | Annual (threshold indexed) | Oct to Nov 2026 | IRS Revenue Procedure sec. 4.26; Treas. Reg. 1.199A | `qbi_*` rows | Medium | A1 to A3 |
| L13 | Non-itemizer charitable deduction (IRC 170(p)) | Federal | $1,000 / $2,000 from 2026, fixed | 2026-11-11 | Law change; confirm yearly | None expected | P.L. 119-21; IRS | `nonitemizer_charitable_cap` rows | Low | A11 |
| L14 | Itemized deduction limit (the "2/37" limit under P.L. 119-21) | Federal | Not modeled (deferred) | TBA | Law change | 2026 tax year onward (*verify*) | P.L. 119-21; CPA | Not stored | Medium for high earners | R17 |
| L15 | ACA premium tax credit: applicable-percentage tables, enhanced-subsidy status, FPL | Federal | 2026 tables are "assumption" rows recalled, not verified; enhanced subsidies end after a year field | 2026-10-19 status check (owner-reported) | Annual; also on any Congressional action | Rev. Proc. for 2027 in Oct to Nov 2026; FPL each January | IRS Rev. Proc. (2025-25 for 2026); HHS poverty guidelines; Congress | `aca_*` rows; Plan Data FPL and benchmark premium | High for bridge-year households | A10 |
| L16 | Early-distribution tax (10%, IRC 72(t)) and its exceptions | Federal | 10% rate; SEPP input | 2026-10 | Law change | None expected | IRC 72(t) | `early_distribution_additional_tax_rate` | Medium | A13 |
| L17 | Rental rules: 27.5-year recovery, passive loss allowance and phase-out, 25% recapture, section 121 | Federal | Constants verified against 2025 rules | 2026-10-13 | Law change; re-check yearly | Re-check at the 2027 update | IRC; Pubs. 527, 925, 946, 523, Form 8582 | `passive_rental_*`, `section_121_*` rows; `RENTAL_TAX_RULES.md` | Medium | A22 |
| L18 | Wash-sale statute (IRC 1091) and broker reporting | Federal | Rules W1 to W5 in the sales-ledger design | 2026-11-11 (W1 only) | Law change | None expected | IRC 1091; CPA | Code rules, design spec | Medium | A12 |
| L19 | 401(k), IRA and HSA contribution limits | Federal | Per-household Plan Data fields with an index toggle; 401(k) default $32,500 includes a catch-up assumption | Per plan | Annual | HSA: May (Rev. Proc.); 401(k) and IRA: Oct to Nov | IRS Rev. Proc. and Notice | Plan Data, not reference data | Medium | R16 |
| L20 | Social Security Trustees Report (depletion date, share payable) | Federal | 22% cut from 2032 default | TBA | Annual | Spring to summer 2027 | SSA Trustees Report | `ss_funding_discount_*` Plan Data | High | C5 |
| L21 | SSA period life table | Federal | Table in `mortality_table.csv` | 2026-10-19 (owner-reported) | Periodic | When SSA publishes a new table | SSA Actuarial Life Table | Reference CSV | Medium | C6 |
| L22 | Illinois individual income tax 4.95% flat, retirement income exempt | Illinois | 35 ILCS 5/203; reviewed in state table | 2026-10 | Each legislative session | Spring 2027 session; effective January | Illinois Department of Revenue; General Assembly | `state_tax.csv` | High (primary state) | A18 |
| L23 | Illinois pass-through entity tax (4.95%) and replacement tax (1.5%, $1,000 exemption) | Illinois | PTE not elected 2026 or 2027; replacement tax modeled | 2026-11-11 | Annual (election); law change (rates) | Election due on the timely entity return, April 15 | CPA; IL DOR | Plan Data `pte_*`; engine constant | Medium | A7, A8 |
| L24 | Illinois estate tax ($4M exclusion, $60,000 adjustment, 2011(b) credit table) | Illinois | Method signed off 2026-11-11 | 2026-11-11 | Law change | None scheduled | Illinois Attorney General calculator; statute | Code in `src/core.py` | High | B1 |
| L25 | Other states' income tax (NC 3.99%, IN 2.95%, AZ 2.5%, CO 4.4%, CA 9.3% graduated, NY 6.85% graduated; FL, TX, TN, NV, SD, WY none) | State | 13 states in `state_tax.csv`; dashboard `REVIEW_REQUIRED_BY_STATE`, blocking | 2026-10-20 (partial: NC, IN, CA, NY) | Each legislative session | Jan 1 changes each year; check each state's revenue-department release in Dec to Jan | State departments of revenue | `state_tax.csv` | High if moving states | A18 |
| L26 | State retirement-income and Social Security exemptions | State | Columns `exempt_retirement`, `exempt_ss`, `retirement_exempt_over_65` | 2026-10-20 | Each legislative session | With L25 | State departments of revenue | `state_tax.csv` | Medium | L25 |
| L27 | State estate and inheritance taxes (IL, NY exclusion $7.35M; others) | State | `estate`, `estate_exempt`, `estate_calc` columns | 2026-10-20 | Law change | With L25 | State statutes; attorney | `state_tax.csv`; `src/core.py` | Medium | B6 |
| L28 | State property and sales tax rates | State | `prop_rate`, `sales_rate` columns; housing data from ZIP metrics | TBA | Annual | Year start | State and local revenue departments; data vendor | `state_tax.csv`, `zip_metrics.csv.gz` | Low to Medium | R9 |
| L29 | State HSA conformity (CA and NJ do not recognize HSAs) | State | `hsa_state_conformity` default TRUE | TBA | Law change | Rare | State statute | Plan Data | Low | B10 |

## R. Other assumptions needing review (Part 3)

Not law and not a single expert's decision: modeling shortcuts, defaults and data sets. Each needs a named reviewer on a schedule. "Reviewer" is the role that should look; nobody is named yet unless stated.

| ID | Assumption | Where it lives | Why it matters | Reviewer | Last review | Frequency | Trigger for an earlier review | Impact | Related | Comment |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | Schema defaults that look like one household's figures: first-retire year 2029, rollover year 2030, spending freeze 2040, home-sale year 2045, post-sale rent $5,000, proceeds account name, HSA window 2031 to 2040, scenario salary $50,000 | `reference_src/schema.csv` | A blank plan projects numbers nobody entered (the W1-04 problem) | Owner | TBA | Per release | Any new plan section | Medium | D8 | W1-04 removed some; these remain. Decide: blank, or neutral defaults |
| R2 | Roth conversion estimate is deliberately simplified: assumes no conversion when estimating Social Security, SALT uses a one-year approximation, gross income = AGI | `src/projection_stages/roth_conversion_and_agi_tax.py` | Drives conversion size | Planner; CPA | TBA | Annual | Any tax-law change in L1 to L13 | High | C10 | Comment in code calls it a "deliberate simplified estimate" |
| R3 | Other-asset sale tax uses the stage-9 ordinary income as the federal stack base | `src/projection_stages/other_asset_sale_tax.py` | Sale-year tax | CPA | TBA | Annual | Large sales | Low to Medium | A15 | Approximations listed in the module docstring |
| R4 | Business income base: net business income after salary and employer FICA | `src/projection_stages/income.py` | S-corp income tax and QBI | CPA | TBA | Annual | Business changes | Medium | A1, A2 | |
| R5 | Social Security early-claim factors are linear between age 60 and full retirement age | `src/projection_stages/social_security_factors.py` | Early-claim benefit | Planner | TBA | Once; after SSA rule change | SSA change | Low | C5 | Code says the error is small |
| R6 | QCD larger than the current year's RMD is capped (phase 1 scope) | `src/projection_stages/spending_and_rmd.py` | QCD planning | CPA | TBA | Annual | QCD law change | Low | L7 | |
| R7 | Rental simplifications: owner split, change of use, MFS living-apart default | `src/projection_stages/rental_property.py`; `RENTAL_TAX_RULES.md` | Rental tax | Tax preparer | 2026-10-13 | Annual | New property | Low to Medium | A23 | |
| R8 | Home sale: estate sale at market value; selling cost 6%; home appreciation | `src/projection_stages/home_sale.py`; schema | Estate and sale year | Planner; real estate adviser | TBA | Annual | Market change | Medium | C15 | |
| R9 | ZIP metrics, top cities and housing optimizer data (no documented source or refresh date) | `reference_src/zip_metrics.csv.gz`, `top_cities.csv` | Housing optimizer outputs | Owner | TBA | Annual | Data vendor change | Low to Medium | L28 | Document the source and the refresh date |
| R10 | Real-loss probability curves | `reference_src/real_loss_probability.csv` | Monte Carlo and optimizer | Planner or actuary | TBA | Annual | Methodology change | Medium | C3 | No source or approval recorded |
| R11 | Per-asset distribution yield, qualified-dividend fraction and tax-exempt yield | `capital_market_assumptions.csv` | Taxable income from investments | Planner; CPA | 2026-06-09 | Annual | CMA refresh | Medium | C1 | Qualified dividends are taxed at ordinary rates today (N2) |
| R12 | Annual earned-income increase 3%; real-estate tax growth 2.5%; core-spending growth with CPI | Plan Data defaults | Cash-flow path | Planner | TBA | Annual | Inflation regime change | High | C2, C7 | |
| R13 | Monte Carlo tuning: 300 paths, parity tolerance between vectorized and exact engines, widened drift gate | schema; tests | Reliability of the success rate | Planner; owner | TBA | Per release | Engine change | High | C3 | Vectorized reads 14 to 18 points optimistic (BACKLOG) |
| R14 | Price and balance feeds (Monarch import mapping, price cache) | `src/monarch_*`, `src/market_data.py` | Starting balances | Owner | TBA | Monthly spot check | Vendor change | Medium | D7 | Mapping redesign is on a separate branch |
| R15 | Help text, Concepts Guide and glossary wording | `documentation/future/`, `.docx` guide | A reader acts on stale text | Owner; planner | TBA | Annual and per release | Any rule change in L | Medium | D1 | Concepts Guide to become in-app HTML |
| R16 | 401(k) model: one earner, one limit, no age-based catch-up (FIN-010 option A) | `src/projection_stages/income.py`; `src/parsing/client_sections.py` | Contribution planning | Planner; owner | 2026-11-10 | When priorities change | Second earner added | Medium | D10, L19 | Option B deferred |
| R17 | 2/37 itemized limit not modeled | Engine | High earners' tax | CPA | TBA | Annual | Itemizing households | Medium | L14 | Deferred in Wave 3 |
| R18 | Estate-tax objective mode and heir assumptions inside the Roth optimizer | schema (`estate_tax_objective_mode`, `heir_*`) | Conversion size near estate-tax range | Planner; estate attorney | TBA | Annual | Estate near the exclusion | Medium | B9 | |
| R19 | Frozen sample plan and frozen holdings prices used for golden tests | `tests/fixtures/` | A drift means engine change | Owner | Standing | Per release | Any engine output change | Medium | D8 | Do not point scripts at the live plan |

## N. Limitation notices (what the "Related" column means by N1 to N10)

The notices are the in-product disclosures defined in `src/limitation_notices.py` (`NOTICES`), shown in preflight, the Tax Assumptions page, the workbook and the advisor report. This section lists them so a Related id can be looked up here. The code is the source for the exact wording and the removal conditions; wording for N1 to N7 is row D1 and for N8 and N10 row D2. N9 (Illinois estate tax, FIN-004 method) was removed once the attorney confirmed the method (row B1). Status is as of 2026-11-12.

| Id | Finding | Severity | Shown when | What it tells the reader | Status | Related rows |
|---|---|---|---|---|---|---|
| N1 | FIN-001 | warning | Plan sells taxable holdings at a gain | Gains from taxable sales were not counted in IRMAA, NIIT, ACA and Social Security taxation | Both removal triggers (WI-024 phases 1 and 2) are marked shipped, so the notice is retired | A15, D1 |
| N2 | FIN-003 | info | Plan has taxable equity holdings | Qualified dividends taxed at ordinary rates (conservative) | Retired: the stacking fix (WI-023) shipped | A21, R11, D1 |
| N3 | FIN-004 | warning | Pre-tax draws before age 59½ | The 10% early-distribution tax was not included | Retired: modeled (WI-039) | A13, D1 |
| N4 | FIN-010 | info | Joint taxable accounts | The survivor's step-up on a spouse's joint account was not modeled | Retired: symmetric step-up shipped (WI-025) | D1 |
| N5 | FIN-007 | warning | Claim before full retirement age with wages | The Social Security earnings test was not modeled | Retired: modeled (WI-040) | D1 |
| N6 | FIN-009 | warning | One-person household with a couple-sized estate exemption | Estate tax may be understated | Active until saved plans no longer carry an explicit couple-sized exemption (a blank exemption is already derived from the household) | B3, D1 |
| N7 | FIN-005, FIN-006 | info | Always | Reference data status by family: verified, assumption or unreviewed | Always on; the status changes as data families are verified | A16, C6, D1 |
| N8 | FIN-001 | warning | QBI on and the plan has an S-corp or sole-proprietor business | QBI treats the business as one business; `qbi_sstb` and `qbi_ubia` come from Plan Data | Active: the CPA's answer is recorded (A1), but `qbi_sstb` is still to be set in the live plan, so the notice stays (see `NOTICE_WORDING_2026-11_WAVE2.md`) | A1, A2, D2 |
| N10 | FIN-005 | info | The Existing Life Insurance module has a policy | Policies are an inventory only; proceeds do not reach the survivor or the estate | Active until policy proceeds are integrated (W4-04) | B5, D2 |

Rows retire their notice only when every "remove" trigger in the code is marked shipped (`Notice.retired`). Check the code before relying on the Status column above, which was read from it on the date given.

## E. Engagement status

| Engagement | Status |
|---|---|
| CPA | Answers relayed 2026-11-11; firm and engagement date not recorded. Open: written confirmation, W2-W5 wash-sale rules, 2027 rows, state rows |
| Estate attorney | Illinois method signed off 2026-11-11. Open: DSUE and IRC 2058 (B2), federal exemption derivation (B3), life insurance inclusion (B5) |
| Financial planner | No sign-off recorded for C1 to C10; planner wording review of N8 and N10 pending |
| Economist / actuary | No named reviewer for C1, C5, C6, C14 |
| Legal / security adviser | None engaged; D1, D3, D4, D5, D7 have owner decisions only |

The question wording for the professionals, the original per-finding questions and the eleven numbered CPA answers (relayed 2026-11-11, not yet in writing) are kept in `PROFESSIONAL_REVIEW_ENGAGEMENT_NOTES_2026-11.md`. That file is not folded into this register because the register holds one row per decision and has no place for ready-to-send question text or the answer-to-question trail; fold it in once the CPA's written confirmation arrives and the questions are closed.

## F. Most useful next steps

1. Ask the CPA in writing for W2 to W5, the 2026 re-check of the rental constants (A22) and the 2027 rows (A17).
2. Ask the estate attorney to confirm B2, B3 and B5 in the same note as B1.
3. Name an approver and a review date for C1, C2 and C5. These drive every projection and have no recorded sign-off.
4. Set `qbi_sstb` in the live plan (A1) and run the redaction tool (D3).
5. Fix the stale statement on the owner's three "owner to decide" document rows (D9). (The backlog's Illinois estate row, B1, was corrected 2026-11-12.)

## Change log

- 2026-11-11: first version (sections A to F), then split into three parts and added sections L and R, the maintenance rules and this log.
- 2026-11-12: added section N (limitation notices N1 to N10), which the Related column already referred to.
