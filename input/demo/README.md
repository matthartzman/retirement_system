# Demo Plan Data (#240)

Fictional household (Alex & Morgan, Illinois) sized to exercise the core
engine end-to-end. Adapted from `tests/fixtures/sample_plan_frozen/` (a
known-valid, already-tested fixture) with names swapped to a clearly
fictional persona — safe to show to prospects/colleagues.

Verified: `parse_client()` + `project()` run clean, 2026-2056, terminal net
worth computes without error.

## To use it

This app reads plan data from `input/*.csv` directly; there is no separate
"demo mode" toggle yet. To try the demo:

1. Back up your current plan: **Settings → Data & Maintenance → Export CSV
   backup**, or just copy `input/*.csv` somewhere safe.
2. Copy every `input/demo/*.csv` file over the matching `input/*.csv` file.
3. Reload the app / open the current plan.
4. When done, restore your backed-up files the same way.

Only the core CSVs are included here (matching the source fixture) — no
JSON/YAML companions. If the app's JSON/YAML load path is needed instead,
regenerate them from these CSVs the same way the live `input/` companions
are kept in sync (see `tools/check_plan_data_sync.py`).
