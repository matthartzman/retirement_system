# Master plan: feature tiers + file-dependency elimination (DRAFT for review)

Status: draft for owner review. **Nothing here is executed**; each work package (WP) needs an explicit owner go.
This document is the single sequencing, staffing and gating plan for two approved designs. It does not repeat their detail; it merges their order, removes duplicated work, and says who (which model, at what effort) should do each piece.

- Tiers design: `2026-10-04-feature-tiers-and-switches-design.md` (referred to as **T**)
- File-elimination design and plan: `2026-10-05-eliminate-file-dependencies-design.md` (referred to as **F**)
- Rental Properties module design: `2026-10-05-rental-property-module-design.md` (referred to as **R**; scheduled as WP12)

## 1. The combined design in one page

| Layer | End state (from T and F) |
|---|---|
| Features | One registry, one switch per feature (nav entry + input rows + engine effect + workbook sheet). Off means hidden, data kept, "Off · N rows entered", and a warning when the engine ignores it. Minimal always-on core: Household, Income, Spending, Holdings and Assets, Assumptions, Build & Results, Settings. |
| Tiers | Simple / Standard / Advanced / Expert are starting switch sets; every switch stays overridable ("Advanced (customized)"); a tier also gates field detail through a `min_tier` tag per field, with "Show advanced". |
| Storage | `plan.db` (the `.rpx` plan file: `plan_rows` + typed tables + revisions + build results), `app.db` (install state, plan registry, active plan), `reference.db` (shipped read-only). API keys in the OS credential store. Demo and actual plan are separate plan files, one active at a time. |
| CSV | Only `csv_exchange` (bulk import with preview/diff, bulk export). Static test enforces it. |
| Migration | One removable `legacy_conversion/` module that converts files and database into a plan file **and** maps the plan to a tier, verified by comparing the first build with the last result the old version produced. Originals are never modified. |
| Workbook | Keeps its five answer-type sections; domains renamed to the nav group names. |

## 2. Where the two plans overlap or conflict (and how this plan removes the rework)

| # | Overlap / conflict | Resolution |
|---|---|---|
| 1 | T-P2 adds toggle rows and backfill to `client_optional_functions.csv`; F-P3 replaces that file with `plan_rows`. | New switchable features get `default_on` in the registry and **no new rows and no backfill**. A flipped switch is written through one `set_feature()` accessor, whose internals change once (WP4). |
| 2 | T-P1 unifies three feature-read paths; F-P3.2 rewrites the same reads. | Unify first (WP1.2), so WP4.2 changes one function, not three. |
| 3 | T-P8 (map an existing plan to a tier, with a before/after safeguard) and F-P8 (converter with before/after verification) are the same mechanism. | One converter, one verification, one first-launch notice. T-P8 is deleted as a separate phase. |
| 4 | T-P5 adds `min_tier` to `schema.csv`; F-P2.7 moves `schema.csv` into `reference.db`. | Tag fields once, in the reference source, in WP3.7. No edit to a file that is about to be removed. |
| 5 | T-P4 stores the tier "in the plan"; F-P3 decides how the plan is stored. | Tier and overrides are ordinary `plan_rows` settings written after WP4. The demo plan is Expert tier. |
| 6 | T-P7 retires about 24 hidden redirect steps and renames domains; F-P3 edits the same frontend and endpoints. | Retire redirects and rename domains first (WP1.1): a smaller surface for every later PR and lower frontend-size-ratchet pressure. |
| 7 | F-P0.2 moves ~150 tests onto a fixture helper; T would touch many of the same tests. | Helper lands first (WP0.2); all later PRs use it. |
| 8 | New CSV-specific code could creep in during the code-only tier work. | WP0.3's static audit ratchet fails any PR that adds file I/O. |
| 9 | The rental module (R) needs the feature registry, typed tables, `reference.db` tax constants and the build-I/O layer; built on today's CSV model it would be rewritten. | Split it: the tax and projection engine lands early behind the switch (no storage), while data, UI and workbook wait for storage (WP12 below). The engine reads one parse boundary, so only the parser's source changes later. |
| 10 | R's tax constants (passive-loss thresholds, 27.5-year life, 25% recapture cap) belong in the tax reference data. | Added to `tax_law_v10.json` in WP12.1; WP3.2 carries them into `reference.db` unchanged. |

## 3. Work packages and sequence

**Delivery rule (owner decision):** one session and **one PR per work package** (WP0, WP1, ...). The numbered PR rows in sections 3 and 4 (0.1, 0.2, 1.1 ...) are **units of work inside that WP's single PR**, done sequentially as separate commits, never as separate sessions or PRs. No parallel work without explicit owner sign-off. Full e2e and CI run once per WP, at its end. Where a unit carries an owner checkpoint (section 6), the WP's PR stays draft until it is cleared.

```
WP0 safety net ─┬─► WP1 features & nav ─► WP12a rental engine (no storage) ─┐ (lane B)
                └─► WP2 stores ─► WP3 reference.db ─► WP4 plan rows ─┬─► WP5 tiers UI ┤
                                          │                          ├─► WP6 datasets ─► WP7 build I/O ─► WP12b rental data/UI/workbook/housing
                                          │                          │                          └─► WP9 csv_exchange ─► WP12c rental CSV ─► WP10 conversion ─► WP11 cleanup
                                          └─► WP8 app state (after WP2, parallel lane) ┘
```

| WP | Contents (source) | Units (commits, 1 PR per WP) | Depends on | Lane |
|---|---|---|---|---|
| WP0 | Golden harness, fixture helper, static audit (F-P0) | 3 | none | A |
| WP1 | Retire redirects + domain rename (T-P7); `feature_enabled()` accessor (T-P1); shrink the core (T-P2); sheet-only toggles (T-P3); uniform off semantics | 5 | WP0 | B |
| WP2 | Stores: DB helpers, `PlanStore`/`AppStore`, `RefData` skeletons (F-P1) | 3 | WP0 | A |
| WP3 | `reference.db` slices, plus `min_tier` tags (F-P2, T-P5 data) | 8 | WP2 | A (agents in parallel) |
| WP4 | `plan_rows`, read path, grid write path, endpoints, mirror deletion (F-P3) | 7 | WP2, WP1.2 | A |
| WP5 | Tier presets and Plan Features UI (T-P4); field-tier filter (T-P5 UI); interview and self-suggest (T-P6) | 3 | WP3.7, WP4 | B |
| WP6 | Holdings, HSA, spending set, YTD tables (F-P4) | 6 | WP4 | A |
| WP7 | Build reads stores; `build_results`; per-plan outputs (F-P5) | 3 | WP4, WP6 | A |
| WP8 | `system_config` split, `SecretStore`, app state, plan registry and demo coexistence (F-P6) | 4 | WP2 (8.4 needs WP4) | C |
| WP9 | `csv_exchange` and adapters, frontend folder IO (F-P7) | 4 | WP4, WP6 | A |
| WP10 | Converter incl. tier mapping, verification, UI, rehearsals (F-P8, T-P8) | 5 | steps authored in WP4-WP8; assembly after WP9 | A |
| WP12a | Rental Properties engine: tax core, projection integration and feature registration (default off), parse boundary, home-conversion hooks (R sections 4, 5, 8) | 3 | WP1.2 (feature accessor), WP0 (golden) | B |
| WP12b | Rental data (typed tables), UI mock and page, workbook sheet and report lines, housing-optimizer `rent_out` integration (R sections 3, 6, 7) | 5 | WP6, WP7, WP12a | B |
| WP12c | Rental CSV import/export template | 1 | WP9, WP12b | A |
| WP11 | Dead-code deletion, packaging, enforcing audit, tests, docs (F-P9) | 5 (+1 later) | WP10 | A |

Critical path: WP0 → WP2 → WP4 → WP6 → WP7 → WP9 → WP10 → WP11. Lanes B and C run beside it and touch different files (nav and registry code, then tier UI; app-state modules), so they do not collide with lane A.
Rental Properties is a **new** dataset, so it needs no conversion step; WP10's rehearsals include a plan with rental properties to prove the converter leaves it intact. The tier table gains Rental Properties in **Advanced** (see T section 4).
**Conversion steps are written in the WP that changes the dataset** (part of that PR's definition of done); WP10 assembles, verifies and ships them.

## 4. Models and effort

Model guide (Claude 5 family and Haiku): **Fable 5.1** or **Opus 5.5** for design-critical work where a wrong shape is expensive to undo; **Sonnet 5.5** for most implementation following an established pattern; **Haiku 4.5** for mechanical edits, searches and doc updates. Effort: low (mechanical), medium (routine, pattern given), high (cross-module or financial-correctness), xhigh (shapes everything downstream).

| Unit | Scope | Model | Effort | Approach |
|---|---|---|---|---|
| 0.1 | Golden harness | Sonnet 5.5 | high | One agent; fixtures from frozen sample + demo plan |
| 0.2 | Fixture helper + migrate ~150 tests | Sonnet 5.5 | medium | **Scripted codemod**, not per-file LLM edits; Haiku reviews the diff summary |
| 0.3 | Static file-I/O audit | Sonnet 5.5 | medium | AST scan + ratchet |
| 1.1 | Retire redirects, rename domains | Sonnet 5.5 | medium | Deletion-heavy; run frontend tests |
| 1.2 | `feature_enabled()`/`set_feature()`, unify 3 read paths, catalog `tier` / `nav_group` / `default_on` | **Opus 5.5** | high | Design-critical; `/code-review` at medium before merge |
| 1.3 | Shrink the core (Estate, Insurance, Reserves, Family & Business, Scenarios, Workbench) | Sonnet 5.5 | high | Default-on, so existing plans see no change; golden must stay equal |
| 1.4 | Sheet-only toggles gate input sections | Sonnet 5.5 | medium | Pattern from 1.3 |
| 1.5 | Uniform off semantics; engine-ignored warnings; pinned tests for engine-participating features | Sonnet 5.5 | high | Tests pin projections with each feature off |
| 2.1 | DB helpers, versioning | Sonnet 5.5 | high | In-memory tests |
| 2.2 | `PlanStore`/`AppStore` API | **Opus 5.5** (or Fable 5.1) | **xhigh** | **Owner review checkpoint** before merge |
| 2.3 | `RefData` skeleton | Sonnet 5.5 | medium | |
| 3.1 | Reference build tool + golden getters | Opus 5.5 | high | Deterministic build; sets the pattern for 3.2-3.8 |
| 3.2 | Tax law | Sonnet 5.5 | high | Financial correctness; golden is the proof |
| 3.3 | State tax | Sonnet 5.5 | medium | |
| 3.4 | CMAs and correlations | Sonnet 5.5 | high | Custom-file semantics become overrides |
| 3.5 | Mortality, real-loss, governance | Sonnet 5.5 | low | |
| 3.6 | Security master | Sonnet 5.5 | medium | |
| 3.7 | Field schema + `min_tier` tags per the approved tier table | Sonnet 5.5 | high | **Owner reviews the tag list** |
| 3.8 | ZIP data, field map, template layout | Haiku 4.5 | low | |
| 4.1 | `plan_rows`, row API, minimal importer, helper builds `plan.db` | **Opus 5.5** | **xhigh** | **Owner review checkpoint** |
| 4.2 | Read path | Opus 5.5 | high | |
| 4.3 | Grid write path, `/api/plan/forms` unification | Opus 5.5 | high | |
| 4.4a-c | Strategy endpoints in three areas | Sonnet 5.5 | high | **Three agents in parallel** following the 4.2/4.3 pattern |
| 4.5 | Delete sync, mirrors, `client_files`, `/api/csv` | Sonnet 5.5 | medium | Deletion checklist from F section 13 |
| 5.1 | Tier presets, tier row, Plan Features UI | Opus 5.5 | high | UX decisions: owner review of screens |
| 5.2 | Field-tier filter, "Show advanced" | Sonnet 5.5 | high | |
| 5.3 | Interview + self-suggest | Sonnet 5.5 | high | Owner reviews the question wording |
| 6.1 | Holdings, liabilities, targets | Sonnet 5.5 | high | |
| 6.2 | HSA schedule | Sonnet 5.5 | medium | |
| 6.3a | `SpendingRepo` + taxonomy/aliases | **Opus 5.5** | **xhigh** | Largest single piece; fixes the repository shape |
| 6.3b | Budget, lines, tier overrides | Sonnet 5.5 | high | |
| 6.3c | Rules, category map, recovery to revisions | Sonnet 5.5 | high | |
| 6.4 | YTD tables | Sonnet 5.5 | high | |
| 7.1 | Build reads stores | Opus 5.5 | high | |
| 7.2 | `build_results` replaces JSON sidecars | Sonnet 5.5 | high | |
| 7.3 | Per-plan outputs | Sonnet 5.5 | medium | |
| 8.1 | `system_config` split, version constant | Opus 5.5 | high | |
| 8.2 | `SecretStore` (OS credential store) | Sonnet 5.5 | high | **Approval gate: new dependency** |
| 8.3 | Small state moves (prefs, audit, logs, backups, caches) | Sonnet 5.5 | medium | |
| 8.4 | Plan registry, active plan, demo coexistence, switcher UI | Opus 5.5 | high | |
| 9.1 | `csv_exchange` core | Opus 5.5 | high | |
| 9.2 | Plan-set import/export | Sonnet 5.5 | high | |
| 9.3 | Re-point adapters | Sonnet 5.5 | medium | |
| 9.4 | Frontend folder IO, deletions | Sonnet 5.5 | high | |
| 10.1 | Converter skeleton | Sonnet 5.5 | high | |
| 10.2 | Assemble steps incl. tier mapping | Opus 5.5 | high | |
| 10.3 | Verification and safeguard | **Opus 5.5** (or Fable 5.1) | **xhigh** | **Owner review checkpoint** |
| 10.4 | First-launch UI | Sonnet 5.5 | medium | |
| 10.5 | Rehearsals | Sonnet 5.5 | medium | Needs a copy of the owner's plan |
| 11.1 | Dead-code deletion | Haiku 4.5 | low | Scripted reachability check first |
| 11.2 | Packaging, smoke tests | Sonnet 5.5 | high | Frozen build on Windows CI |
| 11.3 | Enforcing audit | Sonnet 5.5 | low | |
| 11.4 | Test suite finalization | Sonnet 5.5 | medium | |
| 11.5 | Documentation | Haiku 4.5 | low | Reviewed once |
| 11.6 | Delete converter (later release) | Haiku 4.5 | low | |

| 12.1 | Rental tax core: depreciation, Schedule E, passive-loss limits, recapture (pure functions, IRS-style tests; constants added to `tax_law_v10.json`) | **Opus 5.5** | **xhigh** | **Owner/tax-preparer checkpoint on rules and worked examples** |
| 12.2 | Engine integration (AGI, MAGI, NIIT, cash flow, net worth, sale), feature registration default off, golden unchanged | Opus 5.5 | high | `/code-review` at medium |
| 12.3 | Parse boundary + in-code fixtures + home-conversion hooks (carrying-cost shift, converted-home §121 two-of-five test, recapture at sale) | Opus 5.5 | high | Roth-conversion-under-passive-loss test |
| 12.4 | Typed tables and repository (`rental_properties`, `rental_improvements`, `rental_year_overrides`), field tier tags | Sonnet 5.5 | high | Follows the SpendingRepo pattern (6.3a) |
| 12.5 | UI mockup for owner review (summary strip, property list, detail tabs, convert-my-home) | Sonnet 5.5 | medium | **Owner review checkpoint** before the build |
| 12.6 | Rental Properties page | Sonnet 5.5 | high | Mobile-friendly cards; frontend and Playwright tests |
| 12.7 | Workbook sheet and report lines (Executive Summary, Cash Flow, Net Worth, Balance Sheet, Lifetime Taxes, Charts) | Sonnet 5.5 | high | **Owner reviews sheet layout** |
| 12.8 | Housing optimizer `rent_out` candidates, dual-ownership predicate, disclosure removal | Opus 5.5 | high | Most coupled part; own PR |
| 12.9 | CSV import/export template for properties | Sonnet 5.5 | medium | After `csv_exchange` exists |

Count: 18 units are Opus-class (the five xhigh ones — 2.2, 4.1, 6.3a, 10.3 and 12.1 — may use Fable 5.1), 44 are Sonnet, and 4 are Haiku; 66 units in total, delivered as 13 PRs (one per WP: WP0-WP12c).

## 5. Token-minimizing practices

1. **Self-contained brief per PR.** Each agent gets the PR's row from F section 13, the line references, and the pattern PR to follow, not the whole conversation. Fresh agents with narrow scope cost less than long sessions that re-read everything.
2. **Scripts for mechanical work.** Test migration (0.2), deletions (4.5, 11.1) and renames use codemods or scripted checks, then a model reviews a diff summary.
3. **Targeted tests locally, CI for the full suite.** Run the touched tests plus the golden test; subscribe to PR events and do not poll CI. The Windows `test` job is the long pole.
4. **Parallelize where files do not overlap:** 3.2-3.8, 4.4a-c, and lanes B and C. Do not parallelize inside a single module.
5. **Pattern-setting PRs go first and at higher effort** (2.2, 3.1, 4.1, 6.3a); the follow-on PRs copy the pattern at lower cost.
6. **Review where it pays:** `/code-review` at medium only on 1.2, 4.1-4.3, 6.3a, 7.1 and 10.3; skip it on mechanical PRs.
7. **Batch same-file work in one agent run** (for example 1.1 and 1.3 both edit the nav step list).
8. **Calibrate early.** The cost bands below are assumptions. Record actual spend after WP0 and WP1 and re-baseline the rest.

Planning bands (assumption, not measured): S about 0.2-0.5M tokens, M 0.5-1M, L 1-2M, XL 2-4M. On those bands the whole program, including the rental module (about 8-10M of it), is on the order of 45-50M tokens, so it cannot run in one session; run it **one WP per session** with a short handoff note.

## 6. Gates, checkpoints, rollback

- **Every WP PR:** the five CI jobs, the golden equality test, the frontend size ratchet, architecture-diagram freshness, and the static audit ratchet (no new file I/O).
- **Numbers must not move by accident.** WP1 with defaults, WP2-WP9 and WP10 leave every computed number unchanged. Switching a feature off in WP5 changes results only by design, and the pinned engine tests (1.5) record exactly how.
- **Owner checkpoints:** 2.2 (store API), 3.7 (tier tags), 4.1 (row model), 5.1 and 5.3 (screens and wording), 6.3a (spending repository), 10.3 (verification), and for rental: 12.1 (tax rules and worked examples), 12.5 (screen mockup), 12.7 (workbook layout).
- **Approval gates:** a go per WP; a copy of the live plan before WP4's first rehearsal; approval of the credential-store dependency before 8.2.
- **Rollback:** each PR is independently revertible; the converter is idempotent and writes only new files; originals are never modified.

## 7. Living status (update in the same PR as the work)

| WP | State | Last PR | Notes |
|---|---|---|---|
| WP0.1 | in review | PR #176 (single WP0 PR: 0.1 + 0.2 + 0.3 as commits) | golden baseline for sample_frozen + demo committed; `tools/golden_compare.py`, `tests/test_phase_golden_equality_regression.py` |
| WP0.2 | in review | PR #176 (same PR) | `tests/plan_fixture.py` (`make_plan`, `plan_data`, `plan_config`, `fixture_dir`); 106 tests codemodded onto it; ratchet in `tests/test_plan_fixture_helper_unit.py` |
| WP0.3 | in review | PR #176 (same PR) | `tests/test_no_data_file_io_report_regression.py` + `tests/fixtures/file_io_audit_baseline.json`; baseline 237 data-file I/O calls in 55 `src/` files (csv/json/yaml/open/Path IO), ratchet down only |
| WP1.1 | in review | draft PR (single WP1 PR, units as commits) | 23 hidden redirect steps removed from `STEPS` (ids live on in `navigation.js` redirects; `detailed_results` kept, it is a real page); catalog domains renamed to nav group names (`Investments` to `Investments & Property`, `Whole Plan` to `Reports & Review`); `Housing & Property` kept as its own topic so workbook sheet order does not move |
| WP1.2 | in review | same PR | `feature_enabled()` / `set_feature()` in `module_catalog.py` (one read path, one write path); `tier`, `nav_group`, `default_on` on every catalog entry; payload keys added to `module_taxonomy`; `/code-review` medium run, findings fixed |
| WP1.3 | in review | same PR | Estate, Insurance, Reserve Requirements, Family & Business, Scenarios, Workbench pages switchable, default on; three new rowless features (`csv_row=False`, no `client_optional_functions.csv` rows, no backfill); switch not user-writable for those three until WP4 |
| WP1.4 | in review | same PR | HSA Drawdown, Withdrawal Sequencing, Social Security, Harvesting sections on Optimize follow their module switches |
| WP1.5 | in review | same PR | one off wording ("Off · N rows entered"), engine-ignored warning, `tests/test_engine_participating_features_off_pinned_regression.py` pins each engine-participating feature off |
| WP2.1 | merged | PR #180 | `src/stores/db.py`: connect (WAL/pragmas), `transaction()`, forward-only `migrate()` on `PRAGMA user_version` |
| WP2.2 | merged (OWNER REVIEW CHECKPOINT) | PR #180 | `PlanStore`, `AppStore`, error model, `plan_paths`; API summary in PR body;owner-reviewed |
| WP2.3 | merged | PR #180 | `RefData` skeleton (read-only, content hash, plain getters, `build()` for tool/tests) |
| WP3.1 | in review | draft PR (single WP3 PR, units as commits) | `tools/build_reference_db.py` (deterministic, `--check`), slice builders in `tools/reference_slices/`, getters in `src/stores/ref_getters/`, `reference()` accessor (`src/stores/ref_access.py`), golden-getter pattern (`tests/reference_golden.py`), runbook `documentation/reference/REFERENCE_DB_SLICES.md`; `/code-review` medium run, findings fixed |
| WP3.2 | in review | same PR | tax law (`tax_law_v10.json` to `reference_src/`); `load_tax_law_dataset()` reads the getter; golden equals the old loader's dataclasses; release package allows `src/reference/reference.db` |
| WP3.3 | in review | same PR | state tax rows + overlay getter; `tax_constants.csv` fallback deleted; engine still uses `STATE_TAX_DEFAULTS` as before (the CSV overlay was never applied, and wiring it would move numbers, e.g. Colorado sales rate): owner decision |
| WP3.4 | in review | same PR | CMAs and correlations; `custom_*_file` options become override rows (`custom_capital_market_rows`, `custom_correlation_rows`); upload routes return 410 |
| WP3.5 | in review | same PR | mortality, real-loss curves (`real_loss_curve_rows` override), tax-update dashboard (governance) |
| WP3.6 | in review | same PR | security master (portfolio analytics, TLH, import preview, engine classes, drift tool) |
| WP3.7 | in review (OWNER REVIEW CHECKPOINT; tag list reported approved as is via the orchestrating session, awaiting confirmation) | same PR | field schema + `min_tier` (`reference_src/field_tiers.csv`, 469 fields: 99 simple, 169 standard, 130 advanced, 71 expert); full tag list in the PR body |
| WP3.8 | in review | same PR | ZIP metrics + top cities (5.8 MB db; golden stored as SHA-256), Monarch field map, workbook template layout; `reference_data/` is empty; data-file I/O audit 237 to 207; admin reference-file editor emptied (`SYSTEM_REFERENCE_FILES = []`), its frontend screens retire with WP9 |
| WP3 decisions | recorded (relayed from the orchestrating session, not yet confirmed by the owner directly) | PR #183 | 469-field tier list approved as is; engine stays on built-in state-tax defaults (no CSV wiring); custom CMA/correlation/real-loss files become plan-side override rows, upload routes return 410 until WP4/WP9; `/api/schema` returns JSON |
| WP4 | in progress | draft PR (single WP4 PR, units as commits) | 4.1 done (OWNER REVIEW CHECKPOINT: row-model summary in `documentation/reference/PLAN_ROWS_MODEL.md`, pasted into the PR body): plan.db schema v1 kept, no migration (no part-file column; `csv_exchange.part_file_for_section` maps a section to its old primary file); `PlanStore.find_rows` / `set_value` / `sectioned_data()` (equals `load_csv` for `sample_frozen` and `demo`, key order and `parse_client` output included); minimal importer `src/csv_exchange/` (allowlisted in the file-I/O audit, count stays 207); `make_plan` builds `plan.rpx` (`ws.plan_db`, `ws.store()`, `ws.store_data()`); switches and tier as ordinary rows (`module_catalog.feature_row_key`, `PLAN_TIER_ROW = Plan Settings / Profile / plan_tier`, internals unchanged until 4.5); step C3 in `src/legacy_conversion/steps/c3_plan_rows.py` (not wired into startup) |
| WP4.2 | done (commit on the WP4 PR) | same PR | read path on the plan file: `src/active_plan.py` (`active_plan_path()` = `<workspace>/plan.rpx` or `RETIREMENT_SYSTEM_PLAN_DB`, which the server sets for the build subprocess; WP8.4 swaps in the registry); `load_active_config` reads `PlanStore.sectioned_data()` (an empty plan is filled from the CSV set on first read); `/api/plan/forms` and the protected-field status read and write plan rows; the sectioned SQLite snapshot (`load_sqlite`, `import_csv_to_sqlite`, `local_store` snapshot readers and writers, `config_backend.load_csv`) deleted; at-rest migration sweeps the plan file's rows. Writers still edit the CSV set: `_sync_config_backends()` (called by every CSV writer, and now by Load Saved Plan, snapshot restore and the demo swap) carries the set into the plan rows (`csv_exchange.sync_plan_rows`, keeps row ids) and keeps `client_files` complete for Save As/Load. Left for 4.3: `_client_csv_rows` + `update_config_rows_payload` (grid, positional `row_index`); 4.4: `_client_section_path` / `_read_client_section_rows` / `_write_client_rows`, `_replace_*` and endpoint GETs reading CSV sections; 4.5: optional-function backfill and `set_feature` persistence. Engine input keeps plan row order (the snapshot's sorted-key round trip is gone); golden unchanged; file-I/O audit 207 to 198; details in `PLAN_ROWS_MODEL.md` |
| WP4.3 | done (commit on the WP4 PR) | same PR | grid write path on `plan_rows`: `GET /api/config/rows` serves the plan's rows with `row_index` = `row_id` (+ `revision`); `POST` writes by `row_id` in one transaction with the old normalization and schema validation (422 rolls back, unknown ids skipped); `/api/plan/forms` reads and writes the same rows (POST replaces by key keeping ids, label rules from `plan_label_rules.dropped_at_load`/`canonical_label`); `_client_csv_rows` and the positional index deleted; frontend unchanged (opaque id). Transition mechanism (one): write-back. Row-store writers edit through `active_plan.edit_active_plan` (bridge, edit, `csv_exchange.write_back_rows` of the touched keys into the CSV set via `_write_plan_data_file`, bridge again, all in one plan-file transaction); the bridge (CSV writers) reads the CSV set inside the same lock; a write-back that would not read back raises (409) instead of losing the edit. Narrowing the bridge was rejected (whole-set writers, backfill, part files shared with grid sections). Left: 4.4 strategy endpoints, `_replace_*`, `plan_data_backfill`; 4.5 optional-function backfill, `set_feature`; P3.5 whole-set writers, then the write-back and bridge. Golden unchanged; file-I/O audit 198 to 194; details in `PLAN_ROWS_MODEL.md` |
| WP4.4a | done (commit on the WP4 PR) | same PR | asset, estate, insurance and seed endpoints on `plan_rows` (`strategy_asset_service`: other asset add/delete, note receivable add/delete, 529 add, estate state options/add, trust account add, insurance policy add/delete, life illustration seed, housing and healthcare out-of-pocket seeds). Each runs `work(store)` through the context's `edit_plan` (`app_core._edit_active_plan`: one rows transaction, touched keys written back to the CSV set), finds its next number and rows by section/subsection/label instead of scanning a part file, and answers 409 when the CSV set cannot take the edit. Responses unchanged; `_seed_rows` no longer takes a file name. New rows go at the end of their section, estate rows before the Gifting rows as before; `csv_exchange.write_back_rows` now writes a mid-section insert in place (it used to refuse it). Differences from the CSV code (same engine data, tested): a new row's `notes` no longer pick up a comment line that sat above the next section; the 529 and note numbers see the whole section, not one part file. Pre-existing quirk kept: 529 numbering takes the first digit run, so the next plan is `529 Plan 530`. Left: 4.4b/c (`_replace_*`, withdrawal order, tax assumptions, residency, home sale splits, GET readers, `_client_section_path`/`_read_client_section_rows`/`_write_client_rows`), 4.5. Golden unchanged; file-I/O audit unchanged (194; the helpers these endpoints used die with 4.4c) |
| WP4.4b | done (commit on the WP4 PR) | same PR | Roth, strategy and policy endpoints on `plan_rows` (`strategy_asset_service`): withdrawal account order, large discretionary expenses, forced Roth conversions, tax assumptions (read and save), residency schedule, and the spending adjustments endpoint (moved out of `plan_routes` into the service). GETs read through the context's new `read_plan` (`app_core._read_active_plan`: the bridge, then the open store); saves run `work(store)` through `edit_plan` as in 4.4a. One helper, `_replace_block`, replaces a block by key: a key the plan already holds keeps its row and `row_id` and only its value changes (the write-back writes a changed value cell only, so units and notes of an existing row stay), rows no longer wanted are deleted, new keys are inserted after the block's last row (a new block: end of the section, or after the `Post-House-Sale Rent` rows for large discretionary). Responses, validation and audit events unchanged. Roth guard: `roth_ui_build_guard.canonicalize_roth_rows(store)` makes Roth controls canonical in the rows, run by `edit_active_plan` after every row edit; `canonicalize_roth_csv_content` stays only for the CSV file writer and goes with the CSV set in 4.5. Differences from the CSV code (same engine data, tested): an existing forced Roth conversion row keeps its notes (the account list in them is current only for new rows); the large discretionary GET/POST now read and write one place (the old code wrote the part file that held the first `Cashflow` rows and read `client_spending.csv`, so a plan whose `Cashflow` starts in `client_income.csv` read back its old events). Left for 4.4c: `app_core` `_replace_large_discretionary_expenses`, `_replace_forced_roth_conversions`, `_replace_residency_schedule` and their `_*_from_csv_rows` / row builders are now unused (delete with the other `_replace_*`); liquidity buffers, home sale splits, allocation, housing, backfill. Golden unchanged; file-I/O audit unchanged (194) |
| WP4.4c | done (commit on the WP4 PR) | same PR | liquidity buffers and home sale splits on `plan_rows`; `plan_data_backfill` and `_ensure_user_ui_plan_data_rows` on `plan_rows` (one edit transaction, only when rows are missing); the five `app_core._replace_*` helpers, their CSV readers/row builders and `_client_section_path`/`_read_client_section_rows`/`_write_client_rows` deleted; file-I/O audit 194 to 182. No strategy endpoint reads or writes a part file now. |
| WP5 - WP12c | not started | none | planning only |
