# Annual Maintenance Runbook

Checklist for keeping this retirement planning system accurate as calendar
years pass. Written for whoever is maintaining this system years from now,
who may not have this session's context.

## Why this exists

Retirement projections depend on IRS/CMS/SSA constants that change every
year, and on a household's own YTD tracking that needs a fresh starting
point every January. Nothing in the system enforces these updates
automatically — the app can only *detect and flag* staleness (see
"How the system tells you" below); a person still has to act on the flag.
This document is the actual step list for that person.

## New-year checklist (household-level, ~30 minutes, do in the first week of January)

The **Year-End Transition** page (Track & Reconcile) lists these steps in order, shows which are done, and links to each screen; the list below is the same checklist in prose.

1. Open the app. If reference constants are overdue for review, a banner on
   the Plan Status page lists them (see below) — resolve any household-level
   items now.
2. Go to **Actual Spending (This Year)** → **Accounts & Sources**. If any
   growth-tracked account shows a "Start `{year}` tracking" prompt, click it.
   This copies each account's current value into "Prior Year End Balance" and
   dates it 12/31 of the prior year, so YTD growth tracking and the
   current-year Net Worth/Cash Flow blend start clean for the new year.
3. Update any personal numbers that changed at the new year: new salary, new
   401(k)/HSA contribution elections, new Social Security benefit letter
   figures, new pension COLA.
4. **Close last year's cash reconciliation.** Import the final broker files, then
   on the Sales Ledger page open **Cash in investment accounts** and, for the year
   that just ended, resolve any unmatched rows and click **Close `{year}`**. The close
   freezes the year's reported withdrawals and the plan's figure from a saved run
   that projected that year (build a report in December so one exists). It feeds no
   tax number; a late broker file later shows "Changed since close", and **Reopen**
   lets you close again. Nothing closes a year automatically.
5. **Illinois pass-through entity (PTE) election.** The election is annual and is
   made on the timely entity return (April 15). Decide it each January with the
   CPA: the plan assumes it is not elected for 2026 or 2027 (register rows A8 and
   L23), so a changed decision means changing the plan and re-recording the
   decision there.
6. **Business-income deduction (QBI) review.** If the household has self-employment
   income, confirm `qbi_sstb` (Cashflow > Self-Employment) is set correctly: TRUE
   when the business is a specified service trade or business. The CPA confirmed
   the business is one, but the field defaults to FALSE and must be set in the plan
   itself (see `NOTICE_WORDING_2026-11_WAVE2.md`, notice N8). Also review
   `qbi_ubia` and the QBI thresholds after the new Revenue Procedure.

## Tax-year checklist (maintainer-level, ~30-60 minutes, do in mid-to-late January after the IRS Revenue Procedure for the new year is published)

**The one rule.** `reference_src/tax_law_v10.json` (built into the shipped `src/reference/reference.db`) is the only source of federal
statutory values the engine reads (`src/taxes.py` builds every federal table from
it; `src/tax_law.py` picks, for a given year, the row with the latest
`effective_year` that is on or before that year and not past its `expires_year`).
**Add new dated rows; never overwrite an existing row's value.** Every row carries
an `effective_year`, and that date is also the base year the engine indexes
forward from (`FEDERAL_BRACKETS_VALUE_YEAR`, `STANDARD_DEDUCTION_VALUE_YEAR`,
`IRMAA_TIERS_VALUE_YEAR` and the other `*_VALUE_YEAR` constants in `src/taxes.py`
are derived from those dates -- do not edit them by hand). Editing a value in
place mislabels its value year and silently mis-indexes every later year.

1. Read the relevant IRS Revenue Procedure, CMS Medicare fact sheet and SSA
   announcement for the new tax year, and note the document and date you used
   for each value. After editing `reference_src/`, rebuild the shipped database with
   `python tools/build_reference_db.py` (bump `REFERENCE_RELEASE` in that tool) and run the
   golden tests; the engine reads only `reference.db`. Additive tax-constant rows may re-record the `tax_law` goldens (owner decision, WP12a): the diff must be additions-only, recorded with a reason via `tools/golden_compare.py record --reason ...` and the reference-db flow, with a `GOLDEN_MASTER_CHANGELOG.md` entry, reviewed in the PR. `python tools/build_reference_db.py --check`
   exits 1 when the committed database does not match a fresh build (it compares `ref_meta`, which carries the content hash, and the schema).
2. In `reference_src/tax_law_v10.json`, append a row (or, for brackets, a full
   table) with the new `effective_year`, a `source` naming the document, and
   `status` set to reflect whether the value is verified or an assumption, for
   **every value family the file holds**, for every filing status the family
   already has. The file itself is the list of families (open
   `reference_src/tax_law_v10.json` and add a row for each `family` it holds,
   including any added since this runbook was written), and section L of
   `PLANNING_ASSUMPTIONS_AND_EXPERT_DECISIONS_REGISTER.md` records, per law, what
   the system assumes, how it is sourced and whether it is indexed or fixed
   by statute. Keep one source: do not copy the family list back into this file.
   Families that are statutory and not indexed (the NIIT threshold, the
   student-loan statutory cap, the early-distribution rate, the rental rules in
   `RENTAL_TAX_RULES.md`) still need their value re-confirmed each year.
   Leave the previous rows in place: the lookup uses them for earlier years.
3. Update `reference_src/tax_update_dashboard.csv`: for each family you just
   refreshed, set `year` to the new value year and `last_reviewed` to today.
   The staleness banner compares `year` with the reference year, so do this
   **only after every row of that family is added** -- a bumped date over stale
   values is worse than a visible banner.
4. `tax_constants.csv` has been removed; the dated dataset
   (`reference_src/tax_law_v10.json`) is the single source.
5. **Rental constants.** The rental constants (`residential_rental_recovery_years`, `passive_rental_*`, the 25% recapture cap), the Table A-6 depreciation percentages and the passive-loss thresholds were verified by the household's tax preparer on 2026-10-13 against tax year 2025 rules only. Re-check the 2026 values and Table A-6 with the preparer at this update, then update `documentation/reference/RENTAL_TAX_RULES.md` (rules in that file).
6. **Contribution limits are not reference data.** 401(k), HSA (self-only and
   family) and similar limits are per-household Plan Data fields -- for example
   `annual_401k_limit_base_year` (Cashflow > Retirement Contributions) and
   `self_only_annual_limit_base_year` / `family_annual_limit_base_year` (HSA
   Policy > Contributions), each with an `index_*_limit` toggle. Update them in
   the plan (see the Contributions rows of `reference_src/schema.csv`), not in
   the tax-law dataset.
7. If your own household's per-plan Social Security wage base or Medicare
   premium fields (the plan rows in the "Payroll Tax" / "Wellness >
   Medicare" sections, edited in the app) are meant to track the new official figures rather
   than a custom override, update them there too -- these are separate,
   per-household fields and are **not** auto-populated from the JSON dataset
   (see "Known gaps" below).
8. Confirm `reference_src/state_tax.csv` (rebuild `reference.db` after editing) for your household's state (and any
   comparison state under consideration) -- state legislative sessions run on
   their own schedule, not a fixed month, so re-check this row whenever state
   tax law changes, not just annually.
9. Update `documentation/reference/PLANNING_ASSUMPTIONS_AND_EXPERT_DECISIONS_REGISTER.md`: section L (laws, guidance and rates) gets
   the new values, last-reviewed dates and next expected update; scan sections A to D and R for rows still marked TBA.
10. Measure before you regenerate anything: run
   `python tools/regen_golden_master.py measure`, confirm the movement in
   terminal net worth and lifetime tax is in the direction and size the new
   values imply, then follow `GOLDEN_MASTER_RECOVERY_RUNBOOK.md` to re-pin and
   log it in `GOLDEN_MASTER_CHANGELOG.md`.

## SSA/CMS-announcement checklist (~15 minutes, do in late September/October when the *next* year's figures are announced ahead of time)

1. Note the newly-announced Social Security wage base and Medicare Part
   B/D premiums for next year.
2. You can enter these in the app (the household's Payroll Tax and Wellness > Medicare fields) as soon as they're
   announced (they take effect January 1, so there's no rush, but doing it
   now avoids a January scramble).

## As-needed, not calendar-bound

- **Capital market assumptions** (`reference_src/capital_market_assumptions.csv`,
  `reference_src/asset_correlations.csv`; rebuild `reference.db` after editing): review whenever your long-term
  market outlook actually changes, at minimum annually. Update the
  `capital_market_assumptions` row in `tax_update_dashboard.csv`'s
  `last_reviewed` date after any refresh so the staleness banner reflects it.
- **State tax law**: varies by state legislative session (see above).
- **User-facing documentation, after any module/file consolidation.** When source files
  are merged or renamed (e.g. `tax_data.py` folded into `taxes.py`), prose that names
  the old file — in the Executive Summary's Release Notes, the Glossary, QC notes, or
  this documentation tree — goes stale silently; nothing flags it. A 2026-07 review
  found three such stale references that had survived past consolidations (a stale
  `CLAUDE.md` line count, an Executive Summary pointer to the already-merged
  `tax_data.py`, and a QC-sheet RMD-cohort caveat overtaken by a later engine change).
  After any consolidation, grep the merged/renamed identifier across `src/reporting/`
  and `documentation/` and correct or remove what you find, in the same change that
  did the consolidation — not as a follow-up.

## How the system tells you something is due

- **Plan Status page banner**: surfaces any row from
  `reference_src/tax_update_dashboard.csv` whose computed status is stale or
  blocking (via `src/governance.py:tax_law_dashboard()`), fetched from
  `GET /api/admin/tax-law-dashboard`. Rows marked `CURRENT_UNTIL_LAW_CHANGE`
  (e.g., the RMD divisor table) are excluded even if their `year` is old,
  since those are stable-until-changed, not annually-refreshed.
- **YTD rollover nudge**: on the **Accounts & Sources** panel, shown per
  account whenever its "Prior Year End Date" doesn't match December 31 of
  last year.
- Both mechanisms are advisory, not build-blocking, by design — the app will
  still build reports with stale reference data; it just tells you so you
  can judge whether that's acceptable for the review at hand.

## Known gaps (things a person still has to catch)

- **Per-household Social Security wage base is not auto-populated from
  the tax-law dataset.** The household plan row
  `ss_wage_base_base_year` (Payroll Tax > Social Security) is the one actually used by payroll tax
  calculations (`src/data_io.py`) — it does not read from
  the dataset's `ss_wage_base` row at all. These two
  numbers can drift (they already have, in this plan, as of this writing —
  confirm both against a current SSA source before relying on either). A
  single hardcoded fallback constant (`DEFAULT_SS_WAGE_BASE` in
  `src/data_io.py`) is used only when the household field is blank.
- **Medicare Part B/D/G premiums** (plan rows, "Wellness >
  Medicare") are entered per-household with no reference-table backing at
  all — there's nothing to "de-duplicate," but also nothing that will ever
  flag them as stale. Update them every September/October per the checklist
  above; nothing in the app will remind you.
- **State tax data** has no per-row last-reviewed date, only the single
  dashboard entry covering all states at once — if you maintain plans in
  multiple states, that one flag doesn't tell you which state's data is
  actually stale.
