# Backlog of deferred work

Deferred items that are not in flight. The repository has no GitHub issue
tracker, so this file is the tracker: when an item is picked up, move it to a
spec or plan and delete the line here. Source for the first entries is
`documentation/archive/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
section 9.

**Numbering note (DOC-009).** A bare `#NNN` in this file, in the plan notes and in the
design documents is an *item number* from the owner's numbered work list (for example
`#329` to `#339`, `#345` to `#354`). Pull request numbers also appear as `(#NNN)` at the
end of commit subjects, and the two number ranges overlap (item numbers and pull request
numbers both run through the 300s), so a bare number cannot be told apart by its value.
When you write a new reference, say `item #NNN` or `PR #NNN`. Whether any item number was
ever also a GitHub issue has not been confirmed from this repository.

**Inflow rule (DOC-006, W1-07).** Any plan or spec under `documentation/future/` whose `Status:` line (in its first
20 lines) says "not built", "deferred", "awaits", "owner task", "not approved" or "not yet run" must have a row in this
file that names that document's file name in the Origin column. Add the row in the same change that writes the Status
line. `tests/test_backlog_intake_docs_check_regression.py` enforces it. Rows that wait on an owner, CPA or attorney
decision say so in the Note column, so an approval gate cannot be forgotten.

| Item | Origin | Note |
|---|---|---|
| Automatic Move-2 strategy selection (try `cross_product`, fall back to `anchored` above `MOVE2_CROSS_PRODUCT_CAP`, report which ran) | #331 | Excluded from H2/A3 as scope expansion. |
| Chain the two housing engines (location search feeding the schedule search) | #329 | Not planned. |
| YTD writeback driven by confirmed broker fills | #329 | Not planned. |
| General stress-remediation optimizer | #329 | Not planned. |
| Server-side Planning Cases | #329 | Not planned. |
| Mark Build History snapshots unreproducible when their module set no longer matches | #330 | Not planned. |
| Data-conditional auto-off of modules | #330 | Not planned. |
| Close the vectorized-vs-scalar Monte Carlo success-rate level bias (~14-18 pp optimistic on the frozen fixture; same issue as the widened drift gate in `test_monte_carlo_default_engine_mode.py`) | system review 2026-09-25-2 QA-006 | Investigation in a separate session; see `N1_MC_PARITY_DIAGNOSTIC_2026-09-07.md`. |
| Business Succession: build real inputs on Work Income, then re-home the Build & Results sheet row | `2026-11-04-left-nav-redesign-followups.md` (decision 1) | Not built. The nav shows it only as a workbook-sheet row. |
| Fidelity 1099-B parser (step 5b) | `2026-10-28-realized-sales-ledger-design-and-plan.md` | Not built. Waits for a real Fidelity 1099-B sample, about February 2027. |
| Automatic wash-sale disallowance and basis adjustment | `2026-10-28-realized-sales-ledger-design-and-plan.md` | Not built; a later phase, not v1. Wash-sale scans and flags exist; disallowance is manual. See also the W1 CPA row below. |
| Cash pair-status tax floor: owner approval to turn the default-OFF rule on | `2026-11-03-cash-pair-status-tax-worked-example.md`; `2026-10-31-investment-account-cash-tracking-design-and-plan.md` | Owner decision. Mechanism approved 2026-11-03, turn-on not approved; the engine rule is built and OFF. |
| Run `tools/redact_account_numbers.py` on the live plan (dry run first, then `--apply`), and complete the Phase 5 at-rest protection checklist | `2026-10-31-account-number-protection-design-and-plan.md` (section 6) | Owner task. The tool is built and has not been run on the live plan. |
| Transfer kind in broker importers (task 2.7) | `2026-10-31-transaction-log-design-and-plan.md` | Deferred by the owner 2026-11-02 until a real file shows an in-kind transfer with both legs. Manual transfers cover it. |
| CPA confirmation of wash-sale rule W1 (shares sold in the same sale are not replacements) before release | `2026-11-09-sales-ledger-v3-design.md` (line 265) | Awaits CPA. Joins the CPA engagement in `PROFESSIONAL_REVIEW_ENGAGEMENT_NOTES_2026-11.md`. |
| CPA review of QBI limits (FIN-001), senior-deduction phase-out per person (FIN-002), SALT timing and state-tax basis (FIN-003), Illinois S-corp replacement tax and PTE interaction (FIN-008), 2027 reference rows and state rows (FIN-011); optional check of FIN-006 (SEHI vs itemized medical and ACA credit) | system review 2026-11-10 (`SYSTEM_REVIEW_2026-11-10.md`, W1-07) | Awaits CPA. One batched engagement; the engine changes in Wave 3 wait on the answers. Gate: no rule change before the CPA confirms. |
| Estate attorney review (or Illinois Attorney General calculator comparison) of the Illinois estate-tax method (FIN-004), and of the DSUE and portability treatment including the IRC 2058 deduction (FIN-007) | system review 2026-11-10 (`SYSTEM_REVIEW_2026-11-10.md`, W1-07) | Awaits attorney. Owner starts it now so its elapsed time overlaps Waves 2 and 3. Calculator test points: $4.05M, $4.5M, $5M, $10M. |
| Remove the Excel fallback for the Results Explorer (`src/detailed_results.py`, `_merge_model_index_with_excel` and the `_excel_workbook_*` readers) | `SYSTEM_REVIEW_2026-11-10.md` W3-11 (ARC-007) | Removal trigger: every workbook sheet the Results Explorer shows is in the semantic result model (`fallback_sheet_count` is 0 on a build of the sample and demo plans). The index is now cached on workbook mtime and size. |
| Remove parse-time `migrate_sectioned_data` (`src/plan_data_migration.py`) | `SYSTEM_REVIEW_2026-11-10.md` W3-11 (ARC-007) | Removal trigger: the plan store schema upgrade has migrated every stored plan and `PlanStore` no longer opens a plan older than the current version; then parse stops migrating. |
| Remove `src/legacy_conversion/` | `SYSTEM_REVIEW_2026-11-10.md` W3-11 (ARC-007) | Removal trigger: the owner confirms no pre-v10 workbook or CSV plan is left to convert, with the last conversion run recorded. |
| Remove the `USER_AGENT` import fallback in `src/market_data.py` | `SYSTEM_REVIEW_2026-11-10.md` W3-11 (ARC-007) | Removal trigger: `src/version.py` is guaranteed in every packaged build (the build-package test passes without the fallback); then import it unconditionally. |
