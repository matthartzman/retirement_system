# One identity store, one admin UI: scoping

Status: draft
Date: 2026-11-17

Question from the owner: why are there two identity stores and two admin UIs, and what would it take to have one of each?
This document is the scoping only. No code is written. It does not touch the installed server at `C:\RetirementPlanner`.
It builds on `multi-user-admin-console-integration-design.md` (approved; "Option B": the gateway hosts the Users UI, the two stores
stay separate), `admin-app-plan.md`, `admin-app-process-control-design.md` and `multi-user-server-security-review.md`.
Evidence is cited as `file:symbol`. Anything not read or run is marked **not verified**; section 9 collects them.

## 1. Short answer

**One admin UI: already true.** PR #468 made `admin_app/frontend/users.js` a module shared by the loopback Admin app and the gateway's
`/gateway/admin`. What differs is the host page and the routes behind it, not the Users screen.

**One store: possible as one schema and one code library, not sensibly as one physical file shared by a PC and the server.**
Three real obstacles, none of them "nobody got round to it":

1. **Different secret sealing.** `gateway.db` TOTP secrets are DPAPI-sealed for the gateway service account (`secret_box.py`: `dpapi1:` prefix,
   LocalSystem scope). `identity.db` TOTP secrets are sealed with a key in the signed-in user's OS credential store (`identity/totp.py`,
   `KEY_SECRET_NAME = "identity.totp.key"`). A process running as one account cannot open the other's seals.
2. **Different file permissions on purpose.** Per-user workers run as `rpw_<id>` Windows accounts and must not read the credential file
   (`fsguard.py`, `supervisor.py`). Financial Insights (FI) and the Admin app run as the owner and need to read theirs.
3. **Different semantics.** Gateway sessions are server-side authentication state (`sessions` table: token hash, stage, CSRF). Identity
   "sessions" are an observation table (`live_sessions`) plus a `session_epoch` counter; FI keeps its own in-memory session table.

**Recommendation (Option C, section 5): one shared identity library and schema (`src/identity`, extended), one file per install, one Users UI.**
The server's file stays `gateway.db`; a PC's stays `identity.db`; both open through the same code and the same schema, so every field the
Admin UI edits exists in both places. A same-machine installation that wants a literally shared file can point FI and the Admin app at it,
under the conditions in section 3.3. What the owner gives up: a single file that is simultaneously the PC's and the server's database.

## 2. Canonical store and schema mapping

### 2.1 Which is canonical

**The canonical thing is the schema and the library, and the gateway's credential rules win where they differ.** Reasons:

- The gateway store is the only one that has been through the security review (scrypt concurrency cap, dummy-hash timing equaliser, lockout,
  12-character minimum, sealed TOTP, hashed session tokens) (`gateway/store.py`: `DEFAULT_HASH_CONCURRENCY`, `_DUMMY_SALT` use,
  `MIN_PASSWORD_LENGTH`). Moving the server onto a less-reviewed login path is the worst place to take risk.
- The identity store is the richer *data model* (grants, expiry, notes, session epoch, per-user two-factor flag, recovery codes, activity).
  The gateway needs those anyway for the owner's decisions 2 and 3 (expiry, notes) in the integration design.
- Both already share `src/access_core` for hashing, throttling and lockout (`access_core.hash_password`, `password_matches`,
  `failure_outcome`; used at `gateway/store.py` and `identity/store.py`), so the hard primitive is already common.

So the unified schema is the identity schema (v4) plus the gateway-only tables, with the gateway's stricter rules selectable by configuration.

### 2.2 Mapping

| Concept | `identity.db` (schema v4) | `gateway.db` (schema v2) | Unified |
|---|---|---|---|
| Person | `users`: id, username, display_name, role, pw_hash, pw_salt, scrypt_n, must_change, failed_count, locked_until, created_at, updated_at | same columns; role has a CHECK constraint | Same. Add the CHECK to identity |
| Last sign-in | `last_signin_at` | `last_login_at` | One name; copy across |
| Enabled | `status` ('active'/'disabled') | `disabled` (0/1) | `status`. Gateway code reads through a helper |
| Expiry, notes, session epoch, two-factor-required | `expires_at`, `notes`, `session_epoch`, `totp_required` | absent | Add to gateway (additive, nullable or defaulted). Gateway forces `totp_required = 1` and the store refuses to clear it when `mandatory_totp` is configured |
| Password hash | scrypt, per-user salt and `scrypt_n` | same, same function | Copy bytes verbatim; **no rehash and no reset** |
| Minimum password length | 10 (`access_core.MIN_PASSWORD_LENGTH`) | 12 | A store setting passed at open time. Single-user installs stay 10 (owner decision 4) |
| Two-factor secret | `totp`: secret BLOB sealed to a keyring key and bound to the person; enrolled_at, last_used_step, `recovery_codes` JSON | `totp_secrets`: secret TEXT (`dpapi1:` + base32), created_at, enrolled_at (NULL while pending), last_used_step | Same RFC 6238 parameters on both sides (SHA-1, 6 digits, 30 s, +-1 step), so one base32 secret works in both. Unified table carries recovery codes and a pending flag. The *sealing* is a pluggable `SecretBox` (DPAPI-service, user-keyring, or none) chosen per install |
| App grants | `app_grants`: user_id, app, money_view, views, granted_by, granted_at | none (every active user has the planner) | Add `app_grants` to gateway. **Absence of a row on a gateway install means "implicit planner access" until grants are enforced there**; do not silently turn the implicit planner grant into a denial |
| Sessions (authentication) | none in the store; FI holds an in-memory `SessionTable` and compares `session_epoch` | `sessions`: token_hash, stage, csrf_token, expiry, client_ip | Keep `sessions` as gateway-owned. Add the epoch check to the gateway lookup so "end sessions" works the same way in both |
| Sessions (observation) | `live_sessions`: key, user_id, app, listener, source, started, last_seen | none | Gateway: derive the Admin "who is signed in" view from `sessions`; do not populate `live_sessions` there |
| Activity (per app) | `activity`: at, person (text), listener, event, details, source, app | `audit_log` records sign-ins and lockouts but not per-app use | Fold into one `audit_log` with an `app` column; migrated `activity` rows get the event they already have |
| Admin audit | `admin_audit`: at, admin (text, "owner (PC)"), action, target_user (text), details | `audit_log`: at, actor_user_id/username, event, target_user_id/username, details, client_ip, listener | `audit_log` is canonical (superset). `admin_audit` rows copy in with `actor_username = admin`, no user ids |
| Windows accounts | none | `worker_accounts` (deliberately no foreign key so cleanup can be retried) | Gateway-private; not part of the shared schema |

Column mapping notes: both stores key everything by integer `users.id`. On the gateway that id derives `rpw_<id>`, the worker slot and the
workspace folder, so **gateway ids are never renumbered**. Where both stores exist, people are matched by `username`; the gateway id wins.

## 3. How FI, Planner grants and the loopback Admin app read the store

### 3.1 The access seam

Today FI and the Admin app call `IdentityStore` directly (`financial_trends_reporter/main.py` opens it with `open_identity_store`;
`admin_app/main.py` likewise). The change keeps that shape: both open the shared library with a path and a sealing choice, nothing
talks to the gateway. A read is a plain SQLite open of the file; the library does not need a running gateway for any read or write
except TOTP on a gateway-sealed file (3.3).

### 3.2 PC with no gateway running (the common case)

The PC has `identity.db` as today. The Admin app edits it; FI reads grants and checks expiry and epoch exactly as `access_routes.py`
does now (`store.get_grant(user_id, "insights")`, expiry, `session_epoch`). Nothing about this path changes except that it runs on the
shared library and the unified schema. The Admin app on that PC shows Users, Settings, Processes and Shutdown. The gateway is not
involved, so nothing can go wrong when it is not running.

### 3.3 One physical file on a machine that runs both

Optional, same machine only. FI and the Admin app are pointed at `gateway.db` (`identity_db_path`). It works only when all of these hold:

- The file's ACL lets the owner's account read and write it. Today the gateway keeps it from worker accounts; the owner is a different
  principal, and that grant is a deliberate change to the server's protections (risk R3).
- TOTP: DPAPI seals made by the service open only for that account. Under the owner's account the library cannot unseal them, so **FI
  sign-in with two-factor would fail closed** (refuse, not skip). Fixes, in order of preference: run the Admin app and FI under the same
  account as the gateway service (not acceptable for FI, which handles personal data under the owner); or FI delegates sign-in to the
  gateway's loopback listener (new work, phase 6, not recommended now). Passwords, grants, expiry and the UI work with no such change.
- The gateway can be stopped: SQLite WAL permits it, and all writes go through one library so no schema drift.

### 3.4 Planner grants

`app_grants` rows for `app = 'planner'` exist and the Admin app writes them (`admin_app/routes_users.py`, lines near 107-124), but a Grep of
`src/server/` for `identity`, `get_grant` and `IdentityStore` returned nothing, so **no planner-side enforcement was found** (not verified
elsewhere). Under this design nothing changes for the Planner: on a PC it is single-user and gated by loopback; on the server the gateway
admits every active user. Making the planner grant a real gate is a separate, small change in the gateway's `_run_gate` and is listed in
phase 4 as optional, because turning it on is a behaviour change for existing users.

## 4. Keeping local-only panels off the internet-facing listener

The panels in question: install-wide settings, start/stop of the planner and FI, planner shutdown and system shutdown, clear cache
(`admin_app/routes_system.py`: `/api/settings`, `/api/system/planner-shutdown`, `/api/system/shutdown`, `/api/system/clear-webview-cache`;
`routes_processes.py`; added in #455). The mechanism has three layers, and the first is the one that matters:

1. **They do not exist in the gateway process.** The gateway registers only the Users routes (`gateway/admin_console.py`) and its own
   `/gateway/*` and `/api/auth/*` routes. A contract test builds both apps and asserts the gateway's URL map contains none of
   `/api/settings*`, `/api/system/*`, `/api/processes*`. A route that is not registered cannot be reached by any role, any bug in a role check,
   or any Funnel misconfiguration. This is stronger than a runtime check and is the reason the design does not mount the panels behind an
   "admin and local listener" condition.
2. **The Admin app refuses anything that is not this PC's browser** (`admin_app/trust.py:check_request`): loopback peer address, loopback
   `Host` header (blocks DNS rebinding), no proxy, Tailscale or Funnel headers (Funnel delivers internet traffic from 127.0.0.1, so a header
   is the only tell), same-origin `Origin` and `Sec-Fetch-Site`, JSON content type on writes. It binds loopback only.
3. **Startup refuses a Funnel pointed at the Admin port** (`trust.py:check_funnel_target` via `access_core.tailscale_serves_port`); the
   gateway has the equivalent check for its local port (`server.py`, around lines 340-360).

How the Users UI is still shared: one module (`users.js`), two shells. The Admin app shell adds the Settings, Processes and Shutdown
tabs; the gateway shell (`/gateway/admin`, gateway CSP, CSRF header, no inline script) does not. A test asserts that loading each shell
registers exactly the expected set of tabs, and that the gateway shell's static allowlist contains no settings or process script. The shared
module reads a `features` list from its host and shows only what the host provides. The gateway additionally keeps its existing
`ADMIN_PREFIXES` deny-by-default gate (`gateway/app.py:35`, `_run_gate`).

If the owner later wants those panels reachable remotely, that is a separate decision with its own review. This design does not enable it.

## 5. Options considered

| | A. Keep two stores (today, plus Option B) | B. `gateway.db` canonical, one file everyone opens | C. Shared library and schema, one file per install (recommended) | D. Gateway as identity service (loopback API) |
|---|---|---|---|---|
| What is "one" | One UI (done) | One file, one schema | One schema, one library, one UI | One service, one file behind it |
| FI and Admin app read | Their own `identity.db` | `gateway.db` directly | Their own file via the shared library | Gateway API; gateway must be running |
| PC with no gateway | Works | Needs a gateway-shaped file; TOTP blocked by DPAPI scope (3.3) | Works, unchanged behaviour | **Fails**: no gateway, no sign-in |
| Server login path touched | No | Yes (new columns, seam changes) | Yes (store moves onto the library) | Yes (new API and trust) |
| New features implemented twice | Yes (expiry, notes, grants, audit) | No | No | No |
| Rollback | Trivial | Hard (shared file already written) | Moderate (copy, not move; section 6) | Hard |
| Cost (5-hour cycles, estimate) | 0 beyond phases 2-3 of the integration design | 4 to 6 | 4 to 6 | 6 to 8 |
| Main risk | Divergence over time; two stores answer "who exists" | File ACL and DPAPI scope; weakens server protection | Login-path regression on the server | New remote-ish trust surface and a hard dependency |

**Recommendation: C, and only after the NO-GO conditions that touch the login path are settled (R1).** If the owner's real pain is the
double work (every feature built twice) and not the existence of two files, then C delivers exactly that and A does not. If the pain is only
"the screen differs", A is already complete and C is not worth its cost.

**What the owner gives up with C:** a single file that holds both the PC's people and the server's people (they remain separate databases
with identical structure); automatic sign-in sync between a PC and the server (a person has one password per install unless they are
migrated); the option to avoid the extra login-path work this change causes on the server.

**What they keep:** one admin screen, one set of rules for passwords, expiry, notes, grants and two-factor, one audit format, and a PC that
works with no gateway.

## 6. Migration and rollback without forcing resets

**Hashes.** Both stores hash with `access_core.hash_password(password, salt, n)` and store `pw_hash`, `pw_salt`, `scrypt_n` per person. Copy
the three columns verbatim. Each person signs in with the same password; no reset, no rehash on migration. (Verified by reading both stores'
calls to `access_core`; **not verified** by a round-trip test, which is phase 1 acceptance.)

**TOTP.** The base32 secrets are algorithm-compatible, but the *seals* are not. Moving requires a process that can open the source seal and
write the target seal. For the same-machine case, a one-shot migration is run in the account that owns the source (owner for `identity.db`),
which exports secrets to a bundle protected by a passphrase the owner types; the target side (gateway CLI, running as the service account)
imports and reseals under DPAPI. Secrets never touch disk unsealed, are not logged, and the bundle is deleted after import. If the seal cannot be opened,
that person's two-factor is left unmigrated and the report says who must re-enrol; nobody else is affected, and no password is reset.
Recovery codes copy as stored (they are hashed in the identity table; **not verified** whether hashed, check in phase 3).

**People, grants, activity.** By `username`; the target id wins; grants, expiry, notes and `totp_required` copy across; activity and admin audit
rows append to `audit_log`. A username that exists in both with different passwords keeps the **gateway** hash for the server install; that
person's FI password on that install becomes the gateway password (a visible change, communicated, not a reset). The dry-run prints exactly
these conflicts before any write.

**Rollback.**
- Schema changes are additive; reverting the code leaves unused columns.
- Migration copies, never moves: the source file is left in place, opened read-only by a "retired" marker, and not deleted for a retention period.
- A reverse export rebuilds the legacy `identity.db` from the unified file for every field that existed in it (lossless for those fields).
- Each app has a `identity_backend = legacy | unified` setting until the old path is removed in the last phase.
- The runbook step "copy `gateway.db` and `identity.db` before upgrading" is mandatory; the existing pre-upgrade copy tooling
  (`test_backup_snapshot_and_pre_upgrade_copy_unit.py` covers it) is reused. Not verified whether it covers `identity.db`.

## 7. Phased plan, models, usage

Sizes are relative to a 5-hour cycle on a Pro plan. The calibration note says a multi-user plan estimated at 8-11 weeks took 3 cycles, so these
estimates are more likely high than low. **Check `/usage` against them as the work proceeds.** No figure here is a token count.

| Phase | Work | Model / effort | Cycles | Cost drivers | Weight |
|---|---|---|---|---|---|
| 0. Spikes | Round-trip a hash between stores; open each TOTP seal from the other account; list every process that opens each file; confirm recovery-code hashing; confirm planner enforcement absent | Sonnet, medium | 0.3 to 0.5 | Small scripts; Grep over `src/server`, `financial_trends_reporter` | Light |
| 1. Shared library and schema | Unified schema v5 (additive), pluggable `SecretBox`, min-password setting, `mandatory_totp` rule; conformance test suite that runs the same cases against the legacy identity store, the legacy gateway store and the new library | **Opus, high** (login path) | 1 to 1.5 | Reading `identity/store.py` (683 lines) and `gateway/store.py` (605); writing a large parametrised suite | Moderate to heavy |
| 2. Gateway onto the library | Gateway store becomes a thin layer over the shared library; keep `sessions`, `worker_accounts`; epoch check; behaviour-preserving | **Opus, high** | 1.5 to 2 | **Expensive.** `test_gateway_auth_functional.py` and isolation tests repeat test-fix cycles; Playwright journeys (about 15 s each) | Heavy |
| 3. FI and Admin app onto the library, migration tool | Re-point both; migration dry-run, import, reverse export; hand-over bundle for TOTP | Sonnet high; Opus for the sealing/bundle code | 1 to 1.5 | FI `access_routes.py`; `admin_app/routes_users.py` (264 lines); Windows two-account testing (manual) | Moderate |
| 4. Shared features and audit | Expiry, notes, grants and end-sessions on the gateway; audit merge; optional planner-grant gate | Sonnet, medium | 0.5 to 1 | Mostly additive routes and UI; the optional planner gate is behaviour-changing, split it out | Moderate |
| 5. Retire legacy, document | Remove duplicate store code and `identity_backend` flag after a soak; update runbook, security review, architecture diagram (`tools/generate_system_diagram.py`) | Sonnet, low | 0.5 | Docs, diagram regeneration, `fast_gates.py` | Light |

Total: about 4.5 to 6.5 cycles of work, plus real calendar time for the soak between phases 3 and 5.

Expensive steps and how to scope them:
- **Phase 2** is the costly one. Scope it by never opening `app.py` whole (565 lines): Grep the function name, read the region. Run only the gateway
  and isolation test files while iterating; run the full suite once at the end. Do the conformance suite first so each cycle is a diff against green.
- **Phase 1 test suite** can balloon: cap it at the behaviours listed in section 8 and generate the cases from one table.
- **Windows cross-account checks** (phase 0 and 3) are manual and cannot run in CI; budget them separately and skip in CI as the elevated tests do today.
- Do not read `frontend/js` or the huge dashboard files; none of this touches them. Keep new frontend lines in `admin_app/frontend/` (not verified that the
  size ratchet ignores it; the integration design makes the same note).

## 8. Test plan (summary)

1. One parametrised conformance suite: create, sign in, wrong password, lockout and unlock, must-change, disable, expire, last-admin rule (including two concurrent attempts), role change, TOTP enroll, verify, replay of a used step, reset, recovery code, session epoch, audit row for each, run against both legacy stores and the new library.
2. Hash round-trip: hash made by either legacy store verifies in the new library and the other way round.
3. Migration: dry-run report matches the apply result; a re-run is a no-op; a sealed secret that cannot be opened is reported, not guessed.
4. Route-contract test for section 4: the gateway URL map has no settings/process/system routes; the Admin app app refuses non-loopback, proxied and cross-origin requests as before.
5. Gateway admin prefixes remain deny-by-default (existing gate); ordinary users cannot read another person's record.
6. Rollback drill: migrate, reverse-export, open the result with the old code, sign in with the old password.

## 9. Risks and what was not verified

**Risks**

- **R1: login-path change on an internet-facing server whose review is still NO-GO.** The verdict (`multi-user-server-security-review.md`: NO-GO for
  real users until conditions 1, 2, 3 and 6 are met) would have to be re-run over a rewritten store. Mitigation: phase 1 builds the suite before any change,
  phase 2 is behaviour-preserving, and this work should not be scheduled ahead of the open review conditions. It does not make the server safe to expose;
  it does not close any open review item.
- **R2: two timing/throttle implementations merged.** The gateway's hash-slot cap and dummy-hash equaliser must survive the move (`gateway/store.py`); a test asserts them.
- **R3: file permissions** if the shared-file mode (3.3) is used: granting the owner access to `gateway.db` weakens the server's separation. Not the default.
- **R4: password length mismatch.** A 10-character password valid on a PC is below the server's 12; the minimum applies on set, so existing passwords work, but a
  person migrated to the server cannot choose a short one next time. Confirm that the gateway login does not reject short existing passwords (not verified).
- **R5: grants semantics drift.** Adding `app_grants` to the gateway must not turn the implicit planner access into denial for existing users.
- **R6: cost overrun.** If phase 2 repeats test-fix cycles, stop and re-scope rather than extend.
- **R7: remote exposure of local panels** is prevented structurally (section 4); a future "host everything" request would reopen this.

**Not verified**

- Whether any deployed server component other than the gateway reads `identity.db`, and whether FI runs on the server (the integration design makes the same note).
- Whether `identity.db` recovery codes are stored hashed or encrypted, and how a pending enrollment is stored (read `identity/totp.py` only to line 60).
- That DPAPI LocalSystem seals cannot be opened from the owner's account (documented in `secret_box.py`; not tried).
- That `access_core` hashes are byte-identical across the stores in a round-trip (the call shape matches; no test run).
- That the planner has no grant enforcement beyond `src/server/` (Grep there found none; `workers`, `proxy.py` and `launchers.py` were not read in full).
- File ACLs actually applied to `gateway.db` on the installed server; the existing backup tooling's coverage of `identity.db`.
- Nothing in this document was run. No test, build or Playwright run was done; CI is not relevant (docs only).

## 10. Decisions needed from the owner

1. Is the real goal one codebase for the rules (Option C), or literally one file on one machine (Option B, with its TOTP and permission limits)?
2. Should this wait until the NO-GO conditions that already concern the login path are closed, or is it scheduled independently?
3. Same-machine shared-file mode (3.3): wanted at all, or PC and server stay separate files for good?
4. Planner grant as a real gate on the gateway (phase 4, optional): yes or no?
