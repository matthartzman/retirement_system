# Monarch auto-update + standalone financial trends reporter (tickets 305, 306)

Date: 2026-09-02
Status: Draft — awaiting approval (design only, no implementation yet)

## Background

Today, transaction import into `input/ytd_transactions.csv` is manual: a user
uploads a Monarch CSV export through the UI (`preview_ytd_transactions_import`
/ `ytd_transactions_upload` → `src/import_preview.py`, `src/ytd_tracking.py`).
Dedup is a full-row SHA1 hash (`transaction_hash()` over
`Date|Merchant|Category|Account|Original Statement|Notes|Amount|Tags|Owner`).
That means:

- A row is only ever **added** if its hash has never been seen before.
- If Monarch later corrects a transaction already imported (re-categorized,
  merchant renamed, amount corrected), the corrected row hashes differently
  from the original and is imported as a **second, duplicate-looking row**
  rather than replacing the original — there is no concept of "this is the
  same transaction, updated."
- Nothing about the row identifies it as *the same Monarch transaction* — the
  hash is a fingerprint of the content, not an identity.

`retirement_system` is a Windows desktop app (PyWebView), started via
`main.py` / `launchers/START_APP.bat`. There is no persistent background
process today — confirmed by `main.py`'s two modes (`desktop`, `server`, both
only running while explicitly launched) and by the existing
`src/local_backup_scheduler.py`, which is deliberately **opportunistic**: it
never runs on a timer, only "is this due?" checked from a route or UI action
already in flight.

Ticket 305 asks for two things:
1. An **auto-update toggle** that, when enabled, imports new/changed
   transactions from the Monarch Extractor's output folder unattended every
   day at 4am, then marks the run complete.
2. The underlying import logic upgraded from append-only-by-hash to a true
   **upsert**: replace a transaction whose Monarch id already exists and has
   changed, add one whose Monarch id is new, keyed on a stored Monarch id
   rather than a content hash.

Ticket 306 asks for a second, separate scheduled job — a new standalone app
that, every weekday at 5pm, appends a log entry capturing YTD expenses by
category, holdings value/performance, net worth, and cashflow, and presents
the accumulated history as trend charts with a timeframe selector.

## Decisions from clarification (binding on this design)

- **Scheduling mechanism: Windows Task Scheduler**, not an always-on
  background service and not opportunistic-only. Both the 4am import and the
  5pm report run as headless Python scripts launched by `schtasks`-registered
  tasks, independent of whether the desktop app window is open.
- **Monarch Extractor output already carries a stable per-transaction Monarch
  id column.** The exact column name is unconfirmed (Monarch Extractor's own
  docs live outside this repo, at `../Monarch Extractor`) — the import path
  reads it through a small configurable column-alias map (see "Header
  mapping" below) rather than a hardcoded name, so confirming the exact
  header is a pre-implementation checklist item, not a design blocker.
- **Ticket 306 is a separate standalone app in this repo** (its own
  top-level folder and entry point, own small local server/UI), which
  **imports `src/` calculation modules as a library** rather than
  re-implementing spending/holdings/net-worth/cashflow math. It does not live
  inside the existing desktop app's UI.

## Ticket 305 — Monarch auto-update

### Data model change: Monarch id on transactions

Add one new, additive, optional column to the transaction schema:

```
TRANSACTION_COLUMNS = [..., "Monarch Id"]   # src/ytd_tracking.py
IMPORT_HISTORY_COLUMNS += ["Rows Updated"]  # src/ytd_tracking.py
```

Both are backward compatible: `_read_csv_dicts` already defaults missing
columns to `""`, and `load_transactions_from_csv_text`'s header mapping
already ignores unrecognized/extra columns and fills absent ones — no
existing manual-upload flow, golden-master fixture, or test that doesn't
touch this column needs to change shape. Rows entered manually or imported
from a non-Monarch CSV simply carry `Monarch Id = ""` and behave exactly as
today (hash-based dedup, unchanged).

### Upsert semantics

A new function, `upsert_transactions_by_monarch_id()` in `src/ytd_tracking.py`,
is added alongside (not replacing) the existing `import_transactions()`. The
manual-upload UI keeps calling `import_transactions()` with its existing
`replace` / `reload` / incremental modes unchanged — this is a deliberate
scope boundary to avoid destabilizing tested, working behavior. Only the new
Monarch auto-update path uses the upsert function:

For each incoming row with a non-empty Monarch Id:
1. **Known id, content unchanged** (all mapped fields match the stored row
   for that id) → no-op.
2. **Known id, content changed** → replace the stored row in place (same
   position/date-sort outcome as a fresh row would get), counted as
   *updated*.
3. **Unknown id** → append as a new row, counted as *added*.

For any incoming row with an empty/missing Monarch Id (the extractor should
not produce these, but the importer must not crash if it does): fall back to
the existing hash-based "add if the hash has never been seen and the date is
after the latest existing transaction" logic, unchanged from today.

This is the "replace modified records and add new (not just replace or
append)" behavior ticket 305 asks for, scoped specifically to
Monarch-sourced rows.

### What "the output folder" means for import

**Confirmed 2026-09-02 against the real `Monarch Extractor/monarch_extract.py`**
(superseding the original open items below, kept struck through for history).
The output folder holds four files plus the extractor's own SQLite state, not
one generic export:

| File | Contents | Consumed? |
|---|---|---|
| `new_transactions.csv` | Every still-**pending** new-transaction event, across every past extractor run, each tagged with a `run_id` | yes |
| `changed_transactions.csv` | Every still-pending changed-transaction event, with `previous_<field>` columns for whatever changed | yes |
| `transactions.csv` | Full history — every transaction ever seen | **never** (would just reprocess everything) |
| `duplicates_removed.csv` | Raw rows the extractor already dropped as duplicates | **never** |
| `monarch_state.sqlite3` | The extractor's own delivery-tracking DB | not ours to touch |

So ticket 305's "both new and changed transactions to be consumed are in the
output folder" maps directly onto `new_transactions.csv` +
`changed_transactions.csv`, and those two files are themselves already an
accumulating backlog of pending events, not a delta this importer has to
diff itself — the importer's job is simply to upsert every row in them.

The extractor tracks delivery itself: after this importer's upsert succeeds,
it must run `python monarch_extract.py --mark-delivered <run_id>` (via the
extractor's own `.venv`, since the script imports Playwright unconditionally
even for this flag) for every distinct `run_id` it just imported. Only then
do that run's rows drop out of the two pending files. This replaces the
original design's "move consumed files to an `output/imported/` subfolder"
idea entirely — this importer never moves or deletes anything in the
extractor's output folder. Marking delivered is best-effort: a failure is
reported (`mark_delivered_errors`) but does not fail the already-successful
import, since re-upserting the same already-imported rows next cycle is a
harmless no-op.

~~Open item to confirm before implementation: whether the Monarch Extractor
clears/archives its output folder after each of its own runs, or
accumulates files run over run.~~ Resolved above — it accumulates pending
events until explicitly acknowledged.

### Header mapping (Monarch CSV → internal schema)

A small JSON config, `src/monarch_field_map.json` (or a `local_state/`
override), maps Monarch Extractor column names to the internal field names.
**Confirmed 2026-09-02** against the real extractor: `id` (always lowercase),
`date`, `merchant`, `amount`, `account`, `category`, and `run_id` are fixed
columns on every row of `new_transactions.csv`/`changed_transactions.csv`;
`original_statement`/`notes`/`tags`/`owner` are best-effort passthrough,
present only if Monarch's own raw export included them (the extractor
normalizes whatever extra columns it finds to a lowercase/underscored name).

```json
{
  "id_column": "id",
  "date_column": "date",
  "merchant_column": "merchant",
  "category_column": "category",
  "account_column": "account",
  "original_statement_column": "original_statement",
  "notes_column": "notes",
  "amount_column": "amount",
  "tags_column": "tags",
  "owner_column": "owner",
  "run_id_column": "run_id"
}
```

The import script logs and refuses to run (rather than silently importing
garbage) if `id_column` is missing from a source file's header — this is the
one column the id-based upsert cannot function without.

### Auto-update policy + "mark complete"

Follows the same shape as `src/local_backup_scheduler.py`'s policy file
(`local_state/backup_scheduler.json`) for consistency:

- `local_state/monarch_autoupdate.json` — `{enabled, source_dir, field_map_path}`.
  `source_dir` defaults to `../Monarch Extractor/output` (relative to the
  workspace root, per the ticket).
- A settings toggle in the existing admin/settings UI flips `enabled` and,
  when turning on, registers the 4am Windows Task Scheduler task (via
  `schtasks /create`, run from a PowerShell helper — see "Task Scheduler
  registration"); turning off unregisters it.
- **"Mark the update as complete"** = after each run, write
  `local_state/monarch_autoupdate_status.json`:
  ```json
  {
    "last_run_at": "2026-09-03T04:00:12-05:00",
    "success": true,
    "files_consumed": ["monarch_export_20260903.csv"],
    "rows_added": 12,
    "rows_updated": 3,
    "rows_skipped": 0,
    "errors": []
  }
  ```
  plus one row appended to the existing `ytd_import_history.csv` (reusing
  `append_import_history()`, `Mode = "monarch_auto"`, populating the new
  `Rows Updated` column). The UI's existing import history view shows the
  4am run like any manual import, and a small status chip (last Monarch
  auto-update: succeeded/failed, timestamp) is added next to the toggle.

### Headless 4am script

New `tools/monarch_autoimport.py`, runnable standalone (no desktop window, no
HTTP server — it calls `src/ytd_tracking.py` / the new upsert function
directly, the same way `tools/build_workbook.py` is already invoked
headlessly today per `main.py`'s script-runner mode). Responsibilities, in
order:
1. Load `monarch_autoupdate.json`; exit immediately (writing a `skipped:
   disabled` status) if not enabled.
2. **OneDrive truncation guard** (per standing project practice): before
   reading anything, verify each candidate source file and the destination
   `input/ytd_transactions.csv` are not zero-byte or OneDrive
   placeholder/"not fully downloaded" stubs. Abort the run with a clear error
   in the status file rather than importing partial data if a check fails.
   `C:\RetirementPlanning\...` and the Monarch Extractor's output folder are
   plausible OneDrive-synced paths, so this guard is mandatory, not optional,
   for both this script and the ticket-306 script below.
3. Read `new_transactions.csv` and `changed_transactions.csv` from
   `source_dir` (never `transactions.csv` or `duplicates_removed.csv`),
   apply the header/field mapping, run `upsert_transactions_by_monarch_id()`.
4. Mirror the updated YTD CSVs into the SQLite plan-data store (no Flask
   request context to go through the normal save path).
5. Best-effort acknowledge every imported `run_id` back to the extractor via
   `monarch_extract.py --mark-delivered <run_id>` (see above) — failures are
   reported, not fatal.
6. Write the status file + import history row (success or failure either
   way).

### Task Scheduler registration

A PowerShell helper, `tools/launchers/register_monarch_autoimport_task.ps1`
(matching this project's existing multi-shell launcher convention and the
user's Windows/PowerShell preference), wraps:

```powershell
schtasks /create /tn "RetirementSystem_MonarchAutoImport" /tr "... python.exe ... tools\monarch_autoimport.py" /sc daily /st 04:00 /f
```

Also exposed as a button/toggle in the settings UI, which shells out to the
same PowerShell script (subprocess), so enabling/disabling the toggle in-app
keeps the actual Task Scheduler entry in sync — avoiding a state where the UI
says "enabled" but no OS-level task exists, or vice versa.

## Ticket 306 — Standalone financial trends reporter

### App shape

A new top-level folder, `financial_trends_reporter/` (sibling to `src/`,
`frontend/`, etc.), with its own:
- `main.py` entry point and `launchers/START_TRENDS_APP.bat` +
  `.ps1` launcher, mirroring the existing `launchers/START_APP.bat` pattern.
- Small local stdlib HTTP server (reusing `src/http_runtime/server.py`'s
  `run_local_server`, the same runtime the main app already uses in `server`
  mode, rather than introducing a new web framework/dependency) serving a
  single-page dashboard.
- Its own `data/financial_trends_log.jsonl` — deliberately **not** written
  into `output/` or `input/`, so it can't collide with the main app's
  workspace files or be swept up by the main app's plan-data
  migration/backup logic.

It **imports** `src/` modules as a library (this repo, not a separate
package/repo) to compute each metric group rather than re-deriving them:

| Metric group | Reused from |
|---|---|
| YTD expenses by category | `src/spending_tracker.py: group_actuals()` |
| Holdings value/performance | `src/server_services/holdings_service.py: read_holdings()` + existing holdings valuation/performance path (exact function confirmed at implementation time — holdings pricing lives across `holdings_service.py` and the projection engine's holdings-period code) |
| Net worth | `src/results_model.py: _net_worth_page()` (or the underlying data it's built from) |
| Cashflow | `src/results_model.py: _cashflow_page()` / `src/ytd_tracking.py: _iter_cashflow_rows()` |

This keeps the two apps' numbers guaranteed consistent with the main
dashboard (same source functions), rather than a second, potentially
drifting, calculation path.

### Log format

Append-only **JSON Lines** (`financial_trends_log.jsonl`), one JSON object
per weekday-5pm run:

```json
{"run_at": "2026-09-02T17:00:04-05:00", "as_of_date": "2026-09-02",
 "ytd_expenses_by_category": {"Groceries": 4210.33, "Travel": 2100.00, "...": "..."},
 "holdings": {"total_value": 1842300.12, "ytd_return_pct": 0.081, "by_account": {"...": "..."}},
 "net_worth": {"total": 2314500.00, "assets": 2500000.00, "liabilities": 185500.00},
 "cashflow": {"income": 18500.00, "expenses": 12400.00, "net": 6100.00}}
```

JSON Lines (not CSV) because the category breakdown's key set changes as
categories are added/renamed over time — CSV would require rewriting the
whole file's header on every schema change; JSONL just appends. Re-running
the job twice on the same `as_of_date` **overwrites that date's line**
(read the file, drop any existing line with the same `as_of_date`, append the
fresh one) rather than duplicating it, so a manual re-run or a missed/retried
Task Scheduler fire is safe.

### Trend UI

The dashboard page loads the full JSONL history client-side (files of this
shape stay small — one line per weekday, ~260/year) and renders line/bar
charts (holdings value & performance, net worth, cashflow, expense-by-category
stacked/breakdown) with a timeframe control offering: **Day, Week, Month,
Quarter, YTD, 12-month, Custom range, All time** — a client-side filter over
the loaded history by `as_of_date`, no server round-trip needed per
selection.

Charting library: this app ships as an offline Windows desktop tool (no
guaranteed internet access at runtime), so a chart library is **vendored
locally** (its UMD build committed under
`financial_trends_reporter/frontend/vendor/`) rather than loaded from a CDN —
consistent with how this repo has no CDN dependency anywhere in
`frontend/` today. Exact library choice (Chart.js is the natural default: no
new build tooling, single-file UMD, license-compatible) is confirmed at
implementation time.

### Headless 5pm script

`financial_trends_reporter/tools/append_trends_log.py`, same shape as
`tools/monarch_autoimport.py`: OneDrive-truncation guard first, then compute
the four metric groups via the `src/` imports above, then append/overwrite
today's JSONL line. Registered via a second PowerShell helper,
`register_trends_report_task.ps1`, as a Task Scheduler entry with
`/sc weekly /d MON,TUE,WED,THU,FRI /st 17:00`.

## Non-goals

- Changing the manual CSV-upload import UI/behavior (`import_transactions()`,
  `preview_ytd_transactions_import()`) — untouched, still hash-based, still
  driven by the existing `replace`/`reload`/incremental modes.
- Auto-discovering or parsing Monarch Extractor's own internal file formats
  beyond what's needed to read its `output/` CSVs (no changes to the Monarch
  Extractor codebase itself — out of scope, separate system).
- A shared settings/scheduling UI between the main app and the new standalone
  app — each registers/manages its own Task Scheduler entry independently.
- Real-time/live updates to the trends dashboard; it reflects whatever the
  last completed run wrote (with a manual "run now" action available in each
  app for out-of-band refresh).

## Open items — all resolved 2026-09-02

1. ~~Exact Monarch Extractor output column names.~~ Confirmed directly
   against `Monarch Extractor/monarch_extract.py` (added to this repo the
   same day). See "What 'the output folder' means for import" and "Header
   mapping" above.
2. ~~Whether Monarch Extractor's output folder is cleared/archived between
   runs.~~ Confirmed: it accumulates pending events in `new_transactions.csv`/
   `changed_transactions.csv` until explicitly acknowledged via
   `--mark-delivered <run_id>`. The original "move consumed files" design was
   wrong and has been replaced by that acknowledgment call.
3. ~~Which holdings-performance function(s) to call for ticket 306.~~
   Resolved during implementation: `src.ytd_tracking.ytd_summary()` alone
   supplies YTD category spend, holdings current value/prior-year balance/
   growth, and cashflow components — the same engine the main app's YTD
   dashboard already calls. Net worth adds one plain sum over
   `client_liabilities.csv`'s `balance` column plus account-setup liability
   roles; no direct call into `holdings_service.py` or the projection engine
   was needed.
4. ~~Chart library choice.~~ Resolved during implementation: hand-rolled
   inline SVG (no vendored library) — simple line/bar charts don't need one,
   and it keeps the app dependency-free and fully offline with zero new
   files to vet.
