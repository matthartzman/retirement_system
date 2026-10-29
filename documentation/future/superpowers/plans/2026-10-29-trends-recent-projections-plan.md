# Recent Projections Implementation Plan

Status: implemented (2026-10-29, branch `recent-projections`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third Financial Trends view, "Recent Projections", that shows the next N years (default 5) of the workbook's Net Worth and Cash Flow tables. Groups start collapsed and the Year column is frozen.

**Architecture:** The workbook build emits `projection_tables.json` beside `retirement_plan.xlsx`, extracting it from the worksheets `build_sheet5/6` just wrote, so it can't drift from them. The reporter finds that file through the active plan's latest build snapshot and serves it at `/api/projections`, where the existing percent-view `after_request` scaling covers remote percent-only viewers. A pure JS module turns columns into a collapsible group tree, and a view module renders it.

**Tech Stack:** Python 3.12 / openpyxl / Flask (reporter); vanilla ES modules; pytest; `node --test`.

**Spec:** `documentation/future/superpowers/plans/2026-10-29-trends-recent-projections-design.md`

**Usage note:** each task lists a recommended model, an effort level and a relative usage estimate (against a 5-hour Pro session). Check `/usage` after each task against these estimates.

## Global Constraints

- The file name is `projection_tables.json` and its schema string is `"projection_tables/1"`.
- The window starts at the current calendar year. The year count is 1–30, default 5.
- Collapsed NW is exactly: Year, Investable, Annuities & Pension, Home & Other, Total NW, Δ vs prior.
- Collapsed CF is exactly: Year, Income, Taxes, Spending, Cash Need, Portfolio Draws, Roth Conv, Net Worth.
- The build line reads `Workbook built <Mon D, YYYY h:mm AM/PM> · <N> days ago`. It is amber when it is over 30 days old or `plan_mtime > built_at`.
- The empty state text is: `Recent Projections appear after the plan is rebuilt. Rebuild in the Retirement Planner, then refresh.`
- % means a percent of today's net worth, and the existing `money_view.js` `fmtAmount` is reused. Remote percent-only viewers must never receive dollars.
- localStorage keys: `trends.proj.table`, `trends.proj.years`, `trends.proj.open.nw`, `trends.proj.open.cf`. Every access is wrapped in try/catch.
- An opened group keeps its subtotal column first, with the detail to its right.
- Large-file rule (CLAUDE.md): enter `src/reporting/workbook_builder.py` by Grep only.
- After adding `src/reporting/projection_tables.py`, run `python tools/generate_system_diagram.py` and commit the diagram.

## Review Focus

1. **A plan with Rental Properties on** (Rental Equity, Rental, Rental_Tax) or with LTC/rent columns present: every key lands in a group and NW still reconciles. Tests: Task 1 (`test_conditional_columns_emitted`) and Task 3 (`unknown key falls back to banner group`, `rental keys mapped`).
2. **A window past the plan's last year**, or a plan whose first year is after today: show the rows that exist plus the "The plan ends in YYYY" note, and never show an empty table. Test: Task 3 (`windowRows clamps to plan years`).
3. **A remote percent-only viewer**: `/api/projections` contains no dollar figure, and year, ages and timestamps are left unscaled. Test: Task 2 (`test_percent_viewer_gets_no_dollars`).
4. **A year-count field that is blank, 0, 99, or "abc"**: clamp it to 1–30, using 5 when blank or not a number. Test: Task 3 (`clampYears`).
5. **localStorage throwing** (private mode) or holding a stale open-group key that no longer exists: the page renders collapsed and doesn't throw. Test: Task 4 (`storage failure renders collapsed`).

---

### Task 1: Build emits `projection_tables.json`

Model: Sonnet 5.5, effort medium. Usage: **moderate**. Context is driven by the two sheet builders (352 + 514 lines, readable) and grep-only entry into `workbook_builder.py`, plus one or two fixture build test loops. Scope it down by reusing the existing fixture from `tests/test_projection_sheet_module_extraction_regression.py` instead of a full build.

**Files:**
- Create: `src/reporting/projection_tables.py`
- Modify: `src/reporting/sheets_projection_net_worth.py` (`build_sheet5` returns `COLS`), `src/reporting/sheets_projection_cashflow.py` (`build_sheet6` returns `COL`), `src/reporting/workbook_builder.py` (around the `build_sheet5/6` calls ~1103 and before `build_build_snapshot`, so the file appears in the snapshot's artifacts)
- Test: `tests/test_projection_tables_emit_unit.py`
- Regenerate: `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md`

**Interfaces:**
- Produces: `table_from_sheet(ws, col_map: dict[str, int], *, data_first_row: int = 3) -> dict` returning `{"columns": [{"key", "label", "banner", "subtotal": bool}], "rows": [{"year": int, "ages": [int, int], "values": {key: float | None}}]}`. Rows stop at the first row whose column A is not an int year, so TOTAL and Lifetime rows are excluded. `banner` is the merged row-1 header covering the column. `subtotal` is true for keys starting with `Σ` or in `{"TOTAL NW", "Total_Tax", "Total_Cash_Need", "NW_Check"}`. The age keys (`H Age`/`W Age`, `H_Age`/`W_Age`) go into `ages` and not into `columns`.
- Produces: `projection_tables_doc(nw: dict, cf: dict, *, build_id: str, built_at: str, owners: list[str]) -> dict` returning the shape in spec §3, with `"schema": "projection_tables/1"`.
- Produces: `write_projection_tables(out_dir: str | Path, doc: dict) -> Path`, an atomic write (temp file in the same folder, then `os.replace`) that returns the final path.

- [ ] **Step 1: Write the failing tests**

```python
def test_values_match_sheet_cells(nw_cf_sheets):          # fixture: c, rows -> built ws + returned col maps
    ws, cols = nw_cf_sheets["nw"]
    t = table_from_sheet(ws, cols)
    for i, row in enumerate(t["rows"]):
        for key, v in row["values"].items():
            assert v == ws.cell(3 + i, cols[key]).value

def test_keys_carry_no_owner_names(nw_cf_sheets):
    for name in ("nw", "cf"):
        ws, cols = nw_cf_sheets[name]
        keys = [c["key"] for c in table_from_sheet(ws, cols)["columns"]]
        assert not any(n in k for k in keys for n in ("Matt", "Pat"))   # fixture nicknames

def test_totals_rows_excluded_and_ages_split(nw_cf_sheets): ...      # last row year is an int; "ages" len 2; no Age key in columns
def test_conditional_columns_emitted(rental_on_sheets): ...         # "Rental Equity", "Rental", "Rental_Tax" present
def test_write_is_atomic_and_round_trips(tmp_path): ...             # json.loads(path.read_text()) == doc; no *.tmp left
```

- [ ] **Step 2: Run them and confirm they fail.** `pytest tests/test_projection_tables_emit_unit.py -v -rfE > <scratchpad>/pytest_t1.txt 2>&1`. Expected: an ImportError on `src.reporting.projection_tables`.
- [ ] **Step 3: Implement** `projection_tables.py`, make `build_sheet5/6` return their column maps (existing callers ignore the return value), and in `workbook_builder.py` call `write_projection_tables(output_path_dir, projection_tables_doc(...))`. Use `built_at` = the same UTC ISO timestamp the snapshot uses, and `owners` = `[c h_nick|h_name, c w_nick|w_name]`. Wrap the call so a failure prints a warning and never fails the build.
- [ ] **Step 4: Run the tests and confirm they pass.** Same command, then also `pytest tests/test_projection_sheet_module_extraction_regression.py -v -rfE`. Expected: all PASS.
- [ ] **Step 5: Regenerate the diagram.** Run `python tools/generate_system_diagram.py`, then `pytest tests/test_system_architecture_diagram_freshness_regression.py -v`. Expected: PASS.
- [ ] **Step 6: Commit** with `feat(build): emit projection_tables.json for Recent Projections`.

### Task 2: Reporter `/api/projections`

Model: Sonnet 5.5, effort medium. Usage: **light**. `main.py` (476 lines) and `percent_view.py` (161 lines) are small, and there are no full-suite runs.

**Files:**
- Create: `financial_trends_reporter/projections.py`
- Modify: `financial_trends_reporter/main.py` (route, plus static routes for the two new JS files, following the `/live_snapshot.js` pattern), `financial_trends_reporter/percent_view.py` (add `"ages"`, `"plan_mtime"`, `"built_at"`, `"plan_first_year"`, `"plan_last_year"` to `NON_MONEY_KEYS`, each with a comment)
- Test: `tests/test_trends_projections_unit.py`

**Interfaces:**
- Consumes: Task 1's file and schema.
- Produces: `locate(retirement_system_dir: Path) -> Path | None`. It calls `read_build_results(path=plan_path_for_workspace(dir))`, takes the `snapshot` artifact whose `file == "retirement_plan.xlsx"`, and returns `Path(path).parent / "projection_tables.json"` if that exists, else None.
- Produces: `load(retirement_system_dir: Path) -> dict`, cached by the `(path, mtime_ns)` of the located file. It returns the doc plus `plan_mtime` (epoch seconds of `plan_path_for_workspace(dir)`), `plan_first_year` and `plan_last_year`. It returns `{"missing": True}` when the file is not located or its schema is not `projection_tables/1`.
- Produces: `GET /api/projections` returning `_json(projections.load(retirement_system_dir))`, or a 500 with an `error` string on an exception (the live-snapshot pattern).

- [ ] **Step 1: Write the failing tests:** `test_missing_when_no_build_results`, `test_missing_when_schema_unknown`, `test_locates_via_snapshot_artifact` (in tmp_path, write a plan file with a build_results snapshot whose artifact path points into tmp_path), `test_cache_reloads_on_mtime_change`, and `test_percent_viewer_gets_no_dollars`. The last one runs `percent_view.scale_payload(load(...), 5_000_000)`, then asserts `find_money_leaks(...) == []`, that `rows[0]["year"]` is unchanged, and that `ages` are unchanged.
- [ ] **Step 2: Run them and confirm they fail.** `pytest tests/test_trends_projections_unit.py -v -rfE > <scratchpad>/pytest_t2.txt 2>&1`. Expected: an ImportError.
- [ ] **Step 3: Implement** `projections.py`, the route, the static JS routes and the `NON_MONEY_KEYS` additions.
- [ ] **Step 4: Run the tests and confirm they pass,** plus `pytest tests/test_trends_access_gate_functional.py -v -rfE`. Expected: PASS. Also run `pytest -k "percent_view" -v -rfE`. Expected: PASS (the new non-money keys don't break existing leak tests).
- [ ] **Step 5: Commit** with `feat(trends): /api/projections serves the build's projection tables`.

### Task 3: Group model (pure JS)

Model: Opus 5.5, effort high. This holds the grouping semantics and reconciliation, and a mistake here produces wrong numbers. Usage: **moderate**: one new ~250-line module and a test file, with a fast `node --test` loop.

**Files:**
- Create: `financial_trends_reporter/frontend/projection_groups.js`
- Test: `tests/frontend/trends_reporter_projections.test.mjs`

**Interfaces:**
- Consumes: the `tables.net_worth` / `tables.cash_flow` shapes from Task 1.
- Produces `GROUPS = { nw: [...], cf: [...] }`. Each node is `{id, label, subtotal: key | (row) => number, children: [node | key], context?: key[]}`. The mapping is exactly spec §4.1 / §4.2, using these builder keys:
  - NW: `Investable` = computed `Σ PreTax + Σ Roth + Σ Trust + HSA_1 + Cash`, with children `PreTax` (`PreTax_*`, subtotal `Σ PreTax`), `Roth` (`Roth_*`, `Σ Roth`), `Trusts` (`Trust_*`, `Σ Trust`), `HSA_1` and `Cash`. `Annuities & Pension` = `Σ Ann` (`Pension PV`, `W/H Single/Joint PV`). `Home & Other` = computed `Σ Other − Cash` (`Home Equity`, `Next Housing Equity`, `Rental Equity`, `Startup`, `Autos`, `Note`). Then `TOTAL NW`, and `Δ` = computed from the previous plan year's `TOTAL NW` (null for the first plan year).
  - CF: `Income`=`Σ_Inc` (`Earned, H_SS, W_SS, Pension, W_Sgl, W_Jnt, H_Sgl, H_Jnt, Note, RMD, Rental`). `Taxes`=`Total_Tax` (`Fed, State, NIIT, IRMAA, Payroll, LTCG, Rental_Tax`; context `AGI, Taxable`). `Spending`=`Σ_Spend` (`Spend_Base`, `Housing`▸[`Mort_PI, Prop_Tax, Housing_Utilities, Home_Imp, Housing_Maintenance, Housing_Other, Rent_Det`], `Wellness`▸[`Wellness_Premiums, Wellness_Medical, Wellness_Dental, Wellness_Vision, Wellness_Rx_Otc, Wellness_Other, HC_LTC`], `Travel, Other, Business_Exp, HELOC_PAI`). `Cash Need`=`Total_Cash_Need` (`Other_Cash_Need, Income_Funding, Other_Funding, Cash_Bridge_Gap, HELOC_Draw`; context `HELOC_Bal`). `Portfolio Draws`=`Σ_WD` (`Trust`▸[`H_Trust_WD, W_Trust_WD`, subtotal `Σ_Trust`], `HSA_WD`, `Roth`▸[`H_Roth_WD, W_Roth_WD`, `Σ_Roth`], `IRA`▸[`H_IRA_RMD, H_IRA_Elec, W_IRA_RMD, W_IRA_Elec`, computed sum]; context `Req_Portfolio_Draws`). `Roth Conv`=`Roth_Conv` (`H_IRA_Conv, W_IRA_Conv`). `Net Worth`=`NW_Check`. `H_IRA_Tot` and `W_IRA_Tot` are deliberately dropped.
- Produces: `buildTree(table, which: "nw"|"cf") -> {nodes, unmapped: string[]}`. Keys missing from the table are pruned. A table key not in `GROUPS` goes into the top node whose member keys share its `banner`, falling back to the last group.
- Produces: `visibleColumns(tree, open: Set<string>) -> [{id, label, depth, kind: "subtotal"|"detail"|"context", value: (row) => number|null, groupId, expandable: bool}]`, where each open group yields its subtotal first and then its children.
- Produces: `windowRows(rows, startYear: number, count: number) -> {rows, endsAt: number|null}`. `endsAt` is the plan's last year when the window runs past it.
- Produces: `clampYears(v) -> number` (1–30, default 5).
- Produces: `windowTotal(rows, cols) -> {[id]: number|null}`, which sums flow columns for CF and is used only when `which === "cf"`.
- Produces: `reconcileNW(row) -> number`, the difference (Investable + Σ Ann + Home&Other) − TOTAL NW.

- [ ] **Step 1: Write the failing tests:**

```js
test("collapsed NW is the six spec columns", () => {
  const cols = visibleColumns(buildTree(NW_FIXTURE, "nw"), new Set());
  assert.deepEqual(cols.map(c => c.label), ["Investable", "Annuities & Pension", "Home & Other", "Total NW", "Δ vs prior"]);
});   // Year is rendered separately (frozen)
test("collapsed CF is the seven spec columns", ...);   // Income … Net Worth
test("opening Investable keeps its subtotal first", ...);   // cols[0].id === "investable", kind "subtotal"
test("NW reconciles to the cent on fixture rows", ...);     // Math.abs(reconcileNW(r)) < 0.005 for 2026 sample values in spec §5
test("Δ is null for the plan's first year, else the difference", ...);
test("rental keys mapped", ...);                       // unmapped === [] with Rental Equity / Rental / Rental_Tax present
test("unknown key falls back to banner group", ...);   // key "New_Tax" banner "TAXES" -> under Taxes
test("windowRows clamps to plan years", ...);          // start 2059 count 5 on plan ending 2061 -> 3 rows, endsAt 2061
test("clampYears", ...);                               // "", 0, 99, "abc", 7 -> 5, 1, 30, 5, 7
test("CF window total sums flows, skips context", ...);
```

Use the fixture values from spec §5 (2026: Investable 2,849,071, Σ Ann 1,257,077, Home & Other 1,581,595, Total 5,687,743).
- [ ] **Step 2: Run them and confirm they fail.** `node --test tests/frontend/trends_reporter_projections.test.mjs`. Expected: the import fails.
- [ ] **Step 3: Implement** `projection_groups.js`. It is pure, with no DOM access.
- [ ] **Step 4: Run them and confirm they pass.** Same command. Expected: all pass.
- [ ] **Step 5: Commit** with `feat(trends): projection group model`.

### Task 4: View, toggle and page wiring

Model: Sonnet 5.5, effort medium. Usage: **moderate**. `index.html` is 986 lines, so enter it by Grep at the view toggle (~276), the CSS block (~161) and the view switch (~920). `live_snapshot.js` (520 lines) is the pattern to copy, so read only its mount and render functions.

**Files:**
- Create: `financial_trends_reporter/frontend/projections.js`
- Modify: `financial_trends_reporter/frontend/index.html` (third `data-view="projections"` button; `<section id="projView" aria-label="Recent Projections" hidden>`; `body.proj-mode` CSS that hides `.grid`, the time-scope picker and the custom dates, and the notes; sticky Year column and header; `.proj-ctx` muted style; `.proj-build.stale` amber; under 700 px, compact numbers)
- Test: append to `tests/frontend/trends_reporter_projections.test.mjs`

**Interfaces:**
- Consumes: Task 3 exports; Task 2 `/api/projections`; `money_view.js` `fmtAmount`, `onMoneyViewChange`.
- Produces: `renderProjections(data, ui: {table: "nw"|"cf", years: number, open: Set<string>, now: Date, narrow: boolean}) -> string` (HTML), and `mountProjections(rootEl)`, which fetches, reads and writes the four localStorage keys, wires the NW/CF toggle, Years input, Expand all / Collapse all and the group header buttons (`aria-expanded`), and re-renders on a money-view change. Collapse all also clears the remembered open set.
- Produces: `buildLine(builtAtIso, planMtimeSec, now) -> {text, stale: boolean}`.

- [ ] **Step 1: Write the failing tests:** `renderProjections` for collapsed NW contains exactly 6 `<th scope="col">` in the leaf header row, and the year cell contains `2026` and `64 / 65`. `missing: true` renders the exact empty-state text. `buildLine` covers 26 days old with an older plan (`stale: false`, text matches the Global Constraints format), 31 days (`stale: true`) and the plan changed after the build (`stale: true`). An "end note" test checks that `The plan ends in 2061` appears when the window runs past the plan. For `storage failure renders collapsed`, a stubbed `localStorage` whose getItem and setItem throw lets `mountProjections` render with zero open groups, and a stale stored id `"gone"` is ignored. In percent mode, cells show `%` through `fmtAmount`.
- [ ] **Step 2: Run them and confirm they fail.** `node --test tests/frontend/trends_reporter_projections.test.mjs`.
- [ ] **Step 3: Implement** `projections.js` and the `index.html` changes. Follow the `live-mode` show/hide pattern, and send `reportView("projections")` through the existing listener (no change needed, because it keys on `data-view`).
- [ ] **Step 4: Run the tests and confirm they pass,** then run `npm test`. Expected: all pass. Also run `pytest tests -k "trends or live_snapshot" -v -rfE > <scratchpad>/pytest_t4.txt 2>&1`, because some Python tests read the reporter HTML and JS as text. Expected: PASS.
- [ ] **Step 5: Commit** with `feat(trends): Recent Projections view`.

### Task 5: Browser verification and documentation

Model: Sonnet 5.5, effort low. Usage: **light to moderate**: screenshots plus one real build.

- [ ] **Step 1:** Rebuild the active plan, so a real `projection_tables.json` is written, and confirm the file sits beside the plan's `retirement_plan.xlsx`.
- [ ] **Step 2:** Start the reporter and open Recent Projections at 1280×800. For both tables collapsed, check that `document.querySelector('#projView .table-wrap').scrollWidth <= clientWidth` is true. Expand all and check that horizontal scroll appears with the Year column staying pinned. Compare one 2026 NW row and one 2027 CF row with the workbook by hand.
- [ ] **Step 3:** Repeat at 375 px (mobile preset) and in dark mode, then reset to desktop.
- [ ] **Step 4:** Update the spec's Status line to "implemented". Add one line to the reporter's user-facing help or notes, if the Live Snapshot design did the same.
- [ ] **Step 5:** Run `pytest -m "not slow" -v -rfE > <scratchpad>/pytest_full.txt 2>&1` in the background, then read the tail. Expected: no new failures.
- [ ] **Step 6: Commit** with `docs: Recent Projections status`, then open the PR.

## Cost hot spots

- **Task 1 test loop**: a real `build_workbook` run is slow. Use the sheet-level fixture and save the real build for Task 5 only.
- **Task 4 `index.html`**: never read it whole; Grep the three anchors.
- **Task 5 full suite**: run it once, in the background.
