# Security Review — Retirement Planning System and Financial Insights

**Date:** 2026-11-23 (revision 2)
**Audience:** External auditors; internal product owners
**Basis:** repository commit `89c51a6` / `58ad4e0` (shallow clone, 230 commits visible)
**Owner decisions applied (revision 2):** server mode runs on a **dedicated machine**; Financial Insights **guests must be view-only** (they must not change settings).
**Method:** static source review by six reviewers across two rounds (gateway; local server and admin app; Financial Insights, Monarch Extractor and supply chain; then a full read of `plan_routes.py`, a full read of the remaining unreviewed modules, and a dynamic confirmation pass). Dynamic proof-of-concept scripts ran in-process against the Flask apps with temporary data; they changed no repository files and touched no real plan data. Findings re-read by the lead reviewer: F-01, F-02, F-04, F-15, SEC-01.
**Status vocabulary:** **CONFIRMED** = reproduced by running code; **V** = verified by reading code; **C** = depends on Windows, Tailscale or installed-service behaviour that cannot be observed in the review environment, with owner steps in section 9.
**Still not performed:** penetration testing; dependency CVE scanning; Windows runtime checks (section 9); the large business-logic services `rental`, `spending`, `strategy_asset`, `plan_tier`, `plan_forms` (targeted I/O, subprocess and network greps only, nothing found); the pricing/portfolio subprocess helpers in depth; the pure-arithmetic parts of `live_snapshot.py`; the 1099-B PDF parser library; xlsx formula-injection tracing in the workbook builder.

Pre-review integrity check (OneDrive truncation): all Python files compile, all tracked JavaScript parses, no tracked HTML lacks a closing tag. No truncated files were found.

---

## 1. Executive summary

The system is a local-first retirement planner with three optional network surfaces: a single-user loopback server, a multi-user **gateway** (per-user worker accounts, password + TOTP, reverse proxy, encrypted backups, per-grantee shares), and **Financial Insights** (FI), a net-worth/cash-flow reporter fed by a Monarch extractor and exposed to guests through the gateway or a standalone Tailscale Funnel listener.

**Overall posture: good for a self-hosted, single-household tool; not yet audit-ready for multi-party use.** The authentication, session, CSRF, proxy-header and backup-crypto designs are consistently defensive and mostly test-covered. There is no LLM or AI API traffic, no use of `shell=True`, `eval`, `pickle` or unsafe YAML in server paths, no secrets in tracked files, and no real data found in committed history.

| Severity | Count | Headline items |
|---|---|---|
| Critical | 0 | none |
| High | 2 | **F-01** guest sessions can write to the owner's Financial Insights store (CONFIRMED); **X-1** the Admin app and the local Financial Insights listener have no sign-in and are reachable from worker accounts on the server host (C, owner to verify) |
| Medium | 21 | Open redirect (CONFIRMED); lockout DoS and an unthrottled change-password endpoint (CONFIRMED); future-dated balance poisoning (CONFIRMED); client-controlled session idle time (CONFIRMED); missing security headers; hostile-plan triggers run in the app (CONFIRMED); gateway/LocalSystem trust files; predictable SYSTEM script path; unpinned CI and dependencies; unprotected data at rest |
| Low | 41 | See section 3.6 |
| Info | 7 | See section 3.6 |

Counts are by consolidated register row (section 3.6), which is authoritative for severity and status; duplicate reports of one issue are merged. The per-area tables in 3.1 to 3.3 keep the **original** round-1 ratings for traceability.

**Effect of the owner decisions.** The dedicated-machine decision removes most of the exposure of the unauthenticated loopback server (S-01, now Low) because no other human uses the host, **but it does not remove the risk from worker accounts**, which are untrusted members on the same host and can reach loopback ports (X-1). The view-only decision makes F-01 a defect against intended behaviour, not a design choice.

**Top actions** (in order): (1) make every Financial Insights write route owner-only (F-01) and stop running the Admin app and the 5057 listener on the multi-user host or give them a credential (X-1); (2) bound balance dates, absolute session lifetime and server-side idle tracking (F-02, F-04); (3) fix the `?next=` redirect, throttle change-password and make lockout per-source (SEC-01, SEC-05, SEC-10); (4) security headers on the planner, FI listeners and gateway proxy (SEC-07/F-10); (5) pin CI actions, hash-lock dependencies, add audit steps (F-15, F-16); (6) run the Windows owner checks in section 9 before the Funnel listener goes live.

---

## 1a. Relationship to prior reviews

This review complements `documentation/future/multi-user-server-security-review.md` (Phase 7, 2026-11-16, **CONDITIONAL GO**, six conditions met on the owner's machine; the service and Funnel listener had not yet been installed). That review concentrated on Windows account isolation, ACLs, pre-authentication exhaustion and TOTP sealing, and ran elevated tests. This review did **not** re-run those tests. It adds the surfaces that review did not cover: Financial Insights authorisation and data integrity, the local single-user server and Admin app, frontend injection sinks, supply chain and SDLC. Overlap exists on SEC-02/03/08/09 and X-1/X-2 (Windows file handling, key storage, loopback reachability from worker accounts), where the earlier review's open items should be reconciled against these findings before the Funnel listener goes live. Earlier system reviews are archived in `documentation/archive/reports/`.

---

## 2. System and trust boundaries

| Component | Exposure | Trust model |
|---|---|---|
| Desktop mode (`main.py`) | No socket; in-process JS bridge | OS user |
| Server mode (`src/server`, port 5050) | Loopback by default; non-loopback only if a static token is set | Host/Origin/CSRF gates; **no user authentication on loopback** |
| Admin app (port 5056) | Loopback | Loopback + same-origin + JSON content-type gates + per-boot local token (X-1 fix, 6a); no password sign-in |
| Gateway (`src/gateway`) | Loopback behind Tailscale Funnel | Password + TOTP, `__Host-` cookie sessions, CSRF token, admin/member/viewer roles |
| Workers | One Windows account per user, loopback port, per-worker token | Gateway proxy strips identity/credential headers |
| Financial Insights | Loopback owner listener (5057); guest listener (5058) or via gateway | Session + tab grants + percent/dollar view; owner listener unauthenticated by design |
| Monarch extractor | Scheduled task, persistent Chromium profile | Same OS user |

Data leaving the machine: ticker symbols (holdings disclosure) and provider keys to Yahoo, Stooq, Nasdaq, FMP, Alpha Vantage; authenticated calls to `api.monarch.com` only (redirects refused, URL prefix pinned). Nothing else was found.

---

## 3. Findings

Status: **V** verified in code; **C** needs confirmation (runtime, Windows or deployment). Reference IDs are the reviewers' original IDs (S = local server, SEC = gateway, F = Financial Insights/supply chain).

### 3.1 High

**F-01 · Guest sessions can modify the owner's FI store and trigger jobs — V**
`financial_trends_reporter/access_routes.py:38-43` classifies `/api/run-now`, `/api/run-cancel`, `/api/account` and (as a trends route) `/api/passthrough-decision` and `/api/account-prefs`. The gate checks session, tab grant and money view only. The handlers (`main.py:205-218`, `:381-408`, `:443`) perform no owner check. A guest with any FI access, including percent-only, can change account type, app-account mapping, chart inclusion and passthrough decisions in the owner's single balances database, silently altering net worth, flows and liquid figures shown to the owner and every other guest. The activity log records only a count. They can also repeatedly start the price-refresh subprocess.
**Revision 2: CONFIRMED.** A percent-only guest and a dollar guest each got HTTP 200 on `/api/account`, `/api/account-prefs`, `/api/passthrough-decision` and `/api/run-cancel`. The balances DB changed (account type `Loan`, `app_account` `HACKED`, net-worth preference disabled), `/api/run-now` returned success, and an unauthenticated request got 401. Cause: `_gate` in `access_routes.py` never checks `money_view` or a read-only flag for POSTs, and `/api/account` sits in `TAB_FREE_ROUTES`, so even a tab-limited grant does not block it. In **worker mode** the same calls succeed but the actor is the plan owner editing their own store (gateway viewers are refused by `tests/test_gateway_viewer_gate_contract.py`), so it is not an escalation there; the exposure is the standalone remote listener. Owner decision: guests are view-only, so every POST except sign-in, sign-out, change-password, TOTP and ping must be refused for guest sessions.
*Fix:* make write routes owner-only for remote sessions (or a distinct grant); add a contract test that fails when a POST route is neither owner-only nor deliberately guest-writable (the existing guard covers percent leakage only). *Note:* worker mode uses per-plan stores, which limits blast radius.

### 3.2 Medium

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| S-01 (V) | Loopback server and Admin app have no authentication; any local process or other OS user on a shared host can read or overwrite plans and call shutdown. Requests with no Origin skip CSRF. | `security_audit.py:83-88`; `app_core.py:1140-1170`; `admin_app/trust.py:3-4` | Per-launch random token on loopback, or a Unix socket/named pipe; document server mode as unsafe on multi-user hosts. Desktop mode unaffected. |
| S-02 (C) | No CSP or security headers on the planner server; ~70 `innerHTML` assignments with a privileged desktop bridge (`js_api`). One missed `esc()` on CSV- or `.rpx`-derived text becomes script with API access. Spot checks found no unescaped fields. | `src/server/*`, `frontend/js`; `desktop_app.py:38-40` | CSP + `nosniff` on all responses and a meta tag in `index.html`; lint rule banning unescaped interpolation in `innerHTML`. |
| S-03 (C) | Untrusted `.rpx` (SQLite) opened without `trusted_schema=OFF`, `cell_size_check`, or defensive mode; opening may upgrade in place. Triggers/views in a crafted plan could execute. | `plan_file_service.py:230-235`; `plan_db_replace.py:72,86-96` | Harden pragmas; reject unknown triggers/views; validate read-only first. |
| SEC-01 (V) | Open redirect after sign-in: `nextPath()` accepts `/%09/evil.example`, which the browser normalises to `//evil.example`. Server-side `safe_next` is stricter but not used by this path. | `pages/gateway.js:77-85`; `app.py:126-134` | Apply `safe_next` rules client-side; resolve with `new URL()` and require same origin. |
| SEC-02 (C, code fixed in wave 3) | Check-then-use windows on worker-writable trees in backup/log jobs run as LocalSystem (junction swap between `has_reparse_point` and open). | `backup_store.py:66-77,115-127,213-231,394-406`; `logs.py:30-45`; `fsguard.py:213-239` | Open with no-follow/`FILE_FLAG_OPEN_REPARSE_POINT` and verify final path; run while worker stopped. |
| SEC-04 (V) | Pre-enrolment takeover: anyone with the admin-issued temporary password can enrol their own authenticator within the 72-hour window. | `store.py:51,719-732`; `app.py:531-546` | One-time out-of-band enrolment code; shorter window; admin notification. |
| SEC-05 (V) | Lockout DoS: five failures lock a username for 15 minutes regardless of source, including the only admin; the Funnel listener is internet-reachable. | `store.py:634-649`; `access_core.py:18-19` | Per-user+per-IP counting, exponential delay, exempt valid sessions. |
| SEC-07 / F-10 (V) | Proxied planner/`/insights/` responses and the standalone FI listeners lack CSP, frame-ancestors, Referrer-Policy and (FI) `no-store`. Worker XSS would share an origin with gateway admin APIs; the FI runbook's "back button shows no data" test depends on `no-store`. | `app.py:374-385`; `proxy.py:196-209`; FI `index.html:401` (inline module script) | `setdefault` headers in the proxy; `after_request` on FI listeners; nonce/hash for the inline script. |
| SEC-08 (V, code fixed in wave 3) | Backup key is a plain base64 file (`0o600` has no effect on Windows), not DPAPI-wrapped, same host as archives; no rotation (`key_id` is fixed). | `backup_crypto.py:43-59`; `ops.py:147-161` | DPAPI/passphrase-wrap; ACL check on start; multi-key support. |
| F-02 (V) | A future-dated balance row passes the staleness guard and, via `active = (last_seen = MAX(date))`, deactivates all other accounts; net worth and the percent basis collapse. | `balance_store.py:197,235-236,97-105` | Reject dates > today+1; add jump/magnitude checks; keep last good import. |
| F-03 (V, fixed in wave 3) | No integrity protection on balances DB, log or CSV; the log silently drops bad lines; heuristic rename merging deletes history irreversibly; money stored as REAL. | `trends_log.py:39-57`; `balance_store.py:111-150` | Hash-chain/HMAC the log; snapshot before destructive imports; confirm renames; integer cents. |
| F-04 (V) | Idle timeout trusts client-supplied `idle_ms`; no absolute lifetime; sessions are memory-only. A stolen cookie stays alive with `{"idle_ms":0}` pings. | `sessions.py:51-55`; `access_routes.py:361-371` | Absolute lifetime (e.g. 12 h); server-side activity tracking; cap client influence. |
| F-05 (V) | Remote 500 responses expose exception text and filesystem paths to dollar-view guests. | `access_routes.py:174-178`; `main.py:424` | Opaque error id (as `gateway/app.py:393`). |
| F-08 (V/C) | Percent view divides every figure by one constant `k` (today's net worth). One known dollar anchor (mortgage, salary) recovers all balances. Account names may embed employer/person names. | `percent_view.py:81-91` | Document as obfuscation, not a privacy boundary; jitter/rotate `k`; pseudonymise names. |
| F-11 (V, fixed in wave 3) | Financial data at rest is plaintext with no explicit permissions: trend log, balances DB, `balances.csv`, raw CSVs; Monarch failure dumps (full-page screenshots/HTML of authenticated pages) are never cleaned. OneDrive may replicate. | `monarch_extract.py:1230-1246`; FI package (no ACL calls) | Require disk encryption; startup ACL and OneDrive-path check; retention policy; debug dumps off/redacted by default. |
| F-12 (V, warning added in wave 3) | Persistent Chromium profile holds Monarch session credentials; same-user malware or a copied profile yields full account access. | `monarch_extract.py:32,1192`; `monarch_balances.py:30,142` | Keep outside OneDrive/repo; restrict ACL; dedicated login with MFA. |
| F-15 (V) | CI actions pinned by tag, not SHA; `ci.yml` has no `permissions` block; third-party `codecov-action` in nightly. No `pull_request_target`, no secrets use. | `ci.yml:40-362`; `nightly.yml` | Pin to SHAs + Dependabot; `permissions: contents: read`; `persist-credentials: false`. |
| F-16 (V) | Python dependencies are ranges with no lockfile/hashes; no pip-audit or npm-audit in CI; frozen release is UPX-packed and unsigned. (npm lockfile has integrity hashes.) | `requirements*.txt`; `retirement_planner.spec:144-159` | Hashed lock; audit steps; sign binaries; drop UPX. |
| F-17 (V) | `.claude/settings.json` auto-allows `git push*`/`commit*`/`add*` and `Agent`; SessionStart runs repo-supplied PowerShell with `-ExecutionPolicy Bypass`; the push hook is bypassable via `SKIP_FAST_GATES=1`. | `.claude/settings.json`; `tools/sync_main.ps1` | `ask` for push; deny force-push; CODEOWNERS on `.claude/` and `tools/*.ps1`. |

### 3.3 Low and Info

| ID | Sev | Finding | Fix |
|---|---|---|---|
| S-04 | Low | Save As / Load File accept arbitrary absolute paths in local mode (`plan_file_service.py:121-153`) | Require `.rpx`; refuse overwriting non-plan files |
| S-05 | Low | Provider API keys in URL query strings; HTTP Stooq fallback (`market_data.py:68-73,839`) | Headers where supported; drop HTTP fallback |
| S-06 | Low | `server_api_token` plaintext in app.db (`runtime_config.py:160`) | Keyring/DPAPI or hash |
| S-07 | Low | Non-loopback mode is plain HTTP with a static token, no lockout (`host_guard.py:61-70`) | Require TLS/reverse proxy; startup warning |
| S-08 | Low | Desktop auto-opens downloads with the OS handler; suffix from server (`desktop_api.py:136-240`) | Suffix allowlist |
| S-09 | Low | No CSV/xlsx formula-injection neutralisation (`csv_exchange/core.py:495-513`) | Prefix `'` on cells starting `= + - @` |
| S-10 | Low | Zip import trusts header sizes, unbounded entry count (`plan_set.py:98-102`) | Cap entries; stream with limit |
| SEC-03 | Low-Med (C) | `icacls /reset /T` after link removal is racy (`acl.py:171-181`) | Run with workers stopped; apply ACLs by handle |
| SEC-06 (cost raised, list added in wave 3) | Low | scrypt N=2^15, min length 12, no breach check, no rehash on login (`access_core.py:20-30`; `store.py:41-42`) | Raise N; rehash; common-password list |
| SEC-09 | Low | TOTP secret falls back to plaintext off Windows; DPAPI without entropy (`secret_box.py:82-113`) | Refuse production start without DPAPI |
| SEC-10 | Low | Change-password endpoint skips `_throttled` (`app.py:578-592`) | Throttle; require fresh TOTP |
| SEC-12 / F-06 | Low (C) | Client IP from `X-Forwarded-For`; gateway uses right-most (confirm Funnel appends), FI uses first (spoofable) (`app.py:160-167`; `access_routes.py:81,238`) | Right-most trusted hop |
| SEC-13 | Low | Resource exhaustion by an authenticated member: 64 MiB bodies, 256 MiB responses, no global budget (`proxy.py:50-57`; `build_queue.py:118-130`) | Global in-flight byte budget |
| F-07 | Low | Username enumeration via lockout message in FI (`access_routes.py:218-220`) | Uniform response |
| F-09 | Low | FI share snapshot free text is not HTML-escaped; safety depends on consumers using `esc()` | Extend escaping test |
| F-13 | Low | Scheduled tasks use `-ExecutionPolicy Bypass` and PATH-resolved Python (`register_monarch_extract_task.ps1:107-123`) | Absolute interpreter; `-RunLevel Limited` |
| F-14 | Low (C) | Funnel check at FI startup only (`listeners.py`, `main.py:526`) | Periodic re-check |
| F-18 | Low | Personal identifiers committed (`.claude/launch.json:28`, fixture `ytd_account_setup.csv`, `tools/backup_to_onedrive.py`) | Replace with fictional values |
| F-19 | Low | No root LICENSE; third-party notices cover only segno | Add LICENSE and generated notices |
| F-20 | Low (C) | Committed binaries spot-checked only (`reference.db`, `demo_seed.rpx`) | Full table scan |
| SEC-11, S-11–13, SEC-14–15 | Info | Non-dict JSON → 500 + traceback log; Admin app auth model; launcher PATH hijack and UPX; lxml/openpyxl only on self-generated files; HSTS minimal; cross-site GET navigation refused | See reviewer notes |

---

### 3.4 Round-2 findings (full read of `plan_routes.py` and the remaining modules)

`plan_routes.py` was read in full. All 206 routes are classified in `remote_allowlist.py` (193 allowed, 13 refused, none unclassified), and every route that takes a server path is refused in remote mode. No arbitrary file read, write or delete is reachable in remote mode.

**High**

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| X-1 (C) | The Admin app (5056) and the Financial Insights local listener (5057) authenticate only by "peer is loopback". A worker is an untrusted member, and any code running in a worker account satisfies that test. From there: create an admin in `identity.db`, reset TOTP, disable accounts, write install-wide settings and the provider key, start/stop the planner and FI processes (5056); read the owner's full net-worth history and trigger runs (5057). The runbook lists per-account firewall rules only as "optional later", and Windows Firewall does not filter loopback anyway. | `admin_app/trust.py:42-63`; `admin_app/main.py:119-125`; `financial_trends_reporter/listeners.py:1-8`; `main.py:84-99` | Do not run the Admin app or the 5057 listener on the multi-user host; otherwise add a per-boot token in a file ACL'd to the operator, or a named pipe with an ACL. Owner check: section 9.1. |

**Medium**

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| X-2 (C) | The gateway service runs as LocalSystem and loads `gateway.json` and `log_file` without checking their DACLs, the `--python`/`--install-dir` they name, or `sys.executable`. `acl check` does not test `gateway.json` or the log folder, and `check_readonly` reads only the install folder's own DACL, not its children. A writable `.py`/`.pyd` under the install, or a writable config, is SYSTEM code execution. Protected today only because `acl setup` locks the state folder. | `service.py:77-137`; `acl.py:243-255,340-343`; `supervisor.py:35` | Refuse config/log paths writable by anyone but SYSTEM/Administrators; make `acl check` walk the install tree and cover config and logs; restrict service privileges. Owner check: section 9.4. |
| X-3 (C) | `tools/run_elevated_tests_as_system.ps1` writes a script to the predictable `C:\Windows\Temp\rpw_system_run.cmd` and registers it as SYSTEM. Any local account can pre-create the name and keep write access, then swap content before it runs. | lines 11-16 | Admin-only directory, `CreateNew`, absolute interpreter path. Owner check: section 9.5. |
| PR-08 (V) | The price symbol tester (`/api/prices/test-symbol*`, allowed in remote mode) has no symbol validation or concurrency cap, spawns an unbounded thread per start, and returns `traceback.format_exc()[-4000:]` even in remote mode. `quote(symbol)` keeps `/`, so `A/../../v4/profile/AAPL` reaches other paths on the fixed provider host and spends the shared key's quota (not SSRF; the key is redacted). | `plan_routes.py:230-254`; `pricing_service.py:90-164`; `market_data.py:1160,1213` | Validate `^[A-Z0-9.^=\-]{1,15}$`; `quote(..., safe="")`; cap concurrent jobs; drop `traceback_tail` in remote mode. |

**Low**

| ID | Finding | Fix |
|---|---|---|
| PR-01 | `save-as`, `load-file`, `exit-snapshot` have no `_require(...)` and skip the server-path allowlist; `save_as` can overwrite any writable file (CONFIRMED, S-04). | `_require("write_config")`; pass `_server_path_allowed`; require `.rpx`; refuse overwriting non-plan files |
| PR-02 | `backup_dir`, Monarch `source_dir` and `field_map_path` accept arbitrary absolute paths in server mode; `prune_backups` unlinks "orphaned" files in the backup folder (deletion scope not confirmed, C). | Allowlist on save and at run time; match backup file-name pattern |
| PR-03 | `_server_path_allowed` honours only the first allowlist root (the `try` wraps the loop); fails closed. A symlink inside an allowed folder can escape (C). | `try/except` inside the loop; re-check the resolved file |
| PR-04 | `GET /api/ytd/status` mutates the plan: it merges account setup from sibling `*/input/ytd_account_setup.csv` folders. GET is exempt from the CSRF gate. Remote mode skips the scan. | Make `status` read-only; recovery via explicit POST |
| PR-05 / SEC-11 | A non-object JSON body gives HTTP 500 on about 25 routes (CONFIRMED on 11) and on the pre-authentication gateway login, where the 500 occurs before the throttle, so these requests are not counted. Each hit logs a traceback. | One `_json_obj()` helper returning 400; use the gateway's `_body()` everywhere |
| PR-06 | `isdigit()` accepts characters `int()` rejects (`year=²` gives 500) at seven sites. | `type=int` or `isascii()` |
| PR-07 (fixed in wave 3) | The "CSV writes disabled" switch is not applied to the sales, transactions, cash, reconcile, YTD, spending, seed and plan-registry write routes. | Shared decorator |
| PR-09 | Exception text returned with HTTP 200 or 500 (`str(exc)`, `ClassName: msg`, `traceback_tail`, `stdout_tail` unredacted); `remote_mode.scrub` removes only known roots. | Generic message plus `error_id` in remote mode; proper status codes; `redact_text` on build output |
| PR-10 / S-09 | No formula-injection neutralisation in any CSV export (CONFIRMED: `=cmd|' /C calc'!A0` exported verbatim; also `/api/investment-income.csv`). xlsx path not traced. | Prefix `'` on cells starting `= + - @ tab CR` |
| PR-11 | No per-route size caps below 64 MiB (plan upload, 1099-B `pdf_base64`, broker content); `mode:"restore"` skips plan-quota check; PDF parser unreviewed (C). | Per-route caps; read-only validation open |
| PR-12 | `/api/secrets` accepts any secret name (write-only, refused in remote mode). | Allowlist provider key names |
| PR-13 | NaN/Infinity accepted by `float()` at `plan_routes.py:1287-1290,1432-1437` (C). | `math.isfinite` |
| PR-14 | `/api/plan/backups/run` allowed in remote mode with free-form `trigger`; likely bypasses plan quota (C). | Minimum interval; length limit |
| X-4 | **CONFIRMED** `funnel_guard` fails open: a non-zero `tailscale` exit with empty stdout parses as `{}` and returns `ok=True`. | Treat non-zero exit as unreadable |
| X-5 | `funnel_guard` ignores the `Services` section, denies only ports 5057/5058 (`funnel_command` will publish 5050 or 5056), and parses URLs by regex. | Deny all internal ports; parse `Services`; `urlsplit` |
| X-7 | `/api/plan` Monte Carlo runs outside the build queue; a member can starve CPU (C). | Route through the queue |
| X-8 (timing and key race fixed in wave 3) | Identity store: locked accounts return `locked` before password work (oracle and lockout DoS); `default_key` get-then-set race can mint two TOTP keys (C). | Uniform response; atomic key creation |
| X-9 | Build `stdout_tail` never redacted; many `str(exc)` returns. | See PR-09 |
| X-10 | `safe_next_path` passes `/\evil.com` (no caller today, C). | Reject `\`, `%5c`; `urlsplit` |
| X-11 | `/api/prefs` has no size cap or `_require`; `.before_blank_*` backups never pruned. | Cap; prune |
| X-12 | `tools/upgrade_installed_server.ps1` runs unpinned `pip install` as Administrator. | `--require-hashes` |
| X-13 | `tools/backup_to_onedrive.py` zips `identity.db`, `app.db`, plan files and Monarch CSVs unencrypted to OneDrive; `tools/manage_secret.py` crashes with `NameError: _run` (CONFIRMED). | Exclude/encrypt; fix tool |

Info: X-14 (settings unconfined but routes refused in remote mode: keep both guards), X-15 (scheduler runs users serially, bounded).

### 3.5 Dynamic confirmation results

| Item | Result | Detail |
|---|---|---|
| F-01 | **CONFIRMED** | See section 3.1. Worker mode reproduces but is not an escalation. |
| F-02 | **CONFIRMED, worse than reported** | A `2099-01-01` row deactivated the other two accounts (net worth 131,000 to 1,001). A later legitimate import does **not** recover; the poison persists until the 2099 rows are deleted. |
| F-04 | **CONFIRMED** | One `idle_ms=0` ping per minute kept a session alive for 33.3 simulated hours; the control expired at 601 s. |
| F-05 | **CONFIRMED** (class name and message) | `AttributeError: 'int' object has no attribute 'strip'` returned to a dollar guest; `/api/account-prefs` leaks even to percent guests (it is in `PASS_THROUGH_FOR_PERCENT`). A filesystem-path leak to a dollar guest was not demonstrated directly. |
| SEC-01 | **CONFIRMED** | `?next=/%09/evil.example` gives `https://evil.example/`; `%0a`, `%0d` likewise. Server-side `safe_next` rejects all of these, so only `gateway.js` is affected. |
| SEC-11 | **CONFIRMED** | List/string/number bodies on `/api/auth/login` return 500 before throttling. |
| S-03 | **CONFIRMED, SQL-only impact** | `validate_plan_file`/`check_plan_file` accept foreign triggers, views and side tables. A trigger fired during the in-place v14 migration and on the first app write; a `RAISE(ABORT)` trigger blocked the app's writes. No code execution (`load_extension` disabled, no file I/O functions): impact is silent data tampering and denial of service. `validate_plan_file` upgraded the path passed to it; whether the real import path always uses a temp copy was not verified. |
| S-09 | **CONFIRMED (CSV)** | Raw `=cmd|...` cell in exported CSV. xlsx not traced. |
| S-10 | **PARTIAL; correction** | A 189 KB zip with 190 MB of zeros used 400 MB peak RSS; 150,000 tiny entries added about 115 MB; no entry-count cap. **Forged header sizes are not exploitable**: `zipfile` raises `Bad CRC-32`. The round-1 wording implying header trust is corrected. |
| S-04 | **CONFIRMED (local mode)** | `save-as` overwrote an existing non-plan file with SQLite content; arbitrary extensions accepted. |
| SEC-05 | **CONFIRMED** | 15 bad passwords from 15 IPs locked the user for 900 s; the correct password from the user's own IP then returned 429. |
| SEC-10 | **CONFIRMED, worse than reported** | 30 wrong `current` values on change-password gave no 429, and the endpoint still accepted the correct password while the account was locked: a stolen session can brute-force the current password without limit. |
| SEC-06 | **CONFIRMED** | A user stored with `scrypt_n=16` verified under `2**14` and was never rehashed. |
| S-02 | **NOT REPRODUCED** | 129 `innerHTML`/`insertAdjacentHTML` sites scanned across `frontend/js`, FI frontend, gateway pages and admin frontend; all CSV/user-derived interpolations checked were escaped. Heuristic, not proof; rated Low (hardening). `admin_app/frontend/processes.js:15` interpolates a server-defined name unescaped. |

### 3.6 Consolidated register (authoritative severity and status)

**High (2):** F-01 (CONFIRMED); X-1 (C).

**Medium (21):** S-03 (CONFIRMED); SEC-01 (CONFIRMED); SEC-02 (C); SEC-04 (V); SEC-05 (CONFIRMED); SEC-07/F-10 (V); SEC-08 (V); SEC-10 (CONFIRMED, raised from Low); F-02 (CONFIRMED); F-03 (V); F-04 (CONFIRMED); F-05 (CONFIRMED); F-08 (V); F-11 (V); F-12 (V); F-15 (V); F-16 (V); F-17 (V); X-2 (C); X-3 (C); PR-08 (V).

**Low (41):** S-01 (downgraded: dedicated host; residual risk is X-1); S-02 (downgraded: not reproduced); S-04 (CONFIRMED); S-05; S-06; S-07; S-08; S-09/PR-10 (CONFIRMED); S-10 (partial); SEC-03 (C); SEC-06 (CONFIRMED); SEC-09; SEC-11/PR-05 (CONFIRMED, raised from Info); SEC-12/F-06/F-14 (C); SEC-13; F-07; F-09; F-13; F-18; F-19; F-20 (C); PR-01; PR-02; PR-03; PR-04; PR-06; PR-07; PR-09; PR-11; PR-12; PR-13; PR-14; X-4 (CONFIRMED); X-5; X-7; X-8; X-9; X-10; X-11; X-12; X-13 (CONFIRMED).

**Info (7):** S-11; S-12; S-13; SEC-14; SEC-15; X-14; X-15.

Ratings reflect the owner decisions (dedicated host, view-only guests). Items marked C that the owner's checks in section 9 show to be exposed should be re-rated up one level.

---

## 4. Positive controls (evidence for auditors)

**Authentication and sessions.** scrypt with per-user salt and bounded concurrency; RFC 6238 TOTP with replay protection inside `BEGIN IMMEDIATE`; shared lockout budget; per-IP and per-user throttling; uniform responses and a dummy hash for unknown users; `__Host-` cookie, `Secure; HttpOnly; SameSite=Strict`; 256-bit tokens stored hashed; rotation on stage change; idle 15 min / absolute 12 h; revocation on password change, disable, role change, TOTP reset. (`store.py`, `app.py`, `totp.py`, `signin_throttle.py`)

**CSRF/CORS/Host.** Per-session CSRF token, Origin allowlist, `Sec-Fetch-Site` checks, content-type allowlist, no CORS headers, Host allowlist against DNS rebinding, request-size caps. (`app.py:277-301`; `app_core.py:1116-1177`; `host_guard.py`)

**Proxy and authorization.** Deny-by-default admin prefixes; viewer allowlist that never reaches workers; credential, cookie and forwarding headers stripped; worker `Set-Cookie`/CORS dropped; loopback-only upstream (no SSRF); path-traversal rejection; last-admin protection. (`proxy.py`, `upstream.py`, `viewer_routes.py`)

**Isolation.** One Windows account per user (deny interactive/RDP/network), per-user ACLs, Job Object memory caps, scrubbed environment, `python -E -s -B`.

**Shares.** No bearer links; 128-bit per-grantee ids; owner/grantee-scoped queries; SHA-256 binding of body to row; worker output revalidated (schema, percent-leak scan, Unicode normalisation); revocation deletes bodies; access log; viewer pages use `textContent` only.

**Backups.** AES-256-GCM, per-archive HKDF salt, chunk AAD binding header/index/final flag (reorder/truncate detected), read-back verification, allowlisted restore members, destination confinement.

**Local app.** Desktop mode opens no socket; remote mode deny-by-default allowlist and path confinement; keyring-only secrets with no plaintext fallback, write-only `/api/secrets`; log redaction and account-number masking; list-form subprocess calls; upload magic-byte and schema validation with atomic swap; Monarch connector refuses redirects and size-caps responses.

**Financial Insights.** Two-port trust boundary with startup Funnel guard; fail-closed percent scaling with merchant collapse and leak scan run twice; bound SQL parameters throughout; escaped frontend; importer guards (header, finite values, stale export, account-count drop) with rejection records; per-plan worker stores.

**Round-2 additions.** Worker token required on every worker route before routing (env only, constant-time, never in argv); deny-by-default allow-list matched after routing with every server-path route refused; worker binds `127.0.0.1` with `SO_EXCLUSIVEADDRUSE` and the supervisor checks port ownership before sending the token; Monarch connector uses PKCE S256, single-use state, a URL prefix pin, disabled redirects, an 8 MB response cap and per-account credential stores; plan download/delete check `_inside` and sanitise names; snapshot restore refuses a `db_copy` outside the workspace in remote mode; identity store uses scrypt with a dummy hash, TOTP and recovery-code compare-and-swap, and encrypt-then-MAC sealed secrets; Admin app has fixed page map, no `--host` option and refuses to start if Tailscale serves its port; `insights_schedule` selects members positively so viewers never get a worker.

**SDLC.** No `pull_request_target`; nightly workflow least-privilege; `npm ci` with integrity hashes; account-number check in CI; `.gitignore` covers databases, `*.rpx`, `input/`, FI data, Monarch profile and output; secret-pattern scan of tracked files and the visible history found nothing.

---

## 5. Test coverage

Security-relevant suites exist for access gating, TOTP, CSRF/Origin, Funnel guard, percent leakage, worker allowlist, share snapshot/store/publish, gateway auth/throttle/ACL/backup crypto/pre-auth limits, multi-user isolation, credential exclusion from backups and chart escaping.

**Gaps (no test found):** guest writes to the owner store (F-01); future-dated balances (F-02); client `idle_ms` extension (F-04); `X-Forwarded-For` spoofing; headers on FI listeners and proxied planner pages; unescaped data interpolation across frontends; `next=` redirect with control characters (SEC-01).

---

## 6. Remediation roadmap

| Wave | Items | Effort |
|---|---|---|
| 1 now | F-01 (owner-only writes plus a test that fails on any unclassified POST); X-1 (stop running 5056/5057 on the multi-user host, or add a credential); F-02 (date bound, plus a way to purge poisoned rows); F-04; F-05; SEC-01; SEC-10 and SEC-05; SEC-11/PR-05 | Small each |
| 2 next sprint | SEC-07/F-10 and S-02 headers/CSP; PR-08; F-15, F-16, F-17; X-2, X-3 (once section 9 confirms); X-4/X-5 `funnel_guard`; PR-01 to PR-04; S-03 pragmas and schema allowlist | Small to medium |
| 3 hardening | SEC-04 enrolment; SEC-08 key wrapping; SEC-02/03 handle-based I/O; F-03 integrity; F-11/F-12 at-rest controls; S-01 loopback token (defence in depth); PR-07 shared write gate | Medium to large |
| 4 hygiene | Remaining Low and Info items; F-18; F-19; document percent view as obfuscation | Small |

## 6a. Remediation status (waves 1 and 2, 2026-11-23)

| ID | Status | What changed | Residual / not done |
|---|---|---|---|
| F-01 | **Fixed** | Guest sessions are view-only: `OWNER_ONLY_POST` and `GUEST_WRITABLE_POST` sets in `access_routes.py`; any other write from a guest gets 403. Contract test fails on any unclassified POST route. Worker mode unchanged (plan owner edits their own store; viewers are refused by the gateway). | `/api/view` and `/api/exit` were classified guest-writable (they only log or end the session); confirm that is intended. |
| F-02 | **Fixed (prevention)** | Imports whose latest date is after today+1 are rejected and recorded; mirror path bounded. | No tool yet to purge rows from an earlier poisoned import; delete rows dated in the future from `monarch_balances.sqlite3` by hand. |
| F-04 | **Fixed** | 12-hour absolute session lifetime; client `idle_ms` clamped. | The server cannot tell a real touch from a false report, so idle time stays client-assisted; the absolute cap is the hard bound. |
| F-05 | **Fixed** | Remote guests get a generic message plus `error_id` on any 5xx; detail goes to the server log. | Local owner listener stays verbose by design. |
| SEC-01 | **Fixed** | `nextPath()` rejects control characters, backslashes and `//`, then requires same origin. JS test added. | None. |
| SEC-05 | **Fixed** | Failures lock the offending source address (5 failures, 15 min); an account-wide lock at 50 failures applies only to sources with no successful sign-in in 30 days. Schema 5 adds `login_sources`. Admin unlock clears all. | The per-username soft throttle delay (up to 300 s) is unchanged, so an attacker spraying a username can still slow that user briefly. Per-source counts do not decay. |
| SEC-10 | **Fixed** | Change-password is throttled, refused while locked, and counts failures. | None. |
| SEC-11 / PR-05 | **Fixed (gateway)** | Non-object bodies return 400, counted against the sign-in throttle on pre-auth routes. | The same pattern on about 25 planner routes (`plan_routes.py`) is still open. |
| SEC-06 | **Fixed** | Password hashes are upgraded on successful sign-in when stored cost is below the configured cost. | Cost itself not yet raised; N and a common-password list remain open. |
| X-1 | **Implemented, pending owner verification** | Owner decision: add a credential. Both the Admin app (5056) and the Financial Insights owner listener (5057) generate a per-boot `secrets.token_urlsafe(32)` at startup (`src/http_runtime/local_token_gate.py`) and write it to `local_state/admin_local_token` / `local_state/insights_local_token` (mode 0600; on Windows an explicit `icacls` grant to the current user only, inheritance removed). Every request needs either the HttpOnly, SameSite=Strict session cookie from the launcher's one-time handoff (token file -> `POST /_local/nonce` with `X-Local-Token` -> 60 s single-use nonce -> `/_local/open?n=` -> cookie -> redirect) or the token in `X-Local-Token`; otherwise 401. Compared with `hmac.compare_digest`; the token is never in a URL, log or argv. Existing Host/Origin/Sec-Fetch/proxy-header gates run first and are unchanged. The guest listener 5058 and the gateway are untouched. Tests: `tests/test_local_token_gate_functional.py`. | Same-user malware can read the token file (this stops other accounts, not the owner's own processes). The Windows file ACL (and the folder ACL of `local_state/`) is the protection, and an `icacls` failure only prints a warning. Cookies are shared across ports on 127.0.0.1 (names differ per app), so any page the owner opens from another local listener could see them. A rogue process that binds 5056/5057 before the real app would receive the launcher's token header; the existing port-in-use check does not detect that. Owner check: section 9.1 and the commands in the runbook. |
| SEC-07 / F-10 / S-02 | **Fixed (wave 2)** | `src/http_runtime/security_headers.py`: CSP (`default-src 'self'`, `frame-ancestors 'none'`, `base-uri 'none'`, `object-src 'none'`, `form-action 'self'`), nosniff, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. Gateway proxy adds them with `setdefault` semantics to every forwarded worker and `/insights/` response; the planner server adds them in an `after_request` (its `script-src` keeps `'unsafe-inline'` because `frontend/index.html` uses inline `onclick=` handlers; no external hosts are loaded); Financial Insights adds them on both listeners with `script-src 'self'` plus the SHA-256 of each inline script block (no `'unsafe-inline'` for scripts), and `Cache-Control: no-store` on the remote listener. The facade's 404 path now runs `after_request` hooks too. Test: `test_security_headers_functional.py`. | No CSP meta tag for the desktop `file://` page (no HTTP transport there; a meta CSP could break the in-process bridge, not verified here). Planner scripts still allow `'unsafe-inline'` until inline handlers are removed. Inline styles remain allowed. |
| F-06 / SEC-12 | **Fixed (wave 2)** | `access_core.forwarded_client_ip` (right-most `X-Forwarded-For` entry) is shared by the gateway `_client_ip` and the Financial Insights listener (activity log source and registered session source), replacing the first (client-written) entry. Test: `test_trends_client_ip_regression.py` (spoofed leading entry). | Owner check 9.3 already confirmed Funnel appends the real address on the gateway path; the 443 to 5058 path is not separately tested (run the 9.3 curl with a spoofed header against 443 and read the Activity log source). |
| X-4 / X-5 | **Fixed (wave 2)** | `funnel_guard.read_serve_status` treats a non-zero `tailscale` exit or empty output as unreadable (so `check_funnel` is not ok); the `Services` section is parsed; ports 5050 and 5056 are denied on every external port (5057 and the gateway local and worker ports already were; 5058 only on 443); targets are parsed with `urlsplit` and `ipaddress` (userinfo tricks and non-loopback hosts count as not local). Test: `test_funnel_guard_failclosed_regression.py`. | Windows `tailscale` output shapes were not observed here; run `python -m src.gateway.ops funnel check` on the host (section 9.3 step 1) and confirm it reads the live status. |
| PR-08 / X-6 | **Fixed (wave 2)** | Symbols must match `^[A-Z0-9.^=\-]{1,15}$` (400 otherwise); the verbose tester URLs use `quote(symbol, safe="")` so a `/` cannot walk the provider path; at most 3 background symbol tests run at once (429 beyond); `traceback_tail` is omitted in remote mode. Test: `test_price_symbol_tester_regression.py`. | The non-tester provider paths in `market_data.py` still use plain `quote()` (symbols there come from the plan's own holdings, not a request). The cap is per process (per worker). |
| PR-01 / PR-02 / PR-03 / S-04 | **Fixed (wave 2)** | `save-as`, `load-file` and `exit-snapshot` require `write_config`; user paths (save-as, load-file, backup `backup_dir`, Monarch `source_dir` and `field_map_path`) go through `_server_path_allowed` on save and, for the stored backup and Monarch settings, again on `backups/run` and `monarch-autoupdate/run` (403 outside the allowlist or, in remote mode, the workspace). `_server_path_allowed` now tries every configured root and checks the resolved path (symlinks followed). Save As requires `.rpx` and overwrites only an empty file or a read-only-verified plan file. Test: `test_plan_path_guards_regression.py`. | The allowlist applies only when the server is LAN-bound or in remote mode (as before); desktop mode on loopback still saves anywhere by design. The scheduled (non-route) backup and Monarch task runs read the stored folder without the check; they are the owner's own Windows task. `prune_backups` deletion scope was not changed. |
| PR-04 | **Fixed (wave 2)** | `GET /api/ytd/status` no longer calls `recover_account_setup`; it only reads. The frontend (`loadYtdStatus`) makes one explicit `POST /api/ytd/account-setup/recover {force:false}` per page load before the first read, which keeps the old automatic recovery for the owner and is refused or ignored in remote mode. Test: `test_ytd_status_read_only_regression.py`. | The POST is write-gated (`write_config`) and subject to the CSRF/Origin gate like every other write. |
| S-03 | **Fixed (wave 2)** | Every store open (`PlanStore.open` and the other stores, through `_SqliteStore._check_and_migrate`) now refuses a file that contains any trigger or view (the application schema has none; `SCHEMA_OBJECT_ALLOWLIST` is empty) before any migration or write can fire it. `db.connect` sets `trusted_schema=OFF`, `cell_size_check=ON` and, on Python 3.12+, SQLite defensive mode (helpers `harden` and `foreign_objects` in `src/sqlite_util.py`). `validate_plan_db` (upload and restore validation) opens the candidate read-only and rejects triggers and views before the integrity check. Test: `test_plan_file_hostile_schema_regression.py` (reproduces the firing trigger on a plain connection, then proves the guarded open refuses it, leaves the file byte-identical, and stops an old-version file before the upgrade runs). | Side tables and other foreign non-schema objects are not rejected (only triggers and views, the code-bearing ones). Defensive mode needs Python 3.12 or later; the pinned CI and release Python is 3.14, the minimum supported 3.11 gets the pragmas only. Windows file-locking behaviour of the read-only validation open was not observed here. |
| X-2 (hardening) | **Implemented (wave 2)** | `acl check` now walks the whole install tree (not just the folder's own list) for worker-writable entries, and takes `--config-file` (gateway.json and its folder) and `--log-dir` (folder and files) and reports any write access outside SYSTEM, Administrators and the gateway account; a walk cap or an unreadable entry is reported rather than skipped. Test: `test_gateway_acl_install_walk_unit.py` (Windows APIs faked). | Windows only: not run against a real DACL here. Owner check: `python -m src.gateway.acl check --data-root $Root --gateway-db $Root\gateway.db --install-dir $Install --config-file <gateway.json> --log-dir <log folder>` must print OK; expect a long walk of the install tree. The service itself still does not refuse to start when its config is writable (the check is operator-run). |
| F-15 / F-16 / F-17 | **Partly done (wave 2)** | `ci.yml` has top-level `permissions: contents: read`; every checkout has `persist-credentials: false` (both workflows); a report-only `dependency-audit` job runs `pip-audit` and `npm audit --omit=dev` with `continue-on-error`; `.github/dependabot.yml` covers actions, pip and npm weekly; `.github/CODEOWNERS` covers `.claude/`, `tools/*.ps1` and `.github/`; `.claude/settings.json` moves `git push*` from allow to ask and denies force pushes and remote branch deletion (`settings.local.json` untouched). | **Not done:** GitHub Actions are still pinned by tag, because this session could not resolve commit SHAs (access limited to this repository). Owner command per action: `gh api repos/<owner>/<action>/git/ref/tags/<tag> --jq .object.sha` (follow a tag object with `git/tags/<sha>` if the type is `tag`); actions to pin: `actions/checkout@v7`, `actions/setup-python@v6`, `actions/setup-node@v6`, `actions/upload-artifact@v7`, `actions/cache@v4`, `codecov/codecov-action@v7`. Dependabot will then keep SHA pins current. CODEOWNERS only enforces review when branch protection requires code-owner review. **No `requirements.lock` committed:** `pip-compile --generate-hashes` ran here (Linux, Python 3.13) and produced a Linux-only set (it pulled `jeepney` and `secretstorage` and none of the Windows packages), which would be wrong for the Windows release. Generate it on the Windows build host with Python 3.14: `pip install pip-tools; pip-compile --generate-hashes --strip-extras -o requirements.lock requirements.txt requirements-gateway.txt`, review, commit, then install with `pip install --require-hashes -r requirements.lock` (also closes X-12 for `tools/upgrade_installed_server.ps1`). UPX packing and unsigned binaries (F-16) are untouched. |
| PR-05 / PR-06 | **Fixed (wave 2)** | `plan_routes.py`: all 93 `request.get_json(silent=True) or {}` reads go through `_json_obj()`, which returns `{}` for an absent or empty body and raises a 400 for a list, string or number (a `BaseException` subclass, so the routes' own `except Exception` blocks cannot turn it into a 500); year parameters use `_ascii_digits` (`isascii() and isdigit()`). Test: `test_plan_routes_json_body_regression.py` posts non-object bodies to every route that reads a body (routes with path parameters excluded) and asserts no 5xx. | The gateway side was fixed in wave 1. Routes outside `plan_routes.py` (the other `src/server/*` files, Financial Insights, Admin app) were not re-audited for the same pattern. |
| X-8 / F-07 | **Fixed (wave 2)** | A locked account does the same scrypt work as any other refusal (no timing difference), and, by owner decision, the Financial Insights sign-in answers it exactly like a wrong password (401, same body, no `Retry-After`; was 429 "Too many attempts"); the gateway already did. The owner still sees "locked out" in the activity log. `totp.default_key` creates the sealing key under a lock and returns what was stored. Tests: `test_identity_lockout_timing_regression.py`, `test_lockout_is_indistinguishable_from_a_wrong_password` (replaces the old 429 assertion, changed on purpose). | A real locked-out person sees "incorrect password" for the lock period. An attacker can still lock a known username (per-source locking from wave 1 limits this). The key race is closed in-process only. |
| X-10 | **Fixed (wave 2)** | `safe_next_path` rejects control characters, backslashes and percent-encoded slash forms, on the raw and the decoded text. Test: `test_safe_next_path_regression.py`. | No caller today (as reported). |

Wave 2 not done: SEC-11 follow-ups outside `plan_routes.py` (Financial Insights, Admin app body handling were not re-audited); F-15 SHA pinning (needs network access to the action repositories); `requirements.lock` (needs the Windows build host); the desktop `file://` CSP meta tag; every Windows-specific item (section 11 lists owner commands).

Tests added in wave 1: `test_trends_guest_view_only_contract`, `test_trends_balance_future_date_regression`, `test_trends_session_lifetime_regression`, `test_gateway_json_body_regression`, `test_gateway_lockout_per_source_regression`, `tests/frontend/gateway_next_path.test.mjs`. Two existing tests were adjusted with justification: the account-lock assertion now uses the offending address (the cross-address case has its own test), and schema version pins moved from 4 to 5.

### 6b. Remediation status (wave 3)

Deferred from wave 3 and why: X-7 routes `/api/plan` through the build queue in `workbook_routes.py` and needs the Monte Carlo timing behaviour exercised, which was not done here.

| ID | Status | What changed | Residual / owner action |
|---|---|---|---|
| SEC-04 | **Fixed** | Enrolment now needs a one-time code in addition to the temporary password. The admin console (create, reset password, reset two-factor, "New enrolment code") and the CLI (`create-admin`, `break-glass`) show the code once; the gateway stores only a SHA-256 hash (schema 6: `users.enrol_code_hash`, `enrol_code_expires`), 20-minute expiry, single use (spent when enrolment completes, audited as `enrolment completed`), constant-time compare, wrong codes counted toward the sign-in throttle and the per-source lock. The enrol-by deadline fell from 72 to 24 hours. The enrol page asks for the code first. Tests: `tests/test_gateway_enrol_code_regression.py`. | The admin must relay the code by a different route than the temporary password; if the same person reads both from one screen to one channel the benefit is lost. Upgrade: accounts that had not enrolled when this release is installed have no code, so issue one from the Users page ("New enrolment code"). Owner check below. |
| PR-11, PR-13, PR-14 | **Fixed (minimal edits in `plan_routes.py`)** | New `src/server/request_limits.py`. PR-11: plan upload refused above 40 MiB of base64, broker/1099-B text above 4 MiB, PDF statements above 12 MiB of base64, and a PDF above 150 pages (counted from page objects before the parser runs) or not starting with `%PDF-`; HTTP 413. PR-13: `finite_float` replaces `float()` on the sale confirm and replace bodies, the candidate panel `shares` and the reconcile `tolerance`, so NaN and infinity give 400. PR-14: `/api/plan/backups/run` takes a bounded, cleaned `trigger` (32 characters of letters, digits, `_`, `-`, `.`) and a forced run is allowed once per 5 minutes per process (429 with `Retry-After`). Tests: `tests/test_request_limits_regression.py`. | The `restore` upload mode still skips the plan-quota check (in `plan_file_service.py`, wave 2's file). The page count is a regex over page objects, so a compressed object stream could hide pages from it; the 12 MiB cap bounds that. `plan_routes.py` edits are about 12 one-line changes, so the merge with wave 2 should be small. |
| X-8 (part), SEC-06 | **Partly fixed** | Identity store (Admin app and Financial Insights sign-in): the password hash is now computed before the locked-account short-circuit, so response time no longer separates locked from unlocked usernames (`verify_login`). TOTP default-key creation (`identity/totp.py default_key`) is atomic: check, mint and write under a thread lock and an OS file lock, then read back. scrypt default cost 2**15 to 2**16 (about 64 MiB per hash; the gateway runs at most 4 at once; existing hashes upgrade on sign-in) and a common-password list (`src/common_passwords.py`, about 200 entries, folded for case, punctuation and `@`/`$`) is checked by `check_password_policy` in the gateway, the identity store and Financial Insights. Tests: `tests/test_identity_hardening_regression.py`. | The identity store still returns reason `locked` to its caller, but Financial Insights (the only route that calls it) answers a locked account exactly like a wrong password (401, wave 2), so the response no longer shows the lock state; the owner decided on 2026-11-24 to keep that uniform response. The list is not a breach database. Hash time roughly doubles. |
| PR-07 | **Fixed (no change to `plan_routes.py`)** | New `src/server/csv_write_gate.py` classifies a request (method + path under the sales, transactions, cash, year-end, reconcile, YTD, spending, housing/wellness seed, plan-registry and investment-income symbol-type areas; preview/validate endpoints excepted) and one `before_request` hook, registered in `app_core.py` after the security gate, answers 403 "CSV writes are disabled" before any handler runs while `allow_csv_write` is off; an unreadable config fails closed. Routes that already checked keep doing so. A decorator form (`csv_write_gate(get_config)`) exists for a single new route. Tests: `tests/test_csv_write_gate_contract.py` (classification table, every registered write route under a gated prefix is covered or an explicit preview, hook behaviour on the real app). | Wiring is at the app level, so the 75 unguarded handlers needed no edit and wave 2's `plan_routes.py` is untouched. A new write route outside the listed prefixes is not covered: add its prefix to `GATED_PREFIXES`. The switch is read per request; an operator who flips it must have it picked up by `load_runtime_config()` (unchanged). |
| F-11 / F-12 / X-13 | **Fixed in code (owner checks below)** | (a) Monarch failure dumps are off by default (`--debug-dumps` or `MONARCH_DEBUG_DUMPS=1`), the HTML is redacted (amounts, long digit runs, masked account numbers, numeric attribute values), a screenshot needs the extra `--debug-screenshot` and is announced as showing real balances, and every run deletes dumps older than 7 days (`Monarch Extractor/monarch_debug_dumps.py`). (b) `src/http_runtime/data_exposure_check.py`: at start the Financial Insights and Admin apps check their data folder and token file for other readers (Windows DACL through `acl.read_dacl`; POSIX mode bits) and for a OneDrive path, log it, print a console box and show a banner on their front page; never fatal. (c) `tools/backup_to_onedrive.py` excludes `identity.db`, `app.db`, `*.rpx` (and version copies), `balances.csv`, `monarch_balances*`, `financial_trends_log*` and `local_state/` unless `--include-data`, which writes only an AES-256-GCM `.zip.enc` (`backup_crypto`, scrypt-derived key from a passphrase prompt or file; refuses without a passphrase); no personal folder names remain (the OneDrive destination is `Retirement Planning/Backups` only if that folder already exists). (d) `tools/manage_secret.py` defines `_run` before use. Tests: `test_monarch_extract_debug_dumps_regression.py`, `test_data_exposure_check_functional.py`, `test_backup_to_onedrive_data_encryption_regression.py` (the existing credentials test now passes `include_data=True` for its plan-data assertions: plan data is no longer in the default archive, by design). | The top-level `input/` folder is now excluded from the default archive too (owner decision 2026-11-24). Redaction is best effort and the dump is short-lived and opt-in for that reason. The banner covers the two apps' front pages, not the planner. The Windows DACL branch of the exposure check was tested with fakes only. **Owner check below.** |
| F-03 | **Fixed (integrity, snapshot, held renames, cents, purge tool); UI banner not added** | Trend log: every line carries an HMAC-SHA256 under a key beside the log (`financial_trends_log.jsonl.key`, owner-only) and a signed head record (`.head`: line count and a MAC over all line MACs) detects edits, deleted lines, truncation and unsigned injection. A failing line is left out of figures, quarantined to `.rejected` by the next write, and every discrepancy is appended to `.integrity.json`; `/api/run-status` carries `log_integrity` when damaged. A log with no head (legacy, or restored from a backup, which carries no key) is accepted once and signed by the next write. Balances DB: `snapshot_db` (SQLite backup API, newest 5 in `data/snapshots/`) before any import that merges a rename or mirror-drops an account; a rename merge is automatic only when the new key repeats every old row exactly, a partial match (the old 80% rule) is held in `pending_renames` until `confirm_rename()` or `reject_rename()`; `balance_cents INTEGER` is filled for every exact cent amount (migration never rewrites `balance`, tested bit-for-bit with real-looking values; sub-cent values stay REAL only). New: `financial_trends_reporter/tools/purge_future_balances.py` (dry run by default; `--apply` snapshots first). Tests: `test_trends_log_integrity_regression.py`, `test_balance_store_integrity_regression.py`. | The key sits beside the data, so a process that can read both can re-sign; this stops accidental damage and anyone who can edit the log but not read the key. Readers still read the REAL column (cents are written alongside, not yet the source of truth). There is no UI to confirm a held rename yet (use `balance_store.confirm_rename`); the owner should check `pending_renames` after an import that reports `pending_renames`. No UI banner reads `log_integrity` yet. **Owner check below.** |
| SEC-08 | **Code fixed; DPAPI and DACL behaviour unverified here** | The key file may now be sealed with machine-scope DPAPI (`ops key seal`; `winapi.dpapi_protect_machine`), holds a ring of keys selected by `key_id` so `ops key rotate` keeps old archives readable (`backup_crypto.KeyRing`; a plain single-key file still reads and is a one-key ring), and `ops key export` writes an offline plain copy. The service checks the key file's DACL at start through `key_acl.key_file_findings` (SYSTEM, Administrators, the gateway account and the owner only) and refuses to start otherwise (`--allow-weak-key-acl` overrides, logged). `ops key check` reports the same. Plain-file fallback off Windows. Tests: `tests/test_gateway_backup_key_rotation_functional.py` (fake DPAPI and fake DACL), `tests/test_gateway_ops_functional.py`. | Machine scope means any administrator on the host can open the sealed key (the owner's facts: the service is the only consumer, and Administrators could already read the file); it only stops a copy of the file working elsewhere. No DPAPI entropy is used. The point-in-time ACL check does not stop a later change. **Owner check below.** |
| SEC-02 / SEC-03 | **Code fixed; Windows runtime unverified here** | New `fsguard.pinned(path, root)`: opens the path once without following a final link (Windows `CreateFileW` with `FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS`, no `FILE_SHARE_DELETE`, via `winapi`; POSIX `O_NOFOLLOW`), refuses a link or an open handle whose `GetFinalPathNameByHandle` is outside the user's folder, and keeps the handle open for the body so the verified folder chain cannot be swapped meanwhile. Used for every backup read (app.db, plan files, insight files: size check and read from one handle), restore moves, and the log trim (one `r+b` handle, truncate in place). `acl.lock_user_folder` refuses a recursive `icacls /reset /T` over a tree with content unless the caller asserts the worker is stopped (`worker_stopped=True`; `acl setup --workers-stopped`; the upgrade script passes it after stopping the service; a new account passes it because it has no worker yet). Tests: `tests/test_gateway_handle_pinned_io_regression.py` (comparison logic, a fake Windows API, real symlinks on Linux). | `sqlite_bytes` still opens by name (SQLite needs sibling `-wal` files); it runs inside the pin, which on Windows stops a swap during the read. `remove_reparse_points` plus `icacls /T` is still not atomic, which is why the worker must now be stopped. **Owner verification: section 9.2 (below)** |

**Owner check (SEC-04), PowerShell on the server host after deploying:** create a throw-away user in the admin console and note the code. `Invoke-RestMethod` is awkward with the CSRF flow, so use a browser: sign in as the new user with the temporary password only, press Continue on the enrolment page with a wrong code. Safe: an error, no QR code, and the Audit log shows `enrol code failed`. Then enter the right code. Safe: QR appears, and after confirming the Audit log shows `enrolment completed`. Unsafe: a QR code appears without a code. Finally `Select-String 'enrol_code' C:\RetirementPlanner\logs\*.log` must find nothing (the clear code is never logged).

**Owner check (F-11/F-12/X-13), PowerShell:** (1) start the Admin app and Financial Insights from the working copy; with the folders locked down (section 9.6) no `WARNING (...)` box may appear and `Invoke-WebRequest` of the front page (with the token) must not contain `data-exposure-banner`. To prove it works, temporarily `icacls financial_trends_reporter\data /grant "BUILTIN\Users:(R)"`, restart: a warning box and the banner must appear; then `icacls financial_trends_reporter\data /remove "BUILTIN\Users"`. (2) `python "Monarch Extractor\monarch_extract.py" --help` must list `--debug-dumps`; after a deliberate failure without the flag, `Get-ChildItem "Monarch Extractor\output" -Filter monarch-debug-*` must be empty. (3) `python tools\backup_to_onedrive.py` then `tar -tf`/`Expand-Archive` the new zip into a temp folder: `Get-ChildItem -Recurse -Include identity.db,app.db,*.rpx,balances.csv,monarch_balances*,financial_trends_log*` there must find nothing and no `local_state` folder may exist. Unsafe: any of those present.

**Owner check (F-03), PowerShell in the repository folder on the host that runs Financial Insights:** (1) after the next scheduled run, `Get-ChildItem financial_trends_reporter\data\financial_trends_log.jsonl*` must list `.key` and `.head` and `icacls financial_trends_reporter\data\financial_trends_log.jsonl.key` must show only your account. (2) Preview the poisoned-row purge: `python financial_trends_reporter\tools\purge_future_balances.py` (safe: `would remove 0 row(s)` or a list of future dates; run again with `--apply` to delete, which first copies the database into `data\snapshots`). (3) After an import, `python -c "from financial_trends_reporter import balance_store as b; print(b.pending_renames(r'financial_trends_reporter\data\monarch_balances.sqlite3'))"` must print `[]` or the renames awaiting your decision. Unsafe: `/api/run-status` shows `log_integrity` with `status: damaged` that you cannot explain.

**Owner check (SEC-08), elevated PowerShell on the server host:** `& $PY -m src.gateway.ops key check --config <gateway.json>` (safe: `sealed with DPAPI: yes`, `only the expected accounts can read it`, exit 0; unsafe: a `PROBLEM:` line or `plain file`). Then `Get-Content <key file> -TotalCount 1` must show `RPSEAL1`, never a base64 line. From a non-administrator account (`runas /user:<worker account> powershell`) `Get-Content <key file>` must be denied, and copying the sealed file to another machine and running `ops key check` there must say the sealed key cannot be opened. After `key rotate` and a service restart, `ops backup verify --archive <an archive made before the rotation>` must still print OK. Unsafe: verify fails with a wrong-key error.

**Owner check (SEC-02/03), PowerShell, elevated, on the server host after deploying; use a throw-away user:** the junction tests of section 9.2 now exercise the open-handle check. Run steps 2 to 4 of 9.2 again. Safe: the backup report (`python -m src.gateway.ops backup run` output, or the `errors` in the archive manifest) says `link inside the workspace, skipped` and nothing is written under `victim`. Then `python -m src.gateway.acl setup ... ` **without** `--workers-stopped` while a user folder has files: safe means it stops with `has files and its worker may be running`; with the service stopped and `--workers-stopped` it succeeds. Unsafe: files appear under `victim` during the race loop of 9.2 step 4.

---

## 7. Decisions recorded and open questions

Decided (2026-11-23): server mode runs on a dedicated machine; Financial Insights guests are view-only.

Open:
1. Is the Admin app or the 5057 listener ever run on the same host as worker accounts? (Drives X-1.)
2. Is percent view treated as a privacy control or as obfuscation? (F-08.)
3. Does Tailscale Funnel append `X-Forwarded-For`? (Section 9.3.)
4. Is the repository or any fixture shared outside the household? (F-18.)

## 8. Limitations

Static review plus in-process dynamic checks on Linux; no penetration test and no Windows runtime verification (see section 9). Findings reflect the code at the stated commit. The proof-of-concept scripts were written to a session scratch folder and are not committed; they can be re-created on request and converted into regression tests. Severity ratings assume the dedicated-host, view-only-guest decisions above and should be re-rated for any multi-tenant or commercial use. This document is not a certification.

## 9. Owner verification steps (items that could not be confirmed here)

Run in an elevated PowerShell on the server host unless stated. `$Root` is the gateway data root and `$Install` the install folder. Report the output of each step; "unsafe" results should be re-rated up one level.

**9.1 X-1: can a worker account reach the Admin app and the 5057 listener?**
1. List listeners: `Get-NetTCPConnection -State Listen | ? LocalPort -in 5050,5056,5057,5058,5065 | select LocalAddress,LocalPort,OwningProcess`. Note which of these exist on the server host at all. If 5056 and 5057 are not listening, X-1 does not apply; stop here.
2. Open a shell as a worker account: `runas /user:<worker account> powershell` (accounts use the configured prefix, `rpw_` by default).
3. In that shell: `Test-NetConnection 127.0.0.1 -Port 5056` and `Test-NetConnection 127.0.0.1 -Port 5057`.
4. If a port connects: `Invoke-WebRequest http://127.0.0.1:5057/api/whoami -UseBasicParsing | select StatusCode` and `Invoke-WebRequest http://127.0.0.1:5056/ -UseBasicParsing | select StatusCode`.
- Safe: connection refused or timeout, or a 403/401.
- Unsafe: `TcpTestSucceeded: True` and HTTP 200. Then stop the Admin app and 5057 on this host or add a credential.
- After the X-1 fix: the same two requests from the worker shell must give 401 (PowerShell reports an error whose `.Exception.Response.StatusCode` is `Unauthorized`), and `Get-Content <repo>\local_state\insights_local_token` and `...\admin_local_token` from the worker shell must say access denied.

**9.2 SEC-02/03: junction and reparse-point races in backup, log and ACL jobs**
1. Use a throw-away test user, never a real one. `mkdir $env:TEMP\rp_t\victim`.
2. With the worker stopped, replace the user's data folder with a junction: `Remove-Item $Root\users\<testuser> -Recurse -Force; cmd /c mklink /J $Root\users\<testuser> $env:TEMP\rp_t\victim`.
3. Run a gateway backup (`python -m src.gateway.ops backup ...`) and the log-trim job, then `Get-ChildItem $env:TEMP\rp_t\victim -Recurse`.
- Safe: the job refuses with a reparse-point error and nothing is written under `victim`.
- Unsafe: files appear under `victim`.
4. Race test: in one window loop `while($true){ Remove-Item $Root\users\<testuser> -Force -Recurse -EA SilentlyContinue; cmd /c mklink /J $Root\users\<testuser> $env:TEMP\rp_t\victim >$null; Remove-Item $Root\users\<testuser> -Force; mkdir $Root\users\<testuser> >$null }`; in another, repeat the backup 100 times. Unsafe: any file lands in `victim`.
5. Afterwards `icacls $Root\users\<testuser>` should list only the user, SYSTEM and Administrators.

**9.3 SEC-12 / F-06 / F-14: Tailscale Funnel and X-Forwarded-For**
1. `tailscale funnel status`: it must point only at the gateway port (5065), never 5050, 5056, 5057 or 5058.
2. From an external host: `curl -k -i -H "X-Forwarded-For: 1.2.3.4" https://<node>.ts.net:8443/api/auth/session`, then again with `-H "Tailscale-User-Login: a@b"`.
3. Login-throttle test (use a test username): `1..20 | % { curl -k -s -o NUL -w "%{http_code}\n" -H "X-Forwarded-For: 10.0.0.$_" -H "Content-Type: application/json" -d '{"username":"testuser","password":"x"}' https://<node>.ts.net:8443/api/auth/login }`.
- Safe: 429 appears regardless of the spoofed header, and the audit `client_ip` shows the real address.
- Unsafe: no 429 and the audit log shows the spoofed address. Also confirm whether Funnel appends the real client address as the last `X-Forwarded-For` entry.

**9.4 X-2, SEC-08, SEC-09: service, config, key and secret storage**
1. `sc.exe qc <ServiceName>` (quoted path, run-as account); `wmic service get name,pathname` for unquoted paths containing spaces.
2. `icacls <path to gateway.json>`, `icacls <log folder>`, `icacls $Install /T | findstr /i "Users Everyone Authenticated"`, `icacls $Root`, `icacls <backup key folder>`.
- Safe: write/modify only for SYSTEM, Administrators and the service account.
- Unsafe: `BUILTIN\Users`, `Everyone` or `Authenticated Users` with `(W)`, `(M)` or `(F)` anywhere under `$Install`, on the config, log folder or key folder.
3. As a non-admin: `echo x > "$Install\test.txt"` should fail with Access denied.
4. TOTP secret sealing: query `gateway.db` with `sqlite3` and inspect the TOTP secret column. Safe: DPAPI blob (base64 starting `AQAAANCMnd8`). Unsafe: base32 text, or a log line saying DPAPI is unavailable and secrets are stored in clear text.
5. Scope check: as a different Windows user, try to unseal a copied blob with `[Security.Cryptography.ProtectedData]::Unprotect(...)`. Safe: fails. Unsafe: decrypts (machine scope).
6. Confirm the backup key file is not in a synced or world-readable folder: `icacls <key file>`.

**9.5 X-3: SYSTEM test script path**
1. `icacls C:\Windows\Temp\rpw_system_run.cmd` (if it exists) and `Get-Acl C:\Windows\Temp | fl`.
2. Do not run `tools/run_elevated_tests_as_system.ps1` on a host with untrusted local accounts until it is fixed. Unsafe: a non-admin can create or modify the file.

**9.6 Data at rest (F-11, F-12)**
1. `manage-bde -status` for the drive holding `$Root`, `financial_trends_reporter\data` and `Monarch Extractor`. Safe: protection on. Unsafe: off.
2. `icacls "Monarch Extractor\monarch-browser"`, `icacls "Monarch Extractor\output"` and `icacls financial_trends_reporter\data`: only the operator account and SYSTEM.
3. `Get-ChildItem "Monarch Extractor\output" -Filter monarch-debug-*` and delete leftover failure dumps after reviewing them.
4. Confirm none of these folders is under OneDrive: `(Get-Item <path>).FullName -match 'OneDrive'` must be false.


## 10. Owner verification results (2026-11-23, run interactively on the server host)

Environment observed: a Windows host running the gateway as the `RetirementGateway` service (`LocalSystem`, installed copy `C:\RetirementPlanner\app`), three worker accounts `rpw_1` to `rpw_3`, the standalone Financial Insights (5057/5058) and the Admin app (5056) running as the owner account from the working copy, Tailscale Funnel serving 443 to 5058 and 8443 to 5065.

| Section | Result | Final rating |
|---|---|---|
| 9.1 X-1 | **Confirmed.** With no sign-in, 5057 returned HTTP 200 for `/api/history` (1.27 MB) and `/api/balances` (464 KB); 5056 returned 200 for users, settings, processes, sessions, audit and system status. 5058 returned 401. Both loopback apps run as the owner account, so a local worker would act with the owner's rights. Write routes were deliberately not exercised. | **High, confirmed.** Credential fix implemented (section 6a); verify after deployment with the worker-shell checks in 9.1 |
| 9.2 SEC-02/03 | Guard verified on real Windows junctions: junction detected, ordinary path not flagged, outside-root flagged, removal deletes only the link, target intact. The check-then-open window remains a code finding. | **Low-Medium** (code fix pending) |
| 9.3 SEC-12 / F-06 | A phone on mobile data (no Tailscale) failed three logins; the gateway audit recorded the phone's real public address with `listener=funnel`, not loopback and not a supplied value. Funnel supplies the client address, so the gateway's right-most rule is correct. The guest listener on 443 still uses the first header entry (not tested; code fix). | SEC-12 **closed**; F-06 **Low** |
| 9.4 X-2, SEC-08, SEC-09 | Service path quoted; config and state folders `SYSTEM`/Administrators only; no worker-writable entry anywhere under the install tree; each `data\users\<id>` folder grants only its own `rpw_<id>` account; `shares` gateway-only; `backup.key` readable only by the owner, Administrators and `SYSTEM`; TOTP secrets 2 of 2 sealed with DPAPI and not unsealable by an Administrator account. Service privileges are unrestricted. `C:\ProgramData\RetirementPlannerGateway` lets `Users` create files beside the protected `backups` and `keys` folders. | X-2 **Info**; SEC-08 **Low**; SEC-09 **Info**; ProgramData parent **Low** |
| 9.5 X-3 | `C:\Windows\Temp\rpw_system_run.cmd` absent; the only SYSTEM tasks are vendor updaters in `Program Files`. | **Low** (script defect, not live) |
| 9.6 F-11, F-13, X-13 | BitLocker on and fully encrypted; working copy and sensitive folders restricted to owner, Administrators and `SYSTEM`; no worker-writable file under the folders scheduled tasks run. Four Monarch failure dumps and two OneDrive zips holding real plan files (in a business OneDrive tenant) were found, and **the owner has since deleted them**. | F-11 **Low**; F-13 **Low**; X-13 **closed for these files** (the backup tool still copies unencrypted project data) |

Items still open for the owner: deploy and verify the X-1 credential (section 9.1 commands after the fix), lock down the `ProgramData\RetirementPlannerGateway` parent folder, and consider restricting the service's privileges.

## 11. Owner verification for wave 2 (items that need the Windows server)

Run on the server host after deploying this branch; report each result.

**11.1 Security headers (SEC-07).** From any machine: `curl -k -I https://<node>.ts.net:8443/` and `curl -k -I https://<node>.ts.net/signin`. Safe: each response carries `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`; the 443 (Financial Insights) responses also carry `Cache-Control: no-store`. Then sign in to the planner and Financial Insights in a browser and confirm they work with the browser console open; report any "Refused to ..." CSP message verbatim (the Financial Insights inline script is admitted by hash, so editing `index.html` without restarting the app is the usual cause).

**11.2 Funnel guard (X-4, X-5).** `python -m src.gateway.ops funnel check --funnel-port 5065 ...` (the same arguments as in the runbook) must print "Funnel configuration OK" with the live layout. To prove it fails closed, stop the Tailscale service (`Stop-Service Tailscale`), run the check again (expect "UNVERIFIED", exit 1), then start the service.

**11.3 Guest listener client address (F-06).** From an external host: `curl -k -H "X-Forwarded-For: 1.2.3.4" -H "Content-Type: application/json" -d '{"username":"x","password":"y"}' https://<node>.ts.net/api/signin`, then open the Admin app's Activity page: the source for that "sign-in failed" event must be your real address, not 1.2.3.4.

**11.4 ACL check (X-2).** `python -m src.gateway.acl check --data-root $Root --gateway-db $Root\gateway.db --install-dir $Install --config-file <path to gateway.json> --log-dir <log folder>`. Safe: prints OK. Any "can write" line names a path a worker account could use to run code as SYSTEM.

**11.5 Plan file hardening (S-03).** Open a normal plan, Save As to a `.rpx`, and Load Saved Plan: all must still work. Optional proof of the guard: copy a plan, `sqlite3 copy.rpx "CREATE TRIGGER t AFTER INSERT ON plan_rows BEGIN SELECT 1; END;"`, then Load Saved Plan with it: expect an error naming the trigger.
