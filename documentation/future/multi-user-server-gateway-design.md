# Multi-user server: gateway accounts, login and sessions (Phase 2 design)

Status: draft (built on branch claude/multi-user-phase-2-gateway-auth-c00f4f, not merged)
Date: 2026-11-15

Implements "Phase 2" of `multi-user-server-plan.md` together with its "Security requirements" and decisions
5 (mandatory two-factor login) and 10 (any number of admins). Phase 3 plugs the reverse proxy into the seam
described at the end; nothing here starts workers.

## Reuse of the trends reporter's access code

The reporter's `access_store.py`, `sessions.py` and `access_routes.py` were inspected. They fit only in part:

| Reporter piece | Fits the gateway? | Outcome |
|---|---|---|
| scrypt hashing, password length rule, 5-failure / 15-minute lockout, global sign-in throttle | yes | **extracted** into `src/access_core.py`; the reporter's `AccessStore` now calls it, behaviour unchanged |
| loopback-Host check, proxy-header detection, `tailscale serve status` port check | yes | **extracted** into `src/access_core.py`; `financial_trends_reporter/listeners.py` re-exports the same names and keeps its own message |
| `users` schema (`money_view`, no role, no TOTP, no disable) and the `activity` table keyed by display name | no | gateway has its own schema in `gateway.db` |
| in-memory `SessionTable` (lost on restart, cannot be ended by a CLI, idle extended by page-reported `idle_ms`) | no | gateway sessions live in `gateway.db`, so a break-glass CLI run ends them at once |
| `access_routes.py` (percent view, owner-only listener split, `/api/signin`) | no | reporter-specific; the gateway has its own routes in `src/gateway/app.py` |

The two account stores stay separate on purpose: reporter guests view the owner's own trends on the owner's PC,
gateway users are mutually untrusted planner users. Merging the stores would put reporter guests into the planner's
trust domain. "One login system" is met at the level of the shared primitives; migrating reporter guests into
`gateway.db` is not planned.

## Layout

| File | Role |
|---|---|
| `src/access_core.py` | shared primitives: scrypt, password rule, lockout arithmetic, `FailureThrottle`, `KeyedThrottle`, loopback/proxy/Funnel checks |
| `src/gateway/store.py` | `GatewayStore` over `gateway.db`: schema versioning, users, TOTP secrets, sessions, audit log, last-admin rule |
| `src/gateway/totp.py` | RFC 6238 TOTP (SHA-1, 6 digits, 30 s, +/-1 step, replay refused) |
| `src/gateway/app.py` | `create_gateway_app()`: the gate (Host, Origin, CSRF, session, stage, role), auth and admin routes, pages |
| `src/gateway/upstream.py` | the Phase 3 seam: `Identity`, `Upstream`, `PlaceholderUpstream`, `upstream_headers()` |
| `src/gateway/server.py`, `__main__.py` | the runnable process (`python -m src.gateway`) |
| `src/gateway/cli.py` | server-side CLIs `create-admin` and `break-glass` (no route reaches them) |
| `src/gateway/pages/` | the gateway's own login, TOTP, account and Users pages (not in `frontend/js`) |

## gateway.db

`PRAGMA user_version` holds the schema version; `store._MIGRATIONS` is an ordered list applied in one
transaction each, so later phases append a step. WAL mode, foreign keys on.

- `users(id, username UNIQUE, display_name, role CHECK admin|user, pw_hash, pw_salt, scrypt_n, must_change,
  disabled, failed_count, locked_until, created_at, updated_at, last_login_at)`
- `totp_secrets(user_id PK -> users ON DELETE CASCADE, secret, created_at, enrolled_at NULL = not yet confirmed,
  last_used_step)`
- `sessions(token_hash PK, user_id -> users ON DELETE CASCADE, stage pending|active, csrf_token, created_at,
  last_seen, expires_at, client_ip)`. Only the SHA-256 of the cookie value is stored.
- `audit_log(id, at, actor_user_id, actor_username, event, target_user_id, target_username, details, client_ip,
  listener)`. Usernames are copied as text so deleting a user keeps the history readable. Never holds passwords,
  codes, secrets or cookie values.

The TOTP secret is stored in clear in `gateway.db`; Phase 3's folder permissions make `gateway.db` readable only by
the gateway account, and Phase 6's backup encrypts it.

## Login, two-factor and sessions

1. `POST /api/auth/login {username, password}`. Refused with 429 when the client IP or the whole gateway is
   throttled. A wrong password, unknown user, disabled account or locked account all get the same 401 text, so
   usernames cannot be probed. Five failures (password or code) lock the account for 15 minutes.
2. Success creates a **pending** session (5-minute life) and returns `next`: `enrol` (no confirmed TOTP; the page
   goes to `/gateway/enrol`) or `totp`.
3. `POST /api/auth/totp/enrol/start` returns the secret and `otpauth://` URI; `POST /api/auth/totp/enrol/confirm
   {code}` or `POST /api/auth/totp/verify {code}` promotes the session to **active**. The cookie value and CSRF
   token are rotated at that point (no session fixation).
4. An active session whose user has `must_change` (every admin-created or admin-reset account) may reach only the
   auth API and `/gateway/account` until the password is changed.

Sessions expire after 15 minutes idle (`last_seen`, updated at most every 30 s) and 12 hours absolute. Logout
deletes the row and sends an expired cookie. Disabling, deleting, demoting, a password reset or a TOTP reset ends
every session of that user; a password change ends the user's other sessions.

Cookie: `__Host-rp_session`, `HttpOnly; Secure; SameSite=Strict; Path=/`, no `Domain`, no `Max-Age` (a browser
session cookie).

## CSRF and Origin

- Unsafe methods (POST, PUT, PATCH, DELETE) must carry an `Origin` equal to one of the listener's allowed origins
  (Funnel listener: each `--public-origin`; local listener: `http://127.0.0.1:<port>` and `http://localhost:<port>`).
  A `Sec-Fetch-Site: cross-site` request is refused on any method.
- Every unsafe request except `POST /api/auth/login` must also carry `X-CSRF-Token` equal to the session's token.
  `GET /api/auth/session` returns it in the same shape the planner frontend already reads (`success`,
  `authenticated`, `csrf_token`, `user`), so the existing `dashboard.js` / `admin.js` code works unchanged.
- An unsafe `/api/` body must be `application/json` or `text/plain`, the worker's own rule, because the worker skips
  it for token-carrying requests.

## Client address and throttling

The client address for per-IP throttling and the audit log is the right-most `X-Forwarded-For` entry, and only on
the Funnel listener (Funnel delivers everything from 127.0.0.1). The right-most entry is the one added by the
nearest proxy, so a client-supplied `X-Forwarded-For` cannot pick its own throttle bucket. The reporter takes the
left-most entry, but only for its activity log, never for a security decision. On the local listener
`X-Forwarded-For` and `Tailscale-*` headers are refused (403) and the socket address is used.

Per IP: 10 free failures in 10 minutes, then a doubling delay up to 5 minutes. Whole gateway: 50 free failures in
10 minutes, then a doubling delay up to 60 s.

## Unauthenticated requests

`/api/*` -> 401 `{"success": false, "authenticated": false, "error": "sign in required"}`. Any other path -> 302 to
`/login?next=<path>` (`next` kept only when it is a same-site absolute path).

## Admins

Roles `admin` and `user`; accounts are created only by an admin (no self-signup). An admin can create, promote,
demote, disable, enable, unlock, reset the password of, reset the TOTP of and delete any account. The **last active
admin** (role `admin` and not disabled) cannot be demoted, disabled or deleted: the store checks this inside the
same write transaction (`LastAdminError`). Every admin action writes an audit row with the acting admin's id.

CLIs (run on the server by the Windows administrator, `--password-stdin` for scripts, otherwise a hidden prompt):

    python -m src.gateway.cli create-admin --db <gateway.db> --username <name> [--display-name <text>]
    python -m src.gateway.cli break-glass  --db <gateway.db> --username <admin>

`create-admin` refuses when an admin already exists. `break-glass` works only on an admin account: it sets the new
password, clears TOTP (re-enrolment at next login), unlocks and re-enables the account, and ends its sessions.

## Running the gateway

    python -m src.gateway --db <path>\gateway.db --funnel-port 5065 --public-origin https://<node>.ts.net:8443 [--local-port 5064]

Both listeners bind 127.0.0.1 only. Funnel publishes external 8443 to the Funnel listener (`tailscale funnel
--https=8443 http://127.0.0.1:5065`); 443 belongs to the trends reporter. The local listener refuses to start when
`tailscale serve status` shows its port. The process prints
`RETIREMENT_GATEWAY_READY {"funnel_port": N, "local_port": M}` once listening (port 0 picks a free port).

## Seam for Phase 3

`create_gateway_app(store, upstream=...)`. After the gate has authenticated a request (active session, two-factor
done, password not pending change) and the path is not gateway-owned (`/login`, `/gateway/*`, `/api/auth/*`), the
gate calls `upstream.forward(request, identity)` and returns its `Response`. `identity` is
`upstream.Identity(user_id, username, display_name, role)`; the same object is in `request.environ["gateway_identity"]`.
The default `PlaceholderUpstream` answers 503 JSON for `/api/*` and a short HTML page otherwise.

`upstream_headers(client_headers, worker_port=, worker_token=, body_length=)` is the header contract the proxy must
use. It drops hop-by-hop headers (and any named in `Connection`), `Authorization`, `X-API-Token`, `Cookie`,
`X-CSRF-Token`, `Referer`, `Forwarded`, `X-Forwarded-*`, `X-Real-IP`, `Tailscale-*` and `X-Gateway-*`; it sets
`Host` and (only when the client sent one) `Origin` to `127.0.0.1:<worker_port>` / `http://127.0.0.1:<worker_port>`,
sets `Content-Length` from the re-framed body, and injects `X-API-Token`. `Referer` is dropped because the worker
compares it against its Host when `Origin` is absent. Response `Set-Cookie`
from a worker must be dropped by the proxy (the worker issues none in remote mode).

Enrolment QR code: `segno` 1.6.6 (BSD-3-Clause, pure Python, no dependencies; pinned in `requirements.txt` and
named in the PyInstaller spec's hidden imports) draws the `otpauth://` URI as an SVG data URI on this machine. No CDN
or QR web service sees the secret; the gateway CSP allows `data:` images for it. The key and link stay on the page as
the manual fallback. Licence and source: `src/gateway/THIRD_PARTY_NOTICES.md`.

Not done here: the proxy itself, the supervisor, Windows accounts, idle detection that
ignores background polling (the reporter's `idle_ms` approach; needs Phase 5 frontend work).
