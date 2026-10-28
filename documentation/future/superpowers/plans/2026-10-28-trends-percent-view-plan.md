# Financial Trends Percent View Implementation Plan

Status: approved

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-person `$ / % / Both` setting; %-only remote people never receive a dollar amount; "Both" gets a `$ | %` toggle beside the *Financial Trends* title.

**Architecture:** The page re-sums per-account series when an account toggle changes and applies the Time scope in the browser, so the server cannot send finished percentages. Instead, for a %-only person, the server divides **every** money number in every `/api/` JSON response by one constant `K` = today's net worth (fail-closed: any number not on a short non-money allowlist is divided). Sums and ratios survive scaling, so the browser computes the decided % forms (change since scope start, share of total spending) exactly as it would from dollars, and `K` never leaves the PC. Detail the spec hides (merchants, transactions, reconciliation) is stripped on the server.

**Tech Stack:** Python / Flask / sqlite (`financial_trends_reporter/`), vanilla ES modules, pytest, `node --test`.

**Spec:** `documentation/future/superpowers/plans/2026-10-28-trends-percent-view-design.md` (decisions in §7).

## Global Constraints

- Setting values are exactly `"dollars" | "percent" | "both"`, stored per person as `users.money_view`.
- A newly added remote person defaults to `"percent"`. The local listener (owner's PC) is always `"both"`.
- A `"percent"` person must never receive a dollar amount from any route — enforced on the server, not the page.
- Net Worth and Liquid in % = change since the first day in the Time scope, labelled `% change since <d Mon yyyy>`.
- Spending in % = each category's share of total spending in the period.
- For `"percent"` people: merchant level, transactions and the reconciliation section are not sent.
- Adding a file under `financial_trends_reporter/frontend/` → run `python tools/generate_system_diagram.py` and commit `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` in the same PR.
- Run pytest with `-v -rfE` into a scratchpad log (`> <scratchpad>/pytest_<label>.txt 2>&1`), read it with `tail`.
- `tests/test_trends_access_owner_screens_functional.py::test_remote_index_html_carries_no_owner_screen_markup` stays green: no `api/people` text in `index.html`.

## Review Focus

1. **Net worth ≤ 0 or 0 at the scope start** (or `K ≤ 0` today) — expect "n/a" with a note, never a 4,000% spike or a divide-by-zero. Tests in Task 2 and Task 6.
2. **The spending cache holds dollar JSON strings shared by owner and guest** — scaling a guest's response must not change what the owner gets next. Test in Task 3.
3. **Error bodies** (`500` with `f"{exc}"`) can contain amounts — for %-only people the error text is replaced by a generic message. Test in Task 3.
4. **Owner changes a signed-in person's view** — the change applies on that person's next request, without signing in again. Test in Task 3.
5. **A new `/api/` route added later** — must be scaled by default, and a test fails until the route is classified. Test in Task 4.

---

### Task 1: `money_view` setting (store, routes, People dialog)

**Files:**
- Modify: `financial_trends_reporter/access_store.py` (`_init_extra`, `add_user`, `list_users`, `get_user` row, new `set_money_view`)
- Modify: `financial_trends_reporter/access_routes.py` (`add_person`, new `POST /api/people/view`, `whoami`)
- Modify: `financial_trends_reporter/frontend/access.js` (selector per row and in the add form; staged like reset / delete)
- Test: `tests/test_trends_access_owner_screens_functional.py`

**Interfaces:**
- Produces: `MONEY_VIEWS = ("dollars", "percent", "both")` in `access_store.py`; `AccessStore.add_user(display_name, username, temp_password, now=0.0, money_view="percent") -> int`; `AccessStore.set_money_view(user_id: int, money_view: str) -> None` (raises `ValueError` for other values); `list_users()` rows and `get_user()` dicts carry `"money_view"`; `GET /api/whoami` returns `"money_view"` (`"both"` on local); `POST /api/people/view {id, money_view}` → `{"success": true}`, logged as activity event `"view setting"` with details `"<username> <money_view>"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_new_person_defaults_to_percent_and_whoami_reports_it(tmp_path):
    rig = Rig(tmp_path)
    _add(rig)
    assert rig.call(rig.local, "GET", "/api/people").get_json()["people"][0]["money_view"] == "percent"
    assert rig.call(rig.local, "GET", "/api/whoami").get_json()["money_view"] == "both"
    _, token = rig.signin("ann", "temp password 1")
    # must_change allows whoami
    assert rig.call(rig.remote, "GET", "/api/whoami", cookie=token).get_json()["money_view"] == "percent"

def test_set_money_view_validates_and_logs(tmp_path):
    rig = Rig(tmp_path)
    uid = _add(rig).get_json()["id"]
    assert rig.call(rig.local, "POST", "/api/people/view", {"id": uid, "money_view": "dollars"}).status_code == 200
    assert rig.call(rig.local, "POST", "/api/people/view", {"id": uid, "money_view": "euros"}).status_code == 400
    assert rig.call(rig.local, "POST", "/api/people/view", {"id": 999, "money_view": "both"}).status_code == 404
    assert rig.call(rig.local, "GET", "/api/activity").get_json()["events"][0]["event"] == "view setting"

def test_existing_database_gains_money_view_column(tmp_path):
    # a users table created before this change (no money_view column) is migrated, rows default to "percent"
    ...  # create the old schema by hand with sqlite3, open AccessStore on it, assert list_users()[0]["money_view"] == "percent"
```

- [ ] **Step 2: Run to verify they fail** — `pytest tests/test_trends_access_owner_screens_functional.py -v -rfE > <scratchpad>/pytest_t1.txt 2>&1`; expect 3 FAIL (`KeyError: 'money_view'` / 404).
- [ ] **Step 3: Implement.** Migration in `_init_extra`: `ALTER TABLE users ADD COLUMN money_view TEXT NOT NULL DEFAULT 'percent'` when `PRAGMA table_info(users)` lacks it; bump `SCHEMA_VERSION` to 2. `/api/people/view` sits under the existing `/api/people` owner-only prefix, so the remote gate already 404s it. In `access.js`: a `<select>` ($ / % / Both) per person row and in the Add form; a change stages `{kind:"view", id, money_view}` (replacing any earlier one for that id); save order becomes delete, reset, view, add; unsaved rows show the existing "(unsaved)" tag.
- [ ] **Step 4: Run to verify they pass**, plus the whole access suite: `pytest tests/test_trends_access_owner_screens_functional.py tests/test_trends_access_gate_functional.py -v -rfE`. Check in the browser pane that the selector stages and Exit without Saving discards it.
- [ ] **Step 5: Commit** `"Trends: per-person $ / % / Both setting"`.

### Task 2: `percent_view.py` — scaling and stripping, pure functions

**Files:**
- Create: `financial_trends_reporter/percent_view.py`
- Test: `tests/test_trends_percent_view_unit.py`

**Interfaces:**
- Consumes: `balance_series.snapshot_summary(db_path) -> dict | None` (its `"net_worth"`), `read_history(log_path)` (last entry's `net_worth.total`) as fallback.
- Produces:
  - `NON_MONEY_KEYS: frozenset[str]` — numeric keys left unscaled. Start with `id`, `days`, `year`, `year_fraction`, `count`, `shares`, `quantity`, plus `is_non_money(key)` treating keys ending in `_rate`, `_pct`, `_ratio`, `_fraction` and the keys `pct`, `rate`, `weight` as ratios. Prices, costs and balances are money and are scaled. A key not listed is scaled.
  - `scale_basis(balances_db: Path, history: list[dict]) -> float | None` — today's net worth; falls back to the last history entry; `None` when missing or ≤ 0.
  - `scale_payload(obj: Any, k: float) -> Any` — returns a new structure (never mutates); every `int`/`float` (not `bool`) whose key is not in `NON_MONEY_KEYS` becomes `round(v / k, 6)`; list items inherit the parent key; strings matching `r"\$\s?-?\d"` are replaced by `"(amount hidden)"`.
  - `strip_detail(route: str, payload: dict) -> dict` — `/api/spending`: in `hierarchy` and `prior.detail`, each category's merchants collapse to `{"All merchants": <sum>}` and `prior.detail[..]["merchants"]` is removed; `/api/live-snapshot`: drop `reconciliation`, `unmapped_monarch`, `unmapped_holdings`; `/api/history`: same merchant collapse inside any spending hierarchy in each entry. Other routes unchanged.
  - `find_money_leaks(obj: Any, threshold: float = 50.0) -> list[str]` — paths of numbers outside `NON_MONEY_KEYS` with `abs(v) > threshold`, and of strings matching the `$` pattern. Used by Task 4.

- [ ] **Step 1: Write the failing tests**

```python
def test_scale_divides_money_keeps_allowlist_and_does_not_mutate():
    src = {"net_worth": {"total": 2_000_000}, "days": 30, "pre_tax_rate": 0.24, "series": {"a": [1_000_000, 500_000]}, "ok": True}
    out = scale_payload(src, 2_000_000)
    assert out == {"net_worth": {"total": 1.0}, "days": 30, "pre_tax_rate": 0.24, "series": {"a": [0.5, 0.25]}, "ok": True}
    assert src["net_worth"]["total"] == 2_000_000

def test_sums_survive_scaling():
    a, b, k = [1200.0, 1300.0], [800.0, -50.0], 7_654_321.0
    sa, sb = scale_payload({"v": a}, k)["v"], scale_payload({"v": b}, k)["v"]
    assert [round((x + y) * k, 2) for x, y in zip(sa, sb)] == [2000.0, 1250.0]

def test_dollar_strings_are_hidden():
    assert scale_payload({"note": "differ by $1,234"}, 10.0) == {"note": "(amount hidden)"}

def test_basis_none_when_net_worth_not_positive(tmp_path):
    # empty store and history whose last net_worth.total is -5 → None
    ...

def test_strip_spending_collapses_merchants():
    p = {"hierarchy": {"Expense": {"Home": {"Rent": {"Landlord": 2400.0, "Fee": 10.0}}}},
         "prior": {"detail": {"Expense": {"Home": {"Rent": {"prior": 2300.0, "merchants": {"Landlord": 2300.0}}}}}}}
    out = strip_detail("/api/spending", p)
    assert out["hierarchy"]["Expense"]["Home"]["Rent"] == {"All merchants": 2410.0}
    assert "merchants" not in out["prior"]["detail"]["Expense"]["Home"]["Rent"]

def test_strip_live_snapshot_drops_reconciliation():
    assert "reconciliation" not in strip_detail("/api/live-snapshot", {"reconciliation": {}, "liquid": {}})

def test_find_money_leaks():
    assert find_money_leaks({"total": 0.4, "days": 400}) == []
    assert find_money_leaks({"total": 1234.0}) == ["total"]
```

- [ ] **Step 2: Run to verify they fail** (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** the five functions in `percent_view.py`. Build `NON_MONEY_KEYS` by grepping the keys in `balance_series.py`, `flows.py`, `spending_window.py`, `live_snapshot.py` return dicts; write a one-line comment on each non-obvious entry.
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** `"Trends: percent-view scaling and detail stripping"`.

### Task 3: Apply it on the remote listener

**Files:**
- Modify: `financial_trends_reporter/access_routes.py` (`register_access` gains `percent_basis`; `_gate` withholds; new `@app.after_request`)
- Modify: `financial_trends_reporter/main.py` (pass `percent_basis=lambda: percent_view.scale_basis(balances_db, read_history(resolved_log_path))` to `register_access`)
- Modify: `tests/test_trends_access_gate_functional.py` (`Rig` accepts `percent_basis` and optional extra test routes)
- Test: `tests/test_trends_percent_view_functional.py`

**Interfaces:**
- Consumes: Task 1 `user["money_view"]`; Task 2 `scale_payload`, `strip_detail`.
- Produces: `register_access(app, ..., percent_basis: Callable[[], float | None] = lambda: None)`; constants in `access_routes.py`: `WITHHELD_FOR_PERCENT = {"/api/spending/transactions"}`, `PASS_THROUGH_FOR_PERCENT = {"/api/whoami", "/api/ping", "/api/view", "/api/signin", "/api/signout", "/api/change-password", "/api/run-status", "/api/run-cancel", "/api/passthrough-decision", "/api/account-prefs"}`. A scaled response body gains `"money_view": {"mode": "percent", "basis": "net_worth_today"}` when it is a dict.

Rules, in order, for a remote request whose user has `money_view == "percent"`:
1. Path in `WITHHELD_FOR_PERCENT` → `403 {"success": false, "error": "Not available in the percent view."}` (in `_gate`).
2. After the view: JSON response on `/api/…` not in `PASS_THROUGH_FOR_PERCENT` → parse, `strip_detail`, `scale_payload(…, K)`, re-serialise. `K = percent_basis()`; `None` → `503 {"success": false, "error": "The percent view is not available until account balances are imported."}`.
3. Any status ≥ 400 from a scaled route → body becomes `{"success": false, "error": "Something went wrong. Try again later."}`.

`"dollars"` and `"both"` remote users and all local requests are untouched.

- [ ] **Step 1: Write the failing tests** (a Rig with a test-only route `GET /api/test-money` returning `{"total": 5000.0, "days": 3}`, `percent_basis=lambda: 10000.0`):

```python
def test_percent_user_gets_scaled_json(tmp_path): ...
    # body == {"total": 0.5, "days": 3, "money_view": {"mode": "percent", "basis": "net_worth_today"}}
def test_dollars_and_both_users_and_local_get_dollars(tmp_path): ...
def test_transactions_withheld_403(tmp_path): ...
def test_basis_missing_gives_503(tmp_path): ...             # percent_basis=lambda: None
def test_error_text_replaced(tmp_path): ...                  # test route returns 500 {"error": "bad $1,234"}
def test_cached_string_not_mutated_for_owner(tmp_path): ...  # test route serves one shared json string: guest then local; local still 5000.0
def test_view_change_applies_next_request(tmp_path): ...     # owner sets "dollars" mid-session; next guest call returns 5000.0
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** the rules above. Read `user` from `request.environ` (the gate already loads it per request, which makes Review Focus 4 work).
- [ ] **Step 4: Run** the new file plus both existing access test files; all pass.
- [ ] **Step 5: Commit** `"Trends: percent-only people get scaled data; detail withheld"`.

### Task 4: Leak guard

**Files:**
- Test: `tests/test_trends_percent_view_leak_guard.py`

**Interfaces:**
- Consumes: Task 2 `find_money_leaks`, `scale_payload`, `strip_detail`; Task 3 route sets.

- [ ] **Step 1: Write the tests**

```python
def test_every_api_route_is_classified():
    # every rule in create_app(...).url_map under /api/ is in PASS_THROUGH_FOR_PERCENT, WITHHELD_FOR_PERCENT,
    # OWNER_ONLY_PREFIXES, or KNOWN_SCALED (a set in this test file). A new route fails here until listed.

@pytest.mark.parametrize("route,builder", [...])   # /api/balances, /api/flows, /api/spending, /api/live-snapshot, /api/history, /api/accounts
def test_realistic_payloads_have_no_leaks(route, builder):
    payload = builder()                # reuse existing fixtures: grep tests/ for balances_payload(, flows_payload(,
                                       # spending_window_payload(, live_snapshot.build( and call the same way
    k = 2_000_000.0
    assert find_money_leaks(scale_payload(strip_detail(route, payload), k)) == []
```

- [ ] **Step 2: Run.** Expect failures that name keys wrongly allowlisted or `$` strings — fix them in `NON_MONEY_KEYS` / Task 2, not in the test. Cap at two fix rounds; if a third is needed, stop and report the remaining keys.
- [ ] **Step 3: Commit** `"Trends: guard against dollar leaks in the percent view"`.

### Task 5: One money formatter, and the title toggle

**Files:**
- Create: `financial_trends_reporter/frontend/money_view.js`
- Modify: `financial_trends_reporter/main.py` (serve `/money_view.js`, same pattern as `/spending_dock.js`)
- Modify: `financial_trends_reporter/frontend/charts.js:13` (`fmtMoney` delegates), `frontend/live_snapshot.js:23,83` (`fmtUsd`, `fmtUsd2` delegate)
- Modify: `financial_trends_reporter/frontend/index.html` (toggle next to `<h1>`, set the view from `/api/whoami` before the first render, re-render on change)
- Regenerate: `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md`
- Test: `tests/frontend/trends_reporter_money_view.test.mjs`

**Interfaces:**
- Produces (`money_view.js`): `setMoneyView({allowed: "dollars"|"percent"|"both", shown?: "dollars"|"percent", scale: number})`; `moneyView() -> {allowed, shown, scale}`; `fmtAmount(v: number, digits = 0) -> string` — dollars when `shown === "dollars"`, else `` `${(v / scale * 100).toFixed(1)}% of net worth` `` (`"-"` for null / non-finite); `fmtSharePct(ratio: number) -> string` (`"+3.2%"` / `"-1.0%"`, `"n/a"` for null); `onMoneyViewChange(fn)`.
- `scale`: `1` for a `"percent"` person (data already scaled); for local / `"both"`, today's net worth from `/api/balances` `points.networth` last value.
- Toggle: `<button id="moneyToggle" aria-pressed>` showing `$ | %`, only when `allowed === "both"`; choice remembered in `localStorage["trends.moneyView"]` inside try/catch.

- [ ] **Step 1: Write the failing node tests** — `fmtAmount(250000)` with `{allowed:"both", shown:"percent", scale:1e6}` → `"25.0% of net worth"`; with `shown:"dollars"` → `"$250,000"`; `allowed:"percent"` forces `shown:"percent"` even if asked for dollars; `fmtSharePct(0.032)` → `"+3.2%"`; existing `fmtMoney` tests still pass in dollars mode.
- [ ] **Step 2: Run** `npm test -- tests/frontend/trends_reporter_money_view.test.mjs`; expect FAIL.
- [ ] **Step 3: Implement**, then `python tools/generate_system_diagram.py`.
- [ ] **Step 4: Run** `npm test` (trends files) and `pytest tests/test_system_architecture_diagram_freshness_regression.py -v`. Check in the browser pane: toggle flips every visible amount; reload keeps the choice.
- [ ] **Step 5: Commit** `"Trends: one money formatter and the $ | % toggle"`.

### Task 6: Decided % forms on the charts

**Files:**
- Modify: `financial_trends_reporter/frontend/charts.js` (new pure functions; call sites in `lineChartSvg` axis, `barChartSvg`, flows chart)
- Modify: `financial_trends_reporter/frontend/index.html` (the Net Worth / Liquid / Spending / Flows render calls pick the % form when `moneyView().shown === "percent"`)
- Test: `tests/frontend/trends_reporter_money_view.test.mjs`

**Interfaces:**
- Consumes: Task 5 `moneyView`, `fmtSharePct`.
- Produces (`charts.js`): `toPercentChange(points: {label, value}[]) -> {points, base: {label, value} | null}` — values become `value / base.value - 1`; `base` is the first point with a finite value; `base.value <= 0` → all values `null` and `base: null`; `toShareOfTotal(entries: [name, value, ...rest][]) -> same shape` with value / sum of positive values; `flowsAsShareOfLiquid(series, liquidAtStart: number | null) -> series` (null when `liquidAtStart <= 0`).
- Copy: chart subtitle `% change since 30 Sep 2026`; on `base: null`, the note `Percent change isn't shown: net worth was zero or negative at the start of this period.`; spending header `Share of spending`.

- [ ] **Step 1: Write the failing tests** — `toPercentChange([{label:"a",value:200},{label:"b",value:250}])` → values `[0, 0.25]`; first value `-10` → all null, `base: null`; first value null then 100, 110 → base is the 100 point; `toShareOfTotal([["Home",300],["Food",100],["Refund",-20]])` → `[0.75, 0.25, -0.05]`; `flowsAsShareOfLiquid(..., 0)` → null values.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**; axis ticks in % mode use `fmtSharePct`.
- [ ] **Step 4: Run** the trends frontend tests; check each card in the browser pane in both modes and across Time scopes.
- [ ] **Step 5: Commit** `"Trends: percent change, share of spending and flows as share of liquid"`.

### Task 7: Hide detail and dollar wording for %-only people

**Files:**
- Modify: `financial_trends_reporter/frontend/spending_dock.js` (no third panel; merchant rows not clickable when `allowed === "percent"`)
- Modify: `financial_trends_reporter/frontend/live_snapshot.js` (skip reconciliation section; tax note at line 224 gets a %-mode sentence without amounts)
- Modify: `financial_trends_reporter/frontend/charts.js` (`passthroughReviewHtml` returns `""` when `allowed === "percent"`)
- Test: `tests/frontend/trends_reporter_spending_dock.test.mjs`, `tests/frontend/trends_reporter_live_snapshot.test.mjs`

- [ ] **Step 1: Write the failing tests** — with `allowed:"percent"`: dock renders no `#detailPopup3` content and no `data-merchant` attributes; live snapshot HTML contains no `Reconciliation` heading; no rendered HTML from these modules matches `/\$\s?\d/`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** With `allowed: "both"` nothing is hidden, in either toggle position.
- [ ] **Step 4: Run** all trends frontend tests and the full `pytest -m "not slow"` into a log. Sign in on 5058 as a %-only test person in the browser pane (test account created for this, deleted after) and check DevTools network bodies contain no dollar figures.
- [ ] **Step 5: Commit** `"Trends: percent-only view hides merchant, transaction and reconciliation detail"`; update `documentation/reference/TRENDS_REMOTE_ACCESS_RUNBOOK.md` with the setting and what %-only people see, in the same commit.

---

## Effort and usage (relative; check `/usage` against these as the plan runs)

| Task | Model / effort | Usage vs a 5-hour Pro session | What drives context | How to keep it small |
|---|---|---|---|---|
| 1 Setting | Sonnet / medium | Light | Small files (`access_store.py`, `access_routes.py`, `access.js`) | — |
| 2 `percent_view.py` | Opus / high | Moderate | Reading the return dicts of four payload builders to build the allowlist | Grep `return {` and dict keys; don't read `live_snapshot.py` (1,000+ lines) whole |
| 3 Wire into gate | Opus / high | Moderate | Gate + Rig + new functional tests | Test-only route instead of real data |
| 4 Leak guard | Sonnet / high | **Moderate–heavy — flag** | Finding fixtures; fix rounds on the allowlist | Reuse existing fixtures by grep; two-round cap |
| 5 Formatter + toggle | Sonnet / medium | Light–moderate | `index.html` (869 lines) render flow | Grep the render functions and `whoami` call |
| 6 % chart forms | Sonnet / high | Moderate | `charts.js` (1,128 lines) | Grep `fmtMoney(` call sites (≈30, listed by grep); never read the file whole |
| 7 Hide detail | Sonnet / medium | Light–moderate | Three modules, browser check | One sign-in check at the end, not per change |

Whole plan: roughly one heavy session, or two moderate ones split after Task 4 (server side done and guarded).
