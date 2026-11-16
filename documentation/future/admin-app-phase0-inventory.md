# Admin App Phase 0: Inventory

Status: draft
Date: 2026-11-16
Plan: `documentation/future/admin-app-plan.md` (Phase 0). Read-only inventory; no code changed.

## Summary

- 20 test files load or read `frontend/js/admin.js`, `admin.html` or `admin.css`: 10 MOVE, 8 REWRITE, 2 DELETE (plus 6 related files to rewrite).
- 19 of the 20 assert on panel JS or HTML text, so they are interface contracts (marked **C**).
- 5 planner frontend callers and 3 Python-side callers/lists reference `/api/admin/*`.
- `src/system_config.py` imports cleanly in an isolated process: **yes**.
- Two surprises change later phases: the survey's batch-editor caller is stale, and `admin.js` is 2,034 lines, not 2,048 (the ratchet baseline still says 2,048).

## 1. Tests that load or read the console files

Classes: **MOVE** = moves with the code (re-point paths to `admin_app/frontend/`); **REWRITE** = rewritten against the Admin app; **DELETE** = removed with the feature. **C** = asserts on panel JS/HTML text.

Class is decided by what the assertion protects. Admin-only UI that moves keeps its test (MOVE). Tests whose subject is the planner's relationship to the console (route, redirect, nav) change meaning (REWRITE). Tests covering pages that stay in the planner (plan-level engine sections) or checks that only exist because the file lives in `frontend/` (ratchet, version bump) change or go away.

| # | Test | What it reads | Class | C |
|---|---|---|---|---|
| 1 | `tests/frontend/admin_accessibility.test.mjs` | `js/admin.js`, `admin.html` via vm stub | MOVE | C |
| 2 | `tests/frontend/field_control_accessible_names.test.mjs` (admin block, line 175) | `admin.js` settingControl | MOVE (admin block only) | C |
| 3 | `tests/frontend/ui_prose_guard.test.mjs` | adds `frontend/admin.html` to scan list | MOVE (re-point to Admin app HTML; keep planner scan) | C |
| 4 | `tests/test_admin_all_compact_functional.py` | admin.html, admin.js | REWRITE (checks the "all sections" layout; nav changes) | C |
| 5 | `tests/test_admin_nav_structure_functional.py` | admin.html, admin.css, admin.js | REWRITE (new nav groups) | C |
| 6 | `tests/test_admin_system_config_compact_functional.py` | admin.html, admin.js | REWRITE (engine sections stay in planner) | C |
| 7 | `tests/test_admin_user_ui_model_functional.py` | admin.html, admin.css, admin.js | REWRITE (user UI model becomes `users.js`) | C |
| 8 | `tests/test_ui_responsibility_split.py` | admin.html, admin.js (search, single-section, no file: entries) | MOVE (search/single-section) with planner-side half kept | C |
| 9 | `tests/test_ui_tax_ss_cleanup.py` | admin.html, admin.js (search scope, step-desc) | MOVE | C |
| 10 | `tests/test_ui_dependency_ordering_functional.py` | admin.js `adminDependencyRank`, engine knobs | DELETE the admin assertion; rows are engine knobs that stay in planner, so port the ordering test to wherever the planner editor lands | C |
| 11 | `tests/test_pricing_ui_release.py` | admin.js help copy, admin.html version | MOVE (pricing controls move) | C |
| 12 | `tests/test_pricing_symbol_tester_functional.py` | admin.js symbol tester | MOVE (tester moves) | C |
| 13 | `tests/test_educational_helper_copy_functional.py` | admin.js, admin.html | MOVE for admin-only copy; engine-section copy follows its sections | C |
| 14 | `tests/test_helper_value_definitions_not_boilerplate_functional.py` | admin.js `adminDefaultMeaning` | MOVE or split like 13 | C |
| 15 | `tests/test_choice_dropdowns.py` | admin.js | MOVE or split like 13 | C |
| 16 | `tests/test_roth_user_ui_render_fix.py` | admin.js (negative assert: Roth controls absent) | DELETE (guard has no meaning once admin.js leaves the planner) | C |
| 17 | `tests/test_governance_hardening.py` | admin.html links css/admin.css and js/admin.js; files exist | REWRITE (paths in new package) | C |
| 18 | `tests/test_pywebview_bridge_load_order_regression.py` | admin.html script order, admin.js boot deferral | REWRITE (the Admin app is a browser page, not PyWebView; keep only the DOMContentLoaded boot check) | C |
| 19 | `tests/test_dashboard_shared_helpers_load_order_regression.py` | admin.html must not load dashboard helpers | REWRITE (planner-side guard becomes moot; keep a no-planner-script check for the Admin page) | C |
| 20 | `tests/test_bump_version_comprehensiveness_regression.py` | `admin.html` `?v=` cache busters | REWRITE (version bumper must cover the Admin app HTML or drop the admin cases) | no (tests the bump tool on fixtures) |

Related, not file loaders but affected:

| Test / file | Why | Class |
|---|---|---|
| `tests/test_frontend_size_ratchet.py` (`"admin.js": 2_048`, baseline row 2026-11-11) | per-file ceiling; removing the file means removing the entry | REWRITE (lower ceiling after the move; never raise) |
| `tests/fixtures/frontend_source_grep_baseline.json` (lists `test_admin_*` files) | freeze list of source-grep tests; entries follow renamed or deleted tests | REWRITE |
| `tests/test_recommendations_functional.py:183` | asserts `frontend/*.html == [admin.html, concepts.html, index.html]` | REWRITE |
| `tests/test_database_first_ui_refactor_functional.py:62` | asserts `/system-configuration` route string in `admin_routes.py` | REWRITE |
| `tests/test_admin_local_permissions_functional.py` | asserts `"/frontend/admin.html"` redirect in routes | REWRITE (`/admin` becomes a hand-off page) |
| `tests/e2e/admin-config-change.spec.js` | Playwright against `/admin`; saves a config change and reads `#editorBody` | REWRITE against the Admin app (port 5056) for runtime rows; engine-row cases stay with the planner |
| `tests/test_pricing_symbol_tester_functional.py` | see row 12 | MOVE |
| `tests/test_admin_build_progress_overlay_functional.py` | in the grep-baseline list; reads `index.html` and `dashboard.js`, not the console | no change (planner build overlay) |

Counts for the 20 file-loading tests: **MOVE 10** (rows 1, 2, 3, 8, 9, 11, 12, 13, 14, 15), **REWRITE 8** (rows 4, 5, 6, 7, 17, 18, 19, 20), **DELETE 2** (rows 10, 16). 19 of the 20 are interface contracts (**C**); row 20 is not. Rows 3, 8, 13, 14 and 15 mix admin-only and planner/engine-section assertions and need splitting. The related table adds 6 REWRITE items (ratchet, grep baseline, recommendations, database-first, local-permissions, e2e spec) and 1 no-change.

## 2. Planner callers of `/api/admin/*`

### Frontend

| Caller | Route | Notes |
|---|---|---|
| `frontend/js/dashboard_decomp_checklist_closeout.js:360` | `GET /api/admin/csv-backup` | stays (CSV backup stays in planner) |
| `frontend/js/dashboard_decomp_checklist_closeout.js:691` | `GET /api/admin/tax-law-dashboard` | moves with Governance page; the planner call needs a decision (keep a read-only route or link out) |
| `frontend/js/dashboard_decomp_holdings.js:458` | `GET /api/admin/diagnostics` | stays (workbook build diagnostics stay) |
| `frontend/js/dashboard_decomp_checklist_closeout.js:394,399,406` | navigates to `/system-configuration` (PyWebView and `location.href`) | becomes link to the Admin app |
| `frontend/js/remote_mode.js:22` | hides `a[href="/system-configuration"]` | follows the link change |
| `frontend/js/admin.js` (the moving file itself) | `server`, `clear-webview-cache`, `server/shutdown`, `system-config` (GET), `tax-law-dashboard`, `diagnostics` | moves; `diagnostics` is the one admin.js caller of a route whose feature stays |

### Python

| Location | Use |
|---|---|
| `src/server/admin_routes.py:53-143` | defines the nine routes: tax-law-dashboard, diagnostics, clear-webview-cache, server, mode, server/shutdown, system-config GET and POST, csv-backup |
| `src/server/route_manifest.py:70-73` | lists the same routes under group `admin` |
| `src/server/remote_allowlist.py:32-33,292-302` | remote allow-list and role tiers for these routes |
| `src/api_contracts.py:345,350` | contracts `system_config_rows_v1`, `system_config_rows_update_v1` |
| `src/desktop_api.py:24` | `_SHUTDOWN_URLS` includes `/api/admin/server/shutdown` |
| Python tests | `test_remote_mode_contract.py:144-159`, `test_service_extraction_functional.py:177,220`, `test_batch_assumption_edit_tools_functional.py:46-59`, `test_blank_plan_rows_functional.py:86` (asserts `csv-file` route is 404) |

### Surprise: the plan's survey is stale on the batch editor

The plan cites `dashboard_batch_assumption_edit.js:333,415` as calling `/api/admin/system-config`. In the current tree that file has no `/api/admin` call; line 373 says "no system-config batch editor is injected on the Settings page" (item 180). The route and contracts still exist and `test_batch_assumption_edit_tools_functional.py` still asserts on them, so those assertions guard a contract with no frontend caller. Phase 3 should confirm this and decide whether the route's planner-facing half can simply go.

## 3. `src/system_config.py` import check

Command: `python -I -c "import sys; sys.path.insert(0,'.'); import src.system_config"` from the repo root.

Result: **imports cleanly**. Only `src.system_config` and `src.version` are loaded. `app_core` is not imported; `flask` is not imported. Module-level imports are `hashlib`, `json`, `pathlib`, `typing`.

So a standalone Admin process can use it with no planner app object. Remaining checks for Phase 3: `load_system_config` and `system_setting` are the functions used by the database-first test; the writer side lives in `src/server_services/admin_service.py` and `src/runtime_config.py` and was not import-tested here.

## Other surprises

1. `frontend/js/admin.js` is **2,034** lines now; `test_frontend_size_ratchet.py` still pins 2,048 (it is a ceiling, so it passes, but the headroom is unused).
2. The plan says "about 20 test files"; the actual count is 20 file-loading tests plus 7 related files above.
3. `src/server/admin_routes.py` has a `/api/admin/mode` route (POST) that the plan's Admin route list does not mention; decide whether it moves.
4. Five tests mix admin-only and engine-section assertions and cannot move whole: they need splitting.
