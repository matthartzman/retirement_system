# Monarch Daily Account Balances → Financial Trends Reporter

Design + implementation plan. Date: 2026-10-14. Status: awaiting approval of the "Open items" section.

## 1. Goal

Pull per-account daily balances from Monarch every day (same schedule as transactions) and make them the
source of truth for the Financial Trends Reporter's **Net worth** and **Holdings** charts. Add a UI to map
Monarch accounts to app accounts, classify them, and turn accounts on/off per chart. Replace the
investment-flows bar chart with a monthly line chart plus a YTD summary.

## 2. What the sample files proved (facts, not assumptions)

| Finding | Evidence | Consequence |
|---|---|---|
| CSV is `Date,Balance,Account`, one row per account per day, 18,029 rows, 41 accounts, 2024-01-10 → 2026-10-14 | `Balances_2026-10-14T19-50-27.csv` | Full-history download is only ~780 KB, so every run can re-download everything. No delta logic, and upsert is idempotent. |
| **No account ID in the CSV**, name only | header row | Identity key = normalized name. IDs are not available in this export. |
| Dates are `m/d/yyyy` | rows | Normalize to ISO in the extractor. |
| Liabilities are negative; summing all accounts on 2026-10-14 = **$6,566,764.29**, exactly Monarch's on-screen net worth | computed vs screenshot | Sign convention confirmed. This sum is the acceptance check for the importer. |
| 10 accounts have rows that stop early (closed or replaced), e.g. `Trust Under Agreement (...0299)` ends 2025-02-04; 2 HSAs overlap in time | per-account last date | After an account's last date its value is 0. Inside its first→last range, carry forward across gaps. |
| `®` is valid UTF-8 (`\xc2\xae`); trailing/double spaces exist (`Family Checking and Bill Pay `, `Trust  Under…`) | byte check | Read as `utf-8-sig`; normalize with NFKC, trim, collapse whitespace. Keep the raw name for display. |
| Download is `POST api.monarch.com/download-balances/` with `{"account_ids":[]}` (empty = all); auth is session cookies plus an `x-csrftoken` header, not a bearer token | HAR | Two viable automation paths (see Open item 1). |
| Account type/group is only on the Accounts screen (Cash, Credit Cards, Investments, Real Estate, Vehicles, Loans; subtypes like "Fixed Annuity", "Other") | screenshots | Type must be inferred from the name and then confirmed in the UI (decided: heuristic + editable). |
| The trends log already stores per-account `holdings.by_account`, `net_worth.other_accounts` and `investment_net_flows_by_account` from plan data | `financial_trends_log.jsonl`, `trends_metrics.py` | Plan values remain only as a fallback for dates Monarch doesn't cover. |

**Security note:** `app.monarch.com.har` contains session material. `raw/` is gitignored, but delete the HAR
after Phase 0 (I only read the request shape from it, never cookie or token values).

## 3. Decisions already made

1. Monarch balances are the primary source for Net worth and Holdings; plan-derived values are the fallback.
2. Account type: heuristic from the name, editable per account, stored with the mapping.
3. Holdings = liquid investments + checking + Venmo. **Excluded by default:** annuity/pension, "Other"
   (Masterworks, hucu.ai, RedMane Note), real estate, vehicles, loans, credit cards. Every account is
   toggleable per chart.
4. Flows chart = **one total monthly line** plus a YTD summary header (credits, debits, total). Account
   toggles choose which accounts feed the total.
5. Load all history on first run. Per-account rows. Manual accounts are maintained in Monarch only. Runs on the
   same schedule as transactions (03:30 extract, 04:00 import).
6. Net-worth hover detail omits accounts whose value on that date is zero.

## 4. Design

### 4.1 Data flow

```
03:30  run_monarch.ps1
         ├─ monarch_extract.py --period "This year"      (existing, unchanged)
         └─ monarch_balances.py                           (NEW; failure does not fail the transactions step)
              raw/balances-<ts>.csv  →  output/balances.csv   (normalized: date ISO, account, balance)
04:00  src/monarch_autoimport_job.py
         ├─ import transactions                           (existing)
         └─ import balances  (NEW, non-fatal)  →  balance store
17:00  trends job (existing) → log entry; Net worth/Holdings charts read the balance store via API
```

Why a separate script (not another mode in the 1,400-line `monarch_extract.py`): it isolates the working
transaction job from the new one, and it shares only the login/profile helpers. The cost is a small amount of
duplicated launch code. If you would rather have one script, the alternative is a `--balances` flag, which is
smaller but couples the two jobs' failures.

### 4.2 Balance store

New SQLite file beside the trends log: `financial_trends_reporter/data/monarch_balances.sqlite3`
(gitignored). Tables:

- `balances(date TEXT, account_key TEXT, balance REAL, PRIMARY KEY(date, account_key))` upserted each run.
- `accounts(account_key PK, display_name, type, app_account, first_seen, last_seen, active)` is the registry
  and mapping. `app_account` is many-to-one, so a renamed or replaced Monarch account can map to the same app
  account.
- `account_prefs(chart, account_key, enabled, PRIMARY KEY(chart, account_key))` with `chart` in
  `networth | holdings | flows`.
- `import_runs(run_at, source_file, rows, accounts, latest_date, status)` for freshness and audit.

Import guards (each failure quarantines the file instead of writing, then surfaces a banner like the existing
`priceNote`):

- Header not exactly `Date,Balance,Account`.
- Latest date older than yesterday.
- Account count drops more than 20% versus the prior run.
- Any unparseable date or amount.

Phase 2 must verify this location against the file-elimination guard
(`tests/test_no_data_file_io_enforcing_regression.py`, master-plan spec) before committing to a file. If the
guard objects, the same tables go in the plan DB.

### 4.3 Series engine (`financial_trends_reporter/balance_series.py`, new, pure functions)

- Dense daily value per account: carry forward inside `[first_seen, last_seen]`, 0 outside.
- Chart total = sum over the accounts enabled for that chart. Net worth uses all types by default, and
  liabilities stay negative. Holdings default membership comes from the type table (rule 3).
- Zero-value filter for hover detail: drop accounts with `abs(value) < 0.005` on that date.
- Source merge: use Monarch where any balance row exists for the date, else the log's plan-derived value. Each
  point carries `source: "monarch" | "plan"`.

### 4.4 Account registry and classifier (`account_registry.py`, new)

Name → type rules (first match wins), tested against all 41 current names:
`Mortgage|HELOC|Home Equity|Loan` → Loan; `Visa|MasterCard|Platinum Card|Credit` → Credit card;
`Annuity|Pension` → Annuity/Pension; `IRA|Roth|401k|401(K)|HSA|Health Savings|Brokerage|Trust` → Investment
(Retirement/HSA are subtypes); `Checking|Venmo|Savings` → Cash; street address → Real estate;
`BMW|KIA` or a model year → Vehicle; `iBond` → Investment; everything else → Other. New unseen accounts get
`type=Other` and a "New" badge in the UI, with toggles defaulting to the type's rule.

### 4.5 API (financial_trends_reporter/main.py; the existing same-origin check applies)

- `GET /api/balances` returns `{accounts:[…meta+prefs…], dates:[…], series:{account_key:[values]}, freshness}`.
  About 41 × 630 points is roughly 400 KB, and the client sums by toggle so toggling is instant.
- `POST /api/accounts/<key>` sets type and `app_account`.
- `POST /api/account-prefs` sets `{chart, account_key, enabled}` or a bulk set.
- `POST /api/run-now` additionally triggers the balance import (the existing button).

### 4.6 Frontend (`frontend/index.html` 330 lines, `frontend/charts.js` 485 lines; both readable whole)

- **Accounts panel** (new card or drawer): table of Monarch name | type ▾ | app account ▾ | first/last date |
  latest balance | toggles for Net worth / Holdings / Flows | status (active, or "no data since <date>").
  "New" and "Unmapped" filters. The app-account dropdown is fed from the plan's account setup.
- **Per-chart "Accounts ▾" popover** on Net worth, Holdings and Flows: checkboxes grouped by type, with
  all/none. It writes the same prefs.
- Net worth and Holdings lines are drawn from the series sum. Hover detail uses `rolloverModel`
  (`charts.js:371`), extended to skip zero-value accounts and to group by type.
- **Flows chart:** replace `flowBarChartSvg` (`charts.js:450`) with a monthly line chart. Above it, a YTD
  summary with **Contributions into investments (credits)**, **Withdrawals (debits)** and **Net** (see Open
  item 4). It keeps the data-table fallback and `role`/aria labelling the bar chart has.
- The freshness banner reads "Monarch balances as of <date>" and turns amber when stale.

### 4.7 Flows backend

`investment_net_flows_by_account` is YTD-only today. Add `investment_net_flows_monthly`:
`{account: {"YYYY-MM": {to_checking, from_checking, net}}}`, computed in the same pass in `ytd_tracking.py`
that produces `net_flows_by_account`, including the passthrough/approved-pair logic. It is recomputed in full
each run and stored on the log entry, so the chart reads only the latest entry. Flows stay transaction-derived
(balance deltas would mix in market growth). Account names here are transaction account names, linked to
balance accounts through the same `app_account` mapping.

## 5. Open items for you to confirm (defaults I will use if you don't object)

1. **Download method.** *Default:* Playwright clicks Monarch's own balance-history download, reusing the
   existing `monarch-browser` profile (matches the transaction job, robust to API changes). *Alternative:*
   `fetch('download-balances')` from inside that same page context with the CSRF header, which is faster and
   needs no menu navigation but breaks if Monarch changes the endpoint. Phase 0 tries the click first and
   falls back to the in-page fetch.
2. **Identity.** *Default:* normalized name is the key, with no alias-merge in v1 (a replaced account simply
   shows as a closed row plus a new row, and both can map to one app account). *Alternative:* alias-merge UI.
   Defer unless renames start fragmenting charts.
3. **Closed accounts.** *Default:* value is 0 after the last row, which is why a closed account never
   inflates history. *Alternative:* carry the last balance forward, which is wrong for net worth.
4. **Flows definitions.** *Default:* credits = money moved into investment accounts, debits = money moved out,
   total = credits − debits. This reverses the existing `net = withdrawals − contributions` sign, so I would
   label it "Net contributions" to avoid confusion. Tell me if you want the old sign.
5. **Transaction history depth.** Monthly flows need transactions before this year. `input_backup/ytd_transactions.csv`
   starts 2025-01-01, so the flows line would start January 2025. Confirm this is acceptable.
6. **Dates before 2024-01-10.** Monarch has none, so those dates fall back to plan-derived log values.

## 6. Implementation plan

Models: **Sonnet 5.5** for mechanical or well-specified work, **Opus 5.5** for the correctness-critical logic.
Usage is relative to one 5-hour Pro-plan session (light < 10%, moderate ≈ 10–25%, heavy ≈ 25–40%). These
are relative estimates, not token counts. **Check `/usage` after each phase and compare with these estimates.**

| # | Phase | Model / effort | Usage | Context drivers | Done when |
|---|---|---|---|---|---|
| 0 | **Spike:** confirm the download path against the live Monarch UI (click vs in-page fetch). Save one real CSV as a test fixture (redacted). | Sonnet 5.5 / medium | Light | **HAR is 920 KB, so never read it whole.** Grep it for `download-balances` only. Reading `monarch_extract.py` 1082–1230 plus `register_monarch_extract_task.ps1`. | A script downloads `balances.csv` headlessly, twice in a row. |
| 1 | **Extractor** `monarch_balances.py` (download, `utf-8-sig`, ISO dates, name normalization, write `raw/` plus `output/balances.csv`) and chain it in `run_monarch.ps1`. | Sonnet 5.5 / medium | Moderate | Small new file. Copy only launch/login helpers by function, not by whole-file read. | Fixture normalizes to 18,029 rows, 41 keys. Transactions step still passes if balances fails. |
| 2 | **Balance store + import** (schema, upsert, guards, `import_runs`, call from `monarch_autoimport_job.py`, first-run backfill). Check the file-elimination guard first. | Sonnet 5.5 / medium | Moderate | `monarch_autoimport_job.py` 124 lines, `datasets.py` 216, the guard test. Keep it to those. | Importing the fixture twice leaves 18,029 rows. Latest-day sum = **6,566,764.29**. Bad header and stale file are quarantined. |
| 3 | **Registry, classifier, prefs, API endpoints.** | Sonnet 5.5 / medium | Moderate | `main.py` 128 lines. Read `test_trends_reporter_server_functional.py` first (interface contract). Classifier tested against all 41 names. | Endpoints round-trip. Every current name classifies as expected. Origin check still blocks cross-origin. |
| 4 | **Series engine** (carry-forward, closure = 0, toggles, source merge) and integrate into `trends_metrics.py` as the fallback and per-run log summary. | **Opus 5.5 / high** | Moderate | Pure functions plus `trends_metrics.py` 272 lines. A short test-fix loop is the main variable. | Property tests: totals equal the sum of enabled accounts, closed accounts go to 0, toggling is order-independent. |
| 5 | **Monthly flows backend** (`investment_net_flows_monthly`) in `ytd_tracking.py`. | **Opus 5.5 / high** | **Heavy, the costliest step** | `ytd_tracking.py` is large: **Grep `net_flows_by_account` and `passthrough` and read only those regions (around line 1562–1730), never the whole file.** Passthrough logic is subtle. | Monthly sums over the year equal the existing YTD figures for every account. |
| 6 | **Frontend:** Accounts panel, per-chart popovers, series-driven Net worth/Holdings, zero-hiding rollover, flows line chart + YTD summary, freshness banner. | Sonnet 5.5 / high | **Heavy** | `index.html` 330 + `charts.js` 485 (both readable). Existing frontend tests under `tests/frontend`. Visual checks in the preview browser are the loop driver. | Verified in the browser: toggles change the lines, hover omits zeros, flows chart matches the summary. |
| 7 | **Verification and review:** full `pytest -m "not slow"`, `npm test`, `/code-review`, then a real end-to-end run through the 03:30 → 04:00 chain. | Sonnet 5.5 / medium | Light–moderate | Test output only. Keep failures to targeted reruns. | CI green. One scheduled run produces a fresh balances row and the chart updates. |

**Disproportionately expensive steps and how to scope them down**

- *Phase 5:* the broad `ytd_tracking.py` read is the risk. Grep first, then read about 150 lines. If the
  passthrough logic proves entangled, compute monthly flows from the same transaction rows with a thin
  wrapper rather than modifying the existing function.
- *Phase 6:* the visual iteration loop can balloon. Do the Accounts panel and toggles (data) first, the flows
  chart second, and style polish last. Screenshot once per milestone, not per edit.
- *Phase 0:* do not open the HAR in the editor. A targeted grep is enough.
- Golden masters are not touched (this work is outside the planning engine). If any golden-master test
  unexpectedly changes, run `tools/regen_golden_master.py measure` first and never regenerate in a loop.

**Total:** roughly one to one-and-a-half 5-hour sessions across phases. Phases 0–4 fit in one session. Phases
5–6 are the bulk and are best run as separate sessions.

## 7. Risks

- Monarch changes the download UI or endpoint: the failure is caught by the guards and shows a stale banner
  instead of wrong numbers.
- A name edit in Monarch creates a "new" account and closes the old one: totals stay right (old → 0, new
  starts), the UI flags "New" so the type can be set.
- Hidden accounts in Monarch (the "Show 11 hidden accounts" rows in the screenshot) may or may not be in the
  export. The sample shows 41 accounts, so it appears they are included. Phase 0 confirms.
- Balance store contains real financial data: gitignored like `raw/`, never committed.

## 8. Phase 0 result (2026-10-14)

- **Download path confirmed: the Playwright click works headless.** On `https://app.monarch.com/accounts`
  (note: `app.monarch.com`, whereas `monarch_extract.py` uses `app.monarchmoney.com`, which redirects) the
  button `get_by_role("button", name="Download CSV", exact=True)` triggers `POST api.monarch.com/download-balances/`
  with body `{}` and saves `Balances_<ts>.csv`. The saved login profile (`monarch-browser`) was already
  authenticated. No in-page-fetch fallback is needed.
- The headless file matches the sample: 18,029 rows, 41 accounts, latest-day sum **6,566,764.29**.
- **Format differences the normalizer must accept:** headless dates are ISO (`2024-01-10`) while the manual
  download used `m/d/yyyy`; amounts differ cosmetically (`168376.00` vs `168376`).
- The raw CSV is in `Monarch Extractor/raw/spike/` (gitignored); Phase 1 will turn it into a redacted fixture.
