# Financial Trends: Remote Access — Design

Date: 2026-10-27 · Status: draft for approval

## Intent

The owner wants three kinds of people to use the Financial Trends app (`financial_trends_reporter`, port 5057) from anywhere, not only on the home Wi-Fi:

- the owner, on a phone while away;
- a family member, at their own home;
- the owner's financial advisor, at their own home.

Each guest receives **a link and a password**, and that's all. They install nothing and create no account anywhere else. The owner decides who has access, can remove someone without affecting anyone else, and can see what each person did.

## Decisions the owner made

- **Same view for everyone.** Everyone sees the full app, including the controls that change data (account edits, account preferences, passthrough decisions, starting or cancelling a data refresh). There are no per-person permissions.
- **Location makes no difference.** Home, mobile, or on the home Wi-Fi, the link, sign-in and behaviour are identical.
- **Each person has their own password.** The owner can add people, delete people and reset their passwords. Everyone else can change their own password.
- **No password on the owner's PC.** When the app is used on the PC that runs it, there is no sign-in.
- **Activity log.** It records who signed in and when, and what they did once inside (views opened, actions taken).
- **Exit ends only your own session.** Pressing Exit never stops the server and never affects anyone else, including the owner.
- **10-minute idle sign-out** for remote sessions.
- **Tailscale is acceptable** as the way in, and an odd-looking `https://<pc>.<tailnet>.ts.net` link is fine. No custom domain.
- **Always on.** Whenever the PC is on, the app is running in the background.

## Goals

1. A fixed HTTPS link that works from any browser on the internet, with no software for guests.
2. Per-person accounts with passwords stored only as salted hashes.
3. A complete, owner-readable activity log.
4. An owner-only area on the PC for managing people and reading the log.
5. The server stays up regardless of what anyone does in a browser.

## Non-goals

- Different permissions for different people.
- A custom domain, or Cloudflare.
- Two-factor sign-in, email password resets, or self-service sign-up.
- Access while the PC is off or asleep. The link simply doesn't respond, and that's acceptable.

## Anti-goals (would be a failure even if it "works")

- Anyone reaching any data or API without signing in, unless they're on the owner's PC.
- A guest, or the owner from their phone, being able to stop the server.
- A remote user reaching the people-management or activity-log screens.
- Passwords stored or logged in readable form.

## Architecture

### Two loopback listeners: the port is the trust boundary

Tailscale Funnel delivers internet traffic to the PC through `tailscaled`. That means **every Funnel request arrives from `127.0.0.1`**. Checking the client address can't tell the owner at the PC apart from a guest. So the server runs two listeners, both bound to loopback only:

| Listener | Bind | Who uses it | Sign-in |
|---|---|---|---|
| Local | `127.0.0.1:5057` | The owner's browser on the PC | None. Owner-only screens are available. |
| Remote | `127.0.0.1:5058` | Tailscale Funnel only | Required on every request except the sign-in page and its static assets. Owner-only screens are refused here **whether or not the person is signed in**. |

- Funnel is pointed at the remote port only (`tailscale funnel --bg 5058`). Nothing in Tailscale's config may point at 5057.
- **The LAN (`0.0.0.0`) bind from commit 93616310 is retired.** The launchers go back to loopback, and people on the home Wi-Fi use the same `ts.net` link as everyone else. This also removes the unauthenticated LAN exposure, and the `server_api_token` no longer has to be set for the trends app.
- The owner's own phone uses the link and signs in like anyone else, so the owner needs their own account for that. Owner-only screens stay PC-only even for the owner.
- Both listeners serve the same Flask app instance. Each request must know which listener it arrived on (for example, a per-server flag set into the request environment by `LocalHTTPServer`, or two app wrappers). How that's done is the builder's call. The requirement is that the remote listener can never be mistaken for the local one.
- **Local listener hardening** *(my call)*: 5057 accepts only a loopback `Host` (`127.0.0.1`, `localhost`), which blocks DNS-rebinding pages. It also rejects any request carrying proxy or Funnel headers (`X-Forwarded-For`, `Tailscale-*`). Anyone signed in to Windows on the PC, or any program running there, counts as the owner. The design assumes a single-user PC.
- **Misconfiguration guard** *(my call)*: at startup, the server checks `tailscale serve status --json`. If anything points at 5057, it refuses to start the local listener and prints why. If the `tailscale` command isn't available, it skips the check.
- **Bootstrapping:** the People screen works on 5057 even when no accounts exist. The owner creates their own phone account there, like anyone else's. No CLI is needed.
- The existing Origin check stays. On the remote listener, the expected Host is the `ts.net` name, or the forwarded host Funnel supplies. The builder should confirm what Host header Funnel actually sends.

### Always-on server

- Remove the "stop when the page closes" watchdog (`Lifecycle`, `/api/closing`, the ping-driven shutdown) and stop `/api/exit` from shutting down the server.
- Start the server when the owner logs on to Windows, using a Task Scheduler entry modelled on `financial_trends_reporter/tools/launchers/register_trends_report_task.ps1`. It runs hidden with `--no-open`. *(Builder's call: logon trigger vs. a Windows service. Logon is the expected default.)*
- The owner stops or restarts the server at the PC, through the scheduled task or a small stop script, never from a web page.
- The interactive launchers (`START_TRENDS_APP.bat/.ps1`) open the local page. If the server is already running, they just open the browser instead of failing with "already running".

### Accounts and passwords

- Stored in a **new SQLite file**, separate from the financial data: `financial_trends_reporter/data/access.db`, git-ignored. The builder should confirm `data/` is already ignored.
- Each person has a display name, a username, a password hash, a "must change password" flag, created/updated times, and failed-attempt and lockout fields.
- Hashing uses `hashlib.scrypt` with a per-user random salt (standard library). The repo deliberately avoids web-framework and crypto dependencies (stdlib HTTP runtime), so this stays stdlib. Comparisons use `hmac.compare_digest`.
- Passwords must be at least 10 characters, with no other composition rules. *(My call.)*
- **Guessing protection** *(my call)*: after 5 wrong passwords in a row, the account is locked for 15 minutes. On top of that, a sign-in throttle covers all accounts: past roughly 20 failed attempts in 10 minutes, every sign-in gets a growing delay. This slows attempts spread across many usernames. A lockout can be cleared early by the owner resetting that person's password. Failed attempts are logged, including attempts with unknown usernames. The sign-in error never says whether the username exists. Funnel `ts.net` names show up in public certificate logs, so expect automated guessing.

### Sessions

- On sign-in, the server issues a random token (`secrets.token_urlsafe(32)`) and keeps it server-side, in memory or in `access.db`. The cookie is `HttpOnly; Secure; SameSite=Strict; Path=/` on the remote listener only.
- **Idle timeout is 10 minutes of user inactivity.** The page's 5-second ping and the Live Snapshot polling must **not** reset the idle timer, or nobody would ever be signed out. Only person-driven activity counts, such as clicks, key presses and view changes. One way: the client tracks its last-interaction time and sends it with the ping, and the server expires the session once that's 10 minutes old. Another: only requests marked as user-initiated refresh the session. The mechanism is the builder's call.
- When a session expires, the page shows the sign-in screen. Any unsaved edit is lost, which is acceptable.
- Server restarts may end all sessions. *(Acceptable. In-memory sessions are fine.)*
- Deleting a person or resetting their password ends all their sessions immediately.

### Exit → Sign out

- On the remote listener, Exit ends that browser's session and returns to the sign-in screen. The button can be relabelled "Sign out" there.
- On the local listener there's no session, so Exit just leaves the page (closes the tab or shows a "you can close this tab" message). It never touches the server.

### Activity log

- Stored in `access.db`. Each entry has a timestamp, the person (or "owner (PC)"), the listener (local/remote), the event, and short details.
- Logged events:
  - sign-in succeeded, sign-in failed (with the attempted username), locked out, signed out, session timed out;
  - password changed (by the person), password reset (by the owner), person added, person deleted;
  - **views opened**: the app's tabs and views, sent by the page as it navigates. This is not every background API call;
  - **actions**: `POST /api/account`, `/api/account-prefs`, `/api/passthrough-decision`, `/api/run-now`, `/api/run-cancel`, with enough detail to know what changed (e.g. which account). New values that are amounts don't need logging.
- Never logged: passwords, session tokens, or cookie values.
- Source address: if Funnel forwards the client IP (e.g. `X-Forwarded-For`), record it. Otherwise skip it. *(Builder to confirm.)*
- Retention: keep everything. The volume is tiny.
- *(My call)* The log is for the owner's awareness, not tamper-proof evidence. Anyone with file access on the PC could edit `access.db`. No export for now.

### Owner-only screens (local listener only)

- **People:** list everyone with their last sign-in. Add a person (name, username, temporary password). Delete a person. Reset a password (sets a temporary one). Temporary passwords force a change at the next sign-in. The owner passes them along however they like; the app doesn't email anyone.
- **Activity:** newest-first list, filterable by person and date range.
- These are new tabs or pages in the existing frontend. The remote listener returns 404 for both their HTML and their APIs.

### Remote-user screens

- **Sign in:** username, password, and a clear error that doesn't reveal whether the username exists.
- **Change password:** current password, new password and confirmation. Also shown automatically when "must change password" is set.
- Everything else is the existing app, unchanged.

### One-time Tailscale setup (the owner does this; documented in the plan)

1. In the Tailscale admin console, enable HTTPS certificates and allow Funnel for this PC.
2. On the PC: `tailscale funnel --bg 5058`. This persists across reboots.
3. Note the resulting `https://<pc>.<tailnet>.ts.net/` link. That's the link to give people.

## Open decisions — answered 2026-10-27

- **Guest sign-in:** password only, no second step (the owner's choice, on the designer's recommendation). Two-factor stays a non-goal; revisit if the advisor's access ever needs it.
- **Server start:** at Windows logon. After an unattended reboot the link is down until the owner logs in to the PC. No Windows password is stored for the task.

## Constraints

- The stdlib HTTP runtime and Flask-compatible facade in `src/http_runtime` are used as-is. No new web framework and no third-party auth or crypto packages.
- `tests/test_trends_reporter_server_functional.py` and `tests/test_trends_app_sync_unit.py` stay green. Their Exit/watchdog assertions change deliberately.
- Prefer keeping changes in `financial_trends_reporter/` and its tests. Small hooks in `src/http_runtime` (e.g. tagging which listener a request arrived on) are allowed if a wrapper would be clumsy *(my call)*. Any change under `src/` means running `python tools/generate_system_diagram.py` and committing the diagram, and the main app's own tests must stay green.

## Left to the builder

- How the request knows which listener it came from.
- Session storage (in memory or `access.db`) and the exact idle-activity mechanism, within the rules above.
- The `access.db` schema and migrations.
- Task Scheduler vs. service, and the stop script.
- Layout of the sign-in, change-password, People and Activity screens, matching the existing app's style.
- The exact Host and forwarded headers Funnel sends, confirmed on the real setup.

## Phases (for the implementation plan)

Check `/usage` against these estimates as the plan runs.

| # | Phase | Model / effort | Usage vs. a 5-hour Pro session | What drives it |
|---|---|---|---|---|
| 1 | Always-on server: remove the watchdog, Exit no longer stops the server, loopback launchers, logon task | Sonnet / medium | Light | `main.py` (~440 lines) plus the launchers; a few test edits |
| 2 | Accounts, hashing, sessions, the second listener, sign-in and change-password screens, idle timeout | Opus / high | **Moderate–heavy** | Security-critical; touches `src/http_runtime/server.py` usage, `main.py`, `frontend/index.html`; several test loops |
| 3 | Activity log (server events plus view-change reporting from the page) | Sonnet / medium | Light–moderate | Hooks in every POST route and in the page's navigation |
| 4 | Owner-only People and Activity screens | Sonnet / medium | Moderate | New frontend UI in `index.html` |
| 5 | Tailscale Funnel setup (owner) and end-to-end check from a phone off Wi-Fi | Sonnet / low | Light | Mostly manual; a short verification |

**Likely expensive:** `financial_trends_reporter/frontend/index.html` is large (~900 lines). Grep for the Exit, ping and tab code and read only those regions; never read the whole file. In phase 2, keep the test loop scoped to `pytest tests/test_trends_reporter_server_functional.py`, plus new auth tests, until the end.
