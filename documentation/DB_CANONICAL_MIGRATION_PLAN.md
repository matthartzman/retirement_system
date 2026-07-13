# DB-Canonical Migration Plan (Phase 1)

Status: **Phase 1 complete** (scaffolding + design only). No destructive
changes, no default-behavior changes, no CSV files touched or removed.

Goal (product owner): make the local SQLite database (`src/local_store.py`,
table `plan_snapshots`) the single canonical source of truth for plan data.
CSV/JSON/YAML become strictly import/export ("adapter") formats. The internal
CSV round-trip that currently sits inside the *normal* build/load path (i.e.
happens on every build even when the user never touched a file) is the thing
to eliminate in a later phase.

This document is the map for that work. It does not implement Phase 2/3.

---

## 1. Current data flow (traced, file:function references)

### 1.1 The three parallel plan-editing paths that exist today

**Path A — legacy CSV-first (majority of the UI today).**
`src/server/app_core.py` route handlers (e.g. `_csv_write_rows` call sites at
`app_core.py:781,813,868,883,899,918,943,971,1444`) write user edits directly
to `input/client_*.csv` files via `_plan_data_path()` (`app_core.py:555`) and
`_csv_write_rows()` (`app_core.py:671`). After a write, the route calls
`_sync_config_backends()` (`app_core.py:1606`), which:
  1. `export_client_json_yaml(CSV_PATH, ...)` (`config_backend.py:359`) — CSV →
     JSON/YAML adapter files (`load_csv()` then `save_json()`/`save_yaml()`).
  2. `import_csv_to_sqlite(CSV_PATH, db_path, ...)` (`config_backend.py:275`) —
     **reads the CSV back off disk** via `load_csv()`, writes it into the
     legacy flat `settings` table, and also calls
     `local_store.import_sectioned_plan(data, source="csv_import", db_path=p)`
     (`local_store.py:164`), which converts the sectioned dict into a typed
     `PlanInput` (`domain_models.plan_input_from_sectioned_data`,
     `domain_models.py:202`) and upserts it into `plan_snapshots` — the
     canonical table.

So today, **every edit through the classic UI routes is: write CSV → read CSV
back → convert → write to the canonical DB table.** The DB row is *derived
from* the just-written CSV file on every single save. This is the "internal
CSV round-trip" the product owner wants gone from the normal path.

**Path B — DB-first "Plan Forms" API (already exists, already correct).**
`src/server_services/plan_forms_service.py` (`save_forms_payload`,
`patch_forms_payload`) calls `local_store.import_sectioned_plan()` directly
with in-memory sectioned data — **no CSV file is read or written.** This is
already the Phase 2/3 shape for writes. It coexists with Path A; nothing
currently forces all writers through it.

**Path C — explicit local-folder import.**
`src/local_plan_data_sync.py` (`sync_plan_data_from_folder`,
`sync_plan_data_from_env`) copies a user-selected folder of CSV files into
`input/`. This is a legitimate *adapter import* (the user explicitly chose a
folder) and should stay CSV-shaped even after Phase 3 — it is not part of the
"internal round-trip" problem.

### 1.2 Where a build actually gets `data` from (the `data_io.parse_client` input)

Entry point for engine-config assembly: `src/report_compute.py`:
- `prepare_config_from_sectioned_data(data, url_template, optimize_roth)`
  (`report_compute.py:111`) calls `data_io.parse_client(data, url_template)`
  (`report_compute.py:112`) then `plan_config.ensure_engine_config(...)`.

`data` itself is produced by `config_backend.load_active_config()`
(`config_backend.py:332`), called from three build entry points:
- `src/reporting/workbook_builder.py:1062` (`main()`, the CLI/desktop build)
- `src/server_services/config_service.py:119` (`allocation_preview_payload`, via
  `load_active_config()` in its context)
- indirectly by anything that calls `prepare_config_from_sectioned_data`
  after fetching `data` from `load_active_config()`

`load_active_config()` reads `System Configuration / Runtime / config_backend`
from the bootstrap CSV (`discover_bootstrap_csv()` →
`reference_data`/`multi_user/system_config.csv`) and dispatches:
- `backend == "SQLITE"` (the default): calls `load_sqlite(db_path)`
  (`config_backend.py:292`), which **already prefers the canonical path** —
  it tries `local_store.latest_sectioned_data(p)` first
  (`config_backend.py:300`, reading `plan_snapshots.sectioned_json`) and only
  falls back to the legacy flat `settings` table if that's empty. If the DB
  file doesn't exist yet or has no rows, `load_active_config()` bootstraps it
  once from `input/client_data.csv` via `import_csv_to_sqlite()`
  (`config_backend.py:349-354`).
- `backend in {"CSV","JSON","YAML"}`: reads the adapter file directly
  (`load_csv`/`load_json`/`load_yaml`, `config_backend.py:142,167,185`).

**So as long as `config_backend` (System Configuration / Runtime) is set to
SQLITE (the default) and the plan has been saved at least once, a build's
`data` argument to `parse_client` already comes from the canonical
`plan_snapshots` table, not from a fresh CSV read.** The CSV round-trip is not
in the *read* path today — it is in the *write* path (Path A, §1.1), because
every UI save re-derives the DB row from a CSV file it just wrote, instead of
writing the DB row directly and treating the CSV as a byproduct/export.

### 1.3 CSV reads still hard-coded into the build path regardless of backend

Even with a DB-canonical `data` dict, `data_io.parse_client()` performs two
**unconditional, backend-independent** filesystem reads that are not gated by
which backend produced `data`:

1. **Spending budget lines** — `data_io.py:675-723` looks up
   `client_spending_budget_lines.csv` via
   `workspace_context.candidate_input_files()` (`workspace_context.py:79`)
   and reads it directly with `csv.DictReader`, regardless of `data`'s origin.
2. **Unified spending budget** — `data_io.py:730-734` calls
   `spending_budget_resolver.apply_budget_to_engine_config(c, root=...)`
   (`spending_budget_resolver.py:293`), which via `resolve_spending_inputs()`
   reads more CSV files (`client_spending_budget.csv`,
   `client_spending_taxonomy.csv`, `client_spending_aliases.csv`) straight off
   `input/` — again independent of the `data` argument.
3. **Capital market assumptions** — `data_io.py:147-177`
   (`_load_capital_market_income_assumptions`) reads
   `reference_data/capital_market_assumptions.csv` directly. This one is
   arguably fine to leave CSV-forever (it is shared reference/assumption
   data, not per-plan user data), but it is worth naming explicitly so Phase
   2/3 doesn't assume it needs a DB table.

These three reads mean that even a fully DB-canonical `data` dict does not
yet produce a fully DB-sourced engine config — spending-budget line items and
category rollups still come from disk every build.

### 1.4 Summary table

| Concern | Current source in the *normal* build path | CSV round-trip? |
|---|---|---|
| Household/economic/SS/mortgage/etc. scalars (`parse_client`'s `_v(data,...)` lookups) | `data` dict from `load_active_config()` → SQLITE backend → `local_store.latest_sectioned_data()` (canonical) | No, if backend=SQLITE and plan saved via any path. Yes, transiently, on every **write** through Path A (§1.1). |
| Spending budget lines (`client_spending_budget_lines.csv`) | Direct CSV read in `data_io.parse_client`, unconditional | Yes — always reads CSV, never the DB |
| Unified spending budget/taxonomy/aliases | Direct CSV read via `spending_budget_resolver` | Yes — always reads CSV, never the DB |
| Capital market assumptions | Direct CSV read from `reference_data/` | Reference data, not plan data — likely CSV-forever |
| UI edits (classic routes) | Write CSV → read CSV back → write DB | Yes — full round-trip on every save |
| UI edits (`plan_forms_service.py`) | Write DB directly | No — already Phase-2/3-shaped |

---

## 2. Target flow (Phase 2/3)

**Phase 2 — make the DB the only write target for plan data.**
- Migrate every Path-A route handler in `app_core.py` (and anything else
  calling `_csv_write_rows` for plan-data files) to write through
  `local_store.import_sectioned_plan()` (or a small `patch` helper akin to
  `plan_forms_service.patch_forms_payload`) instead of `_csv_write_rows()`.
- `_sync_config_backends()` becomes purely an **export**: DB → CSV/JSON/YAML,
  never CSV → DB. Its `import_csv_to_sqlite()` call is deleted; its
  `export_client_json_yaml()`-equivalent (now DB-sourced, e.g.
  `local_store.export_latest_plan(..., fmt="csv")`, which already exists and
  is already lossless/DB-sourced) stays, purely for users who want a CSV
  copy.
- `_plan_data_path()` / `_read_plan_data_file()` (`app_core.py:555,598`) stop
  preferring the on-disk CSV (`prefer_existing=True`) as the read-back source
  for the UI's own display of "what did I just save" and read from
  `local_store.latest_sectioned_data()` instead.

**Phase 3 — remove the unconditional CSV reads inside the engine's own load
path.**
- Move the spending-budget-lines and unified-spending-budget data (§1.3,
  items 1–2) into DB tables (new `plan_spending_budget_lines` /
  `plan_spending_taxonomy` tables alongside the existing `plan_spending_policy`
  table in `local_store.py`), or fold them into `plan_snapshots.sectioned_json`
  under new sections so no separate table is needed. Either way,
  `data_io.parse_client()` stops calling `candidate_input_files()` /
  `spending_budget_resolver` with a filesystem `root` and instead reads those
  values out of the already-loaded `data` dict, exactly like every other
  `_v(data, section, subsection, label)` lookup in the file.
- At that point `config_backend.load_active_config()` with backend=SQLITE (or
  the new `engine_config_loader.load_engine_config(source='db')` from this
  Phase-1 seam) is a fully DB-canonical read with zero filesystem CSV
  involvement for user plan data. CSV/JSON/YAML remain available strictly via
  explicit import (`local_plan_data_sync.py`, Path C) and export
  (`local_store.export_latest_plan`).
- Retire `import_csv_to_sqlite()`'s role as a *build-time* bootstrap
  (`config_backend.py:349-354`) — keep it only as the explicit one-time
  "import this legacy CSV folder into my DB" tool it should have been (i.e.
  invoked from an explicit "Import" UI action / CLI flag, not from
  `load_active_config()`'s auto-dispatch).

---

## 3. Risks

- **Golden-master / fixture drift.** `tests/fixtures/golden_master_engine_cases.json`
  and every test that calls `data_io.load_csv(ROOT / 'input' / 'client_data.csv')`
  directly (e.g. `tests/test_167_tax_loss_harvesting.py:15`,
  `tests/test_1_regressions.py`) assume the on-disk CSV is the input. Phase 2/3
  must **not** delete those CSV files (per this task's explicit constraint,
  and because tests still legitimately read them as *fixtures*, which is a
  valid adapter use, not a "normal build path" round-trip). Instead, Phase 2/3
  test work should add a DB-seeding helper (e.g.
  `local_store.import_sectioned_plan(load_csv(path), db_path=tmp_db)`, exactly
  as this Phase 1 deliverable's unit test does — see
  `tests/test_168_engine_config_loader.py`) so tests can assert the DB path
  and the CSV-fixture path produce the same engine config, without ever
  changing what golden-master fixture values themselves encode.
- **Two engine-config assembly entry points must stay in lockstep.**
  `report_compute.prepare_config_from_sectioned_data` is the single
  normalization funnel today; as long as every source (`current`, `db`,
  `import_file`, and any future ones) produces a `SectionedData` dict and
  hands it to that same function, behavior stays consistent by construction.
  The main risk is a future change that bypasses
  `prepare_config_from_sectioned_data` for one source but not another.
- **`_v(data, section, subsection, label)` accessor is shape-sensitive.**
  `domain_models.plan_input_from_sectioned_data` / `to_sectioned_data`
  (`domain_models.py:202,135`) use subsection `"Client"` for household name
  lookups while the real CSV/engine convention is subsection `""` (empty) —
  see `data_io.py:426` (`_v(data,'Household','','member_1_name',...)`) vs.
  `domain_models.py:204` (`_lookup(data, "Household", "Client", ...)`).
  Today this "just works" because `PlanInput.sectioned_data` retains the full
  original sectioned dict verbatim (including the real `""` subsection) and
  `to_sectioned_data()` only *adds* keys under `"Client"`, never overwriting
  `""`. But it means the typed `PlanInput.members`/`.accounts`/
  `.income_streams` fields are a **lossy, best-effort projection** of the
  sectioned data, not a full parse — a future refactor that starts trusting
  the typed fields as canonical (instead of `sectioned_data`) would silently
  drop data. Phase 2/3 should reconcile this before leaning harder on the
  typed model.
- **`load_active_config()`'s auto-bootstrap-from-CSV** (`config_backend.py:
  349-354`) fires whenever the DB is empty/missing, which is convenient for
  first-run but means "the DB is canonical" is not strictly true until that
  bootstrap has happened once. Phase 2 should make this bootstrap an explicit,
  auditable one-time action rather than an implicit side effect of a read.
- **Windows file-locking on SQLite WAL files** in tests — observed directly
  while building this Phase 1 seam's test: `tempfile.TemporaryDirectory()`
  cleanup can raise `PermissionError` on Windows because SQLite's WAL journal
  can still be memory-mapped briefly after the connection's `with` block
  exits. Use pytest's `tmp_path` fixture (deferred cleanup) rather than
  `tempfile.TemporaryDirectory()` in any new DB-seeding test helpers.
- **Reference data vs. plan data.** Not everything CSV-shaped is in scope.
  `reference_data/capital_market_assumptions.csv`,
  `reference_data/tax_update_dashboard.csv`, and similar shared
  assumption/reference tables are not per-plan data and should very likely
  stay CSV/reference files even after Phase 3. Scope creep here would turn a
  bounded migration into an open-ended one.

---

## 4. Phase 1 deliverables (this change)

1. This document.
2. `src/engine_config_loader.py` — additive seam, `load_engine_config(source=...)`:
   - `source='current'` (default): reproduces exactly what
     `config_backend.load_active_config()` +
     `report_compute.prepare_config_from_sectioned_data()` already do today.
     **No behavior change** for any existing caller, because nothing existing
     calls this new function yet.
   - `source='db'`: reads `local_store.latest_sectioned_data(db_path)`
     directly (bypassing the backend-dispatch/auto-bootstrap logic in
     `load_active_config`), merges the same System-Configuration sections
     `load_active_config` would merge, then normalizes through the same
     `prepare_config_from_sectioned_data`.
   - `source='import_file'`: reads one explicit CSV/JSON/YAML adapter file
     (`path=...`), same merge + normalize.
3. `tests/test_168_engine_config_loader.py` — seeds a temp DB and a temp CSV
   file from the same sectioned data (the real `input/client_data.csv`) and
   asserts `source='db'` and `source='import_file'` produce an equivalent
   engine config across 20 representative scalar fields, plus sanity checks
   for the default source and invalid-source handling.

Nothing in `input/`, `src/data_io.py`, `src/config_backend.py`,
`src/local_store.py`, or any existing call site was modified.

---

## 5. Recommended ordering

1. **Phase 2a (writes):** Convert `app_core.py`'s classic route handlers from
   `_csv_write_rows()` to `local_store.import_sectioned_plan()` /
   a new patch helper, one route family at a time (household → income →
   spending → assets → policy), keeping `_sync_config_backends()` as a
   DB→CSV **export** at the end of each route so on-disk CSVs stay
   available for anyone/anything still reading them directly (back-compat
   window). This is the highest-value, lowest-risk step: it removes the
   round-trip described in §1.1 without touching the read path at all.
2. **Phase 2b (read path cleanup):** Once 2a is done and stable, make
   `_read_plan_data_file()` / `_plan_data_path()` prefer the DB over on-disk
   CSV (flip `prefer_existing` semantics), and make
   `load_active_config()`'s CSV-bootstrap (§3, "auto-bootstrap-from-CSV") an
   explicit one-time action instead of implicit.
3. **Phase 3 (engine load path):** Move spending-budget-lines /
   taxonomy/aliases (§1.3, items 1–2) into `plan_snapshots.sectioned_json` or
   dedicated `local_store` tables, and delete the `candidate_input_files()` /
   `spending_budget_resolver` filesystem reads from `data_io.parse_client()`.
   Do this last because it touches the actual numeric engine output and is
   the piece most likely to require new golden-master baselines (regenerated
   deliberately, with sign-off, not as a side effect).
4. **Phase 4 (optional/cleanup):** Retire `import_csv_to_sqlite()`'s implicit
   bootstrap role entirely; keep it only as the backing implementation for an
   explicit "Import legacy CSV folder" UI/CLI action alongside
   `local_plan_data_sync.py`.

This ordering front-loads the highest-value, lowest-blast-radius change
(stop re-deriving the DB from a CSV file on every save) and pushes the
riskiest change (altering what numbers the engine computes) to last, gated on
golden-master re-baselining that Phase 1 explicitly does not do.

---

## 6. What I could not fully determine

- Whether every route in `app_core.py` that calls `_csv_write_rows` is
  reachable only through Path A, or whether some are also invoked by
  CLI/test code that assumes an on-disk CSV artifact exists afterward (would
  affect Phase 2a sequencing/back-compat needs). A full call-site audit of
  `app_core.py`'s ~10 `_csv_write_rows` call sites was out of scope for
  Phase 1's read-only tracing.
- Whether any external/desktop-packaging tooling (outside `src/`) depends on
  `input/client_data.csv` existing and being fresh after every save, versus
  only after an explicit export. This affects how soon Phase 2b's
  `prefer_existing` flip is safe.
