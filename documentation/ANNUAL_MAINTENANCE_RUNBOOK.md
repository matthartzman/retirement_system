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

## Tax-year checklist (maintainer-level, ~30-60 minutes, do in mid-to-late January after the IRS Revenue Procedure for the new year is published)

1. Read the relevant IRS Revenue Procedure and CMS Medicare announcement for
   the new tax year.
2. Update `reference_data/tax_constants.csv`: standard deduction (MFJ,
   Single, HOH, MFS), over-65 additional deduction, 401(k)/HSA/IRA
   contribution limits, Social Security wage base.
3. Update `reference_data/tax_law_v10.json`: federal ordinary brackets, LTCG
   thresholds, IRMAA tiers and surcharges.
4. Update `reference_data/tax_update_dashboard.csv`: bump `year` and
   `last_reviewed` for every row you just refreshed, so the in-app staleness
   banner (Plan Status page, and Settings → System Configuration → Tax-law
   update dashboard) stops flagging them.
5. If your own household's per-plan Social Security wage base or Medicare
   premium fields (`input/client_household.csv`, "Payroll Tax" / "Wellness >
   Medicare" sections) are meant to track the new official figures rather
   than a custom override, update them there too — these are separate,
   per-household fields and are **not** auto-populated from
   `tax_constants.csv` (see "Known gap" below).
6. Confirm `reference_data/state_tax.csv` for your household's state (and any
   comparison state under consideration) — state legislative sessions run on
   their own schedule, not a fixed month, so re-check this row whenever state
   tax law changes, not just annually.

## SSA/CMS-announcement checklist (~15 minutes, do in late September/October when the *next* year's figures are announced ahead of time)

1. Note the newly-announced Social Security wage base and Medicare Part
   B/D premiums for next year.
2. You can enter these into `input/client_household.csv` as soon as they're
   announced (they take effect January 1, so there's no rush, but doing it
   now avoids a January scramble).

## As-needed, not calendar-bound

- **Capital market assumptions** (`reference_data/capital_market_assumptions.csv`,
  `reference_data/asset_correlations.csv`): review whenever your long-term
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
  `reference_data/tax_update_dashboard.csv` whose computed status is stale or
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
  `tax_constants.csv`.** `input/client_household.csv`'s
  `ss_wage_base_base_year` field is the one actually used by payroll tax
  calculations (`src/data_io.py`) — it does not read from
  `reference_data/tax_constants.csv`'s `ss_wage_base` row at all. These two
  numbers can drift (they already have, in this plan, as of this writing —
  confirm both against a current SSA source before relying on either). A
  single hardcoded fallback constant (`DEFAULT_SS_WAGE_BASE` in
  `src/data_io.py`) is used only when the household field is blank.
- **Medicare Part B/D/G premiums** (`client_household.csv`, "Wellness >
  Medicare") are entered per-household with no reference-table backing at
  all — there's nothing to "de-duplicate," but also nothing that will ever
  flag them as stale. Update them every September/October per the checklist
  above; nothing in the app will remind you.
- **State tax data** has no per-row last-reviewed date, only the single
  dashboard entry covering all states at once — if you maintain plans in
  multiple states, that one flag doesn't tell you which state's data is
  actually stale.
