# Feature tiers and unified switches — design

> **Sequencing and staffing are superseded by [`2026-10-05-master-plan-tiers-and-file-elimination.md`](2026-10-05-master-plan-tiers-and-file-elimination.md).** This document remains the authority for the design detail it covers; the master plan decides order, merged phases, models and effort.


Status: approved by the owner on 2026-10-04 (decisions 1-11 below). Ready for implementation planning, phase by phase.
Baseline: `documentation/reference/NAV_FEATURE_MAP.md` (25 nav pages, 21 always on, 4 switchable).

## 1. Goals

1. **Consistency.** One definition of a feature and one meaning of "off".
2. **Usability.** A new household sees about 8 pages, not 25, and grows into the rest.
3. **Maximum flexibility.** The always-on set shrinks to the minimum the projection cannot run without; everything else is a switch the user can flip.

## 2. Confirmed decisions

| # | Decision |
|---|---|
| 1 | Four tiers: **Simple, Standard, Advanced, Expert**. A tier is a starting set of switches. |
| 2 | Every feature switch stays individually overridable; the plan then reads "Advanced (customized)". |
| 3 | A tier also controls field detail: each field carries a minimum tier, and higher-tier fields sit behind "Show advanced". |
| 4 | Minimal always-on core: Household, Income, Spending, Holdings and Assets, Assumptions, Build & Results, Settings. |
| 5 | Left nav keeps life-area groups. Plan Features and the workbook adopt the same group vocabulary (see 7). |
| 6 | Existing plans are mapped to a tier and the rest is switched off, subject to the safeguard in section 6. |
| 7 | Switching off a feature the engine reads means the projection ignores it, with a visible warning. Data is kept. |
| 8 | Field tiers are a `min_tier` column in the field catalog (`reference_data/schema.csv`). |
| 9 | Migration safeguard (section 6) accepted as written. |
| 10 | The workbook keeps its five answer-type sections; only the vocabulary and within-section order align with the nav (section 5). |
| 11 | Tier membership (section 4) accepted as proposed. |

## 3. The model

**Feature** = one switch that governs all four of: nav entry (page or section), input rows, engine participation, workbook sheet. No feature has a sheet-only or nav-only switch.

Off semantics (uniform):
- hidden from nav and sections; no workbook sheet;
- entered data is kept and listed on Plan Features as "Off · N rows entered";
- if the feature participates in the engine, the projection ignores it and the switch states the effect.

**Profile** = `tier` plus a set of per-feature overrides. Stored once in the plan data (travels with the household). Resolved by a single accessor, `feature_enabled(c, key)`, replacing the three read paths today (module toggle row, plan flag, `gated_by` bundle).

**Field tier** = `min_tier` on each field. A page shows fields at or below the plan's tier; a "Show advanced" control reveals the rest for that page. Required fields are never hidden.

## 4. Tier assignments (approved)

| Tier | Adds (cumulative) |
|---|---|
| **Simple** (~8 pages) | Core pages; Roth Conversion; Monte Carlo; Lifetime Taxes; Charts |
| **Standard** | Estate; Insurance (existing life, disability); Reserve Requirements; Social Security timing; Asset Allocation; Survivor stress; Education 529; Hybrid LTC |
| **Advanced** | Charitable Giving (DAF, QCD); Withdrawal Sequencing; Asset Location; Harvesting (loss, gain); State Residency; Scenarios; Actual Spending / YTD; LTC stress; Next Housing Move; Housing Comparison; HSA Drawdown; Tax Capacity; HELOC; Rental Properties |
| **Expert** | Workbench; Equity Compensation; Business Succession; S-Corp vs LLC; Special-Needs; Divorce/QDRO; P&C Umbrella; RMD audit; Account Reconciliation |

Reference sheets (Plan Data, Assumptions, Quality Control, Methodology, Glossary) follow the core and are always built.

## 5. Taxonomy alignment (approved)

Today the nav has 12 groups, the workbook has 5 answer-type sections (Reports, Optimizers, Comparisons, Risks, Reference), and the catalog has 9 domains. Proposal:
- The 5 workbook sections stay as they are (they were just reordered and answer a different question: what kind of result).
- The catalog **domains are renamed to the nav group names** and share one order, so Plan Features, the nav, and the within-section sheet order read the same.
- A feature carries one `nav_group`; the workbook orders sheets within a section by it.

## 6. Migration for existing plans

Rule from decision 6: map the plan to the smallest tier that contains its current features and switch off the rest.

**Safeguard (approved).** Because "off" now means ignored, switching off an engine-participating feature that holds data would change results. So the migration:
1. never switches off a feature that participates in the engine and has entered data (it stays on and the plan shows as customized);
2. runs the projection before and after, and shows the difference on first open; any non-zero difference blocks automatic migration and asks the user.

## 7. Implementation phases

| Phase | Work | Main files |
|---|---|---|
| P1 | Unified registry and `feature_enabled()`; fold `dashboard_step`, `csv_sections`, `gate_kind`, `gated_by`, `gated_by_any_flag` into one declaration; add `tier` and `nav_group` | `src/module_catalog.py`, `src/server_services/config_service.py`, `frontend/js/dashboard_decomp_row_model.js` |
| P2 | Shrink the core: make Estate, Insurance, Reserve Requirements, Family & Business, Scenarios, Workbench switchable; backfill rows | `module_catalog.py`, `frontend/js/dashboard.js` (STEPS), `input/demo/client_optional_functions.csv` |
| P3 | Sheet-only toggles gate their input sections (HSA, Withdrawal Sequencing, Social Security, Harvesting) | `dashboard_decomp_strategy_workspace.js` |
| P4 | Profiles: tier row in plan data, tier picker and "(customized)" on Plan Features, off-state "N rows entered" everywhere | `dashboard_decomp_plan_features.js`, `data_io.py` |
| P5 | Field tiers: `min_tier` column, filter in row model, "Show advanced" | `reference_data/schema.csv`, `dashboard_decomp_row_model.js` |
| P6 | Interview and self-suggest ("Turn on HELOC?" when HELOC data is entered) | new frontend module |
| P7 | Taxonomy alignment (section 5), retire the ~24 hidden redirect steps | `module_catalog.py`, `navigation.js` |
| P8 | Migration with the section 6 safeguard | `src/server_services/`, new tool |

Each phase ships on its own and keeps all gates green (frontend size ratchet, full-row snapshot, nav map doc regenerated).

## 8. Risks

- **Silent result changes** from migration (mitigated in section 6).
- **Engine-participating features** (equity compensation, disability income, business succession, Social Security timing, Next Housing Move): "off means ignored" must be covered by tests that pin projections with each off.
- **Frontend size ratchet:** P1/P4/P5 add code; budget the ceiling raise per phase.
- **Test churn:** many tests pin nav ids and switch keys; P1 should keep old ids as aliases until P7.

## 9. Still open

None. Implementation starts at P1; each phase gets its own plan and PR.
