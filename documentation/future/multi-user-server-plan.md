# Multi-User Server Plan

Status: draft (revision 3: owner decisions recorded 2026-11-15)
Date: 2026-11-15

## Goal

Run the retirement planner on one server here and let several remote users use it from a browser, each
with their own private plan data. Users need only a browser, so the client platform (Windows, Mac, phone,
tablet) stops mattering. This supersedes `documentation/future/macos-port-plan.md` for the "run on a Mac"
goal; the desktop PyWebView mode stays as it is for local single-user use.

Revision 2 folds in two independent critical reviews (one architect, one developer). Both checked the plan
against the code and reached the same verdict: Option A is the right design, but revision 1 had two false
assumptions, under-sized Phase 1 and Phase 5, and overstated the isolation that Option A gives. Nothing here
has been built or measured; Phase 0 exists to confirm the numbers.

## Owner decisions (2026-11-15) and what they change

| Decision | Effect on the plan |
|---|---|
| About 10 users who do **not** trust each other | Separate OS accounts per user are now **required**, not optional: each worker runs under its own Windows account with folder permissions that exclude every other user. Adds about 3-5 days to Phase 3. |
| Monarch moves to the user level, using the Monarch **MCP** (corrected from "map") | Each user connects their own Monarch account to the planner through Monarch's MCP connector with OAuth, and the data lands only in that user's workspace. This is unverified against Monarch's documentation; Phase 0 tests it with a real account, and a CSV upload fallback is designed. The account mapping (`monarch_account_map`) is seeded per user from an admin-curated CSV, separately. Phase 4 is rewritten. |
| Reachable securely from any platform (Windows machine host); implementer chooses the easiest way | **Tailscale Funnel** in front of the gateway, plus gateway login with mandatory TOTP. See "Remote access decision" below. |

### Remote access decision: Tailscale Funnel

Chosen because it is the easiest to implement here and needs nothing from the users but a browser:
- The repo already uses it: `financial_trends_reporter/listeners.py` documents the pattern (Funnel delivers every
  request from 127.0.0.1, so the port is the trust boundary, with a `tailscale serve status` misconfiguration check
  at line 53). The planner reuses that pattern on its own gateway port.
- No router changes, no domain purchase, no certificate work: Funnel gives a public HTTPS name and terminates TLS
  on this machine.
- Works from any browser on any platform; users install nothing.

Costs and rules:
- Funnel is the public internet, so the gateway login, mandatory TOTP, throttling and lockout are the real
  protection, not network privacy. Funnel serves only on a few external ports (443, 8443, 10000); the trends
  reporter's remote listener and the planner gateway must not collide.
- Client IP is lost (everything arrives from 127.0.0.1). Per-IP throttling must use the forwarded header, trusted
  only from the Funnel listener, as the reporter already does for `x-forwarded-for` and `tailscale-*` headers.
- Workers bind loopback on port 0 and Funnel must never target a worker port. Reuse the reporter's check for that.
- Phase 0 confirms bandwidth for workbook downloads and that the Tailscale node stays up as a service.
- Fallback if Funnel proves too limited: Cloudflare Tunnel with Cloudflare Access (adds a login in front of the
  gateway, but needs a domain). The gateway design does not change.

## What the survey found

The app is built as a single-user system. Server mode exists (`python main.py --mode server`, stdlib HTTP on
port 5050), but it assumes one owner:

| Area | Current behavior | Evidence |
|---|---|---|
| Identity | None. Every request is the same all-permissions local user; audit rows hardcode `user_id="local"`. | `src/permissions.py:20`; `src/workspace_context.py:43,47`; `src/server/security_audit.py:88,114-124` |
| Access control | One shared API token, **checked only when the configured host is not loopback**. A loopback worker accepts any local caller with no token. | `src/server/app_core.py:1161`; `src/http_runtime/host_guard.py:63` |
| CSRF | Any request carrying `Authorization` or `X-API-Token` skips the CSRF check and the Content-Type allow-list, so a gateway that injects the token turns the worker's CSRF defence off. | `src/server/app_core.py:1132-1140` |
| Server-path guard | The allow-list for server-side paths switches **off** when the host is loopback. | `src/server/plan_routes.py:172-181` |
| Plan data | One workspace per process, fixed at import; one `plan.rpx`; one `local_state/app.db`; one process-wide active plan. | `src/server/app_core.py:133,137`; `src/plan_registry.py` |
| Path coupling | About 92 call sites use `workspace_root()` and friends; about 60 use `active_plan_*` helpers. | grep counts over `src/` |
| Builds | In-memory job registry; the build is a plain `Popen` (no process group or job object) that itself starts a process pool of up to CPU-count-1 workers. | `src/server_services/build_job_service.py:157,325`; `src/reporting/sheets_strategy.py:445-451` |
| Secrets | One OS credential-store service name; provider keys also read from process environment first. | `src/secrets_store.py:24`; `src/market_data.py:273-310` |
| Package-root fallbacks | The repo's own `output/` is served as a fallback, and the build runs with `cwd=BASE_DIR`. The repo root holds the owner's real data. | `src/server/base_routes.py:76-79`; `src/server/workbook_routes.py:370,411,427` |
| Routes | 266 route decorators (198 in `plan_routes.py`). `/api/shutdown` has no permission check. | `src/server/workbook_routes.py:852-863`; `src/server/admin_routes.py:107` |
| Existing remote-access code | `financial_trends_reporter/` already has scrypt accounts with lockout (`access_store.py`), 10-minute idle sessions (`sessions.py`), login routes (`access_routes.py`) and Tailscale Funnel listeners (`listeners.py`). | those files |
| Frontend headroom | `frontend/js` is 43,668 lines against a ceiling of 43,685: 17 lines of room. | `tests/test_frontend_size_ratchet.py:703` |

## Options

**Option A - one worker process per user behind a gateway (recommended, confirmed by both reviews).**
A gateway authenticates the user and forwards each request to that user's own copy of the server, started with
its own workspace and a random token. The planning code, stores and golden masters stay essentially as they are.
- Both reviewers confirmed Option B is unsafe here: the workspace, runtime config, price caches and active plan
  are module-level singletons fixed at import.
- **Isolation (from the architect review, now applied):** a process per user only isolates *data paths*. It
  becomes a security boundary only with both Phase 1's remote-mode fixes **and** one Windows account per user,
  because users do not trust each other. Containers are not the practical step on this host.

**Option B - one process, request-scoped context.** Rejected for now (about 150 call sites plus global state;
a single missed spot leaks data). The request context already uses `contextvars`
(`src/http_runtime/wsgi_facade.py:35-36`), so it stays feasible later.

**Option C - containers per user.** Not worth the tooling on a Windows host at this scale.

## Architecture (Option A)

```
Browser --HTTPS--> Tailscale Funnel (public HTTPS name, TLS ends on this machine)
                      --> Gateway (login, sessions, CSRF, admin, audit log, supervisor)
                            --loopback + per-worker token--> Worker(user)  [own Windows account, headless, port 0]
                      gateway.db (users, sessions)               data/users/<id>/ plan.rpx, local_state/app.db,
                                                                 output/, saved_plans/, input/
```

- **A hardened front is required; Tailscale Funnel is the chosen one.** The stdlib server has no TLS, no socket timeouts, one thread per
  connection, reads only `Content-Length`, and buffers whole bodies in memory (`src/http_runtime/server.py:17-42`,
  64 MiB cap in `host_guard.py:14`). It must never face the internet directly.
- **Gateway is the sole authority for CSRF, Origin, cookies and identity.** It strips client-supplied
  `Authorization`, `X-API-Token`, `X-Forwarded-*` and `Cookie` headers, injects the worker token, rewrites
  Host and Origin exactly (the worker compares them as exact strings including port, `app_core.py:1097-1100`),
  owns the `/api/auth/session` CSRF token route, and re-frames every request (single `Content-Length`, no
  conflicting headers, timeouts, size limits).
- **Worker** is a new headless entry point, not `main.py --mode server` (which opens a browser on the host at
  `main.py:107` and does not seed the demo plan from source, `platform_runtime.py:117-119`). Model it on
  `tools/e2e_server.py:78-98`; add port-0 binding with the chosen port reported back, explicit provisioning, a
  parent-death watchdog and a scrubbed environment.
- **Install directory:** run from a clean install or frozen build with no owner data, not the working copy.

## Remote mode (Phase 1 contract)

A single opt-in flag (`RETIREMENT_SYSTEM_REMOTE_MODE=1`) switches the worker into these behaviors. It is off by
default so desktop mode and existing tests keep working.

1. The token is required on every request regardless of bind address, including `/api/ping`; startup fails if
   the token is empty.
2. **Deny-by-default route allow-list.** Only routes on an explicit list are served (266 routes exist; a
   block-list will rot). Always refused: `/api/shutdown`, `/api/admin/server/shutdown`,
   `/api/admin/clear-webview-cache`, Monarch scheduled-task routes (`plan_routes.py:344,350`; the task name
   `RetirementSystem_MonarchAutoImport` is machine-wide), `/api/conversion/*`, secret-store UI, and any route
   taking a server path.
3. **One workspace-confinement resolver** applied in the services, covering request paths *and* paths that
   arrive through stored settings or the registry: backup directory (`local_backup_scheduler.py:91`), Monarch
   source dir (`monarch_autoupdate.py:209`), `Runtime/sqlite_db` and `app_db` overrides (`app_core.py:186`),
   `desktop_download_folder`, `local_plan_data_roots` (`plan_routes.py:146-160`), `output_dir`, and the plan
   registry's absolute paths (`/api/plans/switch`, `plan_registry.py:199`). The supervisor pins
   `RETIREMENT_SYSTEM_SQLITE_DB`, `_APP_DB` and `_OUTPUT_DIR` through the environment, and the environment wins.
4. Disable the legacy `BASE_DIR/output` fallback and the `package_root()/input/demo` read; scrub the
   environment passed to workers and build subprocesses (the build currently copies the whole environment,
   `workbook_routes.py:240`).
5. Generic error bodies (today unhandled errors return the exception class and message, `app_core.py:166`);
   remove `base_dir` from the public `/api/ping` and server paths from save responses.
6. Plan upload and download through the browser. The CSRF gate allows only JSON or text bodies
   (`app_core.py:1139`), so `.rpx` upload is either base64 in JSON or an explicit gate change.

## Security requirements

- HTTPS only; passwords with scrypt; cookies `HttpOnly`, `Secure`, `SameSite=Strict`; CSRF owned by the gateway;
  login throttling and lockout; optional TOTP (recommended for financial data).
- Account numbers stay masked to the last 4 digits everywhere, including logs and the admin view.
- **Secrets:** with one Windows account per user, the Windows Credential Manager is private to each account, so
  `secrets_store.py` can work unchanged **if** the worker is launched with the user's profile loaded (Phase 0
  verifies this; the fallback is per-user encrypted secrets in the user's own database). A shared provider key
  is a gateway-held environment variable passed only to workers that need it.
- **Per-user Windows accounts:** standard local accounts created by the gateway with random passwords held in a
  store only the gateway account can read; interactive and remote-desktop logon denied; each user's data folder
  grants access only to that account and the gateway account; `gateway.db`, the gateway code and every other
  user's folder are unreadable to worker accounts; the code and Python runtime are read-only to them; a Job
  Object per worker caps memory. Optional later: Windows Firewall rules per account to limit outbound traffic.
- **Audit:** the gateway keeps its own access and audit log (the per-user `app.db` can be altered by the user's
  own worker), recording the real user id.
- Disk encryption (BitLocker) on the data volume; backups encrypted and kept off synced folders.

## Phases

Each phase lists model and effort, a relative Claude Code usage estimate against a 5-hour Pro-plan session (not a
token count), and what drives the cost. Check `/usage` against these as the plan executes.

### Phase 0 - Decisions and measurement spike

Close decisions 1-7 below before any build work (several gate Phases 1-4). Then measure with throwaway scripts:
cold start and resident memory of one headless worker; **peak memory of a whole build tree** (build subprocess
plus its process pool, not "MB per worker"); two users building at once; what a source worker does on a
completely empty workspace; whether keyring works under a service account; whether killing a worker orphans its
build (Job Object kill test).
- Also prove the per-user-account mechanism on this machine: create two throwaway standard accounts, launch a
  trivial process as each from a service (`LogonUser` plus `CreateProcessAsUser` when the gateway runs as
  LocalSystem, or `CreateProcessWithLogonW` when it runs as an ordinary service account, which cannot be called
  from LocalSystem), with the profile loaded, then confirm account A cannot read account B's folder and that
  Credential Manager entries are separate. Decide whether the new server-only dependency (`pywin32`) or `ctypes`
  is used.
- Also test the Monarch MCP end to end with one real Monarch account (read-only): connect through OAuth from a
  throwaway script, list the tools, pull a sample of transactions and balances, check token refresh after the
  access token expires, and check whether a third-party client can register. This is the go/no-go for the
  connector design versus the CSV upload fallback in Phase 4.
- Also confirm Tailscale Funnel basics: external ports available, bandwidth for a large workbook download, and
  that the node survives reboot as a service.
- Model/effort: Sonnet, medium. Usage: light to moderate. Driver: reading startup and memory logs.
- Exit: written figures and a go/no-go on Option A with per-user accounts; Funnel confirmed or Cloudflare chosen.

### Phase 1 - Remote mode for one worker (sized 8-10 days)

Implement the "Remote mode" contract above, plus the headless worker entry point.
- Inventory by Grep on request-field names, `Path(`, `/api/` route decorators and settings keys; read only the
  matching functions with `offset`/`limit` (`plan_routes.py` is 2,513 lines).
- Route inventory already identified by the reviews: path-taking routes (`/api/plan/save-as`,
  `/api/plan/load-file`, `/api/ytd/account-setup/recover`, backup config and run, Monarch config), process and
  host routes (shutdown, webview cache, scheduled task), and info leaks (`/api/ping`, save responses). Already
  browser-safe: `/api/xlsx`, `/files/<path>`, `/api/export/*`, `/api/import/*`, `/api/admin/csv-backup`.
  `src/desktop_api.py` is the PyWebView bridge only and is not reachable over HTTP, so it is out of scope.
- Exit criterion: a written **shared-state inventory** (scheduled task, credential store, env keys, `BASE_DIR`
  fallbacks, the trends reporter's fixed ports 5057/5058, logs, temp dirs) with each item disabled, namespaced or
  moved per user in remote mode.
- Model/effort: Opus, high for the route allow-list and resolver design; Sonnet, medium for the route changes.
- Usage: heavy. Drivers: large route files, and tests that read panel JS as text (treat their assertions as an
  interface contract). Keep remote mode opt-in because existing security and plan-file tests will break otherwise.

### Phase 2 - Gateway: accounts, login and sessions (4-6 days)

- **Extract and generalise** `financial_trends_reporter` access code (`access_store.py`, `sessions.py`,
  `access_routes.py`) into a shared module so there is one account store and one login system, not two. Inspect
  those files first to confirm they fit; if not, build new and migrate the reporter later.
- Roles `admin` and `user`; admin-created accounts only; first-admin CLI; password change; disable; TOTP.
  **Any number of admins:** an admin can promote or demote another account; the last remaining admin cannot be
  demoted, disabled or deleted; every admin action goes to the gateway audit log with the acting admin's id; a
  new admin enrolls their own TOTP at first login. A break-glass CLI on the server (run by the Windows administrator,
  not reachable from the web) can reset an admin's password and TOTP if all admins are locked out.
- `gateway.db` with its own schema versioning. The gateway serves its own login page, user menu and Users page,
  so none of that lands in `frontend/js`.
- Gateway returns a 401 JSON for `/api/*` and a 302 for HTML pages.
- Model/effort: Opus, high for the design; Sonnet, medium for the build. Usage: moderate to heavy.

### Phase 3 - Supervisor, proxy, per-user accounts and the isolation gate (8-12 days)

- Start a worker per logged-in user with port 0 binding (no free-port race; note `allow_reuse_address = True` at
  `http_runtime/server.py:71` can permit a second bind on Windows), per-user workspace, random token, scrubbed
  environment, and explicit provisioning from the demo seed or a blank plan.
- **Windows Job Objects with kill-on-close** for each worker; never idle-reap a worker while `/api/build/status`
  shows a running job; cap the per-build pool size; a global queue for concurrent builds by intercepting
  `/api/build/start`; a real service wrapper for the gateway (Task Scheduler does not supervise).
- **Per-user Windows accounts** (decision: users are mutually untrusted): the supervisor creates a local standard
  account when an admin creates a user, sets folder permissions, launches that user's worker under it with the
  profile loaded, and disables or deletes the account and profile when the user is removed. Account passwords
  are random, never shown to anyone, and rotated. The gateway service account needs the privilege to create
  accounts and launch processes as them (settled in Phase 0). The code and runtime are installed once, read-only
  to worker accounts; a frozen build in a read-only folder is the simplest way to guarantee that.
- Proxy notes: responses are fully buffered with no keep-alive or WebSocket, so a buffered proxy works. Build
  progress is polled. Block the SSE route `/api/build/events/<id>` (`workbook_routes.py:288`), which buffers
  until the build ends and pins a thread.
- Scheduled backups appear to run only from a route call, so they will not run for reaped workers: run them from
  the gateway.
- **Isolation test harness lands here, as a CI gate**, not at the end: two users, spawned as subprocesses in the
  style of `tests/e2e/fixtures.js:56-94`, because `tests/conftest.py:58-123` builds one workspace per session at
  import time and cannot host two users in-process.
- Model/effort: Opus, high for the supervisor; Sonnet, medium for the rest. Usage: moderate to heavy.

### Phase 4 - Secrets, per-user Monarch and disables (5-7 days; part of the minimum slice)

Revision 1 left this out and would have shipped the shared credential store and the scheduled-task route to
remote users, so it stays inside the minimum slice.
- **Monarch at user level, through Monarch's MCP connector** (owner decision, correcting the earlier "map"
  reading). The existing extractor drives a Playwright browser with a persistent profile and a manual login plus
  2FA (`Monarch Extractor/monarch_extract.py:1018,1192`), which cannot work for a remote user because the login
  needs a visible browser on the server. Monarch's own help page describes an MCP connector at
  `https://api.monarch.com/mcp` that uses OAuth, with access revocable by the user from Monarch's settings.
  Design, assuming that holds up:
  1. The user clicks "Connect Monarch" in the planner. The gateway starts the OAuth authorization in their own
     browser and receives the callback on the Funnel HTTPS name (the redirect address must be registered with
     Monarch). The planner never sees the user's Monarch password or 2FA.
  2. The tokens are stored per user, inside that user's own Windows account (Credential Manager) or an encrypted
     per-user file, never in a shared place. Request read-only access; do not request write.
  3. The planner acts as an MCP client (new server-side dependency, the `mcp` Python SDK; check it supports the
     Python version the build uses). On login or on demand, the user's worker calls the connector's tools for
     accounts, balances and transactions, and maps the results into the existing import shapes
     (`src/monarch_import.py` for transactions, `src/monarch_balances_import.py` for balances; both currently read
     the extractor's output files, and the extractor's `run_id` and "mark delivered" bookkeeping is not needed).
  4. Each user disconnects or revokes at any time; removing a user deletes their tokens.
- **Facts not yet verified (Phase 0 must settle these before any build work).** The help page was not readable
  from here, so none of this comes from Monarch's documentation:
  - the official tool list and whether it covers transactions with ids, dates, merchants, categories and the
    balance history the planner imports (a third-party write-up mentions "data gaps");
  - whether a third-party application such as the planner is allowed to be an OAuth client (dynamic client
    registration, or a registered client id) rather than only the AI tools Monarch names;
  - token lifetime and refresh, because on-demand sync needs a refresh token to work while the user is away;
  - rate limits and result paging for several years of history;
  - the connector's current status: two web sources disagree about a June 2026 launch, a pause and an October 2026
    relaunch.
- **Fallback if the connector cannot serve the planner:** each user downloads Monarch's own CSV export in their
  browser and uploads it (an upload route using the same import schemas, reusing the extractor's raw-export
  normalizing function if it can be called on its own; Grep `monarch_extract.py` first, it is 1,458 lines). This
  stores no Monarch credentials either and works on any platform.
- **Account mapping.** Separately from the connector, provisioning copies an admin-curated mapping CSV into each
  new user's workspace through the existing seeder (`src/monarch_mapping_seed.py`, `seed_mapping`), so a new user
  starts with sensible account matches and can edit them. Mappings are per user.
- The scheduled-task route and the extractor launchers stay disabled for remote users. Unattended scheduled sync
  is not planned in this phase: a reaped worker cannot sync, so sync runs on login and on demand, and a
  gateway-driven schedule can be added later once token refresh is understood.
- Per-user secret handling as in the security section; shared provider key as a gateway environment variable.
- Model/effort: Opus, high for the OAuth and token-handling design; Sonnet, medium for the import mapping.
  Usage: moderate to heavy. Drivers: protocol details and live testing with a real Monarch account.

### Phase 5 - Frontend (3-5 days)

- First, an extraction task to create line headroom under `test_frontend_size_ratchet` (17 lines today); never
  raise the ceiling. Check `wc -l` on `frontend/js/*.js` before and after.
- Upload and download UI for Save As and Load (today they hard-fail without `window.pywebview`:
  `dashboard_decomp_checklist_closeout.js:516-534,653-667`), plus the other path-based callers
  (`dashboard_decomp_local_backups.js:76`, `dashboard_decomp_monarch_autoupdate.js:108`, `dashboard.js:2197`,
  `admin.js:463`, `dashboard_decomp_conversion.js:135,139`) hidden or replaced in remote mode.
- 401 handling is not one place: `api_client.js`, a separate `api` helper in `admin.js:9`, and about 20 raw
  `fetch(` calls across 8 files. Remove the `http://127.0.0.1:5050` fallback at `dashboard.js:5893` in remote
  mode; frontend URLs are root-absolute, so the gateway cannot mount under a path prefix.
- Avoid adding nav steps (the `wi015-navigation-baseline` e2e baseline moves). Do not add tests that grep
  frontend source for string literals.
- Model/effort: Sonnet, medium. Usage: moderate. Driver: `dashboard.js` and `admin.js` are huge; Grep for the
  function, never read whole.

### Phase 6 - Operations (3-4 days)

- Remote access through Tailscale Funnel pointed at the gateway port only (see "Remote access decision"), with
  the reporter's misconfiguration check reused so Funnel can never target a worker or the reporter's local port.
  Mandatory TOTP enrollment at first login. User account lifecycle runbook: create, disable, delete (account,
  profile, folder), password rotation.
- Service wrapper, no-sleep policy, health page, log rotation.
- Nightly encrypted backup of `data/users/` and `gateway.db`, run by the gateway (always-on server), to a
  **configurable destination** that defaults to a folder on the same server outside the synced and user-readable
  trees; retention count configurable; a tested restore, including restoring one user without touching others.
  The destination setting is admin-only and goes through the same path-confinement review as other stored
  paths, since it is a server-side path (it is set by an admin, never by a user). The backup is encrypted with a
  key kept separately from the backup folder, so copying the folder elsewhere later is safe.
- **Upgrades:** an offline "migrate all users" command that backs up each user first and reports failures,
  because startup migration swallows failures by design (`src/bootstrap.py:141-147`) and each user would
  otherwise migrate lazily, possibly several versions late. Include a rollback procedure.
- Model/effort: Sonnet, medium. Usage: light to moderate.

### Phase 7 - Verification and security review (4-6 days)

- Extend the Phase 3 isolation harness: user A cannot read or change user B's plan through any API route,
  crafted path, settings-borne path, copied session id, guessed worker port, forged `Host` or `Origin`, or
  missing token; sessions expire; logout invalidates the cookie; error bodies leak no paths.
- Load test at the target user count, using the Phase 0 build-tree memory figure.
- Fast tier (`pytest -m "not slow"`), `npm test`, Playwright e2e, then the security review skill over the gateway
  and Phase 1 changes. `gateway.db` may need an entry in the `test_no_data_file_io_enforcing_regression.py`
  allow-list.
- Model/effort: Opus, high for the review; Sonnet, medium for the tests. Usage: heavy. Cost control: write pytest
  output to a log with `-v` and read only the tail; isolation tests are slow-tier and Windows-flaky, so run them
  once per change, not in a fix loop.

### Phase 8 - Docs and gates (1 day)

Update `documentation/reference/CLAUDE.md` and the design spec; regenerate
`documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` in every PR that adds a file under `src/`
(`python tools/generate_system_diagram.py`); run `python tools/fast_gates.py` before every push.
- Model/effort: Sonnet, low. Usage: light.

## Naming and CI rules for the new files

- Test files: `tests/test_<scope>_<type>.py` with a type suffix; no tracking ids in names.
- New tests must not assert string literals against frontend source; use Playwright, the Node vm sandbox or an
  API response.
- Plan data keeps going through the store layer; no direct data-file I/O outside the allow-list.
- CI stays on Windows.

## Decisions

Settled by the owner (2026-11-15):
1. About 10 users. 2. Users do not trust each other, so one Windows account per user. 3. Secure access from
any platform, implementer's choice: Tailscale Funnel. 4. Monarch is per user and uses the Monarch MCP connector.

Settled by this plan (override if you disagree):
5. **Two-factor login is mandatory** for every user, because the entry point is the public internet and users
   are mutually untrusted.
6. **Price-provider keys:** one shared key held by the gateway, passed to workers as needed; per-user keys can
   be added later.
7. **Frozen build** installed to a read-only folder on the server, not a source run, so worker accounts cannot
   alter code and a clean install directory comes for free (the existing PyInstaller build seeds a fresh
   workspace for each new account).

Settled by the owner (later the same day):
8. The Monarch MCP is **Monarch's own connector** at `api.monarch.com/mcp` (OAuth, no password stored), not a
   community server.
9. The server machine is **always on**, so the gateway can later run scheduled work (for example a gateway-driven
   Monarch sync) once token refresh is understood.
10. The owner is the only admin now, but **a second admin must be possible**: see Phase 2.

11. The nightly encrypted backup goes **on the same server for now, and the destination is configurable** (a
    gateway setting, changeable without code changes). Same-server backups protect against deletion and bad
    upgrades but not against disk failure, theft or ransomware; the plan keeps the setting so a second disk, a
    network share or an off-site target can be pointed at later. Whatever the target, it must stay out of
    synced folders such as OneDrive.

Nothing is open at the decision level; the only unverified items are the Phase 0 checks (per-user accounts,
Funnel, Monarch connector).

## Risks

- **Cross-user leakage** remains the main risk. Phase 1's allow-list and resolver and Phase 3's isolation gate
  are what prove it, not the process split by itself.
- **Memory:** a build is a process tree with a pool of up to CPU-count-1 workers; two concurrent builds can
  oversubscribe the machine. Phase 0 measures this.
- **Orphaned processes:** no process group or job object exists in `src/`; without Job Objects, killing a worker
  leaves its build running and writing output.
- **Same-account limitation** and Windows host hardening, as above.
- **Golden masters** are not affected (engine code is untouched), but a regression run is still required.
- **Legal and liability** obligations apply if users are paying clients; get advice.

## Rough effort (revised)

| Phase | Revision 1 | Current (rev 3) | Main reason for the change |
|---|---|---|---|
| 0 Spike | 0.5 day | 1.5-2 | empty-workspace start, per-user account launch test, Job Object test, build-tree memory, Funnel check |
| 1 Remote mode | 3-5 | 8-10 | allow-list, settings-borne paths, headless worker, upload/download backend |
| 2 Gateway auth | 3-4 | 4-6 | CSRF ownership, TOTP; offset by reusing the reporter's access code |
| 3 Supervisor, proxy, accounts, isolation gate | 3-4 | 8-12 | Job Objects, build-aware reaping, subprocess harness, one Windows account per user |
| 4 Secrets, per-user Monarch, disables | 1 | 5-7 | Monarch MCP client and OAuth callback, import mapping, map seeding; now in the minimum slice |
| 5 Frontend | 2-3 | 3-5 | size ratchet, 401 handling in many places |
| 6 Operations | 2 | 4-5 | service wrapper, restore test, migrate-all, Funnel, account lifecycle runbook |
| 7 Verification | 3 | 4-6 | subprocess isolation harness |
| 8 Docs | 0.5 | 1 | |
| **Total** | **18-23 days** | **39-54 days (8-11 weeks)** | reviews put the single-account design at 30-42 days (developer) and 5-7 weeks (architect); per-user accounts and the Monarch MCP client add about two weeks |

Minimum viable slice: Phases 0-4 plus a minimal login page with TOTP and Funnel access, admin-created users only,
and Monarch connected through the MCP (or the CSV upload fallback), is about 5.5-7.5 weeks (revision 1 said 1.5-2).
If Phase 0 shows the connector cannot serve the planner, the CSV fallback takes Phase 4 back to about 3-4 days.

## Review log

| Finding (source) | Where it landed |
|---|---|
| Token not enforced on loopback (both) | Remote mode item 1 |
| Gateway token injection disables worker CSRF (architect) | Architecture: gateway owns CSRF; Phase 2 |
| Path guard off on loopback; settings-borne paths (both) | Remote mode items 2-3 |
| Wrong worker entry point; no seeding from source (both) | Architecture; Phase 1; Phase 0 empty-workspace test |
| Route inventory, shutdown routes, scheduled task (both) | Phase 1; shared-state inventory |
| Frontend ratchet 17 lines; 401 handling spread out (developer) | Phase 5 |
| `BASE_DIR` fallbacks leak shared files (both) | Remote mode item 4; clean install directory |
| Windows Job Objects, build-aware reaping, pool cap (both) | Phase 3 |
| Existing reporter access code (architect) | Phase 2 reuses it; decision 3 |
| Proxy semantics, hardened front, SSE, upload gate (both) | Architecture; Phase 3 |
| Upgrades and migration (architect) | Phase 6 |
| Audit and error leaks (architect) | Security requirements; Remote mode item 5 |
| Isolation tests too late; MVP omitted Phase 4 (architect) | Phase 3; Phase 4 in the minimum slice |
| Secrets namespacing gives no isolation (both) | Security requirements; Phase 4 |
