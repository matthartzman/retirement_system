# Year-end transition: design and plan

Date: 2026-11-02.

Status: implemented (merged to main as PRs #380, #383 and #388, 2026-11-03 to 2026-11-04)

Related: `2026-10-31-investment-account-cash-tracking-design-and-plan.md` (sections 9 and 10 and the Phase 6 Built note), the
report-only current-year comparison (built in a separate session from the owner's 2026-11-02 decisions), and
`documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md` (the manual new-year checklist this flow builds on).

## 1. Goal

A short, guided process that moves the app from one calendar year to the next without anything being forgotten, and that
gives the cash reconciliation a firm, owner-confirmed end to each year. Phase 1 is only the cash-year close.

## 2. Owner decisions (2026-11-02)

1. The plan side of the withdrawal comparison is the engine's per-account ledger `row['_account_withdrawals']`
   (alternative A). Only the current year is compared with the engine; past years stay report-only.
2. Each year is **closed manually** by the owner. Nothing closes a year automatically, not even a broker file dated in
   the next year.
3. The close is one step of a guided year-to-year transition. Phase 1 builds the close alone, so the later flow can take it in.

## 3. What exists today (checked 2026-11-02)

| Piece | Where | Note |
|---|---|---|
| Engine start year | `src/parsing/client_sections.py:363` `c['plan_start'] = today().year` | The engine rolls to the new year by itself on 1 January. After that it has no row for the year just ended. |
| Saved engine results | `src/local_store.py` `result_snapshots` in `app.db`, written by `src/report_compute.py` after each build | Machine-level, not per plan; keeps the 10 newest; saved with `plan_snapshot_id=None`, so a snapshot is not tied to a plan. |
| Plan-level key/value store | `PlanStore.get_meta` / `set_meta`, table `plan_meta` (`src/stores/plan_store.py`) | Already in the plan file: **no schema change** needed. Not part of revision restore, so a plan undo does not reopen or close a year. |
| Year-to-date roll-forward | `src/server_services/ytd_service.py` (the "Start `{year}` tracking" prompt on Accounts & Sources) | Existing new-year step; copies current values to "Prior Year End Balance" dated 31 Dec. |
| Reference-data staleness banner | `src/governance.py:tax_law_dashboard()`, Plan Status page | Existing new-year signal (maintainer-level). |
| Cash view | `src/cash_view.py`, `GET /api/cash`, panel `frontend/js/dashboard_decomp_cash_investment.js` (Sales Ledger page) | Withdrawals by pair status, excess returns; the comparison adds pace and an `is_year_closed` seam. |
| Manual checklist | `documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md` | Household steps (YTD roll-forward, personal numbers) and maintainer steps (tax constants). |

## 4. The core problem the close solves

Because `plan_start` follows the calendar, a year can only be compared with the engine **while it is still the current
year**. In January the year that just ended needs a final comparison, but the engine already projects the new year and
the saved snapshot that projected the old year may be pruned or belong to another plan. So the close must:

- **freeze the plan-side figure** for the year from a snapshot that projected that year, at the moment of closing; and
- **freeze the reported side** (withdrawals by pair status per account) so a late file is detected as a change, not
  silently absorbed.

## 5. Design: cash-year close (Phase 1)

### 5.1 Stored record

One `plan_meta` key per closed year, `cash.year_close.<YYYY>`, holding JSON:

```json
{"year": 2026, "closed_at": "2027-01-08T10:12:00Z", "note": "",
 "reported": {"<account>": {"external_withdrawal": 0.0, "internal": 0.0, "unmatched": 0.0, "excess_return": 0.0}},
 "plan": {"source": "snapshot", "built_at": "2026-12-20T09:00:00Z", "by_account": {"<account>": 0.0}},
 "ledger_digest": "<sha256 of the year's cash ledger rows>"}
```

`plan.source` is `"snapshot"` when a usable snapshot was found, else `"none"` (the close is still allowed and the
difference shows "no plan figure"). Account keys are plan account names, never account numbers.

### 5.2 Rules

1. **Close is allowed when** the year has ended (today is on or after 1 January of the next year; read through
   `platform_runtime.today()`), no row of that year is `unmatched`, and every row that straddles year-end (within 5 days
   of 31 December with its pair partner in the other year) has been seen (listed on the close screen; no action needed
   beyond confirming).
2. **Plan figure:** the newest retained snapshot whose first projection row year equals the year being closed and that
   can be tied to the active plan. If none qualifies, `source` is `"none"`. The close screen says which snapshot was used
   and when it was built.
3. **Difference** (reported `external_withdrawal` minus plan figure, per account) is shown only for a closed year.
4. **Drift after close:** on every view, recompute the year's ledger digest. If it differs from the stored one (a late
   file, a re-pairing), the year shows "changed since close" with the old and new totals. Nothing is re-closed
   automatically.
5. **Reopen** deletes the key (with confirmation and an audit event). The year goes back to pace or report-only.
6. **No engine change.** The close feeds no tax number. Feeding the pair-status rule into the engine remains a later
   owner decision (cash plan section 10 item 3).

### 5.3 Interfaces

- `src/cash_year_close.py`: `is_year_closed(store, year)`, `close_status(store, year)` (allowed?, blockers,
  straddling rows, chosen snapshot), `close_year(store, year, note)` and `reopen_year(store, year)`. Pure helpers over
  `cash_view` and `cash_pairing`. Reads `plan_meta` through the store (no direct `stores` import from product code).
- Replaces the comparison's `is_year_closed` seam (which returns `False` today).
- Routes: `GET /api/cash/year-close?year=` (status) and `POST /api/cash/year-close` (`{year, action: "close"|"reopen", note}`).
  Both are registered in `src/server/route_manifest.py`. Writes are audited like the YTD roll-forward (`ctx.audit`).
- Panel: a "Close <year>" control in the Cash in investment accounts panel showing blockers, straddling rows, the
  snapshot used, and a confirm step; a closed year shows its difference, the close date, and "Reopen".

### 5.4 Snapshot to plan link (known gap)

Snapshots are saved without a plan id. Phase 1 uses the best tie available (a plan identifier in the saved result if
present). If none exists, Phase 1 records `source: "none"` rather than guess, and a follow-up adds the plan id at save
time (`save_result_snapshot(..., plan_snapshot_id=...)`; `app.db` already has the column, so no schema change). Until
then the guided flow (Phase 2) asks the owner to build a report in December so a December snapshot exists.

## 6. Design: the guided transition (later phases)

A "Year-end" page, shown from mid-December to the end of January and reachable any time, with an ordered checklist.
Each step links to the screen that does it and shows its state (done, open, not applicable):

1. **December: capture the plan's year** — build a report so a snapshot of the current year exists (needed by step 5).
2. **Import final broker files** — per account, the latest file date; flags accounts with no file dated after 31 Dec.
3. **Resolve cash rows** — unmatched and straddling rows for the year (cash panel).
4. **Confirm year-end CASH balances** — the panel's difference against each `CASH` lot.
5. **Close the cash year** — Phase 1.
6. **Start the new tracking year** — the existing YTD roll-forward (`ytd_service`).
7. **Update personal numbers** — salary, contribution elections, benefit letters (links to the plan sections).
8. **Reference data** — shows the staleness banner's items (maintainer-level; informational).

Checklist state is derived from the data wherever possible (a step is done because the thing is true, not because a box
was ticked). Only steps with no derivable state store a confirmation, again in `plan_meta` (`year_end.<YYYY>.<step>`).

## 7. Risks

| Risk | Mitigation |
|---|---|
| Snapshot belongs to another plan or was pruned | `source: "none"`, never a guessed figure; December reminder; follow-up adds the plan id at save time. |
| Late files after close | Ledger digest; "changed since close", owner reopens and closes again. |
| A close is mistaken for an engine change | Panel and docs say the close feeds no tax number. |
| Plan undo leaves a close in place | Intended: closes are facts about the household's records, not plan edits. Documented. |
| Year boundary in tests | All date logic reads `platform_runtime.today()`; tests pin it. |

## 8. Implementation plan

### Phase 1: cash-year close (no schema change, no engine change)

Depends on the report-only current-year comparison being merged (it provides the comparison table and the seam).

1. **Tests first** (`tests/test_cash_year_close_unit.py`): close blocked by an unmatched row; blocked before 1 January;
   straddling rows listed; record written to `plan_meta` with reported totals, plan figure and digest; snapshot chosen
   only when its first row year matches; `source: "none"` otherwise; drift detected after a late row; reopen removes the
   record; `is_year_closed` true only for a closed year. Pin `platform_runtime.today()`.
2. `src/cash_year_close.py` (section 5.3), wired into `cash_view` in place of the seam.
3. Routes in `src/server/app_core.py` (or the cash routes module) and `src/server/route_manifest.py`; audit events
   `cash_year_closed` and `cash_year_reopened`.
4. Panel: close control and closed-year display in `frontend/js/dashboard_decomp_cash_investment.js`; frontend test in
   `tests/frontend/cash_investment_panel.test.mjs`; raise `TOTAL_JS_MAX_LINES` with a dated note.
5. Regenerate the diagram (`python tools/generate_system_diagram.py`); golden master `measure` must stay MATCH.
6. Docs: Built note here and in the cash plan; add the close to the runbook's new-year checklist.

**Built 2026-11-03 (Phase 1, cash-year close):** `src/cash_year_close.py` (`close_status`, `close_year`, `reopen_year`, `is_year_closed`, `close_summary`, `service`), wired into `cash_view` in place of the seam; `GET`/`POST /api/cash/year-close` (registered in `route_manifest.py`, audit events `cash_year_closed` / `cash_year_reopened`); `PlanStore.delete_meta` and `local_store.list_result_snapshots`; close controls in the Cash panel (`closes` on `GET /api/cash`). No schema change, no engine change; golden master `measure` MATCH. Rulings: the snapshot tie uses the `plan_id` snapshots now record (Phase 3's save-side work already exists), so a snapshot with no matching plan id is never used; straddling rows must be confirmed (`straddles_seen`) rather than ticked individually; the two open questions took Claude's defaults (no broker-file requirement, a close with no plan figure is allowed). Tests: `tests/test_cash_year_close_unit.py`, `tests/test_cash_year_close_functional.py`, `tests/frontend/cash_investment_panel.test.mjs`. Phases 2 and 3 remain unbuilt and need separate approval.

### Phase 2: guided Year-end page

The checklist of section 6 with derived state, linking to existing screens. New JS module (script-order guard and
`frontend/index.html` entries). Separate approval.

**Built 2026-11-03 (Phase 2, guided Year-end page):** `src/year_end.py` (`build`, `service`, `set_confirmation`, `default_year`, `in_season`); `GET /api/year-end` and `POST /api/year-end/confirm` (registered in `route_manifest.py`; audit events `year_end_step_confirmed` / `year_end_step_unconfirmed`); nav step "Year-End Transition" in Reports & Review and a Plan Status banner from 15 December to 31 January (`frontend/js/dashboard_decomp_year_end.js`, added to `index.html` and the script-order guard). Seven of the eight steps are derived from data; only "Update personal numbers" stores a confirmation (`plan_meta` key `year_end.<YYYY>.personal_numbers`). No schema change, no engine change. Rulings: the year shown is the one in progress from July, otherwise the one that just ended; "final broker files" reads each account's latest applied import `date_to` and flags any not after 31 December; "confirm year-end CASH" reuses the panel's difference against each `CASH` lot; the nav hook and render branch were folded into existing `dashboard.js` lines so it did not grow. Tests: `tests/test_year_end_checklist_unit.py`, `tests/test_year_end_checklist_functional.py`, `tests/frontend/year_end_page.test.mjs`.

### Phase 3: snapshot-to-plan link and retention

**Built 2026-11-03.** Found on inspection that the plan-id link already existed: `report_compute` saves each run with `plan_snapshot_id=active_plan_id()` and `local_store.latest_result_snapshot` / `list_result_snapshots` filter by it (used by Phase 1's close and Phase 2's page since they were built). The remaining gap was retention: only the 10 newest runs were kept across all plans, so the December run that projected the year could be pruned by January builds before the close. `local_store._prune_result_snapshots` now also keeps the newest run of each plan and first-projection year (plans with an id only; at most one extra row per plan per year). No schema change, no engine change. Runs saved before plan ids were recorded stay unusable for a close, as designed. Tests: `tests/test_result_snapshot_year_protection_unit.py`.

### Phase 4: verified-account gate on the pair-status floor (owner decisions 2026-11-03; built 2026-11-03)

**Reconciliation.** While Phase 4 was being decided, another session built the engine feed on `main`: the pair-status **floor** (`src/cash_tax_floor.py`, setting `cash_pair_status_tax`, default OFF; cash plan sections 13 to 16 covering pre-tax, HSA and Roth, taxable through the realized-sales ledger). The originally designed current-year blend would have duplicated it and could double-count, so on the owner's choice (2026-11-03) Phase 4 became a **gate on the floor** instead, and the blend was not built.

**Owner decisions (2026-11-03), as applied:**

1. **Eligibility: only closed-year-verified accounts.** With the floor setting ON, an account's reported withdrawals are fed only when the owner has marked it verified (it must appear in a closed year's record, so its plan-minus-reported difference has been reviewed) and it has no `unmatched` row dated in the plan year. The mark is per account and reversible (`plan_meta` key `cash.verified_account.<account>`, audited as `cash_account_verified` / `cash_account_unverified`).
2. **Half-pairs stay unmatched and are never counted**, so they keep their account out of the feed. No per-row override.
3. **Switch default OFF** (the floor's existing setting); with it OFF nothing runs and the golden master is untouched. Accounts left out are listed with the reason in `cfg['cash_pair_floor_skipped']`, and the Cash panel shows "eligible / not fed (reason)" per account with a Mark verified / Remove verification button.
4. **Scope unchanged from the floor:** first plan year only; no engine arithmetic changed by this phase. It only narrows which accounts' reported draws reach the floor. Hand-verified golden-master delta: not needed for this change (no pin moved; `measure` MATCH); it still applies when the owner turns the floor on with real verified accounts.

**Built:** `src/cash_verified_accounts.py` (`is_verified`, `set_verified`, `eligibility`, `gate`, `service`); `cash_tax_floor.apply_gate` (used by `feed`); `POST /api/cash/verify-account` (in `route_manifest.py`); `floor_gate` per account on `GET /api/cash`; panel controls. No schema change. Behavior note: with the floor setting ON and no verified accounts, nothing is fed until an account is verified. Tests: `tests/test_cash_verified_accounts_unit.py`, `tests/test_cash_verified_accounts_functional.py`, `tests/frontend/cash_investment_panel.test.mjs`.

## 9. Open questions for the owner

1. Should closing require that every account has a broker file dated after 31 December, or only show it as a warning?
   (Claude's call if not answered: warning only.)
2. Is a close of a year with `plan.source = "none"` acceptable (reported side frozen, no difference)? (Claude's call:
   yes, with the label "no plan figure".)
