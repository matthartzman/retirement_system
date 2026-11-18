# Financial Insight for multi-user server users: design and implementation plan

Status: draft
Date: 2026-11-17

Scope: give every user of the multi-user server a **view-only Financial Insight (FI) of their own current plan**, behind
the sign-in they already have, with no way to see anyone else's plan. Builds on `multi-user-server-plan.md`,
`multi-user-server-gateway-design.md`, `multi-user-multiple-plans-design.md` and `admin-app-plan.md`. The owner's own
desktop FI (ports 5057 local / 5058 remote) is **not changed**.

## 1. Requirement, as understood

1. FI is multi-user: each remote user gets FI for **their own** data. Nobody reaches another user's plan.
2. FI is a **view-only look into the user's current plan** (the plan active in their planner). It never writes the plan.
3. Minimise change to existing code; maximise usability (no second login, one click from the planner, no setup).

Interpretation to confirm (section 11, question 1): "a remote user's current plan" is read as the user's *own* plan. It
is **not** read as "let person A look at person B's plan". That sharing case needs cross-user access, which the
multi-plan design (decision 2) deliberately avoids; it is an optional later design (section 10, Phase 9).

## 2. What exists today (findings)

| Area | Fact | Evidence |
|---|---|---|
| FI has no per-user plan | Every FI reader resolves one workspace; for the live workspace that is the single active plan. A grant holds only `money_view` and `views`. | `src/active_plan.py:562`; `src/identity/store.py:58`; `financial_trends_reporter/projections.py:29,86` |
| Two account systems | FI guests live in `identity.db` (Admin app, grants `insights`/`planner`). Multi-user planner users live in `gateway.db` (password, mandatory TOTP, sessions in the DB). Kept separate on purpose. | `multi-user-server-gateway-design.md` "Reuse of the trends reporter's access code" |
| Planner users already have per-user isolation | Gateway session -> `Supervisor.endpoint(user_id)` -> one worker per user, under its own Windows account, workspace pinned by environment (`RETIREMENT_SYSTEM_WORKSPACE_ROOT`), worker token on every request. | `src/gateway/proxy.py:66-125`; `src/remote_worker.py:47-55,219`; `src/server/app_core.py:1180-1200` |
| The worker resolves "the current plan" itself | With the workspace pinned, `plan_path_for_workspace(workspace)` returns `active_plan_path()`, i.e. the plan the user has switched to. Plans live in the user's registry (`app.db`). | `src/active_plan.py:562-569`; `multi-user-multiple-plans-design.md` section 4 |
| FI is one Flask-style app that already runs behind a wrapper | `ListenerApp` wraps it and the HTTP server accepts any object with `handle_http`. FI paths collide with planner paths (`/api/history`, `/api/spending...`), so it cannot share the planner's route table. | `financial_trends_reporter/listeners.py:18-27`; `src/http_runtime/server.py:72-78`; `src/server/remote_allowlist.py:68,214-221` |
| FI keeps its own derived stores beside a log path | `log_path.parent` holds the history log, the balances SQLite, the pass-through decisions and the tax-rate file; all derive from one `log_path` argument. Default location is inside the install (`<repo>/financial_trends_reporter/data`), which is shared and read-only on the server. | `main.py:79,205`; `trends_log.py:23`; `live_snapshot.py:1203` |
| Monarch data for a remote user is in the **plan file**, not in FI's SQLite | A remote user uploads Monarch CSVs; rows land in the plan (`store.monarch`). FI reads its **own** `monarch_balances.sqlite3`, fed from the extractor CSV on the desktop. A remote user's FI would therefore show no balances. | `multi-user-server-monarch-secrets-design.md` section 1; `trends_job.py:122`; `src/stores/monarch_repo.py:87,134,143` |
| FI's update job uses machine-level tools | A subprocess runs `tools/refresh_prices.py` from the repo, imports the extractor CSV, and the 5 pm weekday job comes from Task Scheduler. None of that exists per user on the server. | `trends_job.py:57-137` |
| What FI writes | Display preferences (`/api/account`, `/api/account-prefs`), pass-through decisions, its history log, and a view/ping log. It reads the plan through `workspace_store(root)` (read-only by default) and never writes plan rows. | `main.py:194-203,362-400,423`; `app_sync.py:43-52`; `live_snapshot.py:1210-1220` |
| Frontend is nearly prefix-ready | 22 `fetch` sites (18 in `index.html`) all pass through one `window.fetch` wrapper; one absolute module import (`/shared/runtime_history.js`); three `location.href` redirects. | `frontend/index.html:404,990-998,1028`; `frontend/*.js` |
| Gateway idle logic counts any request as activity | `last_seen` is refreshed by any authenticated request, so FI's 5 s ping and 60 s live poll would keep a session alive until the 12 h cap. | `src/gateway/store.py:523-531`; FI `index.html:999-1004` |

The two findings that shape the design:

- **The isolation machinery for "this user, this workspace, this active plan" already exists in the planner worker.**
  FI should borrow it, not rebuild it.
- **FI's data stores and update job assume one owner and one machine.** They must become per-user and per-plan, and
  must read the Monarch data where a remote user actually keeps it.

## 3. Options

**A. One shared FI process for all users** (extend the current remote listener: resolve a workspace per request).
Rejected. It breaks the core server decision that users who do not trust each other run in separate OS accounts. It
needs a workspace parameter threaded through about 26 call sites and module-level caches. `workspace_store(root)` for a
root other than the live workspace returns `<root>/plan.rpx`, **not** the user's active plan, so a user with several
plans would see the wrong one. One bug leaks everyone's finances.

**B. FI served by each user's own worker, under a prefix (recommended).** The worker mounts the FI app at
`/insights/`. The gateway forwards `/insights/...` through the same proxy it uses for the planner, so it inherits login,
TOTP, sessions, CSRF, throttling, the per-user OS account, the worker token and the workspace pin. FI resolves the
active plan exactly as the planner does. No new process, port, Funnel mapping, credential or user table.

**C. A second per-user process for FI** (the shape sketched in the shared-state inventory, section 5). Same isolation
as B but doubles processes per active user (memory and Job Object accounting), needs its own port registration, health
checks and idle reaping, and a second supervisor slot. No benefit over B for a light, read-mostly app.

**D. FI on its own public origin** (Funnel port 10000) sharing the gateway cookie. Keeps FI's absolute paths unchanged
but adds a second origin to harden, a second Funnel mapping, and a cross-origin login redirect that loses the return
path. Rejected: the prefix change in B is about five lines of frontend.

Recommendation: **B**.

## 4. Design

### 4.1 How a remote user reaches the right plan, and only that plan

```
Browser --https:8443--> Gateway                          (existing)
   GET /insights/...      1. session cookie -> user id    (gateway.db; password + TOTP already done)
                          2. CSRF / Origin checks          (existing)
                          3. Supervisor.endpoint(user id)  (that user's worker, Windows account, workspace)
                          4. forward with the worker token (existing upstream_headers)
                       -> Worker (user N only)
                          5. mount checks token + loopback Host (new, section 4.3)
                          6. FI app, workspace = the pinned workspace
                          7. plan = plan_path_for_workspace(workspace) = the user's ACTIVE plan
                          8. stores = <workspace>/output/plans/<plan_id>/insights/
```

Nothing in the URL, query, header or body names a user or a plan; the user id exists only in the gateway session, and
the plan id is read from the user's own registry. So there is no parameter to tamper with. The guarantees are layered:

1. **Identity -> worker**: the gateway session selects the worker; a user cannot name another worker.
2. **Worker -> workspace**: the process runs under that user's Windows account with ACLs that exclude every other
   user, and its workspace is pinned by environment; FI takes its root from `platform_runtime.workspace_root()`, never
   from a request.
3. **Workspace -> plan**: the active plan from the user's own `app.db` registry (already confined inside the workspace).
4. **Plan -> derived stores**: per-plan folder inside the same workspace.

"Current plan" follows **Switch plan** in the planner. The FI header shows the plan's name, when it was last saved and
when it was last built, so it is always clear which plan is on screen.

### 4.2 Worker-side FI ("worker mode")

`create_app(..., mode="worker")` in `financial_trends_reporter/main.py`. Everything else in FI stays as it is.

| Concern | Worker mode behaviour |
|---|---|
| Access gate | No `register_access` (no `identity.db`, no FI sign-in). The mount (4.3) is the gate. `current_listener()` returns `"worker"`; `/api/whoami` returns `{listener: "worker", name: <display name from the gateway>, views: all, money_view: "both"}`. |
| Data location | `log_path = <output>/plans/<plan_id>/insights/financial_trends_log.jsonl`, evaluated **per request** (the 20 references to `resolved_log_path` and `balances_db` in `main.py` become one `_paths()` call). History, balances, display preferences and decisions are therefore per plan; a what-if plan never pollutes the base plan's history, and **delete plan** removes the folder (it already deletes `output/plans/<id>/`). Nothing is written under the install. |
| Monarch balances | New `plan_balance_sync.sync(workspace, db)`: copies the active plan's Monarch balance rows (`MonarchRepo`, new single-query `iter_balances()`) into the FI SQLite through the same guarded import (rows, not a CSV path, as `import_balance_rows` did on the planner side). Runs when FI loads and whenever the plan's last-import id differs from the one stored in the FI database. Then `sync_from_app` runs as today for account type, match and ignore. |
| Update job | `trends_job.run(..., mode="worker")`: no extractor import, no FI-owned subprocess. Prices are refreshed through the planner's own `pricing_service.refresh_prices` (the same code behind the allowed `/api/prices/refresh`, with the scrubbed `remote_mode.subprocess_env()`), so the worker's price cache and the shared provider key are used. Snapshot, log append and `sync_from_app` are unchanged. (Phase 0 correction: the first draft assumed a new in-process refresh was needed.) |
| Triggering updates | The existing **Update** button (`/api/run-now`) plus one automatic update per day: when FI opens and the latest log entry is older than the last NYSE session, it starts one. No Task Scheduler entry per user. See 4.6. |
| View-only | FI opens the plan only through `workspace_store(root, readonly=True)`: a new keyword on `active_plan.workspace_store` (today its read path opens a **writable** connection, which may migrate the schema; Phase 0 finding 3). A plan older than the current schema then shows "open the planner once to upgrade this plan" instead of being upgraded by FI. A regression test asserts the plan file's bytes are unchanged after a full FI session. FI-owned preferences (account chart inclusion, account type override, pass-through decisions) stay editable because they live in FI's per-plan store and change nothing in the planner; owner decision, question 3. |
| Removed or refused | `/api/exit`, `/api/signin|signout|change-password|totp*`, `/api/open-admin` (already removed), `/api/people`, `/api/activity`. Everything not on FI's own allow-list is refused (4.3). |
| Extractor status | `monarch_autoupdate.get_extractor_failure` is skipped in worker mode (the extractor is disabled for workers). |

### 4.3 Mount in the worker

`src/remote_worker.py` creates the server with `create_app()` (line 219). Worker mode wraps it:

```python
app = PrefixMount(planner_app, insights_app, prefix="/insights")   # only when RETIREMENT_SYSTEM_INSIGHTS=1
```

`PrefixMount` has the same shape as `ListenerApp` (`handle_http`). For a path under `/insights/` it strips the prefix and
dispatches to the FI app; everything else goes to the planner untouched. The planner's route table, allow-list and
manifest do not change. Because the planner's token and allow-list checks live **inside** the planner app
(`_remote_mode_gate`), the mount must not rely on them. It applies, before dispatch:

1. the worker token (`remote_mode.worker_token()`, `constant_time_token_ok`), including `/api/ping`;
2. loopback `Host` and the Origin/Referer rule the planner applies;
3. an **FI allow-list** (deny by default), a frozenset of `(method, rule)` pairs in
   `financial_trends_reporter/worker_allowlist.py`, with a contract test that every FI route is classified exactly once
   (the pattern of `tests/test_remote_mode_contract.py`);
4. the path scrub the planner applies to JSON (`remote_mode.scrub`) so no server path leaves the worker;
5. FI's generic error body (no exception text) in remote mode.

Allowed: the page and its static modules, `GET /api/history|accounts|balances|flows|liquid-change|spending|
spending/transactions|live-snapshot|projections|realized|app-accounts|run-status|whoami`, and
`POST /api/account|account-prefs|passthrough-decision|run-now|run-cancel|view|ping`.

### 4.4 Gateway changes

| Change | Detail |
|---|---|
| Flag | `--insights` (default off, like `--monarch-connector`). The supervisor sets `RETIREMENT_SYSTEM_INSIGHTS=1` in the worker environment (`server.py:260` pattern). Off means no mount and `/insights/` is a 404 from the worker. |
| Forwarding | `/insights/...` already passes `_SAFE_PATH` and goes through `WorkerProxy._send`. Add a redirect `/insights` -> `/insights/`. No new route type, no new user lookup. |
| Session JSON | `GET /api/auth/session` gains `insights: true/false` so the planner page can show its link. |
| Activity vs polling | A request carrying `X-Background-Poll: 1` forwards normally but does **not** refresh the session's `last_seen` or the supervisor's `touch`. FI's wrapper adds it to the ping, `/api/run-status` and the live-snapshot poll. A tab left open overnight then times out at 15 minutes like any idle session (this closes the gap the gateway design lists under "Not done here"). The 12 h absolute cap is unchanged. |
| Audit | One gateway audit event `insights_opened` per session (path, no data). Nothing about amounts is logged. |

No change to login, TOTP, CSRF, throttling, the build queue, backups or the supervisor lifecycle.

### 4.5 Frontend changes

FI (`financial_trends_reporter/frontend/index.html`, one small shared snippet):

- The existing `window.fetch` wrapper prepends `BASE` (derived from `location.pathname`, `""` at the root, `/insights`
  under the gateway) to absolute `/api/` and `/shared/` URLs and, in worker mode, adds `X-CSRF-Token` (read once from
  the gateway's `/api/auth/session`, same origin) and `X-Background-Poll` on the polling routes. On a 401 it sends
  the browser to `/login?next=/insights/` instead of `/signin`.
- The `runtime_history.js` import and the three `location.href` calls use the same `BASE`.
- In worker mode the header shows a **Planner** link (to `/`) and **Sign out** (gateway logout); the Exit button is
  hidden. Plan name and "as of" line added to the header.

Planner (`frontend/`): one **Financial Insight** link in the header beside the plan switcher, shown only when the
session says `insights: true`. It is a header link, not a navigation step, so the `wi015` navigation baseline does not
change. The few JavaScript lines are paid for by deleting equivalent lines elsewhere in `frontend/js` (the size ratchet
is never raised).

### 4.6 History without a scheduler

The desktop FI log is written by a 5 pm weekday Task Scheduler job. On the server each user's log starts when they first
open FI (an immediate update) and then gains one entry per session day (auto-update on open) plus any manual
**Update**. Net worth over time still has full depth because the balance series comes from the uploaded Monarch history;
the log supplies the richer per-day detail (holdings, cash flow) from first use onward. A scheduled per-user job
(Phase 8) closes the remaining gap if the owner wants a gap-free log.

### 4.7 Data lifecycle

| Event | Effect |
|---|---|
| Duplicate plan | The copy has no FI history (it starts at its first update); balances re-sync from the copy's own Monarch rows. |
| Delete plan | `output/plans/<id>/` is already removed, which removes the FI stores. No orphans. |
| Switch plan | FI shows the new plan; caches are keyed on the plan file and the store paths. |
| Quota | The FI stores sit inside the workspace, so the existing per-user disk walk counts them. They are small. |
| Backup | **v1 of this work does not back up the FI history log** (balances are reproducible from the plan; the log is not). Phase 7 adds it to archive format v2 if the owner wants it (question 4). |
| Disable | `--insights` off removes the mount; the stored data stays and is reachable again when re-enabled. |

## 5. Security analysis

| Risk | Control | Test |
|---|---|---|
| User A reaches B's FI | No identifier in the request; session -> worker -> pinned workspace -> own registry | Two-user integration run through the gateway (`/insights/api/history` and the page) |
| Mount bypasses the worker token | The mount enforces the token and Host itself, before dispatch | Request with no or wrong token to `/insights/...` is 401, before FI code runs |
| FI writes outside the user's workspace (install folder, repo `data/`) | `log_path` always inside the workspace; confinement through `remote_mode.confine_path` | Run worker-mode FI with the install folder read-only and assert zero files created outside the workspace |
| FI changes the plan | Read-only store only; allow-list has no plan route | Plan file hash unchanged after a full session including **Update** |
| New unclassified route reaches users | Deny-by-default FI allow-list | Contract test fails when a route is unclassified |
| Path or exception leakage | `remote_mode.scrub` plus generic errors in the mount | Force an error and read the body |
| Session kept alive by polling | `X-Background-Poll` policy | Gateway test: poll requests do not move `last_seen`; a real request does |
| Origin/CSRF | FI's POSTs carry the gateway CSRF token; the gateway checks Origin | Gateway test: POST without the token is refused |
| Price-provider load (about 10 users polling every 60 s) | Per-process quote cache already exists; polling stops when the tab is hidden or the session idles | Measure in Phase 5; raise the interval in worker mode if needed |
| Admin sees user data | Gateway admins manage accounts only, as for the planner; there is no admin route into a worker's FI | Covered by the isolation test (admin session gets its own FI only) |

Things only the owner can verify (an elevated or installed build): per-account ACL behaviour under a dedicated worker
account, Funnel end to end, and the worker's memory with FI loaded.

## 6. What does not change

The owner's desktop FI (5057/5058), its `identity.db` guests, the Admin app, the planner's routes and allow-list, the
build queue, the supervisor, backups (v1 of this work), the Funnel mappings (443 stays with the legacy reporter, 8443
with the gateway), and the planner's navigation. Legacy remote guests still see the owner's active plan, by design.

## 7. Usability

- No second login: the gateway session (password + TOTP) already covers `/insights/`.
- One click each way: **Financial Insight** in the planner header; **Planner** in the FI header.
- First open is useful: it runs the first update itself and says what it is doing; an empty state tells the user to
  upload Monarch CSVs in the planner when no balances exist.
- Always clear which plan is shown, and how fresh it is.
- Idle timeouts behave like the planner's; a forgotten tab does not keep the session alive.

## 8. Test plan

Names follow the repo rules (type suffix, no tracking ids). The slow tier starts real workers; run each once.

- `test_insights_worker_mount_functional.py`: token, Host, Origin, prefix stripping, the planner route table unchanged,
  `/insights/` 404 when the flag is off.
- `test_insights_worker_allowlist_contract.py`: every FI route classified exactly once; refused routes return 403.
- `test_insights_worker_paths_confinement_regression.py`: no file written outside the workspace; stores under
  `output/plans/<plan_id>/insights/`; the install folder untouched.
- `test_insights_plan_balance_sync_functional.py`: plan Monarch rows appear in FI's store, idempotent, re-sync on a new
  import, account type and ignore from the mapping, per plan.
- `test_insights_view_only_regression.py`: plan file hash unchanged after opening every view and running **Update**;
  FI never opens a writable store.
- `test_insights_active_plan_functional.py`: Switch plan changes what FI shows; two plans keep separate histories;
  delete plan removes the stores.
- `test_gateway_insights_proxy_functional.py`: forwarding, redirect, `insights` in the session JSON, background-poll
  idle policy, CSRF on FI POSTs, audit event.
- `test_multi_user_isolation_insights_integration.py` (slow): two users through the gateway never see each other's
  history, balances, accounts or plan name; an admin sees only their own.
- `tests/e2e_gateway/insights.spec.js` (Playwright, gateway rig): sign in, click the planner link, charts render,
  **Planner** link returns, an idle tab signs out.
- Existing: `test_trends_access_gate_functional.py` and the percent-view tests stay green (legacy listeners untouched);
  `fast_gates.py`; system diagram regenerated; the `wi015` baseline is **not** re-recorded.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| FI reads a path outside `workspace_store` that I have not found | Phase 0 inventory greps every use of `_APP_ROOT`, `base_dir /`, `Path(...)` in `financial_trends_reporter/`, and the confinement test guards it afterwards |
| `PrefixMount` needs the server facade to accept a second app | Same pattern as `ListenerApp`; Phase 0 spike proves it before anything else is built |
| FI's `index.html` is a large inline script; the prefix change misses a call | All calls go through the one fetch wrapper; Playwright e2e exercises every tab |
| Price calls from many workers hit provider limits | Shared provider key is already budgeted; measure; lengthen the poll in worker mode |
| History starts late for new users | Documented; Phase 8 adds a scheduled update if wanted |
| FI history is not backed up in v1 | Stated above; Phase 7 closes it |

## 10. Implementation plan

Effort is relative to **one 5-hour Claude Code cycle on the Pro plan**, per the calibration from the multi-user server
build (a plan sized at 39-54 developer days took 3 cycles). Total for Phases 0-5: about **1.5 to 2 cycles**.
Suggested split: cycle 1 = Phases 0-3; cycle 2 = Phases 4-5. Phases 7-9 are optional and separate. Check `/usage` as
each phase runs and compare against these estimates.

| Phase | Work | Model / effort | Expected usage and what drives it |
|---|---|---|---|
| 0. Spike and inventory | Prove `PrefixMount` serves a stub FI under `/insights/` from a worker; list every FI path read; confirm read-only plan access; confirm the in-process price refresh entry point | Sonnet 5.5, medium | **Light** (about 5-8% of a cycle). Targeted Grep of `financial_trends_reporter/` (about 6,800 lines in total; read only `main.py`, `trends_job.py`, `live_snapshot.py:1180-1230`). Do **not** read `live_snapshot.py` whole (1,326 lines) |
| 1. FI worker mode (backend) | `mode="worker"`, per-request `_paths()`, listener `"worker"`, `whoami`, FI allow-list, `plan_balance_sync`, `MonarchRepo.iter_balances()`, in-process `trends_job` | Sonnet 5.5, high (Opus 5.5 high for the allow-list and the gate) | **Moderate** (20-25%). `main.py` is 527 lines and edited in about 20 places; tests are fast unit and functional runs; the update-job change is the longest edit-test loop |
| 2. Worker mount | `PrefixMount`, token/Host/Origin/scrub, env flag, mount tests | Opus 5.5, high | **Moderate** (10-15%). Security-critical, small code, careful tests. Keep it to `remote_worker.py` and one new module |
| 3. Gateway | Flag and env, redirect, session JSON, `X-Background-Poll` policy, audit event, tests | Sonnet 5.5, high | **Light to moderate** (10%). Touches `proxy.py` (284 lines), `app.py` (544), `server.py` (420); read only the touched functions |
| 4. Frontends | FI fetch wrapper, `BASE`, header, worker-mode UI; planner link; Playwright spec | Sonnet 5.5, high | **Moderate** (15-20%). `index.html` is about 1,050 lines of inline script: Grep the `fetch` sites, never read it linearly. Playwright runs compress least; budget one retry round. Planner side: tiny, but check `wc -l frontend/js/*.js` before and after |
| 5. Isolation and integration tests | Two-user integration run, view-only and confinement regressions, measurements (memory, poll load) | Sonnet 5.5, medium | **Heavy relative to its code size** (20-25%) because real workers start (slow, Windows-flaky). Run each slow test once; do not loop fix-and-rerun. Use the pytest log-file rule (`-v -rfE` to a scratch file) |
| 6. Docs and gates | Update `CURRENT_SYSTEM_DESIGN_SPEC.md`, the runbook (flag, restore drill, owner steps), regenerate the system diagram, run `tools/fast_gates.py` | Sonnet 5.5, low | **Light** (5%) |
| 7. Optional: back up the FI log | Archive v2 member for each plan's log, strict member regex, restore round trip | Opus 5.5, high | **Moderate**: touches audited backup code (`backups.py`, `backup_store.py`); keep the member list to one extra pattern |
| 8. Optional: scheduled per-user update | Supervisor-driven weekday update for enabled users | Sonnet 5.5, high | **Moderate**; interacts with the build queue and worker lifetime |
| 9. Optional, separate design: share a view with a guest | Cross-user, view-only access with percent view and tab limits | Opus 5.5, max for the design | **Heavy**; needs its own security review (it crosses the isolation boundary) |

Expensive steps to scope down:

- Phase 4: do not open `frontend/index.html` linearly; Grep `fetch(` and `location.href`. Do not run the full Playwright
  suite; run the one new spec and the `wi015` spec once.
- Phase 5: slow integration tests start real workers; run the new modules once each, then only re-run a failure.
- Anywhere: never read `live_snapshot.py`, `dashboard.js` or `admin.js` whole (see the large-file table in the project
  instructions).

Order of work with exit criteria: Phase 0 proves the mount; Phase 1 passes without the gateway (direct worker test);
Phase 2 passes the mount tests; Phase 3 passes the gateway tests; Phase 4 passes the Playwright spec; Phase 5 passes
the slow tests and the existing isolation modules; then the docs and gates.

## 11. Owner decisions needed

1. **Scope of "a remote user's current plan"**: each user sees their **own** plan (recommended, this design), or also
   other people (guests/advisors) can look at it (Phase 9, separate design).
2. **Access**: every user when `--insights` is on (recommended: minimal, no new column), or a per-user switch in the
   Users page (one `gateway.db` migration step).
3. **View-only meaning**: FI never writes the plan, but a user can still set FI display preferences (account chart
   inclusion, type override) in their own FI store (recommended), or FI is fully read-only with no preferences.
4. **History backup**: accept that the FI log is not backed up in v1 (recommended; balances are reproducible), or do
   Phase 7 first.
5. **History start**: first open and one entry per session day (recommended), or add the scheduled update (Phase 8)
   before launch.
6. **Naming in the planner header**: "Financial Insight" (matches the desktop app) or "Insights".

## 12. Not verifiable here

The installed-build behaviour (per-account ACLs for the new `insights` folder, memory per worker with FI loaded, Funnel
end to end, real price-provider load with ten users) needs the owner's elevated or installed environment, as in the
earlier multi-user phases.

## 13. Phase 0 results (2026-11-17)

Spike script (throwaway, not committed): a `PrefixMount` with the shape of `ListenerApp`, wrapping a stub planner app and
the **real** FI `create_app(workspace, log_path=...)`, served by one `LocalHTTPServer`.

| Question | Result |
|---|---|
| Can the worker serve FI under `/insights/` beside the planner? | **Yes.** `/api/history` answered by the planner (`{"who": "planner"}`), `/insights/api/history` by FI (`[]`), and `/insights/`, `/insights/charts.js`, `/insights/api/whoami`, `/insights/api/balances` all returned 200. The server needs only `handle_http`; the planner's `create_app()` returns the facade `app`, which has it. The design stands. |
| Does `/insights` (no slash) work? | It serves the page, but relative URLs would resolve against `/`; the gateway redirect to `/insights/` is required (as designed). |
| What does FI write when given a workspace and a log path? | Only under the log folder (`output/plans/<id>/insights/monarch_balances.sqlite3` appeared next to the log), **plus `local_state/identity.db`**, created by `register_access`. Worker mode must skip `register_access` (as designed) so no identity database is created in a user's workspace. Nothing was written under the install folder. |
| Every FI path read or write outside `workspace_store` | Inventory: `_APP_ROOT/frontend/*` and `_REPO_ROOT/frontend/js/runtime_history.js` (install files, read only); `default_log_path(_APP_ROOT)` and `default_db_path(_APP_ROOT)` (install `data/`) used by `main()` startup `sync_from_app`, `prune_trends_log` and the two CLI tools (desktop only, never reached in worker mode); `base_dir/"local_state"/"retirement_system_v10.db"` computed in `live_snapshot.py:1192`, `realized_view.py:42`, `trends_metrics.py:230` but **only passed through, not opened** (`_plan_rows` ignores it and reads the plan); `base_dir/"tools"/"refresh_prices.py"` (replaced by `pricing_service`); `live_snapshot.baseline_prices` writes `baseline_prices_<year>.json` into `data_dir`, which is the log folder (covered). `get_extractor_failure(workspace)` looks for `Monarch Extractor/` in the workspace and returns `None` when absent. So `log_path` redirection plus skipping `register_access` covers every write. |
| Plan access mode | `active_plan.workspace_store(root)` read path opens `PlanStore.open(path, create=False, readonly=False)`: a writable connection that can migrate the schema. The other readers in `active_plan.py` already use `readonly=True`. **Phase 1 adds `readonly` to `workspace_store`** and FI uses it. |
| Price refresh | The planner's `pricing_service.refresh_prices` already runs `tools/refresh_prices.py` in the worker (allowed route `/api/prices/refresh`, scrubbed environment). FI reuses it rather than getting a new implementation. This shortens Phase 1. |

Changes to the plan: Phase 1 gains the one-keyword `workspace_store(readonly=...)` change and loses the "new in-process
price refresh" work (net: slightly smaller). Phase 2 can start from the spike's 20 lines. No change to the effort
estimate. The mount is proven; the remaining risks are the token/Host enforcement inside the mount (Phase 2) and the
frontend prefix (Phase 4).

## 14. Phase 1 results (2026-11-17, branch `insights-worker-mode`)

Built: `create_app(..., mode="worker")`; `worker_mode.py` (per-plan store folder, `WorkerListenerApp`, gate, `whoami`,
`ping`, `view`); `worker_allowlist.py`; `plan_balance_sync.py` (plan Monarch rows -> FI store, stamped, mirrored);
`balance_store.import_balance_rows`; `MonarchRepo.all_balances`; `trends_job.run(worker=True)` (planner's own price
refresh, plan-fed balances); the listener type `"worker"`.

Change from the draft: view-only is enforced by a **scope**, not a keyword. `active_plan.read_only_plan_access()` makes
every plan read open read-only (no schema upgrade) and every plan write raise `PlanReadOnlyError`; the worker wrapper
holds it for the whole request, and `trends_job.run(worker=True)` holds it for the whole update. One small change in
`active_plan.py` covers every reader the reporter uses, including the many `_reading(path)` callers that opened a
writable connection. Tests: `tests/test_insights_worker_mode_functional.py` (9) and the 984 related existing tests pass;
`tools/fast_gates.py` passes. Not done here (later phases): the token/Host/Origin mount (Phase 2), gateway flag and
polling policy (Phase 3), frontend prefix and planner link (Phase 4).

## 15. Phase 2 results (2026-11-17, branch `claude/insights-worker-mount-57c2b9`)

Built: `src/remote_insights_mount.py` (`PrefixMount`, `insights_enabled`, constant `INSIGHTS_ENV`) and
`remote_worker.build_app(workspace, planner_app)`, which mounts FI only when the worker's environment has
`RETIREMENT_SYSTEM_INSIGHTS=1`; otherwise the planner app is used unchanged and `/insights/` is a planner 404. The
variable is read from the process environment only, is not in `FORBIDDEN_ENV`, and no request can set it.

The mount enforces, before FI code runs and only for `/insights` paths: the worker token (`X-API-Token` or Bearer,
`/api/ping` included; no configured token refuses everything), a loopback `Host`, and the planner's Origin/Referer rule
(`host_guard.origin_netloc_allowed`). `/insights` without a slash is a 302 to `/insights/` (query kept) after the token
check. On the way out it scrubs JSON bodies with `remote_mode.scrub` and replaces the `error` of any 5xx JSON body, or
an exception escaping FI, with `remote_mode.GENERIC_ERROR`. Planner paths (including `/insightsfoo`) are passed through
byte for byte; the planner route table, `remote_allowlist.py` and the route manifest did not change. The FI deny-by-default
allow-list (Phase 1) still applies behind the mount, and a regression test drives the refused routes through it.

Tests: `tests/test_insights_worker_mount_functional.py` (19) and `tests/test_insights_worker_mount_allowlist_regression.py`
(8). Not done here: gateway flag, redirect and poll policy (Phase 3); frontend prefix and planner link (Phase 4);
two-user isolation (Phase 5).

## 16. Phase 3 results (2026-11-17, branch `claude/insights-gateway-phase3`)

Built, all in `src/gateway/`: the `--insights` flag (default off) which sets `RETIREMENT_SYSTEM_INSIGHTS=1` in every
worker's environment and `GatewayConfig.insights`; for a signed-in user `/insights` (GET or HEAD) is a 302 to `/insights/`
with the query kept, and `/insights/...` otherwise goes through the existing forwarding to that user's own worker (no new
route type or lookup); `GET /api/auth/session` gains `insights` (true only when the flag is on and the session is active);
one audit event `insights_opened` per session (on the first page load, details are the path only).

Polling policy: a request carrying `X-Background-Poll: 1` to a `/insights/` path (flag on) is forwarded normally but does
not call `store.touch_session` or `supervisor.touch`, so an idle tab times out at the normal idle limit; the 12 h cap is
unchanged. The header is ignored on planner paths and when the flag is off. No change to login, TOTP, CSRF, throttling,
the build queue or the supervisor lifecycle. Not done here: FI sends the header and the planner link (Phase 4).

Tests: `tests/test_gateway_insights_proxy_functional.py` (14); the whole `test_gateway_*` set and the mount tests pass (325).


## 17. Phase 4 results (2026-11-17, branch `claude/insights-frontend-ca752b`)

Financial Insight page: new `financial_trends_reporter/frontend/insights_client.js` (pure functions plus one installer; served
at `/insights_client.js` and added to the worker allow-list). `BASE` comes from `location.pathname` (`""` at `/`,
`/insights` under the gateway). The `window.fetch` wrapper prepends it to `/api/` and `/shared/` URLs (never to the
gateway's `/api/auth/`), adds `X-CSRF-Token` to unsafe methods (token read once from the gateway's same-origin
`/api/auth/session`) and `X-Background-Poll: 1` on `/api/ping`, `/api/run-status` and the non-forced live-snapshot poll; a
401 goes to `/login?next=/insights/` (worker) or `/signin` (desktop). A static `import` cannot take a variable, so the
`runtime_history.js` import became the relative `./shared/runtime_history.js`, which resolves correctly at both `/` and
`/insights/`. Desktop behaviour at `/` is unchanged (empty `BASE`, no extra headers).

Worker-mode UI (`whoami.listener === "worker"`): plan name, an "as of" line from the newest log entry, a **Planner** link and
**Sign out** (`POST /api/auth/logout`), Exit hidden, and an empty state pointing to the Monarch CSV upload. On open: empty
history starts one update (`POST /api/run-now`) with a status line; otherwise at most one automatic update per day, only
when the newest entry is older than the last weekday 21:00 UTC market close (the desktop's 15-minute freshness update does
not run in worker mode).

Planner: the **Financial Insight** link is added by `frontend/js/remote_mode.js` (which already knows it is behind the
gateway) when `/api/auth/session` says `insights: true`. It is a header link before the plan switcher, not a step, so the
`wi015` baseline and the frozen script list are unchanged; the few lines were paid for by condensing that file's header
comment (net -2 lines, ceiling not raised).

Found and fixed here (a Phase 3 gap): an unauthenticated `/insights/api/...` call got a 302 to the login HTML, which `fetch`
follows as a success, so an ended session never reached the 401 handler. The gateway now treats `/insights/api/` as an API
path (JSON 401/409). The page itself still redirects.

Tests: `tests/frontend/trends_reporter_insights_client.test.mjs` (11, no source greps), `tests/e2e_gateway/insights.spec.js`
(5, real gateway and worker; `tools/gateway_e2e_server.py` now starts the gateway with `--insights`), and a gateway
regression for the 401. Not covered in a browser: the 15-minute idle sign-out (not configurable on a real gateway); the
policy is covered by the Phase 3 gateway tests, and the browser spec checks the poll header and that an ended session
reaches `/login?next=/insights/`. Not done here: two-user isolation measurements (Phase 5).
