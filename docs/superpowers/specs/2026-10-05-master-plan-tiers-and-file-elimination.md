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

```
WP0 safety net ─┬─► WP1 features & nav ─► WP12a rental engine (no storage) ─┐ (lane B)
                └─► WP2 stores ─► WP3 reference.db ─► WP4 plan rows ─┬─► WP5 tiers UI ┤
                                          │                          ├─► WP6 datasets ─► WP7 build I/O ─► WP12b rental data/UI/workbook/housing
                                          │                          │                          └─► WP9 csv_exchange ─► WP12c rental CSV ─► WP10 conversion ─► WP11 cleanup
                                          └─► WP8 app state (after WP2, parallel lane) ┘
```

| WP | Contents (source) | PRs | Depends on | Lane |
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

| PR | Scope | Model | Effort | Approach |
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

Count: 18 PRs are Opus-class (the five xhigh ones — 2.2, 4.1, 6.3a, 10.3 and 12.1 — may use Fable 5.1), 44 are Sonnet, and 4 are Haiku; 66 PRs in total.

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

- **Every PR:** the five CI jobs, the golden equality test, the frontend size ratchet, architecture-diagram freshness, and the static audit ratchet (no new file I/O).
- **Numbers must not move by accident.** WP1 with defaults, WP2-WP9 and WP10 leave every computed number unchanged. Switching a feature off in WP5 changes results only by design, and the pinned engine tests (1.5) record exactly how.
- **Owner checkpoints:** 2.2 (store API), 3.7 (tier tags), 4.1 (row model), 5.1 and 5.3 (screens and wording), 6.3a (spending repository), 10.3 (verification), and for rental: 12.1 (tax rules and worked examples), 12.5 (screen mockup), 12.7 (workbook layout).
- **Approval gates:** a go per WP; a copy of the live plan before WP4's first rehearsal; approval of the credential-store dependency before 8.2.
- **Rollback:** each PR is independently revertible; the converter is idempotent and writes only new files; originals are never modified.

## 7. Living status (update in the same PR as the work)

| WP | State | Last PR | Notes |
|---|---|---|---|
| WP0 (WP0.1) | WP0.1 in review | draft PR on `claude/wp0-1-golden-harness` | golden baseline for sample_frozen + demo committed; `tools/golden_compare.py`, `tests/test_phase_golden_equality_regression.py` |
| WP0.2 | in review | draft PR on `claude/wp0-2-fixture-helper` (stacked on WP0.1) | `tests/plan_fixture.py` (`make_plan`, `plan_data`, `plan_config`, `fixture_dir`); 106 tests codemodded onto it; ratchet in `tests/test_plan_fixture_helper_unit.py` |
| WP0.3 | in review | draft PR on `claude/wp0-3-static-audit` (stacked on WP0.2) | `tests/test_no_data_file_io_report_regression.py` + `tests/fixtures/file_io_audit_baseline.json`; baseline 237 data-file I/O calls in 55 `src/` files (csv/json/yaml/open/Path IO), ratchet down only |
| WP1 - WP11 | not started | none | planning only |
