# Shared view of Financial Insight for guests and advisors: design (Phase 9)

Status: draft (design only; owner decisions recorded 2026-11-18 in sections 3 and 13; no code, migration or test is written until the owner signs off this design and multi-user-shared-view-security-review.md)
Date: 2026-11-18

Scope: let the owner of a plan on the multi-user server show a **read-only Financial Insight (FI) view** of that plan to
someone else (a guest such as an advisor or a family member) without giving that person any way into the owner's
workspace, worker or planner, or into anyone else's data. This is Phase 9 of `multi-user-insights-followups-plan.md`
and the only follow-up that crosses the per-user isolation boundary that `multi-user-multiple-plans-design.md`
(section 11, decision 2) and `multi-user-server-security-review.md` hold. Builds on `multi-user-insights-design.md`
(FI served by each user's own worker) and `multi-user-server-gateway-design.md` (accounts, TOTP, sessions).

Companion document: multi-user-shared-view-security-review.md (threat model, abuse cases, controls mapped to tests,
sign-off checklist). Every claim about existing code below cites the file and line that was read; "not verified"
marks what was not. Line numbers are as of main at `329d4fe`, after Phase 8 (PR #481) merged.

## 0. Summary

**Recommendation: Option A, a published snapshot.** When the owner publishes, the owner's own worker renders the chosen
tabs of their active plan through the same percent functions the desktop remote view uses. The gateway checks that
output and stores it as one JSON record under its locked data root. A guest signs in to the gateway (password and
mandatory TOTP, as every account does today) with a new low-privilege **viewer** account. A small, separate route table
in the gateway serves the guest that record and nothing else. A viewer session never reaches any worker, so the rule
"the session's own user id selects the worker" (`src/gateway/proxy.py:73,114`) stays intact.

Two findings in the code shape the design (section 2):

1. **The desktop tab limit is not a server-side control.** A grant's `views` list is used only by `whoami` and by the
   `/api/view` report. The data routes of a tab outside the grant still answer 200: reproduced in process on
   2026-11-18 (security review, finding F1). Phase 9 reuses the vocabulary and the percent functions, but it enforces
   tabs **by construction**: a record contains only the routes of the granted tabs.
2. **The gateway gate forwards every signed-in, non-gateway request to a worker, whatever the role**
   (`src/gateway/app.py:283-300`). The supervisor starts and provisions a worker for any account id
   (`src/gateway/supervisor.py:180-193,442-450`). Phase 8's scheduler would also pick any active account and start its
   worker (`src/gateway/insights_schedule.py:122-125,143`). A guest account therefore has to be split off at the gate,
   before any forwarding, with refusals in the proxy and the supervisor as a second and third layer, and the scheduler
   must select members only.

## 1. Requirements

### 1.1 What is being asked

The owner of a plan wants another person to look at that plan's Financial Insight: trends, the current snapshot of
holdings, and projections. That person must see only what the owner chose, only for as long as the owner allows, and
must not be able to change anything or reach anything else.

### 1.2 Requirements

| # | Requirement |
|---|---|
| R1 | A guest sees only records granted to their own account. Nothing in a request can widen that set (session to record, never request to record). |
| R2 | The guest's code path never opens the owner's plan, workspace or worker, and never starts a worker. |
| R3 | What a guest may see is decided on the server when the record is built (money view, tabs). No filtering is left to the guest's browser. |
| R4 | Guests authenticate like every gateway account: password, mandatory TOTP, lockout, throttling. Their sessions are shorter. |
| R5 | The owner can revoke at once (the guest's next request), every share expires, and the owner can see who looked and when. |
| R6 | Expired, revoked and unknown records give the same response (no existence leak). A revoked record's data is deleted. |
| R7 | Records live under the gateway's locked data root and are covered by `acl check` and by backups as decided in section 8. |
| R8 | Audit events (created, published, viewed, revoked, expired) carry ids only, never amounts. |
| R9 | The guest route table is a new, minimal, deny-by-default table. It is not an extension of the planner's allow-list or of FI's worker allow-list. |
| R10 | No secret appears in a URL. There is no "share link": the guest's own session is the only credential. |
| R11 | No download or export unless the owner decides otherwise (question 5). |
| R12 | Admins manage accounts but cannot create, read or change shares (keeps "admins do not see user data", `multi-user-insights-design.md` section 5). |

### 1.3 Not in scope

- Letting a guest change anything: no **Update**, no account settings, no pass-through decisions, no plan edits.
- Sharing the planner itself, plan files or builds. The multi-plan decision "No copying of plans between users"
  (`multi-user-multiple-plans-design.md` section 11, decision 2) is unchanged.
- The desktop FI (ports 5057/5058) and its `identity.db` guests. That listener's tab-limit gap (finding F1) is reported
  as a separate fix; it is not built here.

## 2. What exists today (findings)

| Area | Fact | Evidence |
|---|---|---|
| Grant vocabulary to reuse | Desktop FI grant: `money_view` is `dollars`, `percent` or `both`; `views` is a JSON list of tabs `live`, `trends`, `projections` | `src/identity/store.py:32,58-66,386-405`; `financial_trends_reporter/access_routes.py:26` |
| Percent filter: server-side on the desktop | An after-request hook scales every `/api/` JSON body for a percent person, strips detail per route, withholds transactions and replaces error bodies | `access_routes.py:46-49,140-141,151-168`; `percent_view.py:68-83,136-150` |
| Tab limit: client-side only on the desktop | The server reads `views` only in `whoami` and the `/api/view` report; the page hides tabs; the other tabs' data routes answer 200 | `access_routes.py:236,244,329-331`; `financial_trends_reporter/frontend/index.html:1014-1037`; probe (security review F1); `tests/test_insights_grant_gate_functional.py:79-87` covers only `whoami` and `/api/view` |
| Worker-mode FI has no percent hook | `create_app(mode="worker")` registers the worker gate and returns before `register_access` | `financial_trends_reporter/main.py:470-472` (desktop wiring `473-482`) |
| The percent functions are pure | `scale_basis`, `scale_payload`, `strip_detail`, `find_money_leaks` take data and return new data | `percent_view.py:52-65,68-83,136-150,153-173` |
| The desktop percent basis includes plan annuity values | `scale_basis(balances_db, history, plan_annuity_values.account_values(...))` | `main.py:479-481` |
| `projections.py` loads; it does not filter | It finds the active plan's latest build output and returns `{"missing": True}` when stale | `financial_trends_reporter/projections.py:26-35,85-96` |
| FI serves the active plan only, read-only per request | The worker wrapper holds `read_only_plan_access()` for the whole request; FI resolves the active plan | `financial_trends_reporter/worker_mode.py:3-5,57-67`; `projections.py:86` |
| FI error bodies carry exception text | The worker mount replaces 5xx error text with a generic message | `main.py:346-348,356-358`; `src/remote_insights_mount.py:94-96` |
| The gate forwards with no role check | After the session, stage, must-change and admin-path checks, every non-gateway path goes to `up.forward` | `src/gateway/app.py:283-300` |
| Gateway-owned paths get protective headers | `no-store`, `X-Frame-Options: DENY`, `no-referrer` and the CSP are set for gateway paths and some status codes only | `app.py:40,171-172,314-324` |
| Any account id gets a worker | `endpoint` starts a worker; `_start` and `user_created` create the workspace and the Windows account | `src/gateway/supervisor.py:170,180-193,214-219,442-450` |
| The role column is a closed set | `role TEXT NOT NULL CHECK (role IN ('admin', 'user'))`; migrations are additive, one transaction each | `src/gateway/store.py:54,48-117,214-224` |
| Account expiry exists and is enforced per request | `users.expires_at` (admin console phase 2; the brief calls it `access_expires`) | `store.py:111-116,610-612` |
| Sessions | Hashed tokens, pending 5 min, idle 15 min, absolute 12 h, CSRF per session, `__Host-` cookie `SameSite=Strict` | `store.py:38-40,153-154,590-617`; `app.py:30,135-136` |
| Sign-in stages | Password -> pending session -> TOTP -> active, with rotation; pending and must-change sessions reach short lists only | `app.py:42-45,268-275,285-288,394-416,424-432` |
| Admin namespace denied by default | Prefix match before any route runs, pinned by a contract test | `app.py:33-35,153-154,289-290`; `tests/test_gateway_admin_guard_contract.py` |
| Gateway-served files use exact allowlists | `STATIC` and `ADMIN_STATIC` name every file | `app.py:36,373-377`; `src/gateway/admin_console.py:25-32` |
| Every account id feeds backups and the supervisor | `store.user_ids()` is all rows | `store.py:660-661`; `src/gateway/server.py:302,309` |
| Phase 8's scheduler treats every active account as an FI user | `eligible_users` keeps every account that is neither disabled nor expired; `_update_user` then starts that account's worker | `src/gateway/insights_schedule.py:122-125,137-156`; `server.py:322-323` |
| A direct worker call already exists | `call_worker` sends one request with the worker token and reads at most 8 MiB, with no sign that it stopped short | `src/gateway/supervisor.py:131-144` (read cap at `:142`); used by the scheduler, `insights_schedule.py:130` |
| `acl check` walks only user folders | The data root's own entry is checked, `users/<id>` folders are walked | `src/gateway/acl.py:245-271` |
| Archive format 3 | `gateway.db` archived whole; insight files are a separate strict member family; restoring `gateway.db` writes a new file | `src/gateway/backup_store.py:36,42,47,52,54,251-254,419-442` |
| An old `gateway.db` revives old state | Open item P7-O12 (deleted or disabled users come back) | `multi-user-server-security-review.md`, "Open" table |
| Planner and FI allow-lists are separate, deny by default | About 270 planner pairs; FI's own worker table | `src/server/remote_allowlist.py:1-15,30,286`; `financial_trends_reporter/worker_allowlist.py:17-59` |
| Route prefixes are free | No planner, FI or gateway route uses `/api/share`, `/api/viewer`, `/gateway/viewer` or `/gateway/sharing` | Grep of `src/`, `financial_trends_reporter/*.py` and `admin_app/*.py`, 2026-11-18 |

## 3. The owner's five questions (answered 2026-11-18)

The owner answered all five on 2026-11-18. Four answers are the recommended default. Q4 takes a **90-day** default
expiry instead of the recommended 30 days, which is a setting, not a design change. The right-hand column is kept as a
record of what another answer would have changed. Only one alternative (a live view) would have replaced part of the
build.

| # | Question | Owner's answer (2026-11-18) | If the owner had chosen otherwise |
|---|---|---|---|
| Q1 | Who are the viewers? **Answered: recommended default** | New low-privilege **viewer accounts** in `gateway.db` (`kind = 'viewer'`), created by an admin, each sponsored by exactly one owner. Existing server users cannot be grantees in v1. | "Existing users too": a policy switch (who may be a grantee), no schema change. The text-only rendering test (section 10) becomes a hard gate first, because the owner's text would then render inside a planner session. "Owners create their own viewers": one owner route and a per-owner cap; no schema change. |
| Q2 | Live look or published copy? **Answered: recommended default** | **Published point-in-time copy** (Option A). The owner refreshes it with a button; optionally Phase 8's scheduler refreshes it after each scheduled update. | "Near-live" (refresh every N hours) stays inside A: a setting. A true live view is Option B, which replaces 9b and 9c with per-guest enforcement in every FI route. The data model, accounts, gate branch, owner UI and tests carry over. |
| Q3 | What may a guest see? **Answered: recommended default** | Per share: **percent view** by default (amounts as a percent of today's net worth); the owner may choose dollars for a share. Tabs are chosen by the owner from Snapshot, Trends and Projections (all three ticked by default). Real account names are shown (decision 3b). Never: transactions, account settings, update controls, any write. | Dollars: one field value. Fewer or more tabs: the same list. "Hide account names": one more projection step in 9b (decision 3b, section 13). |
| Q4 | Revoke, expiry, who looked? **Answered: 90-day default (recommended was 30)** | Revoke takes effect on the guest's next request; every share expires (default **90 days**, maximum 365, renewable); the owner sees a view log (viewer name and time, no address); the admin audit has ids only. | Other expiry limits are settings. Showing the guest's address to the owner: one column. "No expiry": a setting, not recommended. |
| Q5 | Download or export? **Answered: recommended default** | **No** download or export in v1. No route exists. A guest can still print or screenshot what is on screen (residual risk). | "Yes": an export route that renders the same stored record, so its scope matches by construction. It is audited and adds no new data path. |

## 4. Options

| Option | Idea | Isolation | Freshness | Code surface | Verdict |
|---|---|---|---|---|---|
| A. Published snapshot | The owner's worker renders the granted view into a record; the gateway stores it; a guest session is served the record by a small gateway viewer | **Holds.** The guest never reaches a worker; `forward` and `endpoint` keep selecting the session's own worker | As of the last publish (button, optional schedule) | One worker route, a gateway publisher, the viewer routes and two pages | **Recommended** |
| B. Live read through the owner's worker | The gateway proxies a guest to the owner's worker with a scoped grant | **Crossed.** A guest session would select another user's worker, the one invariant every isolation test relies on (`proxy.py:73,114`). Every FI route, including parameterised ones, would need per-guest enforcement in the worker, and today's tab limit is client-side (F1) | Live | Large: per-route scope checks, a guest identity header trusted by the worker, guest load on the owner's worker | Rejected |
| C. Export a file | The owner downloads a page or PDF and sends it | None needed | Fixed | Small (a worker export route) | Fallback only; see Q5 |

Why A and not B, in short:

1. **Blast radius.** In A, a bug in the guest path can leak, at worst, one record the owner already chose to share. In
   B, a bug in any FI route leaks the owner's live data outside the grant, and a bug in the proxy change could select
   any user's worker.
2. **Enforcement location.** A filters once, at publish time, in code that runs under the owner's own Windows account
   and can read only the owner's workspace. B filters on every request, in every route, for a principal the worker has
   never served before.
3. **Load and lifetime.** In A, a guest's reading never starts or keeps alive the owner's worker. In B, it does both.

## 5. Design

### 5.1 The new rule and its layers

**A viewer session is answered only by the gateway. It never reaches a worker.**

1. **Gate.** The session lookup already joins `users` (`store.py:605-606`). It also reads the new `kind` column. For any
   kind other than exactly `member`, the gate answers only the viewer route table (5.6). This branch sits after the
   stage and must-change checks (`app.py:268-288`) and before the admin-path check, the gateway-path return and the
   forward (`app.py:289-300`). It fails closed: an unknown kind is treated as a viewer.
2. **Proxy.** `Identity` gains `kind`, default `"member"`; it is built in one place (`app.py:283`). `WorkerProxy.forward`
   refuses any identity whose kind is not exactly `member` (503 with a generic body, plus an audit event).
3. **Supervisor.** `endpoint`, `_start` and `user_created` take a store predicate and refuse an id that is not a
   member. A viewer therefore never gets a workspace, a Windows account (`accounts.ensure`) or a worker.
4. **Data.** A viewer has no `data/users/<id>` folder and no `worker_accounts` row. Per-workspace consumers (backups,
   the supervisor's known ids, `server.py:302,309`) switch from `user_ids()` to a new `member_ids()`. Phase 8's
   scheduler selects members only: `eligible_users` (`insights_schedule.py:122-125`) adds a positive `kind == "member"`
   test, so a viewer is never offered to `_update_user`, which would start a worker (`insights_schedule.py:143`).

### 5.2 Data model (`gateway.db` migration step 4)

Additive, in the style of step 3 (`store.py:111-116`), applied in one transaction like every step (`store.py:214-224`).
`SCHEMA_VERSION` goes from 3 to 4. An old gateway refuses a newer database, as it does today (`store.py:217-218`).

```sql
ALTER TABLE users ADD COLUMN kind TEXT NOT NULL DEFAULT 'member'
    CHECK (kind IN ('member', 'viewer') AND (kind = 'member' OR role = 'user'));
ALTER TABLE users ADD COLUMN sponsor_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

CREATE TABLE shares (
    id TEXT PRIMARY KEY CHECK (length(id) = 32),            -- secrets.token_hex(16); not a capability
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grantee_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL DEFAULT '',                        -- the plan the first publish rendered
    title TEXT NOT NULL,                                     -- the owner's words, normalised like plan names
    money_view TEXT NOT NULL CHECK (money_view IN ('percent', 'dollars')),
    views TEXT NOT NULL,                                     -- JSON list, a subset of live, trends, projections
    scope_rev INTEGER NOT NULL DEFAULT 1,                    -- +1 on every scope change
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'suspended', 'revoked')),
    state_reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    published_at REAL,                                       -- NULL: nothing to serve
    published_rev INTEGER,
    snapshot_sha256 TEXT,
    snapshot_bytes INTEGER,
    CHECK (owner_user_id <> grantee_user_id)
);
CREATE INDEX shares_grantee ON shares(grantee_user_id, state);
CREATE INDEX shares_owner ON shares(owner_user_id, state);

CREATE TABLE share_access_log (                              -- the owner's "who looked and when"
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_id TEXT NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
    viewer_user_id INTEGER,
    at REAL NOT NULL
);
CREATE INDEX share_access_log_share ON share_access_log(share_id, at);
```

Decisions inside the model:

- **A viewer is an account with `kind = 'viewer'`, not a new role.** `role` is a closed `CHECK` (`store.py:54`).
  Changing it needs a table rebuild with foreign keys switched off. SQLite ignores that pragma inside a transaction,
  and the runner applies each step inside one (`store.py:214-224`). A separate column also leaves admin and user
  semantics untouched: `is_admin` stays `role == "admin"` (`src/gateway/upstream.py:36-37`). The `CHECK` makes "viewer
  and admin" impossible, and `set_role` (`store.py:327-338`) also refuses viewers.
- **One id space, one login path.** Viewers live in the same `users` table, so password hashing, TOTP, lockout,
  throttling, expiry, audit and the admin console are reused unchanged. Separate tables would duplicate that code and
  create two id spaces: viewer 3 and user 3 would be one confusion away from the wrong worker.
- **Sponsor.** `sponsor_user_id` is NULL for members. For a viewer it is the one owner who may grant that viewer shares.
  It is what lets an owner pick a grantee without browsing or probing other accounts (no enumeration). An advisor who
  serves two owners gets two viewer accounts. Relaxing this later is a policy change only (Q1).
- **Scope reuses the grant vocabulary, not the store.** `money_view` and `views` carry the same names as the identity
  grant (`src/identity/store.py:61-62`) and the same tab names (`access_routes.py:26`; `worker_mode.py:25`). The
  desktop's `both` corresponds to the share's `dollars`: the page may toggle to percent, and nothing is hidden.
  Desktop guests (`identity.db`) and server accounts (`gateway.db`) stay separate on purpose
  (`multi-user-server-gateway-design.md`, "Reuse of the trends reporter's access code").
- **Binding the record to its row.** `published_rev`, `snapshot_sha256` and `snapshot_bytes` pin the stored file. A
  file that does not match its row is never served (5.5).
- **Retention.** Revoked rows stay 90 days so the owner's history makes sense, then they are purged together with their
  access log. Expired rows are kept the same way.
- **Limits.** At most 10 shares per owner and 5 viewers per sponsor (settings). At most one publish per share per minute.

### 5.3 What a record may contain (scope)

Tabs and the FI routes rendered into them. The mapping comes from the page's fetch sites (`index.html:352-361`,
`683-710`; `charts.js:661`; `live_snapshot.js:529`; `realized.js:228`; `projections.js:142`, all under
`financial_trends_reporter/frontend/`):

| Grant name | Tab label | Routes rendered | Parameters pre-rendered |
|---|---|---|---|
| `trends` | Trends | `/api/history`, `/api/balances`, `/api/flows`, `/api/liquid-change`, `/api/spending` | `/api/spending` for each fixed Time scope: 1 Week, 1 Month, 3 Months, 6 Months, YTD, 1 Year, All Time (`index.html:353-361`); Custom is not offered |
| `live` | Snapshot | `/api/live-snapshot`, `/api/realized` | `live-snapshot` per fixed Time scope, prices frozen at publish (no refresh); `realized` for the current and prior tax year |
| `projections` | Projections | `/api/projections` | none |

Which panel `realized` belongs to, and the exact query parameters of each route, are confirmed in 9b step 0 (not
verified here).

**Never included, in either money view:** `/api/spending/transactions` (transaction rows; withheld from percent guests
on the desktop, `access_routes.py:46`), `/api/accounts` and `/api/app-accounts` (account settings), `/api/run-status`,
`whoami`, and every `POST`.

**Percent view.** Each rendered payload goes through `percent_view.strip_detail(route, payload)` and then
`percent_view.scale_payload(payload, k)`. `k` is `percent_view.scale_basis(balances_db, history,
plan_annuity_values.account_values(...))`. These are the same calls, in the same order, with the same basis as the
desktop (`access_routes.py:161-165`; `main.py:479-481`). The result must then pass `percent_view.find_money_leaks(...)
== []`; any finding fails the publish. With no basis (balances not imported yet), the publish is refused with the same
plain message the desktop gives (`access_routes.py:161-163`).

**Dollars view.** Payloads exactly as the owner sees them, minus the never-included routes.

**Data that is not money passes through in both views.** The owner sees it in the preview before publishing: account
and category names, merchant names (dollars view only; percent collapses them to "All merchants",
`percent_view.py:86-94`), dates, counts, years, the owners' ages and the plan's first and last years
(`NON_MONEY_KEYS`, `percent_view.py:15-31`).

### 5.4 Publishing: the owner's worker renders, the gateway stores

```
Owner browser               Gateway (service account)                        Owner's worker (owner's account)
POST /api/share/<id>/publish
  (session, CSRF, Origin)  1. row WHERE id=? AND owner=<session user> AND state='active'; else uniform 404
                           2. per-owner lock; at most 2 publishes at once
                           3. supervisor.endpoint(<session user>)  -------->
                           4. POST /insights/api/share-snapshot          5. mount: token, loopback Host, Origin
                              worker token; body built from the ROW:     6. read_only_plan_access() for the request
                              expected plan, money view, views, rev      7. active plan == expected? else 409
                                                                         8. render granted routes in process
                                                                         9. percent: strip, scale, leak check
                           <-------------------------------------------- 10. JSON (scrubbed by the mount)
                          11. validate: 200, JSON, size cap, schema, keys within scope, leak check again
                          12. write <data_root>/shares/<id>.json.tmp, fsync, os.replace
                          13. UPDATE ... SET published_* WHERE id=? AND state='active' AND scope_rev=<rev sent>
                              (0 rows: a revoke or scope change won the race -> delete the file just written)
                          14. audit share_published (share id, owner id, rev, bytes)
```

**The worker route** is `POST /api/share-snapshot` in FI worker mode, reached through the existing mount at
`/insights/` (`src/remote_insights_mount.py:70-73` checks the token; `src/remote_worker.py:93-104` mounts FI). It gets
one new `ALLOWED` entry in `worker_allowlist.py`. It runs inside the read-only plan scope the worker wrapper already
holds (`worker_mode.py:66`). It dispatches FI's own `GET` handlers in process, so it uses the same code and caches as
the routes and adds no new reader of the plan. A non-200 result for a route marks that panel `{"available": false}`.
The error body is never copied (FI error bodies carry exception text, `main.py:346-348`). Output:

```json
{"schema": "shared_view/1", "share_id": "<32 hex>", "scope_rev": 3, "generated_at": "<ISO UTC>",
 "plan": {"id": "<plan id>", "name": "<plan name>"}, "money_view": "percent", "basis_date": "<date>",
 "views": {"trends": {"/api/history": "...", "/api/spending?scope=ytd": "..."}, "projections": {"/api/projections": "..."}}}
```

**Only the gateway calls that route.** `WorkerProxy.forward` refuses `/insights/api/share-snapshot` from any browser
session, the way it refuses build event streams (`proxy.py:77-78`). The publisher gets the owner's endpoint from
`supervisor.endpoint(<session user>)` and sends the request with the existing `call_worker`
(`src/gateway/supervisor.py:131-144`). Health checks and build polling use that helper, and so does Phase 8's scheduler
(`insights_schedule.py:130`). It reads at most 8 MiB and does not report a body it cut short (`supervisor.py:142`), so
it gains a `max_bytes` argument. The publisher reads the cap plus one byte and refuses an oversized body as too large,
never parsing a truncated one.

**What the gateway checks (step 11)** before anything is stored, treating the worker's output as untrusted input:

- HTTP 200, `application/json`, at most `--share-max-mb` (default 8 MiB, the existing `call_worker` read limit; 9b
  measures real sizes).
- Exactly the schema's top-level keys; `share_id` and `scope_rev` equal to the request; `views` keys within the row's
  `views`. A worker that returns more than it was asked for has a bug, so the publish fails (fail closed).
- For percent records, `percent_view.find_money_leaks` again, in the gateway. Whether that module imports cleanly in
  the gateway process is not verified (`percent_view.py:13` imports `balance_series`); 9b step 0 checks it.
- Every string is normalised before storing: Unicode NFC, control and bidi-override characters removed, each string
  capped (200 characters for names, the title 60, like plan names in `multi-user-multiple-plans-design.md` section 2).

**Triggers:** share creation (first publish), **Refresh now**, scope change, renewal and, optionally, Phase 8's
scheduler after a successful scheduled update. That hook sits in `InsightsScheduler._update_user` after the update
and before the worker is released, so it reuses the endpoint the scheduler already holds
(`insights_schedule.py:137-156`). A guest never triggers a publish.

**Refresh needs the share's plan to be active.** FI serves the active plan only (`worker_mode.py:3-5`;
`projections.py:86`). The worker answers 409 when the active plan is not the share's plan. The owner then sees
"Open <plan> in the planner to refresh this view", and the scheduler skips the share and reports it. Rendering a
non-active plan would need a change in active-plan resolution; it is left out of v1 (section 12).

### 5.5 Storage under the locked data root

- **Body:** `<data_root>/shares/<share_id>.json`, a sibling of `data/users/` (`supervisor.py:170`). The path is built
  from the row's id (checked against `^[0-9a-f]{32}$`), never from request text.
- **ACL:** gateway-only, like the data root and `data/users/` (`acl.py:6-9,164-166`). `acl setup` locks the folder.
  `acl check` gains a walked `check_private` for it beside the user-folder walk (`acl.py:251-260`), so a worker
  account that can read any record is a failure.
- **Integrity:** the viewer serves a body only when its SHA-256 equals `snapshot_sha256` and its embedded `share_id`
  and `scope_rev` equal the row's. A mismatch is a 404 to the guest and a `share_integrity_failed` audit event. The
  owner sees "republish".
- **Links:** the folder is gateway-only, so no worker can plant a junction in it. Reads still use
  `fsguard.has_reparse_point` like every other privileged gateway read (`backup_store.py:213,224`).
- **Housekeeping (hourly):** delete bodies whose row is missing, revoked, expired or unpublished; write
  `share_expired` once per expired share; purge revoked and expired rows after 90 days.
- **At rest:** the same protection as plan files (ACL, no extra encryption). Archives are encrypted (section 8).

### 5.6 The guest route table (`VIEWER_ALLOWED`)

A new module in `src/gateway/` (proposed name `viewer_routes.py`) holds a frozenset of `(method, rule)`, deny by
default. It is matched after routing, the way FI's worker gate does it (`worker_mode.py:82-86`). It is written out in
full and derived from nothing else: not from `remote_allowlist.py` and not from `worker_allowlist.py`.

| Method | Rule | Purpose | Exists today |
|---|---|---|---|
| GET | `/login` | sign-in page | yes (`PUBLIC`, `app.py:42`) |
| POST | `/api/auth/login` | password step | yes |
| GET | `/api/auth/session` | session JSON (gains `kind`; `insights` false for viewers) | yes (`app.py:496-506`) |
| POST | `/api/auth/totp/enrol/start`, `/api/auth/totp/enrol/confirm`, `/api/auth/totp/verify` | second factor | yes (`PENDING_ALLOWED`, `app.py:43-44`) |
| GET | `/gateway/enrol` | enrolment page | yes |
| POST | `/api/auth/logout` | sign out (adds `Clear-Site-Data: "cache"` for viewers) | yes (`app.py:486-494`) |
| POST | `/api/auth/password` | change password | yes (`MUST_CHANGE_ALLOWED`, `app.py:45`) |
| GET | `/gateway/account` | account page | yes |
| GET | `/gateway/static/<name>` | `gateway.js`, `gateway.css` | yes (`app.py:36,373-377`) |
| GET | `/gateway/viewer` | the guest page | new |
| GET | `/gateway/viewer/static/<name>` | exact file allowlist, like `ADMIN_STATIC` | new |
| GET | `/api/viewer/shares` | my shares: id, title, owner's display name, as-of, expiry, views, money view | new |
| GET | `/api/viewer/shares/<share_id>` | one record body | new |
| GET | `/api/viewer/shares/<share_id>/status` | still available? (background poll) | new |

**Everything else** a viewer session asks for gets a 404 JSON body for `/api/...` paths and a 302 to `/gateway/viewer`
for any page, including `/`. The login page sends a signed-in browser to `next` or `/`
(`src/gateway/pages/gateway.js:55-58,96,115`), so a guest lands on their page. This covers every planner path, `/insights/...`, `/gateway/admin*`, `/api/auth/admin/*`,
`/gateway/users`, and the owner routes `/api/share/*` and `/gateway/sharing`.

**Selection rule (session to record).** `/api/viewer/shares` takes no identifier. It lists rows where
`grantee_user_id = <session user>`, `state = 'active'`, `expires_at > now`, the record is published and the owner's
account is usable. The id in the other two routes can only pick within that set, because the query always includes
`grantee_user_id = <session user>`. Another guest's id, a revoked, expired, unknown or malformed id all get the same
404 body. This is the rule the multi-plan design uses for plan ids (`multi-user-multiple-plans-design.md` section 2).
A strict alternative is decision 9: one share per viewer account, and routes that take no id at all.

**Headers and limits come from existing gateway code.** `/api/viewer/` and `/api/share/` join `_is_gateway_path`
(`app.py:171-172`), so they are never forwarded and get `no-store`, `X-Frame-Options: DENY`, `no-referrer` and the CSP
(`app.py:314-324`). A viewer's request bodies stay under the 32 KiB gateway cap (`app.py:60`), because the branch
returns before the forward-only raise (`app.py:293`). The status route honours `X-Background-Poll: 1`, as `/insights/`
does (`app.py:278-282`), so an open tab does not keep a guest's session alive.

### 5.7 Sign-in, TOTP and sessions for viewers

- **Same path:** the same login, the same mandatory TOTP (enrolment on first sign-in), the same lockout and throttles
  (`app.py:380-416,447-463`). An admin-created account starts with `must_change`, so the temporary password works only
  for the auth API and the account page (`app.py:45,285-288`).
- **Shorter sessions:** idle 10 minutes and absolute 2 hours for viewers; members keep 15 minutes and 12 hours
  (`store.py:38-39`). `get_session` already joins the user row (`store.py:605-606`) and applies the kind's idle limit;
  `create_session` and `rotate_session` (`store.py:590-599,624-636`) set the kind's absolute limit.
- **Enrol-by deadline:** a viewer who has not enrolled TOTP within 72 hours of creation, or of an admin reset, is locked
  until an admin issues a new temporary password. Today nothing limits that wait (`create_user`, `store.py:265-284`), so
  whoever first uses an intercepted temporary password enrols their own phone.
- **Admin resets suspend shares:** when an admin resets a viewer's password or TOTP, that viewer's shares become
  `suspended` (`state_reason = 'credentials reset'`) until the owner enables them again. An admin therefore cannot
  quietly become a guest.

### 5.8 Owner routes (members only; refused to viewers by 5.6)

| Method | Rule | Behaviour |
|---|---|---|
| GET | `/gateway/sharing`, `/gateway/sharing/static/<name>` | owner page; exact file allowlist |
| GET | `/api/share/list` | my shares with state, scope, as-of, expiry and last viewed |
| GET | `/api/share/viewers` | viewer accounts I sponsor: display name, account expiry, enrolled yes or no |
| POST | `/api/share/create` | `{viewer_id, title, money_view, views, expires_in_days, expected_plan_id}`: the row, then the first publish |
| GET | `/api/share/<share_id>/preview` | the stored body, exactly what the guest receives |
| POST | `/api/share/<share_id>/publish` | refresh now |
| POST | `/api/share/<share_id>/scope` | `{money_view, views}`: delete the body first, `scope_rev + 1`, republish |
| POST | `/api/share/<share_id>/expiry` | `{expires_in_days}`: renew or shorten, at most `--share-max-days` |
| POST | `/api/share/<share_id>/revoke` | revoke now |
| POST | `/api/share/<share_id>/enable` | enable a suspended share (republishes) |
| GET | `/api/share/<share_id>/views` | the access log for this share |

Every query includes `owner_user_id = <session user>`. Any other id gets one uniform 404. A `viewer_id` that is not a
viewer sponsored by the session user gets the same "That viewer was not found." The gate already enforces CSRF,
`Origin`, Fetch-Metadata and body types on every unsafe request (`app.py:243-267`). `expected_plan_id` is the plan the
owner saw on the page. The worker refuses a mismatch, so switching plans in another tab cannot publish the wrong plan.

### 5.9 Audit and the owner's access log

Gateway audit events (`store.py:230-235`; details are at most 300 characters, `store.py:42`) carry ids and counts
only: `viewer_created`, `share_created`, `share_published` (rev, bytes), `share_publish_failed` (a reason code),
`share_scope_changed`, `share_viewed` (once per session and share), `share_revoked`, `share_expired`, `share_suspended`
(reason), `share_enabled`, `share_integrity_failed` and `viewer_forward_refused`. Never amounts, titles or record
content.

The owner's view log is `share_access_log`: one row per guest session and share at most every 10 minutes, kept 90
days, showing the viewer's display name and the time. The guest's address stays in the admin audit only (`client_ip`).

### 5.10 Flags and settings

`--shared-views` (default off; the gateway refuses to start with it unless `--insights` is also on). When it is off,
the owner and viewer routes return 404, nothing is published, and stored rows and bodies are kept. Settings:
`--share-max-mb` (8), `--share-default-days` (90), `--share-max-days` (365), `--viewer-idle-minutes` (10),
`--viewer-max-hours` (2), `--max-shares-per-owner` (10), `--max-viewers-per-sponsor` (5).

## 6. UI

### 6.1 Guest (`/gateway/viewer`)

- After sign-in: the list of what is shared with me. If there is only one, it opens directly.
- Header: "Shared by <owner display name>", the title, **"As of <date and time>"** always visible (with a "more than
  7 days old" badge), and, for percent records, "Amounts are shown as a percent of net worth on <basis date>".
  **Sign out** is always there.
- Only the tabs present in the record. The Time scope offers only the pre-rendered presets. There is no **Update**, no
  account editing and no download.
- When a share is unavailable (revoked, expired, unknown): "This view is not available. Ask the person who shared it
  with you." The text is the same in every case.
- **Rendering is text only.** Record strings are inserted as text (`textContent` or escaped templates), never as HTML,
  under the gateway CSP (`default-src 'self'`, no inline script; `app.py:40`).
- **Reuse.** If FI's chart modules (`charts.js`, `projections.js`, `live_snapshot.js` and others) can render from a data
  object without `index.html`'s inline script, the gateway serves them through the exact allowlist. Otherwise a small
  viewer renderer is written. 9c step 0 decides (not verified here).
- A status poll every 60 seconds, sent as a background poll. When the share is no longer available, the page clears its
  content and shows the message above. On sign-out the page clears its content as well.

### 6.2 Owner (`/gateway/sharing`)

- A **Share...** link in the FI header. It is a page link, so FI's `BASE` rule for fetches is unaffected
  (`financial_trends_reporter/frontend/insights_client.js:14-18`).
- Three sections: **Shared views** (a table with Refresh, Change what is shared, Extend, Revoke, Preview, Who looked),
  **Share a view**, and **My viewers** (the accounts an admin created for me, with expiry and whether they have signed
  in yet).
- Share a view: choose the viewer -> choose what to share (default: percent view, all three tabs) -> choose the expiry
  (default 90 days) -> **preview exactly what the guest will see** -> Publish.
- Three plain statements shown when creating a share: (1) percent hides amounts only from someone who knows none of
  them; (2) the guest can keep anything they have seen; (3) this is a copy as of now and does not update by itself
  unless scheduled.
- Refresh needs the plan to be open in the planner; the page says so plainly.

### 6.3 Admin console

- The users list gains **Kind** (Member or Viewer) and **Sponsor**, plus the number of shares each account owns and
  receives (counts only).
- **Add viewer:** display name, username, temporary password, sponsor (a member) and account expiry (default 90 days).
  It does not run the `user_created` lifecycle hook, so no workspace and no Windows account are created
  (`supervisor.py:442-450`).
- Role change is hidden and refused for viewers. Disable, delete and the resets work as for any account; a reset also
  suspends the viewer's shares (5.7).
- Admins cannot create, read or change shares.
- `users.js` is shared with the desktop Admin app and served from `admin_app/frontend` (`admin_console.py:25-32`). The
  new columns sit behind a `FEATURES` flag like the existing ones (`admin_console.py:36-40`). `users.js` itself was not
  read for this design.

## 7. Lifecycle

| Event | Effect |
|---|---|
| Create | Row `active` and unpublished, then the first publish. If it fails, the row stays unpublished and the guest sees "not available". |
| Refresh | Republish when the owner's active plan is the share's plan; otherwise refused with a plain message (the scheduler skips the share). |
| Scope change | The body is deleted first, `scope_rev + 1`, then a republish. A failed republish leaves nothing to serve, never the wider old body. |
| Revoke | `state = 'revoked'`; the body is deleted after the commit. The guest's next request gets the uniform 404, and an open tab clears itself within 60 seconds. |
| Expiry | At `expires_at` the guest gets the same 404. Housekeeping deletes the body and audits `share_expired` once. The owner can renew, which republishes. |
| Owner disabled, or the owner's account expired | Nothing is served while the owner's account is unusable (the viewer query joins the owner's row); bodies are kept and serve again when the owner is re-enabled. |
| Owner deleted | Sponsored viewers are deleted (audited); shares cascade (`ON DELETE CASCADE`); bodies are purged in the same lifecycle step that removes the workspace (`supervisor.py:460-472`); housekeeping is the backstop. |
| Viewer disabled or expired | Sessions end (existing, `store.py:610-616`); nothing is served to them. |
| Viewer deleted | Sessions, TOTP and shares cascade (`store.py:67,75` and the new foreign keys). |
| Admin resets a viewer's password or TOTP | That viewer's shares are `suspended` until the owner enables them (5.7). |
| Plan deleted | Shares of that plan are revoked: a hook on a successful `POST /api/plans/delete` passing through the proxy, plus a refresh-time check (the worker answers "plan not found"). Decision 7. |
| Plan switched | No effect on the record; refresh needs that plan active again. |
| Plan renamed | No effect; the title is the owner's own. |
| One user restored from an archive (`restore_user`) | `gateway.db` is untouched, so shares are unchanged; the next refresh shows the restored data. |
| `gateway.db` restored | Every share in the restored copy is `suspended` (reason `restored`) and has no body; the owner enables each one again (section 8). |
| `--shared-views` turned off | Routes return 404; rows and bodies are kept; turning it on again restores the previous state. |
| Body missing or digest mismatch | Guest 404, `share_integrity_failed` in the audit, "republish" for the owner. |

## 8. Backup and restore (archive format 3, now on main)

- **Share rows** live in `gateway.db`, which every full archive already holds as its own member
  (`backup_store.py:251-254`). Nothing new is needed in the archive for them.
- **Record bodies are not archived (recommended default, decision 6).** They can be rebuilt by republishing, like the
  balances SQLite that format 3 deliberately leaves out (`backup_store.py:44-47`). Leaving them out also keeps the
  restore allowlist exactly as it is (`backup_store.py:42,52,54`); the Phase 7 plan calls widening that allowlist "the
  dangerous part" (`multi-user-insights-followups-plan.md`, Phase 7 risks).
- **Restoring `gateway.db` suspends every share.** `restore_gateway_db` already writes to a new file and never touches
  the live database (`backup_store.py:419-442`). It gains one step: open the new file and set every active share to
  `state = 'suspended', state_reason = 'restored'` before returning. Without this step, an old `gateway.db` would bring
  back revoked shares, the same class of problem as P7-O12. The owner enables each share again, which republishes it.
- **`restore_user`** is unchanged (`backup_store.py:319-343`).
- **If the owner wants bodies archived (decision 6 answered "yes"):** format 4 adds a separate, strict member family
  `shares/<32 hex>.json` (never a loosened regex). It is restored only together with `gateway.db` into a new data root,
  and a body is served only after its digest matches the restored row and the owner enables the share again.
- **Runbook:** one line on what is and is not backed up, and one restore-drill step ("after restoring `gateway.db`,
  every share shows Suspended: restored").

## 9. What does not change

The planner's routes and allow-list (`remote_allowlist.py`); FI's worker allow-list except one new entry; the FI mount;
the supervisor lifecycle for members; login, TOTP, CSRF and throttling code paths (viewers only add their own limits);
the archive format and `restore_user` (with the default answer to decision 6); the desktop FI and `identity.db`; the
Funnel mappings; the planner's navigation and the `wi015` baseline.

## 10. Test plan

Names follow the repo rules (type suffix, no tracking ids). The new modules do not exist yet, so they are named
without a folder: the Python modules go in `tests/`, the `.mjs` module in `tests/frontend/` and the Playwright spec in
`tests/e2e_gateway/`. The slow tier starts real workers; run each slow module once. The security review maps every
control to one of these tests.

| Module (new unless stated) | Covers |
|---|---|
| `test_gateway_share_store_unit.py` | Migration 3 -> 4 on a copy of a version 3 database keeps every row and makes everyone a member; the `kind` and role `CHECK`; sponsor cascade; scoped queries; share id format; `member_ids()` excludes viewers |
| `test_gateway_viewer_gate_contract.py` | Walks every gateway route and a list of planner and FI paths as an active viewer: only `VIEWER_ALLOWED` answers; the fake upstream and supervisor record zero calls; an unknown `kind` is treated as a viewer; Phase 8's `eligible_users` never selects a viewer; the table is a fixed literal, not derived from the planner's |
| `test_gateway_viewer_session_functional.py` | Pending, must-change and enrolment stages for viewers; idle and absolute limits; enrol-by deadline; logout headers; admin reset suspends shares |
| `test_gateway_share_routes_functional.py` | Owner and viewer routes: scoping, uniform 404 bodies (byte-equal), CSRF and Origin, limits, sponsor rule, no enumeration |
| `test_gateway_share_publish_functional.py` | Output validation, size cap, schema and key checks, leak check, atomic write, digest binding, revoke and scope-change races, plan mismatch, browser block of the snapshot route |
| `test_insights_share_snapshot_functional.py` | The worker route: views by construction; percent output equal to what the desktop percent hook returns for the same data; leak check; no error text; active-plan rule; plan file hash unchanged |
| `test_gateway_share_lifecycle_functional.py` | Expiry, owner disabled or deleted, viewer deleted, plan deleted hook, housekeeping orphan sweep, `--shared-views` off |
| `test_gateway_share_backup_functional.py` | `gateway.db` carries the rows; bodies are not archived (default); the `restore_gateway_db` output has every share suspended; `acl check` reports a worker-readable shares folder (Windows-only parts skip elsewhere) |
| `test_multi_user_isolation_shared_view_integration.py` (slow) | Two owners and two viewers through the real gateway and real workers: id guessing, replay across sessions, planner, `/insights/` and admin routes refused, enumeration, revocation on the next request, no worker started for a viewer |
| `gateway_viewer_render.test.mjs` | Hostile strings in a record render as text; the page fetches only its three routes |
| `shared-view.spec.js` | Playwright: owner shares and previews; guest signs in with TOTP and sees the percent view; revoke then reload shows "not available"; Back after sign-out shows no data |
| Existing, must stay green | `tests/test_gateway_insights_schedule_unit.py` (Phase 8; its selection changes in 9a), `tests/test_multi_user_isolation_integration.py`, `..._attacks_integration.py`, `..._routes_integration.py`, `..._insights_integration.py`, `tests/test_gateway_admin_guard_contract.py`, `tests/test_gateway_insights_proxy_functional.py`, `tests/test_insights_worker_mount_functional.py`, `tests/test_remote_mode_contract.py`, the percent-view tests (`tests/test_trends_percent_view_*.py`, `tests/test_realized_percent_view_unit.py`), `tests/test_gateway_backup_*.py`; `tools/fast_gates.py`; the system diagram regenerated for new modules |

## 11. Phase plan after sign-off (9a-9e)

Effort is relative to **one 5-hour Claude Code cycle on the Pro plan**, using the calibration in
`multi-user-insights-design.md` section 10. Total for 9a-9e: about **1 to 1.5 cycles**. Suggested split: cycle 1 =
9a and 9b; cycle 2 = 9c to 9e. Check `/usage` as each phase runs and compare against these estimates.

| Phase | Work | Model / effort | Expected usage and what drives it |
|---|---|---|---|
| 9a. Data model, viewer accounts, gate | Migration step 4; store methods (`create_viewer`, `member_ids`, scoped share queries); `Identity.kind`; the gate branch and `VIEWER_ALLOWED`; refusals in the proxy and supervisor; members-only selection in Phase 8's `eligible_users`; viewer session limits, enrol-by deadline, resets suspend shares; admin console **Add viewer**; the store, gate-contract and session tests | Opus 5.5, high (the gate is the boundary) | **Moderate to heavy** (20-25%). `store.py` (695 lines) and `app.py` (604) change in a few functions: Grep, then read only those. The contract test that walks every route is the longest edit-test loop |
| 9b. Publish path | FI worker route and allow-list entry; view-to-route map, fixed scopes, percent pipeline, leak check; proxy browser block; gateway publisher (`call_worker` with a new `max_bytes`, validation, atomic write, digest, race guards); optional refresh hook in Phase 8's `_update_user`; housekeeping; plan-delete hook; size and time measured on the demo plan | Opus 5.5, high | **Moderate to heavy** (20-25%). Step 0 Greps the realized and live parameters and the `percent_view` import. Never read `live_snapshot.py` (1,326 lines) or `index.html` linearly. Real-worker functional tests are slow: run each once |
| 9c. Viewer page and route table | `/gateway/viewer` page and script, static allowlist, render from one record, status poll, sign-out clearing; frontend render test; Playwright guest spec | Sonnet 5.5, high (Opus 5.5 high to review the route table) | **Moderate** (15-20%). Step 0 decides between reusing FI's chart modules and a small renderer: Grep their exports, do not read them whole. Playwright compresses least; budget one retry round |
| 9d. Owner UI and operations | `/gateway/sharing` page, owner routes, FI header link; `acl setup` and `acl check` for the shares folder; `restore_gateway_db` suspends shares; runbook lines | Sonnet 5.5, high | **Moderate** (15%). The FI link: Grep `index.html` and leave its fetch wrapper alone. `acl.py` changes are a few lines plus tests |
| 9e. Isolation and abuse gates, then review sign-off | The two-owner, two-viewer slow integration module; the full abuse matrix; existing isolation modules; fast gates; diagram; the security review's sign-off pass, updated with results | Opus 5.5, max for the sign-off review; Sonnet 5.5, medium to run the slow tier | **Heavy relative to its code** (20-25%) because real workers start (slow, Windows-flaky). Run each slow module once; re-run only failures; log pytest to a scratch file (`-v -rfE`) |

Expensive steps to scope down:

- 9a: the gate-contract test should walk the route map in process (fake upstream), not start real workers.
- 9b and 9e: slow tests start real workers; run the new module once, then re-run only a failure.
- Anywhere: never read `live_snapshot.py`, `dashboard.js` or `admin.js` whole; Grep first.

Order of work with exit criteria: 9a passes the contract and store tests with no publish path; 9b passes the worker and
publisher tests; 9c passes the render test and the guest Playwright spec; 9d passes the lifecycle and backup tests;
9e passes the slow module and the existing isolation modules, and the security review is signed off **before any
rollout** (the flag stays off until then).

## 12. Risks and limitations

| Risk | Mitigation |
|---|---|
| The gate branch is the whole boundary; one missed path would forward a viewer | Positive allow-list at the gate; refusals in the proxy and the supervisor; a contract test that walks every route; the slow two-owner test |
| Percent view does not hide amounts from someone who knows one real figure | Said plainly to the owner when sharing; recorded as residual risk in the security review |
| A guest keeps what they saw | Said plainly; no export in v1; residual risk |
| Old numbers read as current | "As of" always visible, a badge after 7 days, refresh by button or schedule |
| The owner's text renders in another person's browser (first time on this server) | Text-only rendering, normalisation at publish, gateway CSP, a frontend test with hostile strings |
| Record size with a long history | 8 MiB cap (raising it needs `call_worker`'s new `max_bytes`); 9b measures; fewer pre-rendered scopes if needed |
| Refresh works only while the share's plan is active | Documented. Possible later extension: render a named registered plan inside a scoped read, which changes active-plan resolution and is not in v1 |
| `users.js` is shared with the desktop Admin app | New columns behind a `FEATURES` flag (`admin_console.py:36-40`) |
| Phase 8's scheduler (merged) treats every active account as an FI user | 9a makes `eligible_users` select members only; the supervisor refusal (5.1, layer 3) is the backstop; the scheduled refresh stays an optional hook and the button works without it |

## 13. Owner decisions (recorded 2026-11-18)

The owner answered every decision on 2026-11-18. Thirteen of the fourteen are the recommended default; decision 4
takes a 90-day default expiry (recommended: 30 days).

| # | Decision | Owner's answer (2026-11-18) |
|---|---|---|
| 1 | Q1: who the viewers are | Viewer accounts only: admin-created, each sponsored by one owner; members are not grantees in v1 |
| 2 | Q2: live or copy | Published copy (Option A); refresh by button and after the scheduled update (decision 10) |
| 3 | Q3: what a guest sees | Percent view by default, dollars opt-in per share; owner-chosen tabs (all three ticked by default); transactions never |
| 3b | Replace account names with generic labels in shared records | No: real names are shown, and the owner sees them in the preview |
| 4 | Q4: revoke, expiry, who looked | Revoke on next request; **90-day default** (recommended was 30), 365 maximum; owner sees viewer and time, no address |
| 5 | Q5: export | No export |
| 6 | Archive record bodies | No: rows travel in `gateway.db`; a restored `gateway.db` suspends every share |
| 7 | Deleting a plan revokes its shares | Yes |
| 8 | Viewer session limits and enrol-by deadline | 10 minutes idle, 2 hours absolute, 72 hours to enrol |
| 9 | Record selection | Share id within the session's own set (not one share per viewer) |
| 10 | Phase 8 refresh hook | On when `--insights-schedule` is set, only for shares whose plan is active |
| 11 | An admin reset suspends the viewer's shares | Yes, until each owner re-enables them |
| 12 | Desktop tab-limit gap (finding F1) | A separate small fix soon, on the desktop remote listener; not part of Phase 9 |
| 13 | Limits | 10 shares per owner, 5 viewers per sponsor, 8 MiB per record |

Still open before 9a starts: the owner's acceptance of residual risks R-1 to R-12 (security review, section 8), and the
owner's sign-off of this design and the security review.

## 14. Not verified here

- Whether FI's chart modules can render from a data object without `index.html`'s inline script (9c step 0).
- Whether `financial_trends_reporter.percent_view` imports cleanly inside the gateway process (9b step 0).
- SQLite: the cross-column `CHECK` in `ADD COLUMN` and the self-referencing foreign key added by `ALTER` (expected to
  work; the 9a migration test proves it).
- Record size and publish time with a real plan and live prices.
- The exact parameters of `/api/realized` and `/api/live-snapshot`, and which panel `realized` belongs to.
- Browser behaviour of `no-store` pages in the back-forward cache after sign-out, and `Clear-Site-Data` over Funnel.
- Whether worker responses set `Cache-Control` themselves (the gateway adds `no-store` only on its own paths).
- Per-account ACLs for the new folder on the installed service (the owner's elevated run, as in earlier phases).
- The internals of `admin_app/frontend/users.js` (not read).
