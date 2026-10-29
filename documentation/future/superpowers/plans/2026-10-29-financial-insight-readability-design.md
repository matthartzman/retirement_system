# Financial Insight: Recent Projections Readability, Renames and Deferred Fixes (design + implementation plan)

Date: 2026-10-29. Follows `2026-10-29-trends-recent-projections-design.md`.
One reporter-only PR. Out of scope: the workbook's Net Worth sheet getting a "Loans &
Other Liabilities" column. That runs in its own session and PR.

## 1. Intent

The Recent Projections tables (Net Worth and Cash Flow) are hard to read once groups are
expanded:

- In the body, a subtotal cell and a detail cell look the same (same weight, same color),
  so you can't see where one group ends and the next begins.
- Rows have only a faint hairline, so following one year across a wide table is easy to lose.

The user chose **Option 2: group rules and zebra rows**, for both tables. In the same PR:
two renames (the page and the first view) and five small fixes deferred from the Recent
Projections review.

### Goals
- Summary columns are obviously different from detail columns, in the header and the body.
- An open group's columns are bracketed, so where each group starts and stops is visible with
  "Expand all" on.
- Every other row is shaded, including the frozen Year column, in light and dark mode.
- "Live Snapshot" becomes **Current Snapshot** everywhere a person can read it.
- "Financial Trends" becomes **Financial Insight** everywhere a person can read it.
- The five deferred fixes (§5) land with tests.

### Non-goals
- No change to the numbers, grouping, collapse state, Years window or the API's shape.
- No renaming of code identifiers, file and folder names, URL paths, `localStorage` keys,
  CSS classes, the `trends_server` launcher scripts or the Task Scheduler task name.
  The renames are user-visible text and live docs only.
- No hover highlight (it's useless on a phone and the zebra rows already do the job).

### Anti-goals (a failure even if it "works")
- Zebra shading that shows through as transparent under the sticky Year column while
  scrolling sideways.
- Rules or shading that make the collapsed, default view busier than today.
- A rename that misses a visible spot (sign-in page, exit screen, browser tab), so two names
  appear side by side.

## 2. Table styling (Option 2)

### 2.1 Columns

| Element | Today | New |
|---|---|---|
| Subtotal cell (`kind: "subtotal"`) in the body | weight 400 | **weight 600**, primary text color |
| Detail cell (`kind: "detail"`) in the body | weight 400, primary color | weight 400, muted color (`#555` light / `#b8b8c0` dark), 12px |
| Context cell | italic grey | unchanged |
| Detail header | `.d1` `#555`, `.d2` 11px | unchanged |
| Open **top-level** group | blue underline on its header | unchanged, **plus** a 1px rule (`#9a9aa2` light / `#5a5e66` dark) on the left of its first column and the right of its last column, from the header through the body and the footer |
| Open **nested** group (Housing, Wellness, Trust, Roth, IRA, Pre-Tax…) | blue underline | unchanged, **plus** a lighter 1px rule (`#d4d4d8` / `#3a3d44`) on the same two edges, unless that edge is already a top-level rule |
| Total column (NW `Total NW`; CF `Net Worth`) | none | 2px rule on its left (`#9a9aa2` / `#5a5e66`), in every state |

The Total column rule marks where the balance sits apart from the parts that make it up.
NW's `Δ vs prior` sits to the right of `Total NW` and stays inside that rule.

### 2.2 Rows
- `tbody tr:nth-child(even)` cells, **including the sticky `th.proj-year`**, get an opaque
  `--proj-row-alt` background: `#f5f6f8` light, `#24272d` dark. It must be opaque, because
  the sticky column overlaps scrolled cells.
- The existing 1px hairline stays.
- The CF `tfoot` total row is not striped. It keeps its 2px top rule and bold.
- The sticky `thead` keeps `var(--card-bg)`.

### 2.3 Where it's computed
- `projection_groups.js` `visibleColumns()` adds two pure fields to each column:
  `edge: { left: 0|1|2, right: 0|1|2 }`, where 0 = none, 1 = nested open-group rule and
  2 = top-level open-group rule; and `totalRule: boolean`. That puts the logic in the
  module that already has unit tests, not in CSS selectors.
- `GROUPS` gets a `rule: true` flag on the `total` (nw) and `networth` (cf) nodes.
  `totalRule` comes from that flag, never from a label.
- `projections.js` `headerCell()`, `cell()` and the footer cells map those fields to
  classes: `el1 el2 er1 er2 tr` on `th` and `td`, and `sub` on subtotal `td`s.
- All CSS lives in `index.html` next to the existing `.proj-*` rules, with dark-mode values
  under the existing `@media (prefers-color-scheme: dark)` pattern. Nothing new is added
  below the 700px breakpoint: the rules are 1–2px and survive the compact padding.

### 2.4 Builder's latitude
Exact grey values may be tuned for contrast (WCAG ≥ 3:1 for the rules against the
background, ≥ 4.5:1 for muted detail text) as long as top-level rules stay visibly darker
than nested ones.

## 3. Rename: "Live Snapshot" → "Current Snapshot"

User-visible text and live docs:
- `frontend/index.html`: the view toggle button (line ~316), `#liveView` `aria-label`, the
  `live-tabs` `aria-label` ("Current Snapshot section") and CSS comments.
- `frontend/live_snapshot.js`: "Current Snapshot is unavailable: …", "Couldn't load the
  Current Snapshot (…)", and the header comment.
- Comments and docstrings that use the name: `live_groups.js`, `realized.js`, `main.py`,
  `live_snapshot.py`, `realized_tax_line.py`, `src/market_data.py`, `src/ytd_tracking.py`.
  These keep the code findable by the name on screen.
- Docs: `documentation/reference/readme/README.md`, `FUNCTIONAL_SPEC.md` §4.10 (the switch
  becomes **Current Snapshot | Trends | Recent Projections**, which also fixes the spec's
  stale two-way switch), `TRENDS_REMOTE_ACCESS_RUNBOOK.md`.
- Left unchanged: `data-view="live"`, `trendsView_v1` values, `/api/live-snapshot`, file
  names, test file names, archived docs and past release notes (they're history).

## 4. Rename: "Financial Trends" → "Financial Insight"

- `frontend/index.html`: `<title>`, `<h1>`, and the exit screen's `<h1>` (line ~981).
- `frontend/signin.html`: `<title>Financial Insight — Sign in</title>` and the `<h1>`.
- `frontend/change_password.html`: `<title>`.
- `tools/INSTALL_DESKTOP_ICON.py`: the shortcut name becomes `Financial Insight`, with the
  comment "Start Financial Insight". Rerunning the installer would leave the old
  `Financial Trends Reporter` shortcut behind, so the installer removes that old file
  (`.lnk`/`.bat`/`.command`/`.desktop`) if it's present.
- Launcher messages: `stop_trends_server.ps1` ("Financial Insight server stopped."),
  `register_trends_server_task.ps1` (help text only, not the task name).
- Comments: `frontend/js/runtime_history.js`, `dashboard_decomp_build_lifecycle.js`,
  `src/reporting/workbook_builder.py`, `dashboard_decomp_row_model.js` (one line; edit it
  with Grep + a targeted Edit, never a full read).
- Docs: README, `FUNCTIONAL_SPEC.md` (header line 4, §4.10 heading "Financial Insight
  (companion app)"), `TRENDS_REMOTE_ACCESS_RUNBOOK.md` title and intro.
- Tests that pin the text change with it:
  `tests/frontend/trends_reporter_update_on_open.test.mjs` (title/h1),
  `tests/test_functional_spec_feature_currency_regression.py` (the
  `"Financial Trends Reporter"` phrase pair), and docstrings in
  `test_readme_end_user_feature_currency_regression.py`.
- A new release note, `documentation/reference/release_notes/2026-10-financial-insight-readability.md`,
  linked from `index.md`.

## 5. Deferred fixes

| # | Fix | Where | Change |
|---|---|---|---|
| D1 | Catch the rare error when a rebuild lands mid-page-load | `financial_trends_reporter/projections.py` `_read()` | `path.stat()` runs outside the `try`. If a rebuild replaces the file between `locate()`'s `is_file()` and `stat()`, a `FileNotFoundError` becomes a 500 and the page shows "Couldn't load…". Move the `stat` inside the `try`; an `OSError` returns `None`, which reads as `{"missing": True}`. Also wrap `read_build_results`/`locate` in `load()` so a plan file mid-write behaves the same. On the page, the next switch to the view (or a refresh) recovers. |
| D2 | Cache the plan-input check | `projections.py` `_plan_changed()` | `plan_state()` hashes the plan file's revision and every dataset on every `/api/projections` call. Cache the digest per plan path, keyed by `(st_mtime_ns, st_size)` of the plan file, behind the module's existing `_lock`. Compare the cached digest to `results["plan_state"]`. An unreadable `stat` falls through to today's behavior. |
| D3 | Tighten the "doesn't add up" warning in % mode | `projections.js` `renderProjections()` | The `>= 0.01` threshold is in dollars. For a percent-only viewer the server sends values divided by net worth, so 0.01 means 1% of net worth (tens of thousands of dollars) and real mismatches stay hidden. Use `const tol = moneyView().allowed === "percent" ? 1e-7 : 0.01;` and add a `reconcileTolerance()` helper to `projection_groups.js` so it's unit-testable. The "off by" text already formats through `amount()`. |
| D4 | Escape the year and age cells | `projections.js` `yearCell` and the CF footer label | `r.year`, `ages.join(" / ")` and `${rows.length}-yr total` go into HTML unescaped. Wrap them in `esc()`. The data comes from our own build, so this is defense in depth. |
| D5 | Remove leftover `plan_mtime` mentions | `main.py:312` comment; `2026-10-29-trends-recent-projections-design.md:96` | Replace with "`plan_changed` (the plan's inputs differ from what the build read)". |

## 6. Constraints and contracts
- Python tests read panel JS as text in places. Before editing, read
  `tests/frontend/trends_reporter_projections.test.mjs` and
  `tests/test_trends_projections_unit.py`, and treat their assertions as the interface.
- `tests/test_frontend_size_ratchet.py` caps file sizes. `index.html` and `projections.js`
  will grow slightly, so update the ratchet entry with a dated comment if it trips.
- No new files under `src/` or `frontend/` (except the release note), so the system diagram
  shouldn't change. Run `python tools/generate_system_diagram.py` anyway and commit only if
  it differs.
- Run pytest per `~/.claude/CLAUDE.md`: `-v -rfE`, output to a scratchpad log, in the
  background for the full run.

## 7. Implementation plan

Check `/usage` after each task against the estimates below. All tasks are light to moderate
against a 5-hour Pro session. Together, about a third of a session.

### Task 1: Pure column fields (TDD)
- **Model / effort:** Sonnet 5.5, medium.
- **Usage:** light. Drivers: `projection_groups.js` (195 lines) and the existing projections
  test file. No broad search.
- Steps:
  1. Write failing tests in `tests/frontend/trends_reporter_projections.test.mjs`:
     - Investable open, Pre-Tax closed: `edge.left=2` on Investable, `edge.right=2` on the
       last Investable child.
     - Investable and Pre-Tax both open: Pre-Tax's first column gets `edge.left=1`, and an
       edge shared with a top-level edge stays 2.
     - Everything collapsed: no edges.
     - `totalRule` is true only on Total NW / Net Worth.
     - `reconcileTolerance("percent") === 1e-7` and `reconcileTolerance("both") === 0.01`.
  2. Implement `edge`, `totalRule` and `rule: true` in `projection_groups.js`.
  3. Run `npm test`.

### Task 2: Render classes and CSS
- **Model / effort:** Sonnet 5.5, medium.
- **Usage:** moderate. Drivers: `projections.js` (191 lines) and a Grep-and-offset read of
  the `index.html` CSS block (lines ~200–310). Never read all ~1,000 lines.
- Steps:
  1. Tests: `renderProjections()` output has `class="… sub"` on subtotal `td`s, `el2`/`er2`
     on an open group's edges and `tr` on the Total column, in `thead`, `tbody` and `tfoot`.
  2. Map the fields to classes in `headerCell`, `cell` and the footer.
  3. Add the CSS (§2.1–2.2), light and dark.
  4. Visual check in the browser pane: start the reporter, open Recent Projections, and look
     at NW and CF, each collapsed, partly open and with Expand all. Also check dark mode
     (`resize_window colorScheme`) and the 375px mobile preset, and scroll sideways to
     confirm the sticky Year column stays opaque on striped rows. Screenshot each table.
- **Watch:** this is the one task that can turn into a tweak-and-screenshot loop. Cap it at
  two rounds of visual tuning, then show the user the screenshots.

### Task 3: Deferred fixes D1–D5 (TDD)
- **Model / effort:** Sonnet 5.5, medium.
- **Usage:** light. Drivers: `projections.py` (76 lines) and `test_trends_projections_unit.py`.
- Steps:
  1. D1 test: monkeypatch `Path.stat` to raise `FileNotFoundError`. `load()` returns
     `{"missing": True}`, and the endpoint returns 200.
  2. D2 test: count `plan_state` calls across two `load()`s with an unchanged plan (1),
     then after touching the plan file (2).
  3. D3 test: percent-only data off by 0.005 (0.5% of NW) shows the warning; dollar data
     off by $0.004 doesn't.
  4. D4 test: a row with `year: "<b>"` renders `&lt;b&gt;`.
  5. Implement, then edit the two D5 lines.

### Task 4: "Current Snapshot" rename
- **Model / effort:** Haiku 5.5, low (mechanical).
- **Usage:** light. One Grep for `Live Snapshot` (about 20 hits outside archives, listed in
  §3), then targeted Edits. Don't open large files whole.
- Steps: edit each §3 site, rerun the Grep (only archived docs, release notes and
  identifiers should remain), run `npm test`.

### Task 5: "Financial Insight" rename
- **Model / effort:** Haiku 5.5, low; Sonnet if the installer cleanup needs thought.
- **Usage:** light. Same Grep-then-edit pattern (§4).
- Steps: edit each §4 site; update the pinned tests in the same commit; add old-shortcut
  removal to `INSTALL_DESKTOP_ICON.py` with a unit test if one exists for the installer
  (otherwise a dry check on the computed paths); write the release note.

### Task 6: Full verification and PR
- **Model / effort:** Sonnet 5.5, low.
- **Usage:** moderate, mostly waiting. The full `pytest` runs in the background into a
  scratchpad log; read it with `tail`. Don't loop the full suite. Fix failures with single
  `pytest tests/…::test -v` runs, then one final full run.
- Steps: `npm test`; `pytest -m "not slow"`; full `pytest`; the system diagram check;
  `/code-review`; a draft PR with screenshots from Task 2.

**Most expensive:** Task 2's visual loop and Task 6's full suite. Both are capped above.
Tasks 4–5 are cheap if they stay Grep-driven. Reading `index.html` or
`dashboard_decomp_row_model.js` whole would multiply their cost.
