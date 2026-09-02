# Monarch auto-update + standalone financial trends reporter (tickets 305, 306) — Implementation Plan

**Status: implemented (2026-09-02).** Approved for execution and built in
this same session. Phases A and B are both functionally complete and
test-covered.

1. ~~Real Monarch Extractor schema (Task A1).~~ **Resolved 2026-09-02** —
   the Monarch Extractor's actual source (`Monarch Extractor/monarch_extract.py`)
   was added to this repo and read directly. `src/monarch_field_map.json`'s
   defaults are now confirmed-correct, not guesses, and a real design gap was
   found and fixed in the process: `new_transactions.csv`/
   `changed_transactions.csv` accumulate every still-pending event across
   every past run (not just the latest), and the extractor expects
   `--mark-delivered <run_id>` after a successful import — the importer now
   does this instead of the original (wrong) "archive consumed files"
   scheme. See the spec's "What 'the output folder' means for import"
   section and Task A6 below.

   **Security note, for the record:** the first attempt to add this
   subdirectory (commit `6796b9a`) also committed the extractor's full
   Chromium/Playwright browser profile — including its live cookie jar and
   saved-password database for the logged-in Monarch Money session — and was
   briefly pushed to this repo while it was public. The user rotated Monarch
   Money credentials and set the repo private; the branch history was then
   rewritten to drop that commit entirely (replaced by `6a7039e` /
   `4390ac5`, adding only the two real source files plus `.gitignore` rules
   for `monarch-browser/`, `.venv/`, `output/`, and `raw/`). Never commit
   anything from `Monarch Extractor/` beyond `monarch_extract.py` and
   `run_monarch.ps1`.
2. **Task Scheduler registration is still untested on real Windows.** Both
   PowerShell scripts (`register_monarch_autoimport_task.ps1`,
   `register_trends_report_task.ps1`) were reviewed but only run in a Linux
   dev/CI environment, which cannot execute `schtasks`. Run each once by
   hand on the target Windows machine and confirm with
   `schtasks /query /tn "<name>" /v /fo LIST` before relying on the 4am/5pm
   triggers.

Implementation deviated from this plan's original task list in a few places
where testing surfaced a better answer; each is called out inline below.

**Spec:** `docs/superpowers/specs/2026-09-02-monarch-autoupdate-reporting-design.md`
(read first — every decision below traces back to a section there).

**Tech stack:** Python (stdlib + existing repo deps only — no new runtime
dependency for ticket 305; ticket 306 vendors one JS charting library UMD
build, no new Python dependency). Windows Task Scheduler via PowerShell
(`schtasks`), per project preference for PowerShell over Bash on Windows.

**Out of scope (do not touch):** the manual CSV-upload import UI/API
(`import_transactions()`, `preview_ytd_transactions_import()`,
`/api/ytd/transactions/upload`), the Monarch Extractor codebase itself.

---

## Phase A — Ticket 305: Monarch id upsert + 4am auto-update

### Task A1: Confirm Monarch Extractor output schema — DONE (2026-09-02)
- Read the real `Monarch Extractor/monarch_extract.py` directly (added to
  this repo). Confirmed: `id` (lowercase)/`date`/`merchant`/`amount`/
  `account`/`category`/`run_id` are fixed columns; `original_statement`/
  `notes`/`tags`/`owner` are best-effort passthrough. Confirmed the file set
  (`new_transactions.csv`/`changed_transactions.csv` to consume;
  `transactions.csv`/`duplicates_removed.csv` never) and the
  `--mark-delivered <run_id>` acknowledgment protocol.
- `src/monarch_field_map.json` updated with confirmed (not guessed) defaults,
  including the new `run_id_column`.

### Task A2: `Monarch Id` column + `Rows Updated` history column
- Modify `src/ytd_tracking.py`: add `"Monarch Id"` to `TRANSACTION_COLUMNS`,
  add `"Rows Updated"` to `IMPORT_HISTORY_COLUMNS`.
- Verify `normalize_transaction()` passes the new key through untouched
  (defaults to `""`), and that `transaction_hash()` deliberately continues to
  hash only the original 9 columns (adding `Monarch Id` to the hash would
  silently change dedup behavior for every existing manually-uploaded row —
  must not happen).
- Test: extend/duplicate the golden-master and CSV round-trip regression
  tests enough to prove the new column doesn't break `read_transactions` /
  `write_transactions` / existing fixtures that lack it.

### Task A3: `upsert_transactions_by_monarch_id()`
- New function in `src/ytd_tracking.py`, implementing the three-way logic
  from the spec (no-op / replace-in-place / add-new by Monarch id, hash
  fallback for id-less rows).
- Returns a result dict shaped like `import_transactions()`'s, plus
  `updated` count.
- Unit tests: new file `tests/test_monarch_upsert_by_id_unit.py` covering:
  same id + same content (no-op), same id + changed content (replace, single
  row survives, values match new), new id (append), empty-id fallback to
  existing hash behavior, and idempotent double-run of the same input file.

### Task A4: Header/field mapping loader
- `src/monarch_field_map.json` + a small loader in `src/ytd_tracking.py` (or
  a new `src/monarch_import.py`) that maps arbitrary Monarch column names to
  the internal row shape, refusing (clear error, not a crash) when the
  configured id column is absent from a file's header.
- Unit tests for: correct mapping, missing id column → explicit error,
  unmapped extra columns ignored (matches existing `load_transactions_from_csv_text`
  tolerance).

### Task A5: Auto-update policy + status files
- `local_state/monarch_autoupdate.json` policy read/write helpers, mirroring
  `src/local_backup_scheduler.py`'s `load_policy`/`save_policy` shape.
- `local_state/monarch_autoupdate_status.json` writer (last run outcome).
- Settings UI: toggle + status chip (last run time/result) in the existing
  admin/settings page; wire the toggle's on/off to Task A7's PowerShell
  registration script via subprocess.
- Route/service tests mirroring
  `tests/test_local_backup_scheduler_routes_ui_contract.py`'s pattern.

### Task A6: `tools/monarch_autoimport.py` headless script
- Implements the spec's sequence: policy check → OneDrive-truncation guard →
  read `new_transactions.csv`/`changed_transactions.csv` + map + upsert →
  mirror into SQLite → best-effort `--mark-delivered <run_id>` for every
  imported run → write status/history.
- OneDrive guard is a small, reusable helper (share it with Task B5 rather
  than duplicating) — e.g. `src/onedrive_guard.py`: checks file size > 0 and,
  on Windows, checks for the cloud-placeholder reparse-point attribute before
  treating a file as safe to read.
- Functional test: run the script end-to-end against a temp workspace with
  fixture Monarch CSVs (new file, then a second run with one changed row and
  one new row) and assert the resulting `ytd_transactions.csv` and status
  file match expectations.

### Task A7: Task Scheduler registration (PowerShell)
- `tools/launchers/register_monarch_autoimport_task.ps1` (create/update) and
  a matching `unregister_...ps1` (or a single script taking
  `-Action Register|Unregister`).
- Manual verification only (no automated test for real `schtasks` calls):
  document the exact commands in the script's header comment so a human can
  audit before running, since this mutates OS-level scheduled tasks.

### Task A8: Regression pass
- Full existing YTD/import test suite (`pytest tests/ -k "ytd or import" --tb=short -q`)
  to confirm zero behavior change to the manual-upload path.
- Golden master check (`python -m tests.test_frozen_sample_plan_golden_master_regression`)
  since `TRANSACTION_COLUMNS` changed.

---

## Phase B — Ticket 306: standalone financial trends reporter

### Task B1: Scaffold `financial_trends_reporter/`
- New top-level folder: `main.py`, `launchers/START_TRENDS_APP.bat` +
  `.ps1`, `data/` (gitignored, like `input/`/`local_state/` in the main app),
  `frontend/` (own small HTML/CSS/JS + vendored chart library), `tools/`.
- `main.py` reuses `src/http_runtime/server.py: run_local_server` to serve a
  minimal route set (static dashboard + one JSON endpoint returning the
  parsed JSONL history) — no new web framework.
- Update `PROJECT_MANIFEST.md`'s root-directory list to document the new
  folder (per that file's own stated rule: everything at root must be
  referenced there).

### Task B2: Confirm reusable calculation entry points
- Read `src/server_services/holdings_service.py` and the projection/holdings
  code it delegates to, plus `src/results_model.py: _net_worth_page()` /
  `_cashflow_page()`, closely enough to identify the *exact* function(s) to
  call for each of the four metric groups (spec's table names the modules;
  this task nails down the precise call signatures and what "as of today"
  inputs they need).
- Write this down as a short addendum to the spec (or inline code comments)
  so the mapping is explicit before Task B3 depends on it.

### Task B3: `append_trends_log.py` computation + JSONL writer
- `financial_trends_reporter/tools/append_trends_log.py`: OneDrive guard
  (reuse `src/onedrive_guard.py` from Task A6) → compute the four metric
  groups via the Task B2 entry points → read existing JSONL, drop any line
  with today's `as_of_date`, append the fresh line, write back.
- Unit tests: JSONL append/overwrite-same-date logic in isolation (fixture
  metric payloads, not real projection runs) — fast and deterministic.
- Functional test: one end-to-end run against a small fixture workspace
  (reusing existing YTD/holdings test fixtures already in `tests/`) asserting
  the four metric groups in the written line are numerically sane (matches
  what the equivalent existing dashboard call would report for the same
  fixture data).

### Task B4: Trend dashboard UI
- Static page + vendored chart library (default: Chart.js UMD, confirmed per
  spec's open item) rendering the four chart groups.
- Timeframe selector (Day/Week/Month/Quarter/YTD/12-month/Custom/All time)
  implemented as a client-side filter over the loaded JSONL history — no
  server-side date-range endpoint needed for v1.
- Manual UI verification: start the app, seed a handful of fixture JSONL
  lines spanning several months, and click through every timeframe option in
  a browser to confirm the charts and their axis ranges respond correctly
  (per this project's UI-change testing discipline — type-checking a JS file
  is not evidence the chart renders correctly).

### Task B5: Task Scheduler registration (PowerShell, weekday 5pm)
- `financial_trends_reporter/tools/launchers/register_trends_report_task.ps1`
  with `/sc weekly /d MON,TUE,WED,THU,FRI /st 17:00`, mirroring Task A7's
  register/unregister shape.

### Task B6: Regression pass
- New app's own test suite green.
- Confirm zero changes leaked into the main app's `src/` beyond whatever
  read-only helper functions Task B2 identified as reusable (this app should
  be additive-only from the main app's point of view).

---

## Cross-cutting checklist (both phases)

- [ ] OneDrive truncation guard runs before any read in both headless
      scripts (per standing project practice for files under
      `C:\RetirementPlanning\...`).
- [ ] Both scheduled scripts are safe to run twice in a row with no new data
      (idempotent) and safe to run with zero source data present (no crash,
      clear "nothing to do" status).
- [ ] Neither script requires the desktop app or its HTTP server to be
      running.
- [ ] PowerShell (not Bash) for every Windows automation script, per stated
      preference.
- [ ] `documentation/API_CONTRACTS.md` / `PROJECT_MANIFEST.md` updated for
      any new persisted file shape or top-level folder.
