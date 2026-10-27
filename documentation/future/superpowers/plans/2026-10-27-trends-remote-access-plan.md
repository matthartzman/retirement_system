# Trends Remote Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner, a family member and the advisor reach the Financial Trends app from anywhere through one HTTPS link and a personal password, with the server always on.

**Architecture:** One Flask-facade app served on two loopback listeners: 5057 (local, no sign-in, owner-only screens) and 5058 (remote, Tailscale Funnel only, sign-in required). A thin `ListenerApp` wrapper in `financial_trends_reporter/` tags each request with its listener via `LocalRequest.environ`, so nothing under `src/` changes. Accounts, the activity log and (optionally) sessions live in `financial_trends_reporter/data/access.db`.

**Tech Stack:** Python stdlib only (`hashlib.scrypt`, `hmac`, `secrets`, `sqlite3`, `http.server` via `src/http_runtime`), vanilla JS in `frontend/`, PowerShell/Task Scheduler.

**Spec:** `documentation/future/superpowers/plans/2026-10-27-trends-remote-access-design.md`

## Global Constraints

- Ports: local `127.0.0.1:5057`, remote `127.0.0.1:5058`. Both loopback only. Funnel points at 5058 only.
- Passwords: `hashlib.scrypt`, per-user random salt, `hmac.compare_digest`, minimum 10 characters, no other rules. Never stored, logged or echoed in readable form.
- Lockout: 5 consecutive wrong passwords locks that account 15 minutes; a global throttle past ~20 failures in 10 minutes adds a growing delay to every sign-in. The sign-in error never reveals whether a username exists.
- Session: `secrets.token_urlsafe(32)`; cookie `HttpOnly; Secure; SameSite=Strict; Path=/`, remote listener only. Idle timeout 10 minutes of user inactivity; the 5-second ping and Live Snapshot polling must not extend it.
- Owner-only screens (People, Activity) and their APIs return 404 on the remote listener, signed in or not.
- Local listener accepts only `Host` of `127.0.0.1`/`localhost`, and rejects requests carrying `X-Forwarded-For` or any `Tailscale-*` header.
- Exit never stops the server. The page-close watchdog, `/api/closing` and `Lifecycle` are removed.
- No new third-party packages. If anything under `src/` changes: run `python tools/generate_system_diagram.py` and commit the result.
- Never read `frontend/index.html` whole; grep for `exitBtn`, `sendPing`, `pagehide`, tab code.
- Run pytest as `pytest <paths> -v -rfE > <scratchpad>/pytest_<label>.txt 2>&1` (background for long runs) per the user's CLAUDE.md.

## Review Focus

Each line is pinned by a test in the task named in brackets.

1. A request to 5058 that spoofs `Host: 127.0.0.1` or omits cookies must still be treated as remote and refused. [Task 3]
2. Expired/forged/tampered cookie on a data API gets 401 JSON, not the dashboard HTML or a 500. [Task 3]
3. Deleting a person or resetting their password kills their live session on the very next request. [Task 4]
4. Unknown username and wrong password return byte-identical error bodies and similar timing path (dummy hash verify). [Task 3]
5. The Activity log and server logs never contain a password, cookie or token, including on failed sign-in and on password change. [Task 5]

## File Structure

| File | Responsibility |
|---|---|
| `financial_trends_reporter/access_store.py` (new) | `access.db`: users, scrypt hashing, lockout, activity log tables and queries |
| `financial_trends_reporter/sessions.py` (new) | In-memory session table with idle expiry |
| `financial_trends_reporter/listeners.py` (new) | `ListenerApp` wrapper (tags requests local/remote), local-listener hardening, Funnel misconfiguration guard |
| `financial_trends_reporter/access_routes.py` (new) | `register_access(app, store, sessions)`: auth gate, sign-in/out, change-password, People/Activity APIs, event hooks |
| `financial_trends_reporter/main.py` (modify) | Drop `Lifecycle`/closing/exit-stops-server; two listeners; startup checks |
| `financial_trends_reporter/frontend/signin.html`, `access.js` (new); `index.html` (modify, targeted) | Sign-in page, change-password dialog, People/Activity tabs, Sign out, ping idle reporting, view-change reports |
| `financial_trends_reporter/launchers/*`, `tools/launchers/register_trends_server_task.ps1` (new), `stop_trends_server.ps1` (new) | Loopback launchers, logon task, stop script |
| `tests/test_trends_access_*.py` (new) | Unit and functional tests per task |

---

## Phase 1 — Always-on server, loopback launchers, logon task

Model/effort: Sonnet, medium. Usage: **light**. Drivers: `main.py` (441 lines, already read once), two small launcher scripts, three test edits. Not expensive.

### Task 1: Remove the watchdog; Exit never stops the server

**Files:** Modify `financial_trends_reporter/main.py`, `tests/test_trends_reporter_server_functional.py` (tests at lines ~110-133), `financial_trends_reporter/frontend/index.html` (lines ~864-873 only).

**Interfaces:** Produces `create_app(retirement_system_dir, log_path=None) -> Flask` (the `lifecycle` parameter is gone); `/api/ping` stays (returns success, Phase 2 gives it meaning); `/api/exit` returns `{"success": true}` and does nothing else; `/api/closing` is deleted (404).

- [ ] **Step 1: Replace the two Lifecycle tests with** `test_exit_endpoint_does_not_stop_the_server` (post `/api/exit` → 200; app still serves `/api/history` 200) and `test_closing_endpoint_is_gone` (post `/api/closing` → 404).
- [ ] **Step 2: Run** `pytest tests/test_trends_reporter_server_functional.py -v` → expect those two FAIL (`TypeError`/200).
- [ ] **Step 3: Delete** `Lifecycle`, `IDLE_TIMEOUT_SECONDS`, `CLOSE_GRACE_SECONDS`, `/api/closing`, `lifecycle.watch()`, `time` import if unused; make `/api/exit` a no-op success; `main()` builds the server without a holder.
- [ ] **Step 4: In `index.html`** remove the `pagehide` beacon; the Exit button stops confirming a server stop and shows "You can close this tab." (Phase 2 retargets it to Sign out remotely). Keep `sendPing`.
- [ ] **Step 5: Run** the file again → PASS; also `pytest tests/test_trends_app_sync_unit.py -v` → PASS.
- [ ] **Step 6: Commit** `git commit -m "Trends: Exit no longer stops the server; remove page-close watchdog"`.

### Task 2: Loopback launchers, "already running" opens the browser, logon task, stop script

**Files:** Modify `launchers/START_TRENDS_APP.ps1` and `.bat`, `main.py` (`--host` default stays `127.0.0.1`; drop `_lan_ip` and the LAN print); Create `financial_trends_reporter/tools/launchers/register_trends_server_task.ps1` (`-Action Register|Unregister`, trigger AtLogOn, hidden, `python financial_trends_reporter\main.py --no-open`, restart on failure, no run-time limit; modelled on `register_trends_report_task.ps1`), `stop_trends_server.ps1` (`Stop-ScheduledTask` then kill any leftover `python` listening on 5057/5058 by `Get-NetTCPConnection`).

**Interfaces:** `main.main(argv)` returns 0 and **opens the browser** (unless `--no-open`) instead of returning 1 when the port is already served by this app.

- [ ] **Step 1: Test** `test_second_instance_opens_the_browser_and_exits_cleanly` (replace the existing "refuses to start" test at line ~97): with the port taken, `main([])` returns 0 and `webbrowser.open` was called with `http://127.0.0.1:<port>` (monkeypatch both).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** in `main()`. **Step 4: Run** → PASS.
- [ ] **Step 5: Edit the launchers** back to loopback (no `--host 0.0.0.0`); write the register and stop scripts. Verify syntax with `powershell -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw <file>)) | Out-Null"` for each (no registration is executed by the plan).
- [ ] **Step 6: Commit** `"Trends: loopback launchers, logon task and stop script; relaunch opens the browser"`.

---

## Phase 2 — Accounts, hashing, sessions, second listener, sign-in, idle timeout

Model/effort: Opus, high. Usage: **moderate–heavy**. Drivers: security-critical code (reasoning, not file reads), `index.html` regions around the ping/Exit code, repeated test loops. **Expensive steps:** Task 3's auth-gate test matrix and Task 5's browser check. Scope down by running only `tests/test_trends_access_*.py` plus `tests/test_trends_reporter_server_functional.py` until the end of the phase; do the browser check once, not per change. If the user chooses a second sign-in step (open decision a), add a TOTP task here (+1 task, moderate).

### Task 3: Accounts store, hashing, lockout, sessions, listener tagging, auth gate

**Files:** Create `access_store.py`, `sessions.py`, `listeners.py`, `access_routes.py`; Modify `main.py`; Test `tests/test_trends_access_store_unit.py`, `tests/test_trends_access_gate_functional.py`.

**Interfaces:**
- `access_store.AccessStore(path: Path)`: `add_user(display_name, username, temp_password) -> int`; `verify_login(username, password, now) -> LoginResult(ok: bool, user_id: int|None, must_change: bool, reason: Literal["ok","bad","locked"])` (runs a dummy scrypt for unknown usernames); `set_password(user_id, new_password, must_change)`; `delete_user(user_id)`; `list_users()`; `touch_last_signin(user_id)`; `register_failure_global(now)`/`global_delay(now) -> float`. `ValueError` for passwords under 10 chars.
- `sessions.SessionTable(clock=time.monotonic, idle_seconds=600.0)`: `create(user_id) -> str`; `get(token) -> Session|None` (None and removed if idle-expired); `note_interaction(token, idle_ms: int)` (sets last-active to `max(existing, now - idle_ms/1000)`); `end(token)`; `end_user(user_id)`.
- `listeners.ListenerApp(app, listener: Literal["local","remote"])` with `handle_http(...)` that builds `LocalRequest(..., environ={"listener": listener})` and calls `app.dispatch_request`; `listeners.current_listener() -> str` reads `request.environ["listener"]`.
- `access_routes.register_access(app, store, sessions, log)`: a `before_request` gate. Remote: allowed unauthenticated are `GET /signin`, `POST /api/signin`, `GET /signin.js` only; everything else without a valid session → 401 JSON for `/api/*`, 302 to `/signin` for pages. Local: Host check and forwarded-header rejection (421/403), no sign-in.

- [ ] **Step 1: Write failing unit tests** (`test_trends_access_store_unit.py`): `test_password_hash_is_salted_and_verifies`, `test_short_password_rejected`, `test_five_wrong_passwords_lock_for_15_minutes_then_clear` (injected `now`), `test_reset_clears_lockout`, `test_unknown_user_and_wrong_password_give_same_result_shape`, `test_global_delay_grows_after_20_failures_in_10_minutes`, `test_idle_session_expires_after_10_minutes_and_note_interaction_extends_it`, `test_end_user_kills_all_sessions`.
- [ ] **Step 2: Write failing gate tests** (`test_trends_access_gate_functional.py`), driving `ListenerApp(app, "remote")` and `"local"` via `handle_http`: `test_remote_data_api_requires_sign_in` (401), `test_remote_page_redirects_to_signin`, `test_remote_signin_sets_secure_httponly_strict_cookie`, `test_spoofed_localhost_host_header_on_remote_is_still_remote`, `test_tampered_cookie_gets_401_not_500`, `test_signin_error_body_identical_for_unknown_user_and_wrong_password`, `test_remote_has_no_owner_only_routes` (404 for `/api/people`, `/api/activity`, signed in), `test_local_needs_no_sign_in`, `test_local_rejects_foreign_host_and_forwarded_headers`.
- [ ] **Step 3: Run** `pytest tests/test_trends_access_store_unit.py tests/test_trends_access_gate_functional.py -v -rfE > <scratchpad>/pytest_p2t3.txt 2>&1` → FAIL (modules missing).
- [ ] **Step 4: Implement** the four modules to the interfaces above. scrypt parameters n=2**15, r=8, p=1 stored with the hash so they can change later. Schema: `users(id, display_name, username UNIQUE, pw_hash, pw_salt, scrypt_params, must_change, created_at, updated_at, failed_count, locked_until, last_signin_at)`; `PRAGMA user_version` for migrations. Cookie name `trends_session`.
- [ ] **Step 5: Wire `main.py`**: `create_app` calls `register_access`; `main()` starts a second `LocalHTTPServer` on `--remote-port` (default 5058) in a daemon thread, each wrapped by its own `ListenerApp`; `assert_safe_to_bind` still guards both; `--no-remote` flag for tests/dev. Confirm `server_api_token` is not required for loopback binds (existing `assert_safe_to_bind` behavior; add a test only if it is).
- [ ] **Step 6: Run** the new tests plus `tests/test_trends_reporter_server_functional.py` and `tests/test_trends_reporter_origin_check_regression.py` → PASS (existing tests use the bare app and local semantics: `create_app` without a wrapper must behave as local).
- [ ] **Step 7: Commit** `"Trends: accounts, sessions, two loopback listeners and sign-in gate"`.

### Task 4: Sign-in, sign-out, change password, idle reporting; Funnel misconfiguration guard

**Files:** Modify `access_routes.py`, `listeners.py`, `main.py`, `frontend/index.html` (ping/Exit region + a small change-password dialog), Create `frontend/signin.html`, `frontend/signin.js`; Test `tests/test_trends_access_session_functional.py`.

**Interfaces:**
- `POST /api/signin {username, password}` → 200 `{success, must_change}` + cookie; 401 generic error; 429 with `Retry-After` while locked/throttled.
- `POST /api/signout` → ends the caller's session only, clears the cookie. On local, returns success and does nothing.
- `POST /api/change-password {current, new}` → 200, or 400 for short/wrong current. While `must_change` is set, only this endpoint, signout and the static assets work (409 `{"must_change": true}` elsewhere).
- `POST /api/ping {idle_ms}` → calls `sessions.note_interaction`; 401 when the session has expired.
- `GET /api/whoami` → `{listener, name, must_change}` (the page uses it to relabel Exit as Sign out and to show owner-only tabs).
- `listeners.check_funnel_target(run=subprocess.run) -> str|None` returns a message if `tailscale serve status --json` shows anything targeting port 5057, `None` otherwise or when `tailscale` is missing. `main()` refuses to start the local listener when it returns a message.

- [ ] **Step 1: Write failing tests**: `test_signin_then_data_api_works`, `test_signout_ends_only_that_session` (two users, one signs out, other still 200), `test_ping_without_interaction_does_not_extend_idle` (fake clock: pings with `idle_ms` = elapsed leave expiry unchanged → 401 at 10 min), `test_interaction_reported_by_ping_extends_idle`, `test_must_change_blocks_other_apis_until_changed`, `test_change_password_rejects_wrong_current_and_short_new`, `test_delete_user_kills_live_session_next_request` and `test_password_reset_kills_live_session` (store+sessions via the Task 5 APIs may be called directly here), `test_lockout_returns_429`, `test_funnel_guard_flags_5057_target_and_skips_when_tailscale_missing` (inject `run`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the interfaces. The page's `sendPing` becomes `sendPing()` posting `{idle_ms}` where `idle_ms` is `Date.now() - lastInteraction`, updated by `pointerdown`, `keydown`, `scroll`, and view changes; Live Snapshot polling never touches it. Any 401 from `fetch` redirects to `/signin`.
- [ ] **Step 4: Run** all `tests/test_trends_access_*.py` and the server functional file → PASS.
- [ ] **Step 5: Browser check (once, in the preview):** start with `--no-open --remote-port 5058`, sign in on 5058, confirm the dashboard loads, Exit reads "Sign out" and returns to sign-in, 5057 shows no sign-in and no people tab yet.
- [ ] **Step 6: Commit** `"Trends: sign-in/out, change password, idle timeout, Funnel misconfiguration guard"`.

---

## Phase 3 — Activity log

Model/effort: Sonnet, medium. Usage: **light–moderate**. Drivers: one hook point (the gate) plus `index.html` view-change code.

### Task 5: Server-side event log and view reporting

**Files:** Modify `access_store.py`, `access_routes.py`, `frontend/index.html` (tab/view switch code, found by grep); Test `tests/test_trends_access_activity_unit.py`.

**Interfaces:** `AccessStore.log_event(person: str, listener: str, event: str, details: str = "", source: str = "") -> None`; `AccessStore.read_events(person=None, since=None, until=None, limit=500) -> list[dict]` newest first with keys `at, person, listener, event, details, source`. `POST /api/view {view}` logs `view` (whitelisted view names; unknown → 400). Gate logs actions for `POST /api/account`, `/api/account-prefs`, `/api/passthrough-decision`, `/api/run-now`, `/api/run-cancel` with details naming the account key / decision key / item count, never amounts. Person is `"owner (PC)"` on local.

- [ ] **Step 1: Write failing tests**: `test_events_logged_for_signin_failed_signin_lockout_signout_timeout`, `test_failed_signin_logs_attempted_username_and_never_the_password`, `test_actions_logged_with_account_detail_and_no_amounts`, `test_view_endpoint_logs_known_views_and_rejects_unknown`, `test_local_actions_attributed_to_owner_pc`, `test_events_never_contain_cookie_or_token` (sign in, act, scan every row and stored text for the password and token strings), `test_read_events_filters_by_person_and_dates`, `test_source_recorded_from_x_forwarded_for_when_present` (remote only; the real header is confirmed in Phase 5).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (logging in the gate and sign-in routes; session-timeout is logged when `sessions.get` expires a session). **Step 4:** page posts `/api/view` on each tab/view change. **Step 5: Run** all trends access tests + server functional → PASS. **Step 6: Commit** `"Trends: activity log of sign-ins, views and actions"`.

---

## Phase 4 — Owner-only People and Activity screens

Model/effort: Sonnet, medium. Usage: **moderate**. Drivers: new UI in a new `access.js` (keeps `index.html` edits to a tab button and a script tag, avoiding the large file).

### Task 6: People and Activity APIs and screens (local listener only)

**Files:** Modify `access_routes.py`, `frontend/index.html` (tab button + `<script src="/access.js">` only), Create `frontend/access.js`; Test `tests/test_trends_access_owner_screens_functional.py`.

**Interfaces (local only; 404 on remote):** `GET /api/people` → `[{id, display_name, username, last_signin_at, locked, must_change}]`; `POST /api/people {display_name, username, temp_password}` (400 on short password / duplicate username); `DELETE`-by-body `POST /api/people/delete {id}`; `POST /api/people/reset {id, temp_password}` (sets must_change, clears lockout, ends sessions); `GET /api/activity?person=&from=&to=`; `GET /access.js` (local only; the remote page never loads it). All owner actions are logged as `person added|deleted`, `password reset`.

- [ ] **Step 1: Write failing tests**: `test_people_crud_on_local_with_no_accounts_existing` (bootstrapping), `test_duplicate_username_rejected`, `test_reset_sets_must_change_unlocks_and_ends_sessions`, `test_delete_ends_sessions`, `test_people_list_never_returns_hashes`, `test_activity_api_filters`, `test_owner_screen_routes_404_on_remote_even_when_signed_in` (also `/access.js`), `test_remote_index_html_has_no_people_tab_data` (the People tab stays hidden unless `/api/whoami` says `listener == "local"`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** APIs and `access.js` (People table with add/reset/delete using `confirm()` for delete; Activity table with person and date filters; matches the app's existing styles).
- [ ] **Step 4: Run** all trends tests (`pytest tests/test_trends_*.py -v -rfE > <scratchpad>/pytest_p4.txt 2>&1`, background) → PASS; `npm test` untouched here (no frontend module tests added).
- [ ] **Step 5: Browser check (once):** add a person on 5057, sign in as them on 5058, see the entries in Activity, reset and delete, confirm the kicked session lands on sign-in.
- [ ] **Step 6: Commit** `"Trends: owner-only People and Activity screens"`.

---

## Phase 5 — Tailscale Funnel setup and phone test (owner does the Tailscale steps)

Model/effort: Sonnet, low. Usage: **light**. Mostly documentation.

### Task 7: Runbook, final checks, draft PR

**Files:** Create `documentation/reference/TRENDS_REMOTE_ACCESS_RUNBOOK.md` (Tailscale steps, phone checklist, how to stop/restart, how to add a person, how to confirm the Host/forwarded headers Funnel sends and record the finding); Modify `documentation/future/superpowers/plans/2026-10-27-trends-remote-access-design.md` (answers to open decisions; header note that the 93616310 LAN bind is retired).

- [ ] **Step 1:** Write the runbook with the exact manual steps (admin console: enable HTTPS certificates, allow Funnel for the PC; PC: `tailscale funnel --bg 5058`, `tailscale funnel status`, confirm nothing serves 5057 with `tailscale serve status`; register the logon task; the `ts.net` link). Claude does **not** run any Tailscale or firewall command.
- [ ] **Step 2:** Phone checklist (off Wi-Fi): link loads and shows sign-in; wrong password shows the generic error; correct sign-in; temporary password forces change; Live Snapshot works; walk away 10 minutes → signed out; Sign out works; second person unaffected; owner deletes the person → their phone is kicked next tap; `https://<link>/api/history` without cookie is 401; People/Activity not reachable on the phone; reboot-and-logon check.
- [ ] **Step 3:** If any file under `src/` changed (none planned), run `python tools/generate_system_diagram.py` and commit it.
- [ ] **Step 4:** Full relevant run: `pytest tests/test_trends_*.py tests/test_trends_reporter_server_functional.py -v -rfE > <scratchpad>/pytest_final.txt 2>&1`; docs-only rule applies to the PR only if no code changed (it did, so CI applies).
- [ ] **Step 5:** Push, open a **draft** PR, bind it with the ccd_pr tools, hand the user the manual steps and checklist.

---

## Self-review notes

- Spec coverage: two listeners (T3), hardening and guard (T3, T4), always-on and logon task (T1–2), accounts/lockout/throttle (T3), sessions and idle (T3–4), Exit/Sign out (T1, T4), activity log (T5), owner screens (T6), Tailscale setup (T7). Funnel's real Host/forwarded headers are verified in Phase 5, not assumed.
- Open decisions pending the user: (a) second sign-in step; (b) logon vs boot start (affects only `register_trends_server_task.ps1` in Task 2).
- Usage: check `/usage` against the estimates above after Phase 2; if it is already heavy, split Task 4's browser check into the Phase 4 check.
