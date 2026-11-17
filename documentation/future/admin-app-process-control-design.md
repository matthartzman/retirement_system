# Admin app: process control and live sessions (design note)

Status: draft
Date: 2026-11-17

Adds two things to the Admin app's "App settings" page: start / stop / status of the Retirement Planner and Financial
Insights (FI), and a live list of signed-in sessions with an end-session action. Engine code is untouched.

## 1. Launching a detached child

`admin_app/processes.py` holds a fixed table of two apps. A request names one of them (`planner` or `insights`); it never
supplies a command, argument or path, so nothing a caller sends reaches a command line.

| App | Command (cwd = repo root, `sys.executable`) | Port |
|---|---|---|
| Planner | `main.py --mode server`, workspace passed as `RETIREMENT_SYSTEM_WORKSPACE_ROOT` | `Dashboard.port` setting, default 5050 |
| FI | `financial_trends_reporter/main.py --retirement-system-dir <workspace> --no-open` | 5057 local, 5058 remote listener |

**Deviation from START_APP.bat.** `START_APP.bat` starts the Planner in desktop mode (a PyWebView window, no HTTP
socket). That has no port to show or probe, so the Admin app starts the Planner in **server mode**, the same entry point
(`main.py`) with `--mode server`. The user gets a loopback server they open in a browser, not the desktop window. FI
matches `START_TRENDS_APP.bat` plus `--no-open` and the workspace argument, as `financial_trends_reporter/admin_launch.py`
already does for the Admin app.

Detaching: `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` on Windows, `start_new_session` elsewhere. Output goes to
`local_state/admin_processes/<app>.log` (not `DEVNULL`, so a crash on start is diagnosable).

## 2. Tracking a process

- **Primary:** a record `local_state/admin_processes/<app>.json` with `pid`, `port`, `started_at` and the process start
  stamp. A record counts only if the pid is alive and, when `psutil` is importable, the start stamp still matches (guards
  against pid reuse). `psutil` is optional; it is not a declared dependency.
- **Fallback:** the port answering. A port that answers with no record is shown as `running (started outside the Admin
  app)`, with no pid.
- States: `running` (port answers), `starting` (record alive, not answering, under 45 s old), `stopped`.
- **Stop:** the Planner is asked to shut down through its own shutdown route first (the existing
  `SettingsService.shutdown_planner`), then the recorded pid's tree is killed (`taskkill /T /F`). FI has no shutdown route,
  so its recorded pid is killed. **The Admin app only ever kills a pid it recorded.** An app started elsewhere returns a
  409 telling the person to close it from its own window; the Admin app does not find a pid by port and guess.
- Start refuses nothing it cannot see: if the port already answers it reports "already running" and spawns nothing.

## 3. When the Admin app exits

Children keep running (they are detached, the same as starting them from a launcher). Stopping the Admin app does not
stop the apps it started. A restarted Admin app finds them again from the records. A record whose process is gone reads as
`stopped`. The panel says so in one line.

## 4. Why the routes cannot be abused from non-loopback

No new trust decision: the routes are registered on the same app behind the same `before_request` gate
(`trust.check_request`): loopback peer, loopback `Host`, no proxy / Funnel header, same-origin `Origin` /
`Sec-Fetch-Site`, JSON `Content-Type` on writes. FI's remote listener is a different process and port; it never imports or
mounts any Admin route, and the Admin app has no `--host`. Further narrowing for these routes:

- app name must be one of two literals (anything else is 400 and does nothing);
- every start, stop and ended session writes `admin_audit` (`process.start`, `process.stop`, `session.end`); a start or
  stop that was already in the requested state is not audited again;
- `tests/test_admin_app_processes_functional.py` repeats the refusals (non-loopback peer, foreign Host, forwarding header,
  cross-origin, non-JSON) against each new write route and asserts nothing was spawned, killed or audited.

Residual risk, unchanged from the existing boundary: any program running as the signed-in Windows user can reach loopback
and could already call `/api/system/planner-shutdown`. These routes add start and stop of two fixed local programs to that
set, nothing more.

## 5. Live sessions

**Finding.** There was no session list to read. FI keeps sessions in memory (`financial_trends_reporter/sessions.py`); the
identity store holds only a per-person `session_epoch`. The Planner has no sign-in on this computer, so it has no sessions.
(The multi-user gateway has its own `gateway.db` and its own people; it is out of scope here.)

**Design.** A small mirror table in the identity store, `live_sessions` (`key`, `user_id`, `app`, `listener`, `source`,
`started_at`, `last_seen`), created with `CREATE TABLE IF NOT EXISTS`, so no schema-version bump.

- `key` is a hash of the cookie token; the token is never stored or returned.
- FI registers a row at sign-in, refreshes `last_seen` from the person-driven idle report it already receives, and drops
  the row at sign-out or when its gate ends the session. FI clears its own rows at start (a restart holds no sessions).
- The Admin app lists rows seen in the last 11 minutes (FI's idle timeout is 10), joined to the person. "From" is
  Remote (with the forwarded address) or This computer.
- **End session** is the existing machinery: `store.end_sessions(user_id)` bumps the epoch, which every app already honours
  on its next request, and now also clears the mirror rows. **This ends all of that person's sessions in every app**, not
  one row, because the epoch is per person. The button and confirmation say so. Ending a single session would need a
  per-session "ended" flag checked in FI's gate; not done, noted as a follow-up.

Not ruled by a table: a crashed FI leaves rows until they age out of the 11-minute window (pruned after a day).

## 6. Frontend

`admin_app/frontend/processes.js` replaces the old App settings page body (stale desktop-mode host/start-command cards
and the planner-only Shut down button). Page lists both apps and the Admin app (state, port, pid, Start / Stop) and the
sessions table; it refreshes every 4 s. The admin frontend line ceiling was not raised: the old page code and a stale
comment block were deleted to make room (ceiling lowered 855 to 854).

## 7. Verification

Unit-style tests use a fake spawner through the WSGI facade; a Playwright spec drives the panel with a stateful mock for
start / stop (so no real app is launched). A real start and stop of the Planner on a spare port and throwaway workspace
was run by hand. Not exercised: a real FI start/stop (the dev FI holds 5057), and the Funnel path.
