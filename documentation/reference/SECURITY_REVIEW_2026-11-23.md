# Security Review — Retirement Planning System and Financial Insights

**Date:** 2026-11-23
**Audience:** External auditors; internal product owners
**Basis:** repository commit `58ad4e0` (shallow clone, 230 commits visible)
**Method:** static source review by three parallel reviewers (gateway; local server and admin app; Financial Insights, Monarch Extractor, supply chain). Key findings F-01, F-02, F-04, F-15 and SEC-01 were re-read by the lead reviewer.
**Not performed:** dynamic testing, penetration testing, dependency CVE scanning, review of Windows-only code paths at runtime, review of `plan_routes.py` in full (2,640 lines), `config_service.py`, `conversion_service.py`, `funnel_guard`, and deployment configuration (service accounts, `gateway.json`, Tailscale Funnel settings). Findings marked **C** depend on these gaps.

Pre-review integrity check (OneDrive truncation): all Python files compile, all tracked JavaScript parses, no tracked HTML lacks a closing tag. No truncated files were found.

---

## 1. Executive summary

The system is a local-first retirement planner with three optional network surfaces: a single-user loopback server, a multi-user **gateway** (per-user worker accounts, password + TOTP, reverse proxy, encrypted backups, per-grantee shares), and **Financial Insights** (FI), a net-worth/cash-flow reporter fed by a Monarch extractor and exposed to guests through the gateway or a standalone Tailscale Funnel listener.

**Overall posture: good for a self-hosted, single-household tool; not yet audit-ready for multi-party use.** The authentication, session, CSRF, proxy-header and backup-crypto designs are consistently defensive and mostly test-covered. There is no LLM or AI API traffic, no use of `shell=True`, `eval`, `pickle` or unsafe YAML in server paths, no secrets in tracked files, and no real data found in committed history.

| Severity | Count | Headline items |
|---|---|---|
| Critical | 0 | — |
| High | 1 | F-01 guest sessions can write to the owner's Financial Insights store and start jobs |
| Medium | 17 | Unauthenticated loopback server; missing CSP/headers on planner and FI listeners; open redirect; enrolment takeover window; lockout DoS; unvalidated balance dates; unpinned CI actions and dependencies; unprotected data at rest |
| Low | 14 | See §5 |
| Info | 5 | See §5 |

**Top five actions** (in order): (1) lock down FI write routes for remote sessions and bound balance dates; (2) add security headers to the planner and FI listeners and the gateway proxy; (3) fix the client-side `?next=` redirect; (4) pin CI actions, add a hashed Python lockfile and audit steps; (5) document and enforce data-at-rest requirements (disk encryption, ACL checks, retention of Monarch debug dumps).

---

## 2. System and trust boundaries

| Component | Exposure | Trust model |
|---|---|---|
| Desktop mode (`main.py`) | No socket; in-process JS bridge | OS user |
| Server mode (`src/server`, port 5050) | Loopback by default; non-loopback only if a static token is set | Host/Origin/CSRF gates; **no user authentication on loopback** |
| Admin app (port 5056) | Loopback | Loopback + same-origin + JSON content-type gates; no sign-in |
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
*Fix:* make write routes owner-only for remote sessions (or a distinct grant); add a contract test that fails when a POST route is neither owner-only nor deliberately guest-writable (the existing guard covers percent leakage only). *Note:* worker mode uses per-plan stores, which limits blast radius.

### 3.2 Medium

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| S-01 (V) | Loopback server and Admin app have no authentication; any local process or other OS user on a shared host can read or overwrite plans and call shutdown. Requests with no Origin skip CSRF. | `security_audit.py:83-88`; `app_core.py:1140-1170`; `admin_app/trust.py:3-4` | Per-launch random token on loopback, or a Unix socket/named pipe; document server mode as unsafe on multi-user hosts. Desktop mode unaffected. |
| S-02 (C) | No CSP or security headers on the planner server; ~70 `innerHTML` assignments with a privileged desktop bridge (`js_api`). One missed `esc()` on CSV- or `.rpx`-derived text becomes script with API access. Spot checks found no unescaped fields. | `src/server/*`, `frontend/js`; `desktop_app.py:38-40` | CSP + `nosniff` on all responses and a meta tag in `index.html`; lint rule banning unescaped interpolation in `innerHTML`. |
| S-03 (C) | Untrusted `.rpx` (SQLite) opened without `trusted_schema=OFF`, `cell_size_check`, or defensive mode; opening may upgrade in place. Triggers/views in a crafted plan could execute. | `plan_file_service.py:230-235`; `plan_db_replace.py:72,86-96` | Harden pragmas; reject unknown triggers/views; validate read-only first. |
| SEC-01 (V) | Open redirect after sign-in: `nextPath()` accepts `/%09/evil.example`, which the browser normalises to `//evil.example`. Server-side `safe_next` is stricter but not used by this path. | `pages/gateway.js:77-85`; `app.py:126-134` | Apply `safe_next` rules client-side; resolve with `new URL()` and require same origin. |
| SEC-02 (C) | Check-then-use windows on worker-writable trees in backup/log jobs run as LocalSystem (junction swap between `has_reparse_point` and open). | `backup_store.py:66-77,115-127,213-231,394-406`; `logs.py:30-45`; `fsguard.py:213-239` | Open with no-follow/`FILE_FLAG_OPEN_REPARSE_POINT` and verify final path; run while worker stopped. |
| SEC-04 (V) | Pre-enrolment takeover: anyone with the admin-issued temporary password can enrol their own authenticator within the 72-hour window. | `store.py:51,719-732`; `app.py:531-546` | One-time out-of-band enrolment code; shorter window; admin notification. |
| SEC-05 (V) | Lockout DoS: five failures lock a username for 15 minutes regardless of source, including the only admin; the Funnel listener is internet-reachable. | `store.py:634-649`; `access_core.py:18-19` | Per-user+per-IP counting, exponential delay, exempt valid sessions. |
| SEC-07 / F-10 (V) | Proxied planner/`/insights/` responses and the standalone FI listeners lack CSP, frame-ancestors, Referrer-Policy and (FI) `no-store`. Worker XSS would share an origin with gateway admin APIs; the FI runbook's "back button shows no data" test depends on `no-store`. | `app.py:374-385`; `proxy.py:196-209`; FI `index.html:401` (inline module script) | `setdefault` headers in the proxy; `after_request` on FI listeners; nonce/hash for the inline script. |
| SEC-08 (V) | Backup key is a plain base64 file (`0o600` has no effect on Windows), not DPAPI-wrapped, same host as archives; no rotation (`key_id` is fixed). | `backup_crypto.py:43-59`; `ops.py:147-161` | DPAPI/passphrase-wrap; ACL check on start; multi-key support. |
| F-02 (V) | A future-dated balance row passes the staleness guard and, via `active = (last_seen = MAX(date))`, deactivates all other accounts; net worth and the percent basis collapse. | `balance_store.py:197,235-236,97-105` | Reject dates > today+1; add jump/magnitude checks; keep last good import. |
| F-03 (V) | No integrity protection on balances DB, log or CSV; the log silently drops bad lines; heuristic rename merging deletes history irreversibly; money stored as REAL. | `trends_log.py:39-57`; `balance_store.py:111-150` | Hash-chain/HMAC the log; snapshot before destructive imports; confirm renames; integer cents. |
| F-04 (V) | Idle timeout trusts client-supplied `idle_ms`; no absolute lifetime; sessions are memory-only. A stolen cookie stays alive with `{"idle_ms":0}` pings. | `sessions.py:51-55`; `access_routes.py:361-371` | Absolute lifetime (e.g. 12 h); server-side activity tracking; cap client influence. |
| F-05 (V) | Remote 500 responses expose exception text and filesystem paths to dollar-view guests. | `access_routes.py:174-178`; `main.py:424` | Opaque error id (as `gateway/app.py:393`). |
| F-08 (V/C) | Percent view divides every figure by one constant `k` (today's net worth). One known dollar anchor (mortgage, salary) recovers all balances. Account names may embed employer/person names. | `percent_view.py:81-91` | Document as obfuscation, not a privacy boundary; jitter/rotate `k`; pseudonymise names. |
| F-11 (V) | Financial data at rest is plaintext with no explicit permissions: trend log, balances DB, `balances.csv`, raw CSVs; Monarch failure dumps (full-page screenshots/HTML of authenticated pages) are never cleaned. OneDrive may replicate. | `monarch_extract.py:1230-1246`; FI package (no ACL calls) | Require disk encryption; startup ACL and OneDrive-path check; retention policy; debug dumps off/redacted by default. |
| F-12 (V) | Persistent Chromium profile holds Monarch session credentials; same-user malware or a copied profile yields full account access. | `monarch_extract.py:32,1192`; `monarch_balances.py:30,142` | Keep outside OneDrive/repo; restrict ACL; dedicated login with MFA. |
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
| SEC-06 | Low | scrypt N=2^15, min length 12, no breach check, no rehash on login (`access_core.py:20-30`; `store.py:41-42`) | Raise N; rehash; common-password list |
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

## 4. Positive controls (evidence for auditors)

**Authentication and sessions.** scrypt with per-user salt and bounded concurrency; RFC 6238 TOTP with replay protection inside `BEGIN IMMEDIATE`; shared lockout budget; per-IP and per-user throttling; uniform responses and a dummy hash for unknown users; `__Host-` cookie, `Secure; HttpOnly; SameSite=Strict`; 256-bit tokens stored hashed; rotation on stage change; idle 15 min / absolute 12 h; revocation on password change, disable, role change, TOTP reset. (`store.py`, `app.py`, `totp.py`, `signin_throttle.py`)

**CSRF/CORS/Host.** Per-session CSRF token, Origin allowlist, `Sec-Fetch-Site` checks, content-type allowlist, no CORS headers, Host allowlist against DNS rebinding, request-size caps. (`app.py:277-301`; `app_core.py:1116-1177`; `host_guard.py`)

**Proxy and authorization.** Deny-by-default admin prefixes; viewer allowlist that never reaches workers; credential, cookie and forwarding headers stripped; worker `Set-Cookie`/CORS dropped; loopback-only upstream (no SSRF); path-traversal rejection; last-admin protection. (`proxy.py`, `upstream.py`, `viewer_routes.py`)

**Isolation.** One Windows account per user (deny interactive/RDP/network), per-user ACLs, Job Object memory caps, scrubbed environment, `python -E -s -B`.

**Shares.** No bearer links; 128-bit per-grantee ids; owner/grantee-scoped queries; SHA-256 binding of body to row; worker output revalidated (schema, percent-leak scan, Unicode normalisation); revocation deletes bodies; access log; viewer pages use `textContent` only.

**Backups.** AES-256-GCM, per-archive HKDF salt, chunk AAD binding header/index/final flag (reorder/truncate detected), read-back verification, allowlisted restore members, destination confinement.

**Local app.** Desktop mode opens no socket; remote mode deny-by-default allowlist and path confinement; keyring-only secrets with no plaintext fallback, write-only `/api/secrets`; log redaction and account-number masking; list-form subprocess calls; upload magic-byte and schema validation with atomic swap; Monarch connector refuses redirects and size-caps responses.

**Financial Insights.** Two-port trust boundary with startup Funnel guard; fail-closed percent scaling with merchant collapse and leak scan run twice; bound SQL parameters throughout; escaped frontend; importer guards (header, finite values, stale export, account-count drop) with rejection records; per-plan worker stores.

**SDLC.** No `pull_request_target`; nightly workflow least-privilege; `npm ci` with integrity hashes; account-number check in CI; `.gitignore` covers databases, `*.rpx`, `input/`, FI data, Monarch profile and output; secret-pattern scan of tracked files and the visible history found nothing.

---

## 5. Test coverage

Security-relevant suites exist for access gating, TOTP, CSRF/Origin, Funnel guard, percent leakage, worker allowlist, share snapshot/store/publish, gateway auth/throttle/ACL/backup crypto/pre-auth limits, multi-user isolation, credential exclusion from backups and chart escaping.

**Gaps (no test found):** guest writes to the owner store (F-01); future-dated balances (F-02); client `idle_ms` extension (F-04); `X-Forwarded-For` spoofing; headers on FI listeners and proxied planner pages; unescaped data interpolation across frontends; `next=` redirect with control characters (SEC-01).

---

## 6. Remediation roadmap

| Wave | Items | Effort |
|---|---|---|
| 1 — now | F-01, F-02, SEC-01, F-04, F-05 | Small; each is a few lines plus a test |
| 2 — next sprint | SEC-07/F-10 headers, S-02 CSP, F-15 pinning, F-16 lock + audit, F-17 push policy, SEC-05, SEC-10 | Small–medium |
| 3 — hardening | SEC-04 enrolment, SEC-08 key wrapping, SEC-02/03 handle-based I/O, S-01 loopback token, S-03 SQLite pragmas, F-03 integrity, F-11/F-12 at-rest controls | Medium–large |
| 4 — hygiene | Low/Info items, F-18 identifiers, F-19 licences, documentation of percent view as obfuscation | Small |

## 7. Questions for product owners

1. Is server mode ever used on a shared or multi-user machine? (Drives S-01 priority.)
2. Are FI guests expected to edit account settings, or view only? (F-01.)
3. Is percent view marketed or treated as a privacy control? (F-08.)
4. Does Tailscale Funnel append `X-Forwarded-For`? (SEC-12, F-06.)
5. Is the repository, or any fixture, ever shared outside the household? (F-18.)

## 8. Limitations

Static review only; findings reflect the code at the stated commit. Severity ratings use likelihood × impact for a self-hosted deployment and should be re-rated for any multi-tenant or commercial use. This document is not a certification.
