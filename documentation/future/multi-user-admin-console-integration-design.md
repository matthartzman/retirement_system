# Multi-user server: one user-management UI (Admin console behind the gateway)

Status: approved
Date: 2026-11-17

Owner decision (2026-11-17): retire the gateway's own `/gateway/users` page and put the planner's Admin console
behind the gateway sign-in, so there is one user-management UI. This document is the design only. No code is
written, and nothing here touches the installed server at `C:\RetirementPlanner`.

Read with `multi-user-server-gateway-design.md` (accounts, login, CSRF), `multi-user-server-supervisor-design.md`
(workers and the `rpw_<id>` Windows accounts), `multi-user-server-security-review.md` and `admin-app-plan.md`.
Evidence is cited as `file:symbol`. Anything not read or run is marked **not verified**.

## 1. Summary and recommendation

The two UIs sit on two different user stores with two different trust models:

| | Gateway (`src/gateway/`) | Admin console (`admin_app/`) |
|---|---|---|
| Store | `GatewayStore`, `gateway.db` (`users`, `totp_secrets`, `sessions`, `audit_log`, `worker_accounts`) | `IdentityStore`, `identity.db` (`users`, `app_grants`, `totp`, `activity`, `live_sessions`, `admin_audit`) |
| Who may use it | Anyone with a password and TOTP, over the internet (Funnel) and loopback | Loopback only, no sign-in, "owner (PC)" is the only actor (`admin_app/trust.py`, `routes_users.py:ADMIN_NAME`) |
| Side effects of a user change | Starts, stops and deletes per-user workers, `rpw_<id>` Windows accounts, workspaces (`supervisor.py:user_created/disabled/deleted`) | None. It edits rows only |
| CSP | `default-src 'self'` (no inline script or style) (`app.py:CSP`) | `'unsafe-inline'` allowed; `index.html` uses inline `onclick` |
| Other powers | none | install-wide settings write, start/stop planner and other processes, shutdown (`routes_system.py`, `routes_processes.py`) |

**Recommendation (option B below): the gateway hosts the Admin console's Users experience itself.** The
gateway's store stays the only identity store on the server. The shared Users UI (`admin_app/frontend/users.js`
and `admin.css`) is served by the gateway at `/gateway/admin`, talks to admin-only routes the gateway already
guards, and is adapted to hide what has no meaning on the server. The standalone `admin_app` process is not run on
the server and is not proxied.

Why not proxy the whole `admin_app` (option A): it would need a second process trusting an identity header from
the gateway, it would put install-wide settings, process start/stop and shutdown on an internet-facing listener
behind a role check, its CSP and inline handlers conflict with the gateway CSP, and its store would still not be the
one that drives login. Section 3 lists what option A would cost.

## 2. Identity: which store is canonical, and how people map to everything else

**Canonical: `GatewayStore`.** It is the store that authenticates (scrypt password, mandatory TOTP, lockout,
sessions) and that the supervisor keys everything off (`user_id` → worker slot, `rpw_<id>` account, `data/users/<id>`
workspace). A second store that could say "this person exists" would have to be reconciled with it on every change.
On the multi-user server `identity.db` is not used. (Financial Insights is not part of the multi-user server; **not
verified** that no deployed component there reads `identity.db`, to be checked in phase 1.)

Mapping, with no mapping table needed: **an Admin-console "person" is a gateway `users` row.** The row id is the
only key; `rpw_<id>`, the worker slot, the workspace folder and the audit `target_user_id` all derive from it.

Lifecycle, as the console would drive it (all already implemented by the gateway routes and `_notify` hooks):

| Console action | Gateway effect | Data consequence |
|---|---|---|
| Add person | `store.create_user(..., must_change=True)`, then `user_created`: workspace folder, `rpw_<id>` account with random password and logon rights, Monarch mapping seed | New empty plan data. If the Windows account step fails the user row exists without an account; today's behaviour is unchanged and phase 1 adds a test that the page shows the error |
| Disable | `set_disabled`; sessions ended; worker stopped, build queue entries dropped; Windows account disabled | Data kept. Reversible with Enable |
| Enable | row enabled; Windows account enabled | Worker starts at next sign-in |
| Delete | worker stopped, final backup if backups are configured, Windows account and profile deleted, workspace folder removed | **Irreversible: all of that person's plans and data are deleted.** The console's current text ("This cannot be undone") is not enough; the gateway-mode dialog must say plans and data are deleted and require typing the username to confirm |
| Reset password / reset two-factor | temp password with `must_change`; TOTP row removed, re-enrol at next sign-in | none |

No new data is stored for existing users. Rows created before this change simply have no value for any new column.

## 3. Serving the console behind the gateway

### 3.1 Option B (recommended): gateway-hosted, shared UI

- **Paths.** `GET /gateway/admin` (page, admin only), `GET /gateway/admin/static/<name>` (an allowlist of exactly the
  shared files: `users.js`, `admin.css`, the small adapter script), and the existing `POST/GET /api/auth/admin/...`
  routes. `GET /gateway/users` becomes a redirect to `/gateway/admin#users`. All of these are inside the gateway's
  existing `/gateway/` and `/api/auth/` namespace, so the worker proxy never sees them
  (`app.py:_is_gateway_path`, checked before `up.forward`).
- **Session and CSRF.** Unchanged: the same session cookie, the same per-session `X-CSRF-Token`
  required on every unsafe request (`app.py:_run_gate`). `users.js` today sends no CSRF header (it has no session);
  the gateway-mode adapter reads the token from `/api/auth/session` the way `gateway.js` does and adds the header.
- **Origin / Host / Fetch-Metadata.** Unchanged and inherited: loopback Host only on the local listener, public
  origin allow-list on Funnel, `Origin` required on unsafe methods, `Sec-Fetch-Site: cross-site` refused. The
  admin console's own loopback-only `check_request` is not used on the server.
- **CSP.** The page is served with the gateway CSP, so: no inline script, no inline style, no `onclick`. `users.js`
  already avoids inline handlers and styles (its header says so; `esc()` guards every dynamic string); the new shell
  page is written for the gateway rather than reusing `admin_app/frontend/index.html`, which has inline `onclick`.
  A test asserts the served CSP and that the page loads with zero CSP violations.
- **What admin_app needs to change.** Nothing needs to trust the gateway session, because `admin_app` is not in the
  request path. Changes are confined to the shared Users module: (a) read its API base path and CSRF token from the
  host page instead of hard-coding `/api/users`, (b) read a `features` object from the list response and hide
  sections that have no meaning (section 5), (c) take the password minimum from the server (12). The standalone
  desktop Admin app keeps working as it does today.
- **API shape.** Either `users.js` calls the gateway's existing `/api/auth/admin/users/<id>/...` routes through a
  small JS adapter, or the gateway adds a thin Python compatibility layer that returns the console's JSON shapes.
  Recommended: the Python layer (`src/gateway/admin_console.py`), because it is unit-testable without a browser and
  keeps the JS identical in both hosts. It must be generated from the same store calls, with no second code path for
  authorization.
- **Ordinary users never reach admin routes.** Today this is one prefix check in `_run_gate`
  (`/api/auth/admin/` and `/gateway/users`). The design makes it deny-by-default: every route under
  `/gateway/admin`, `/gateway/admin/static`, `/api/auth/admin/` and the compat prefix requires an active admin session,
  checked in the gate before any route function runs; a contract test walks the app's URL map and fails if any route
  whose path matches an admin prefix is reachable by a user session (403) or an anonymous one (302/401). A user also
  gets no link to the page.

### 3.2 Option A (rejected): proxy the whole `admin_app`

Needed: run `admin_app` as a second process; the gateway forwards `/admin/*` with an identity header it signs;
`admin_app` drops its loopback-only checks (`trust.py` rules 1-3) and trusts that header; its CSP and inline handlers
are rewritten; `routes_system.py` and `routes_processes.py` (settings write, start/stop planner, shutdown, end
sessions) are removed or gated; its `admin_audit` actor becomes the signed-in admin; and its store is replaced by
the gateway's anyway. That is Option B's work plus a second trust boundary, so it is rejected.

## 4. Gateway-only capabilities the owner wants kept

| Capability | Where it lives in the console |
|---|---|
| Unlock | "Unlock" button in the dialog's "Password, sessions and removal" section, shown only while the person is locked (gateway store `unlock`) |
| Make admin / Make user | The dialog's Role select, saved with Save. Server rule unchanged |
| Last-admin rule | Enforced in the store, not the UI: demoting, disabling or deleting the only active admin is refused with the same message, surfaced inside the dialog. Tests cover role change, disable and delete, and two concurrent attempts |
| Audit log (who did what) | The console's "Admin audit" page reads the gateway `audit_log` (actor, event, target, details, client address, listener). It replaces the console's `admin_audit`, whose actor is the fixed string "owner (PC)". The gateway log is a superset (it also records sign-ins and lockouts) |
| Mandatory two-factor and TOTP reset | The "require two-factor" switch is not shown (section 5). "Reset two-factor" stays. First sign-in after a reset forces re-enrolment |
| 12-character minimum password | Gateway-mode server value is 12 (`store.py:MIN_PASSWORD_LENGTH`). The console's 10 comes from `access_core.MIN_PASSWORD_LENGTH`, shared with the single-user Admin app and Financial Insights. Reconcile on the server by passing the minimum into the console (server-provided, not a JS constant) and keeping 12 in the gateway store; the single-user apps stay at 10 (decided) |
| Temporary-password flow | `must_change=True` for every created or reset password, unchanged |
| Reset password prompt | Replaced by the console's inline field (no `window.prompt`) |

## 5. Console fields with no meaning on the gateway

| Field | Recommendation | Security effect if wrongly shown or ignored |
|---|---|---|
| Access expiry | **Implement** (decided; phase 2). Add `users.expires_at`; refuse at login, TOTP verify and on every session lookup; treat expired like disabled for worker stop | If shown but not enforced, an admin believes access ended when it did not. Enforcement touches the login path, so it needs the most tests |
| Notes | **Implement** (decided; phase 2). Admin-only, never in any user-facing response or in worker identity headers | Low risk if admin-only; a free-text field could hold sensitive data, so it is excluded from the audit log details |
| Planner access grant | **Hide.** Every active user has the planner; "Can sign in" is the Disable/Enable switch | Showing an off switch that does not block anything is false assurance |
| Financial Insights grant, money view, per-view access | **Hide.** Financial Insights is not in the multi-user server | Same false-assurance risk; no gateway enforcement exists |
| Require two-factor | **Hide; show "Two-factor: required"** | A working off switch would defeat mandatory TOTP (plan decision 5) on an internet-facing server |
| End sessions | **Implement** as a small admin route (ends all of one person's sessions; disable already does this) | none beyond admin-only |
| Edit display name | **Implement** (admin route, audited). Needed because the redesigned Edit dialog shows an editable name | Name is shown in the audit and in the worker identity display name; sanitise length and control characters |
| Activity by app | **Hide in phase 1.** The gateway audit page covers who did what; per-app activity could map to proxy request logs later | none |
| Settings, Processes, Shutdown pages | **Not exposed.** Server settings stay with the gateway CLI and config; these controls start and stop processes on the host | Exposing them to a web role check would be the largest new attack surface in this change |

## 6. Migration, rollback, tests

**Migration.** Schema version 3 adds nullable columns (`expires_at`, `notes`); existing rows keep working with
NULL. The owner's existing single-admin `gateway.db` needs no data change: the admin, their TOTP and the worker
account are untouched. No people are imported from a local `identity.db`: password and TOTP secret formats differ
(TOTP is sealed with a different key), and the server's people are created through the console. The runbook gets a
"copy `gateway.db` before upgrading" step.

**Rollback.** Everything is additive. Phase 1 keeps `/gateway/users` available behind the redirect until phase 3
removes `users.html`. Reverting the code leaves the new columns in place and unused. Restoring the pre-upgrade copy
of `gateway.db` is the fallback.

**Test plan** (Playwright in `tests/e2e_gateway`, gateway functional tests, `tests/test_multi_user_isolation_*`):
1. Route contract: walk the URL map; every admin-prefixed route returns 403 to a user session and 302/401 to anonymous.
2. An ordinary user cannot list, read, edit, disable, delete or reset any other person, and cannot reach `/gateway/admin`
   or its static files; ids are not enumerable by trying them.
3. Missing or wrong `X-CSRF-Token`, forged `Origin`, wrong `Host`, cross-site Fetch-Metadata: each refused on every admin write.
4. Last-admin rule for role change, disable and delete, including two simultaneous requests.
5. Min password 12 enforced by the server regardless of the page.
6. Served CSP equals the gateway CSP; the admin page runs with no CSP violation (browser console check).
7. Delete removes the `rpw_<id>` account and workspace (elevated test, skipped without elevation as today), and the confirm text names the data loss.
8. Disable stops a running worker and ends sessions; expiry (phase 2) refuses an already-open session at its next request.
9. Notes and expiry never appear in any non-admin response or in proxy identity headers.
10. Audit rows carry the real actor for every console action.

## 7. Phases and estimates

Sizes are 5-hour Claude Code cycles on a Pro plan (see memory note on plan calibration); check `/usage` against
them as work proceeds. Recommended model for every phase: Sonnet, medium effort; use high effort only for phase 2
login-path changes.

| Phase | Work | Cycles | Cost drivers | Weight |
|---|---|---|---|---|
| 1. Console on the gateway | `/gateway/admin` page and static allowlist; shared `users.js` parameterised (base path, CSRF, features, min password); compat layer; deny-by-default admin guard and route-contract test; `/gateway/users` redirect; Playwright journeys | 1 to 1.5 | Reading `users.js` (188 lines) and `admin.css`, the gate; Playwright runs of a real gateway (about 15 s each) | Moderate |
| 2. Missing admin features | Migration v3 (`expires_at`, `notes`); edit-name and end-sessions routes; expiry enforced on login, TOTP and session lookup; tests | 1 | Login path is security-critical: repeated test-fix cycles in `test_gateway_auth_functional.py`; scope by running only gateway tests while iterating | Moderate to heavy |
| 3. Retire and document | Audit page on the gateway log; delete-confirmation wording; remove `users.html` and old JS; update runbook, security review and architecture diagram | 0.5 | Docs edits; diagram regeneration | Light |
| 4. Optional | Per-user activity (no `identity.db` import, decided) | 0.5 | New code with little reuse | Moderate |

Total for phases 1 to 3: about 2.5 to 3 cycles. Not a spend-heavy search: avoid reading `dashboard.js`-sized files; this
touches `src/gateway/` and `admin_app/frontend/` only. Keep new frontend lines out of `frontend/js` so the size ratchet
is unaffected (`admin_app/frontend/` and `src/gateway/pages/` are outside it; **not verified** that the ratchet and
architecture-diagram checks treat `admin_app/frontend` that way).

## 8. Decisions (owner, 2026-11-17)

All eight questions are answered. Nothing below is open.

1. **Option B confirmed.** The gateway hosts the Users UI at `/gateway/admin` on `gateway.db`. `admin_app` is not run or proxied on the server.
2. **Access expiry: implement** (phase 2), enforced at login, TOTP verify and every session lookup.
3. **Notes: implement** (phase 2), admin-only, excluded from audit details and from any non-admin response.
4. **Minimum password: 12 on the multi-user server only.** The single-user apps (Admin app, Financial Insights) and `access_core.MIN_PASSWORD_LENGTH` do not change; the console receives the minimum from the server.
5. **No import from `identity.db`.** People are re-created by hand (the phase 4 import is dropped).
6. **Settings, process start/stop and shutdown stay off the server.**
7. **Delete requires typing the person's username**, with a warning that their plans and data are deleted.
8. **PR 466 is closed as superseded.**

Phase 4 now contains only the optional per-user activity view. Phases 1 to 3 are unchanged; implementation has not started and begins only on the owner's go-ahead.

## 9. Phase 2 as built (2026-11-17)

Schema version 3 adds `users.expires_at` and `users.notes` (additive; older rows keep working). Expiry is enforced at
password check, on every session lookup (pending and active, so the second-factor step is covered) and is audited;
an expired person gets the same generic sign-in error as any failure and is not counted toward lockout. An expired
admin does not count as an active admin, so the last-admin rule also refuses expiring the only usable admin;
`break-glass` clears an expiry. The console gained edit-name, notes, access end and End sessions
(`/api/auth/admin/console/users/update`, `.../end-sessions`). Notes are admin-only and never in the audit text.

Known limit: when an expiry passes by itself, the person is locked out at the gateway but their `rpw_<id>` Windows
account is not disabled until an admin disables them or sets a past date in the console (which stops the worker and
disables the account). No sign-in path reaches that account, so this is housekeeping, not an access path.
