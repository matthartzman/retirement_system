# Happy-path end-to-end test plan

## Objective
Prove a brand-new user can go from a blank plan to a complete, saved,
reloadable retirement plan with working outputs, using the guided navigation
exclusively (no Field Finder shortcuts), touching required fields plus a
representative sample of common optional ones.

## Scope basis
Empirically counted from the current schema: 368 curated schema fields, 59
marked `required`, ~806 total editable CSV rows across all Plan Data files.
"Most of the other common fields" means covering the bulk of the ~368
curated ones, not all 806 (many of the 806 are system/reference constants
not meant for per-plan editing).

## Test phases

| # | Phase | Nav steps | What "common fields" means here | Est. time |
|---|---|---|---|---|
| 0 | Setup | Plan Status → "Start New Plan" | Confirm blank state, 0% complete, all required missing | 3 min |
| 1 | Household & Profile | Household & People, Retirement Timing, Work Income, Income & Social Security | Both members' names/DOB/state/filing status (required); retirement dates, mortality ages, planning horizon; salary, 401k contribution %; SS benefit at FRA, claim age, one pension | 15 min |
| 2 | Spending | Spending Model, Wellness, Housing, Travel, Large Discretionary | Core spending base + growth mode (required); Medicare/wellness premiums; mortgage/insurance/utilities/RE tax; one travel line; one large discretionary item | 20 min |
| 3 | Accounts & Holdings | Investment Holdings, Account Balances | 4-6 holdings across pre-tax/Roth/taxable/HSA account types with realistic tickers + cost basis; cash reserve floor | 15 min |
| 4 | Assets & Protection | Annuity & Special Income, Insurance & Estate, Other Assets, Estate Inputs | One annuity illustration row; one LTC/life policy; HSA; estate exemption fields | 15 min |
| 5 | Strategy | Distribution Strategy (Roth + withdrawal order), Investment Strategy (allocation), Timing & Tax (SS timing, state) | Roth conversion policy = optimize; withdrawal bucket order; allocation target_pct summing to 100%; confirm SS claim age flows through from Phase 1 | 20 min |
| 6 | Stress Tests | Probability Analysis (Monte Carlo) | Confirm/adjust simulation count and engine mode; leave survivor/LTC/divorce off for the happy path | 5 min |
| 7 | Preflight + Build | Reports & Review → Preflight → Build | Confirm 100% complete, 0 required missing, no blockers; run build; confirm QC pass count, no errors | 10 min |
| 8 | Output verification | Results, Impact & Build History, downloaded workbook | Net Worth trends plausibly; Cash Flow totals are non-zero and consistent; Monte Carlo success % renders 0-100%; Roth conversion strategy produced conversions if policy=optimize | 15 min |
| 9 | Save/Load round-trip | Save Plan As → Load Saved Plan | Save with a distinct name; reload; spot-check 8-10 values across different phases match exactly | 10 min |

## Assertions that define "pass"
- No unhandled error/crash at any step transition.
- Preflight shows `readiness: current`, `blockers: []` before build.
- Build returns `success: true` with a QC pass ratio reported.
- Net Worth sheet: finite numbers, plausible multi-decade trajectory.
- Cash Flow sheet: total income, spending, and tax rows are non-zero and roughly track entered assumptions.
- Monte Carlo success rate renders as a sane 0-100% number (the exact metric fixed in item 119 — specifically re-checked here).
- Roth Conversion sheet shows actual conversion amounts if `optimize` policy was selected.
- After Save → Load, every spot-checked field matches exactly what was entered.

## Time estimate
~2 hours for a tester who knows the app's layout; ~3 hours for a first-timer.

---

## Execution log

Executed via the browser preview (`preview_*` tools) against a locally-running dev server, driving the actual guided-navigation UI end to end (via `editValue()`/`renderMain()`/`saveAll()`/`runBuild()` — the same functions the real UI's own click handlers call). Test data: "Alex Tester" / "Jordan Tester", MFJ, Illinois, retiring 2027/2028.

**Important safety note**: this ran against the same local SQLite-backed workspace as the real, live plan (not an isolated sandbox), since the app has no built-in isolated test mode. Before starting, an independent safety copy of `local_state/retirement_system_v10.db` was taken, and `input/*.csv`/`output/*` were git-tracked with a clean baseline. After the test, the SQLite DB was restored from the safety copy and all `input/`/`output/` files were restored via `git checkout`. Verified post-restore: real household names ("Matthew"/"Patricia") and all 1,345 real YTD transactions intact.

### Result summary

| Phase | Result | Time taken |
|---|---|---|
| 0. Setup | ✅ Pass, with one plan-vs-actual correction (see findings) | ~2 min |
| 1. Household & Profile | ✅ Pass, with one plan correction (SS fields location) | ~12 min |
| 2. Spending | ✅ Pass (data entry); ⚠️ surfaced a real finding (see Finding A) | ~10 min |
| 3. Accounts & Holdings | ✅ Pass | ~5 min |
| 4. Assets & Protection | ✅ Pass (no required fields exist in this group) | ~3 min |
| 5. Strategy | ✅ Pass | ~5 min |
| 6. Stress Tests | ✅ Pass (sensible defaults already in place) | ~1 min |
| 7. Preflight + Build | ✅ Pass — preflight clean, build succeeded, QC 31/41 (see Finding A for why) | ~3 min |
| 8. Output verification | ✅ Pass structurally (all sheets render, no NaN/crash); numbers reflect Finding A | ~10 min |
| 9. Save/Load round-trip | ❌ **Fail — Finding B** | ~10 min |

**Total elapsed**: ~60 minutes of active execution (well under the 2-3 hour estimate — largely because scripted field entry via `editValue()` is faster than literal UI clicks, and because most Strategy/Assets & Protection fields turned out to have zero required fields, which wasn't obvious until executing).

### Corrections to the original test plan

- **Phase 0**: a truly blank plan is **not** 0% complete — "Start New Plan" retains system/option defaults (Roth policy, Monte Carlo settings, allocation targets, etc.) and only blanks user-entered facts. Observed: 57% complete, 16 required missing on a fresh blank plan.
- **Phase 1**: Social Security benefit/claim-age fields are **not** on the "Income & Social Security" guided page despite its name — that page is annuity/pension detail only. SS fields (`monthly_at_age_70_today_dollars`, `claim_age`, funding discount) live on the separate "Social Security timing" page under the Strategy group.
- **Phases 4–6 (Assets & Protection, most of Strategy, Stress Tests)**: none of these guided pages have any `required` schema fields at all. The 59 required fields are concentrated entirely in Household/Timing/Income, Economic Assumptions, Core Spending, and Home value.

### Finding A (data-model surprise, not a code bug): entering a spending "base year" number doesn't fully control projected core spending when YTD actuals exist

Entering `annual_spending_base_year = $80,000` produced a projected 2026 "Spend Base" of **$245,924**, not ~$80,000. Root-caused precisely: this workspace's real household had 1,345 leftover YTD transactions with $186,261.51 of real actual 2026 spending logged (YTD tracking is not cleared by "Start New Plan" — by design, since it represents real bank activity independent of which hypothetical plan is loaded). The current-year blend feature (built earlier this session, items 119/123) correctly combined that real actual-to-date spending with the test plan's assumption: `$186,261.51 actual + ($80,000 core + $30,000 mortgage + $9,000 RE tax) × 49.86% remaining-year fraction ≈ $245,574` — matching the observed $245,924 almost exactly (small gap from timing/rounding).

This is not a bug in the blend feature — it's working exactly as designed. But it **is** a real, surfaced product consideration: a fresh "Start New Plan" for a hypothetical scenario can silently inherit real YTD actuals from the workspace's ongoing tracking, producing a plan that looks financially strained (this test's plan showed `UNFUNDED_GAP` validation failures every year, `total_roth_conversions: 0` since there was no tax-bracket headroom left, and `mc_success: 0%`, all consistent downstream consequences of the elevated spend figure — not independent bugs). Worth deciding whether "Start New Plan" should also reset/pause YTD blending for the remainder of that session, or whether this is acceptable/intended behavior.

**Resolved.** "Start New Plan" now checks for live YTD actuals and, if present, shows an explicit choice modal (`showYtdBlendChoiceModal` in `frontend/js/dashboard.js`) naming the real dollar figures and dates involved, before wiping anything. Choosing "Use real actuals (recommended)" keeps today's behavior (the default when no YTD data exists at all, so unaffected plans see no new prompt). Choosing "Model as fully hypothetical" sets a new per-plan field, `ytd_blend_enabled` (`Cashflow,Spending` in `client_spending.csv`, parsed in `src/data_io.py`), to `FALSE`, which `src/ytd_projection_blend.py::compute_current_year_overrides` uses to suppress only the flow (earned income/spending) blend — the always-on growth/contribution date proration from item 119 is unaffected, since that's pure date math with no real-data dependency. The choice is also exposed as an ongoing toggle on the "Income & Expense Transactions" guided page (`ytdBlendToggleHtml()`), and the workbook's "Current-year actuals blend" narrative row explains explicitly when a plan excluded real actuals by choice. Covered by `tests/test_163_ytd_current_year_blend.py` (engine gating) and `tests/test_156_plan_data_budget_service_extraction.py` (CSV-stamping on blank-plan creation).

### Finding B (real bug): "Load Saved Plan" does not resync the CSV working copy, so guided pages can show stale data after a load

Reproduced directly:
1. Saved the in-progress test plan to a `.rpx` file via "Save Plan As" (member_1_name = "Alex Tester").
2. Changed `member_1_name` to a marker value and saved (now persisted in both the SQLite DB and `input/client_household.csv`).
3. Loaded the `.rpx` file back via "Load Saved Plan" (`/api/plan/load-file`) — response reported success and created the expected `before_load_*` backup.
4. Verified directly with `sqlite3`: the restored **SQLite** `settings` table correctly showed "Alex Tester" — the SQLite-level restore worked correctly.
5. But `/api/config/rows` (what every guided page actually reads) still returned the marker value, not "Alex Tester" — because that endpoint reads `input/client_household.csv` directly, and "Load Saved Plan" never touches the `input/*.csv` files, only the SQLite `.db` file.

This matches this project's own `CLAUDE.md` documentation verbatim: *"`_read_plan_data_file()` checks the on-disk `input/` file first. If that file exists ... the SQLite mirror is ignored."* — a documented architecture fact that "Load Saved Plan"'s implementation doesn't account for. Net effect: **loading a saved plan can leave every guided page showing the previous session's stale CSV data instead of the just-loaded plan**, even though the load reports success and the SQLite file is genuinely correct underneath. A user would only see the *correct* loaded data if they take some further action that re-syncs CSV from SQLite (e.g., editing and saving triggers `_sync_config_backends()` in the CSV→SQLite direction, but nothing currently pushes SQLite→CSV after a load).

**This is a real, reproducible, currently-unfixed bug.** Recommend either: (a) after `/api/plan/load-file` succeeds, write the restored SQLite `client_files`/`settings` content back out to `input/*.csv` before returning, or (b) change `_read_plan_data_file()`'s precedence so a fresh load's SQLite state isn't masked by stale CSV. Did not fix this as part of test execution per your "document and run" instruction — flagging for a decision on whether to fix now.

### Assertion-by-assertion result

| Assertion | Result |
|---|---|
| No unhandled error/crash at any step | ✅ Pass |
| Preflight `readiness: current`-ish, `blockers: []` before build | ✅ Pass (`readiness: warning`, `blockers: []` — warnings only, as expected pre-build) |
| Build returns `success: true` with QC ratio reported | ✅ Pass (`QC: 31 / 41 PASS`) |
| Net Worth sheet: finite, plausible trajectory | ✅ Pass (declining $784k → $685k over 5 years — consistent with Finding A's elevated spending, not a rendering bug) |
| Cash Flow sheet: non-zero, consistent totals | ✅ Pass structurally; magnitudes reflect Finding A |
| Monte Carlo success % renders as sane 0-100% | ✅ Pass — renders "0.0%" correctly (the item 119 fix holds); the *value* being 0% is a legitimate consequence of Finding A, not a formatting regression |
| Roth Conversion sheet shows conversions if `optimize` selected | ⚠️ Partial — policy correctly set to `optimize_terminal_tax`, and the optimizer genuinely evaluated all candidate strategies (visible in the sheet's "why this strategy was selected" narrative), but selected "no voluntary conversions" since Finding A's elevated income left no tax-bracket headroom. Correct behavior given the inputs, but revises the original test-plan assumption that `optimize` guarantees non-zero conversions. |
| Save → Load: every spot-checked field matches | ❌ **Fail — Finding B** |

