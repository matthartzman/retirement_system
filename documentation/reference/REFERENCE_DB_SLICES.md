# reference.db slices: how to move one reference dataset into the database

Shipped reference data (tax law, CMAs, mortality, ...) moves from `reference_data/` files into one read-only SQLite file, `src/reference/reference.db`, one *slice* per PR (WP3.2-3.8). WP3.1 set up the machinery and one demonstration slice, `tax_update_dashboard`. Copy it.

## The pieces of a slice (all named `<slice>`)

| Piece | Where | What it does |
|---|---|---|
| Source | `reference_src/<file>` | Dev-only authoring file. Never bundled, never read at runtime. |
| Builder | `tools/reference_slices/<slice>.py` | `SOURCES = (...)` + `build(src) -> {table: (columns, rows)}`. Typed cells (`None`/`int`/`float`/`str`; no `bool`). Put an integer `seq` column first if order matters, because every table is sorted. Use `_source.read_csv(path, HEADER)`. |
| Registration | `tools/reference_slices/__init__.py` `SLICES` | One line. |
| Getter | `src/stores/ref_getters/<slice>.py` | `def <getter>(ref: RefData \| None = None)`. Uses `reference()` when `ref` is None. Only `ref.query(...)`, no file I/O. Builds fresh objects on every call. Returns **exactly** the old loader's structure. |
| Golden registration | `src/stores/ref_getters/__init__.py` `GOLDEN_GETTERS` | `"<name>": getter` (wrap a getter that takes arguments so the wrapper covers all of them). |
| Golden fixture | `tests/fixtures/reference_golden/<name>.json` | The old loader's output, captured once. |
| Database | `src/reference/reference.db` | Committed. Rebuilt by `python tools/build_reference_db.py`. |

Runtime access: `from src.stores.ref_access import reference` (shared handle, hash checked once, thread-safe). Overrides: `RETIREMENT_REFERENCE_DB=<path>`; tests use `set_reference_for_tests(path)` / `set_reference_for_tests(None)`. There is no fallback to the old files.

## Recipe (one PR per slice)

1. **Capture the golden first.** Add an entry to `CAPTURES` in `tools/capture_reference_golden.py` that calls the old loader the way product code does, with date-dependent arguments pinned. Then run `python tools/capture_reference_golden.py <name>`. Commit the JSON unchanged. Do this for every distinct loader result consumers use.
2. **Move the source.** Run `git mv reference_data/<file> reference_src/<file>`. A file that is still read at runtime by another slice stays put until that slice lands.
3. **Write the builder** and add it to `SLICES`. Store values in their natural types and let the getter shape them (the demo stores `blocking` as 0/1 and returns `bool`). Use the spec's table names (`tax_law`, `cma`, `state_tax`, ...).
4. **Write the getter** and register it in `GOLDEN_GETTERS`.
5. **Rebuild:** `python tools/build_reference_db.py`. Commit `src/reference/reference.db`.
6. **Switch every consumer** listed for the slice in the design spec (P2 table) to the getter, in the same PR.
7. **Delete the old path:** the loader, its file constants, fallbacks and the `CAPTURES` entry. Also update tools and docs that cite the old file (`grep -rn "<file>"`). Lower the audit ratchet: `python tests/test_no_data_file_io_report_regression.py --record`.
8. **Prove nothing moved:**
   `python -m pytest tests/test_reference_golden_regression.py tests/test_reference_db_unit.py tests/test_no_data_file_io_report_regression.py -q`,
   `python tools/build_reference_db.py --check`, `python tools/golden_compare.py compare`, the consumer's own tests, and `python tools/generate_system_diagram.py` (commit if it changed).

## Rules

- A golden fixture is never edited by hand and never re-captured from the new getter. A mismatch is a getter bug.
- The getter output must match the golden as text. The encoding (`tests/reference_golden.py`) keeps `1` and `1.0`, tuples and lists, key order and non-string keys distinct.
- Shipped data changes (for example the annual tax update) edit `reference_src/`, rebuild, and bump `REFERENCE_RELEASE` in the tool.
- `--check` compares content (`ref_meta` and table DDL), not bytes, because the SQLite header records the library version. Two builds with the same library are byte-identical.
- Every file in `reference_src/` must belong to exactly one slice, or the build fails.

## Field tiers (`min_tier`)

`reference_src/field_tiers.csv` tags every field of the catalog (`schema.csv` plus `generated_schema_coverage.csv`) with the smallest tier that shows it: `simple`, `standard`, `advanced` or `expert` (cumulative). The build fails if a field is untagged or a tag names no field. Rules used for the first tagging: a field is at least as high as the feature that owns its section (Equity Compensation and Divorce/QDRO fields are `expert`, DAF/QCD/HSA/Scenarios are `advanced`, Education 529 and Reserves are `standard`); inside a feature, the headline inputs are lower and tuning knobs higher (Monte Carlo simulation counts `advanced`, regime and shock knobs `expert`; Roth policy and years `simple`, guardrails `expert`). The UI filter (a later work package) always shows a required field that is empty, whatever its tag. To retag a field, edit the CSV and rebuild.
- Huge goldens (zip_table) are stored as a SHA-256 of the canonical text (`digest_golden` in tests/reference_golden.py), recorded from the old loader's output.
