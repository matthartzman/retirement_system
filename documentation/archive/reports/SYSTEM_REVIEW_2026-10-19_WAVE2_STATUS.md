# System Review 2026-10-19 — Wave 2 Status

Companion to `SYSTEM_REVIEW_2026-10-19.md` section 9 (Wave 2). Checked against `main` at f9f910e (2026-10-20). Only WI-005 to WI-009 of Wave 1 are merged; WI-010/010a are in a parallel session; WI-012, WI-013, WI-015 and WI-016 are not on main.

| Item | Status | Note |
|---|---|---|
| WI-017 | Blocked | Needs WI-013 and WI-016 |
| WI-018 | Blocked | Needs WI-015 |
| WI-019 | Blocked | Needs WI-018 (WI-007 is merged) |
| WI-020 | Blocked | Needs WI-018, WI-019, WI-014 |
| WI-021 | Blocked | Needs WI-018, WI-020 |
| WI-022 | Blocked | Needs WI-012 (WI-002 and WI-005 are done). Measure-only, no pins change |
| WI-023 | Blocked | Needs WI-022, then planner sign-off before any re-pin |
| WI-024 | Blocked | Needs WI-023; two phases per Wave 0 decision (c); planner sign-off before each re-pin |
| WI-025 | Blocked | Needs WI-024 |
| WI-026 | Done (branch) | See below |

## WI-026 (ARC-004, option 2)

Removed: `src/plan_data_read.py` and its unit test; the legacy `client_files` / `input/*.csv` fallbacks in `financial_trends_reporter/trends_metrics.py` (liabilities and plan rows now come from the plan file only); the never-written legacy `audit_events` table in `config_backend.init_sqlite`; the `plan_snapshots` table and its four summary tables, plus the `result_snapshots` foreign key to it, in `local_store.init_local_store` (the nullable `plan_snapshot_id` column stays). The plan_data_read allow-list line in the no-data-file-IO test was dropped.

Kept: `client_files` and `get_client_file` (the conversion and `plan_db_replace` still require them), and the conversion's reads of `client_files` / `plan_snapshots` from an existing legacy database (`legacy_conversion/sources.py` checks table existence). Existing databases keep their old tables.

Tests: three `test_trends_metrics_unit.py` cases that seeded the removed fallback now seed `plan.rpx`; a new regression asserts a legacy `client_liabilities.csv` is ignored when the plan has no liabilities. No calculation, golden or tax result changed. No professional review needed.
