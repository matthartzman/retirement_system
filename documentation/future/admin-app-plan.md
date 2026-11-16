# Admin App: Design and Implementation Plan

Status: draft
Date: 2026-11-16

## Goal

Create a third local app, the **Admin app**, that owns everything an administrator does across the system:

1. The **system-wide configuration** that today lives in the Retirement Planner's System Configuration console
   (`frontend/admin.html`, `frontend/js/admin.js`, `src/server/admin_routes.py`).
2. The **user management** that today lives inside Financial Insights (the owner-only People and Activity views:
   `financial_trends_reporter/frontend/access.js`, the `/api/people*` and `/api/activity` routes in
   `financial_trends_reporter/access_routes.py`, the accounts in `data/access.db`).
3. **Expanded user management**: one account list for the whole system, with per-app access grants (Financial
   Insights now, the Retirement Planner reserved for the multi-user server), enable/disable, access expiry,
   two-factor sign-in, session control, and a cross-app activity and admin audit log.

Financial Insights changes so that it no longer owns accounts: it signs people in against the shared identity
store and lets them in only if the Admin app has granted them Financial Insights access.

This plan is deliberately the first slice of Phase 2 of `documentation/future/multi-user-server-plan.md`
("extract and generalise the reporter's access code into a shared module so there is one account store and one
login system"). Everything here is built so the future gateway can adopt the identity store and the Admin app
unchanged.

## What the survey found

| Area | Current behavior | Evidence |
|---|---|---|
| Planner admin console | A separate page (`/admin`, `/system-configuration` redirect to `/frontend/admin.html`) served by the planner process; `admin.js` is 2,048 lines (very large band). | `src/server/admin_routes.py:35-50`; `frontend/admin.html` |
| Admin nav | Three groups: System configuration (App settings, Runtime & files, Dashboard & security, Build timeout, Workbook build diagnostics), Market data (Pricing controls, Capital market assumptions, Asset correlations, Refresh & drift), Tax & accounts (Tax-law dashboard, Tax modeling, Global rebalancing, Annuity calibration). | `frontend/js/admin.js:1588-1718` |
| "System config" is two things | One editor saves **runtime rows to `app.db` settings** (install-wide) and **engine-knob rows to the active plan** (per plan). Engine sections: Annuity Calibration, Asset Class Assumptions, Asset Correlations, Plan Settings, Rebalancing. | `src/server_services/admin_service.py:111-123`; `src/engine_defaults.py:110` |
| Runtime settings reload | `_runtime_config()` re-reads on every call, so a second process editing `app.db` takes effect without a restart (host/port changes still need one). | `src/server/app_core.py:172-176` |
| Permissions | A local shim: every request is `user_id="local"` with every permission; `_require("manage_clients")` always passes. | `src/permissions.py` |
| Planner callers of admin routes | Batch assumption editor reads `/api/admin/system-config`; checklist close-out uses `/api/admin/csv-backup`, `/api/admin/tax-law-dashboard` and navigates to `/system-configuration`; holdings uses `/api/admin/diagnostics`. | `dashboard_batch_assumption_edit.js:333,415`; `dashboard_decomp_checklist_closeout.js:360,386-407,689`; `dashboard_decomp_holdings.js:512` |
| FI accounts | `AccessStore` in `data/access.db`: scrypt hashes, `must_change`, lockout after 5 failures, global throttle, `money_view` (dollars/percent/both), and an `activity` table. No roles, no disable, no TOTP, no expiry. | `financial_trends_reporter/access_store.py` |
| FI people UI | Owner-only routes answer 404 on the remote listener; the People page is `access.js`, injected only on the local listener. | `access_routes.py:34,69-86,224-296`; FI `index.html:1020` |
| FI sessions | In-memory `SessionTable`, 10-minute idle; `sessions.end_user()` is called on reset/delete, which only works because the people routes run **in the same process**. | `financial_trends_reporter/sessions.py`; `access_routes.py:262,285` |
| FI listeners | Local 5057 (owner, no sign-in, loopback Host only, proxy headers refused) and remote 5058 (Tailscale Funnel, sign-in required). | `financial_trends_reporter/listeners.py`; `main.py:475-520` |
| Tests touching the console | About 20 test files read or load `admin.js`/`admin.html` (Python, Node and one Playwright spec). | `grep -l "admin.js\|admin.html" tests` |
| Route manifest | `/admin`, `/system-configuration` and ten `/api/admin/*` routes are listed. | `src/server/route_manifest.py:7,67-70` |

The one finding that shapes the design most: **half of "system configuration" is not system-wide**. The five
engine sections are stored per plan; moving them into an admin app would put per-plan assumptions behind an
administrator, which is wrong for the planner's user and wrong for the multi-user server (each user owns their
plan).

## Options

**Option A - separate Admin app process (recommended).** A new package `admin_app/`, structured like
`financial_trends_reporter/`, on its own loopback port, reusing `src.http_runtime`. It owns the identity store
and install-wide settings. The planner and Financial Insights link to it.
- Matches the request ("an admin app"), keeps admin code out of the planner's frontend size budget, and is the
  shape the multi-user gateway needs (the gateway's admin surface is this app behind the gateway's sign-in).
- Cost: a third process to launch, and settings changes now cross a process boundary (handled below).

**Option B - keep the console in the planner process, move user management into it.** Cheaper, but puts account
management into a process that, in the multi-user design, runs once per user under that user's Windows
account. Rejected: user management cannot live in a per-user worker.

**Option C - put the console inside Financial Insights.** FI already has sign-in and a remote listener, but its
remote listener faces the internet through Funnel; hosting system administration there widens the attack
surface for no gain. Rejected.

## Design

### Components

```
                 identity.db (users, grants, totp, activity, admin audit, session epochs)
                   ^ read/write                         ^ read (+ activity writes, own password change)
                   |                                    |
Admin app (127.0.0.1:5056, local only) ---------- Financial Insights (5057 local / 5058 remote via Funnel)
   |  install-wide settings (app.db settings rows, via src/system_config.py)
   v
Retirement Planner (5050 / PyWebView) -- keeps per-plan engine knobs, links to the Admin app
```

### 1. Shared identity store: `src/identity/`

Extract `AccessStore` into `src/identity/store.py` (generalised; the FI module becomes a thin re-export during the
transition, then is deleted).

Location: `local_state/identity.db` in the workspace root, through the store layer (needs an entry in the
`test_no_data_file_io_enforcing_regression.py` allow-list, like `access.db` today). Schema version starts at 3 so
it continues from `access.db`'s `user_version = 2`.

Tables:

| Table | Columns (new in **bold**) |
|---|---|
| `users` | id, display_name, username, pw_hash, pw_salt, scrypt_n, must_change, created_at, updated_at, failed_count, locked_until, last_signin_at, **role** (`admin`/`user`), **status** (`active`/`disabled`), **expires_at** (nullable), **session_epoch** (int), **notes** |
| `app_grants` (new) | user_id, app (`insights`, `planner`), **money_view** (insights only), **views** (JSON list, insights only; null = all), granted_by, granted_at |
| `totp` (new) | user_id, secret (encrypted, see below), enrolled_at, last_used_step, recovery_codes (hashed) |
| `activity` | existing columns plus **app** |
| `admin_audit` (new) | at, admin, action, target_user, details (never passwords, codes, secrets, amounts or full account numbers) |

Rules:
- `money_view` moves from `users` to the `insights` grant. No grant means no Financial Insights sign-in.
- The last active admin cannot be demoted, disabled, expired or deleted (the store enforces it, not only the UI).
- Disabling, deleting, expiring, resetting a password, resetting TOTP, revoking a grant or changing a money view
  increments `session_epoch`; apps compare it on every request (below).
- Usernames stay lower-cased and unique. Passwords keep scrypt and the 10-character minimum.
- **TOTP secrets** are encrypted with a key held in the Windows Credential Manager through `src/secrets_store.py`
  (a new entry, not in `identity.db`), so a copied database does not yield working second factors.
- **Migration**: on first start, if `data/access.db` exists next to the FI log and `identity.db` has no users,
  copy users (hashes and salts unchanged, so nobody has to reset a password), give each an `insights` grant
  carrying their old `money_view`, copy the activity rows with `app = 'insights'`, then rename `access.db` to
  `access.db.migrated` (never delete). The owner becomes the first `admin` account through a one-time CLI
  (`python -m admin_app create-admin`), because the owner never had an FI account (they use the local listener).

### 2. Admin app: `admin_app/`

- `admin_app/main.py`: argparse like FI (`--retirement-system-dir`, `--port 5056`, `--no-open`), already-running
  detection (FI's `_port_in_use`), loopback bind only, no remote listener.
- Trust boundary, same as FI's local listener: loopback `Host` only, proxy headers refused, Origin check on
  writes, and FI's `check_funnel_target(5056)` refuses to start if Tailscale serves the admin port. There is no
  admin sign-in in this slice (local owner only); the multi-user gateway adds admin sign-in with TOTP in front of
  the same routes later. This is decision 2 below.
- Routes:
  - Users: `GET/POST /api/users`, `POST /api/users/{update,reset-password,disable,enable,delete,reset-totp,
    end-sessions}`, `GET/POST /api/users/grants`. Every write goes to `admin_audit`.
  - Activity: `GET /api/activity?app=&person=&from=&to=` across apps; `GET /api/audit`.
  - Settings: `GET/POST /api/settings` (install-wide runtime rows only; engine rows are rejected with 400),
    `GET /api/settings/pricing-test` (the symbol tester), `GET /api/tax-law-dashboard`.
  - System: server status of each app (ping 5050/5057/5058 on loopback), Tailscale Funnel status read-only,
    clear WebView cache, shutdown of the Admin app itself.
- Frontend: `admin_app/frontend/` with `index.html`, `admin.js` (moved from `frontend/js/admin.js`, trimmed),
  `users.js` (new; replaces FI's `access.js`), `admin.css` (moved). Same guided three-column layout as today.

New nav:

| Group | Pages |
|---|---|
| Users & access | Users (list, add, edit, grants), Two-factor sign-in, Sessions, Activity, Admin audit |
| System | App settings (hosts, ports, start commands, cache, status of each app), Runtime & files, Dashboard & security, Build timeout |
| Market data | Pricing controls (provider keys, CACHE/LIVE/OFFLINE), Refresh & drift |
| Governance | Tax-law update dashboard (read-only) |

What does **not** move (stays in the planner, see section 4): Capital market assumptions, Asset correlations,
Tax modeling (Plan Settings), Global rebalancing, Annuity calibration, Workbook build diagnostics, CSV backup.

### 3. Financial Insights changes

1. **Sign-in against `identity.db`.** `register_access` takes the shared store. A sign-in succeeds only if the
   user is `active`, not expired, and has an `insights` grant. Same error text for every refusal ("Incorrect
   username or password") so the sign-in page does not reveal which accounts exist or are disabled.
2. **TOTP.** After the password, users with TOTP enrolled enter a 6-digit code; `last_used_step` blocks replay.
   Enrolment is self-service on first sign-in when the admin has set "two-factor required" on the user (default
   on for new users; decision 3). New page `financial_trends_reporter/frontend/totp.html`.
3. **Cross-process revocation.** Each session records the user's `session_epoch` at sign-in. The gate already
   reads the user row on every request (`access_routes.py:92`); it now also ends the session if the epoch has
   moved, the user is disabled or expired, or the grant is gone. This replaces the in-process
   `sessions.end_user()` calls, which cannot reach FI from the Admin app.
4. **Money view and views from the grant.** `user["money_view"]` becomes `grant["money_view"]`;
   `POST /api/view` refuses a view outside the grant's `views` list, and the frontend hides those tabs from
   `/api/whoami` (which gains `views`).
5. **Remove owner-only people code.** Delete `/api/people*`, `/api/activity`, `/access.js`, `OWNER_ONLY_PREFIXES`
   and `access.js`. The local listener's People button becomes "Manage people", opening
   `http://127.0.0.1:5056/#users` (and starting the Admin app if it is not running, by the same launcher pattern
   FI uses for itself).
6. **Activity rows** carry `app = 'insights'`; the existing `ACTIONS` map is unchanged.
7. Self-service password change stays in FI (it writes the shared store and bumps nobody's epoch but its own
   other sessions).

### 4. Retirement Planner changes

1. **Remove the console**: delete `frontend/admin.html`, `frontend/js/admin.js`, `frontend/css/admin.css` after
   the move. `/admin` and `/system-configuration` answer with a small page that opens the Admin app
   (`http://127.0.0.1:5056/`), or a 302 when it is running; in PyWebView mode `openSystemConfigurationConsole()`
   opens the Admin app in the system browser instead of navigating the planner window.
2. **Engine knobs stay as plan assumptions.** Keep a planner route for the five engine sections, renamed from
   `/api/admin/system-config` to `/api/plan/engine-assumptions` (GET/POST, engine rows only, saved to the active
   plan exactly as `admin_service.save_system_config` does now). The batch assumption editor switches to it. The
   five pages become a "Plan assumptions" group reached from the planner's existing Settings area, reusing the
   section-settings renderer. To stay inside the frontend size ratchet, that renderer is moved from `admin.js`
   into one shared module rather than duplicated (see Phase 5).
3. **Keep** `/api/admin/diagnostics` and `/api/admin/csv-backup` in the planner (they are per workspace), renamed
   under `/api/workspace/` with the old paths kept as aliases for one release.
4. **Move** `/api/admin/system-config` (runtime rows), `/api/admin/mode`, `/api/admin/server`,
   `/api/admin/clear-webview-cache`, `/api/admin/tax-law-dashboard` to the Admin app. The checklist close-out's
   tax-law check calls a read-only planner route that the Admin app also uses, so the governance logic stays in
   `src/governance` and is not duplicated.
5. `/api/admin/server/shutdown` stays (the planner shuts itself down); the Admin app calls it.
6. Update `src/server/route_manifest.py`, regenerate the architecture diagram.

### 5. Settings across processes

- The Admin app writes install-wide rows with the existing store functions (`src/system_config.py`,
  `set_system_settings`, `system_config_rows`) on the planner workspace's `app.db`. SQLite handles the two
  writers; the planner already re-reads per call. Settings flagged "restart required" (host, port) show a banner
  in the Admin app with a "Restart planner" action (shutdown, then the existing launcher).
- `_record_admin_config_change` keeps recording change events in `app.db`, and the Admin app adds an
  `admin_audit` row with the acting admin.
- Forward compatibility: in the multi-user server, install-wide settings must not live in a per-user `app.db`.
  The Admin app reads and writes them through one module (`admin_app/settings.py`) so that a later move to a
  `system.db` is a one-file change. Not done in this plan.

### 6. Security

- Account numbers stay masked to the last 4 everywhere, including the activity and audit views.
- No passwords, TOTP codes, secrets, cookies or amounts in any log.
- The Admin app never listens on anything but loopback and refuses to start if Funnel targets its port.
- FI's remote listener gains TOTP and grant checks; it still never exposes user-management routes.
- Run the `security-review` skill over the FI gate and the Admin app before merging Phase 4.

## Decisions this plan makes (override any of them)

1. **Engine knobs stay in the planner** as per-plan "Plan assumptions"; only install-wide settings move. An
   admin-owned "defaults for new plans" page can come later.
2. **Admin app is loopback-only with no sign-in** in this slice, the same trust as FI's local listener. Admin
   sign-in arrives with the multi-user gateway.
3. **TOTP is required by default for new FI users**, optional per user; existing migrated users are prompted to
   enrol at next sign-in.
4. **Planner access grants are stored but not enforced** until the multi-user gateway exists (there is no planner
   sign-in today).
5. **Port 5056** for the Admin app (not on Chrome's restricted list; clear of 5050, 5057, 5058).
6. **One identity database** in the workspace's `local_state/`, migrated from `access.db` without forcing
   password resets.

## Implementation plan

Each phase lists model and effort, its share of a 5-hour Claude Code cycle on the Pro plan (not a token count),
and what drives the cost. **Check `/usage` against these estimates as the plan executes.**

**Calibration.** Sizes are in 5-hour Claude Code cycles, not developer-days. The multi-user server plan was
estimated at 39-54 days (8-11 weeks) and was implemented in 3 cycles, about one cycle per 13-18 estimated days.
This plan's first draft said 14.5-20.5 days; at that ratio it is about 1-1.5 cycles. Phase 5 gets extra margin
because its cost is test churn (about 20 files reading the console source) and Playwright re-runs, which compress
less than writing new code does.
Every PR runs `python tools/fast_gates.py` before push, regenerates
`documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` when files under `src/` or `frontend/` change, and
names test files `tests/test_<scope>_<type>.py` with no tracking ids. New tests do not assert string literals
against frontend source.

### Phase 0 - Inventory (about 0.05 cycle; open cycle 1)

- List every test that loads `admin.js`/`admin.html` and classify it: moves with the code, rewritten against the
  Admin app, or deleted with the removed feature. List every planner caller of `/api/admin/*` (survey above has
  the starting set).
- Confirm `src/system_config.py` can be imported by a process with no planner app object (no `app_core` import
  side effects).
- Model/effort: Sonnet, low. Usage: light. Driver: Grep over `tests/` and `frontend/js`; do not read `admin.js`
  whole.

### Phase 1 - Shared identity store (0.15-0.2 cycle)

- `src/identity/store.py` (from `AccessStore`), schema v3, grants, epochs, roles, status, expiry, last-admin rule,
  admin audit, `access.db` migration, `create-admin` CLI. FI keeps working through a re-export with no behavior
  change yet.
- Tests: `tests/test_identity_store_unit.py`, `tests/test_identity_migration_functional.py` (migrated hashes still
  verify; money view lands on the grant; `access.db` renamed, not deleted).
- Model/effort: Opus, high for the schema and migration; Sonnet, medium for the tests. Usage: moderate. Drivers:
  `access_store.py` is small; the cost is the migration test matrix.

### Phase 2 - Admin app shell and user management (0.2-0.3 cycle)

- `admin_app/` package, launcher (`admin_app/launchers/START_ADMIN_APP.bat`), loopback trust checks, user,
  grant, activity and audit routes, `users.js` page (add, edit, grants with money view and views, disable,
  expiry, reset password, end sessions, activity by app).
- Tests: `tests/test_admin_app_users_functional.py` (routes through the WSGI facade),
  `tests/test_admin_app_listener_regression.py` (non-loopback Host refused, proxy headers refused, Funnel check),
  one Playwright spec for add-user and grant.
- Model/effort: Sonnet, medium (Opus, high for the trust-boundary review). Usage: moderate. Driver: new code,
  small files.

### Phase 3 - Financial Insights on the shared store (0.15-0.2 cycle)

- Switch `register_access` to the shared store; grant, status, expiry and epoch checks in the gate; money view
  and views from the grant; `/api/whoami` gains `views`; delete the people routes and `access.js`; "Manage
  people" link.
- Update `tests/` that cover FI access (Grep `access_routes`, `access_store`, `/api/people`); add
  `tests/test_insights_grant_gate_functional.py` (no grant, disabled, expired, epoch bump each end the session on
  the next request).
- Model/effort: Sonnet, medium. Usage: moderate. Drivers: FI's `main.py` (525 lines) and its tests; read only the
  gate and route sections.

### Phase 4 - Two-factor sign-in (0.15-0.25 cycle)

- TOTP enrolment and verification in FI (stdlib HMAC; no new dependency), recovery codes, admin reset from the
  Admin app, encrypted secrets via `secrets_store`.
- Tests: RFC 6238 vectors, replay refusal, lockout interaction with the existing throttle.
- Then the `security-review` skill over the FI gate and Admin app.
- Model/effort: Opus, high. Usage: moderate to heavy. Driver: the security review pass.

### Phase 5 - Move system configuration (0.5-0.8 cycle; the expensive phase)

- 5a. **Extract the shared settings renderer** (section settings, field help, CSV grid) from `admin.js` into one
  module that both the Admin app and the planner's Plan assumptions page load. Measure `wc -l frontend/js/*.js`
  before and after.
- 5b. Move the install-wide pages and routes to the Admin app; add `/api/plan/engine-assumptions` to the planner;
  switch the batch assumption editor; add the Plan assumptions group; redirect `/admin` and
  `/system-configuration`; aliases for the renamed workspace routes; update `route_manifest.py`.
- 5c. Delete `admin.html`/`admin.js`/`admin.css` from `frontend/`. **Lower** the `test_frontend_size_ratchet`
  ceiling by the lines that left `frontend/js` (never raise it), and add a separate ceiling for
  `admin_app/frontend` at its post-move size.
- 5d. Migrate the ~20 console tests per the Phase 0 classification; re-record
  `tests/e2e/admin-config-change.spec.js` against the Admin app. The planner's nav steps are not changed, so the
  `wi015-navigation-baseline` should not move; if it does, re-record with `WI015_RECORD=1`.
- Model/effort: Opus, high for 5a and the route split; Sonnet, medium for 5b-5d. Usage: **heavy**.
- **Disproportionately expensive**: `admin.js` is very large (Grep the function, read with `offset`/`limit`,
  never whole); ~20 test files; Playwright. Scope it down by doing 5a as its own PR with no behavior change,
  migrating tests file by file with `pytest tests/test_x.py -v` (not the full suite) in the loop, and running the
  full suite once at the end, logged to the scratchpad with `-v -rfE`.

### Phase 6 - Launchers, docs and gates (about 0.1 cycle, mostly waiting on the full test run)

- Desktop shortcut and start scripts for the Admin app; the planner's launcher does not start it automatically.
- Update `documentation/reference/CLAUDE.md` (architecture map: three apps, identity store), the design spec,
  and the FI README; regenerate the architecture diagram.
- Full `pytest` (logged, background), `npm test`, Playwright e2e, `python tools/fast_gates.py`.
- Model/effort: Sonnet, low. Usage: light to moderate (the full test run is the driver).

## Rough effort

| Phase | First draft (days) | Calibrated (5-hour cycles) | Usage within its cycle |
|---|---|---|---|
| 0 Inventory | 0.5 | ~0.05 | light |
| 1 Identity store | 2-3 | 0.15-0.2 | moderate |
| 2 Admin app and users | 3-4 | 0.2-0.3 | moderate |
| 3 FI on the shared store | 2-3 | 0.15-0.2 | moderate |
| 4 Two-factor | 2-3 | 0.15-0.25 | moderate to heavy |
| 5 Move system configuration | 4-6 | 0.5-0.8 | heavy |
| 6 Launchers, docs, gates | 1 | ~0.1 | light to moderate |
| **Total** | **14.5-20.5 days** | **about 1.3-1.9, plan for 2 cycles** | |

Suggested split:
- **Cycle 1:** Phases 0-3 (identity store, Admin app with user management, FI on the shared store). Ends with a
  working, shippable user-management feature.
- **Cycle 2:** Phase 4 (two-factor plus the security review), Phase 5 and Phase 6. If Phase 5's test migration
  runs long, stop after 5b (the move works, old console still present) and finish 5c-5d and Phase 6 in a short
  third cycle.

Phases 1-4 (user management) and Phase 5 (configuration move) are independent after Phase 1 and can ship in
either order; user management first delivers the visible feature sooner and carries less test churn.

## Risks

- **Test churn in Phase 5**: ~20 files read the console source; some assert on panel JS as text and are an
  interface contract. Classify first (Phase 0) rather than discovering them in a fix loop.
- **Two writers on `app.db`**: low risk with SQLite and short transactions; covered by a test that saves from the
  Admin app while the planner reads.
- **Lock-out of the only admin**: the store refuses to remove the last admin; the `create-admin` CLI is the
  break-glass path (local, not on any listener).
- **Migration surprises**: `access.db` is renamed, never deleted, so a rollback is a rename back plus the
  previous release.
- **Golden masters**: engine code is not touched; the engine-knob save path is moved, not changed, so no pin
  should move. Run `pytest tests/test_phase_golden_equality_regression.py -v` once after Phase 5 to confirm.
