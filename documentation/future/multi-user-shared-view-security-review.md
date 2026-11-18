# Shared view of Financial Insight: security review (Phase 9, design stage)

Status: draft (design-stage review of multi-user-shared-view-design.md; nothing is built; owner decisions recorded 2026-11-18; the rest of the sign-off checklist in section 9 is open)
Date: 2026-11-18

## Verdict: GO to build 9a-9e behind a default-off flag. This is not a release sign-off.

The design (Option A, a published snapshot served by a separate gateway route table) keeps the property every earlier
isolation review relies on: **the session's own user id selects the worker** (`src/gateway/proxy.py:73,114`). No guest
request reaches a worker, starts one, or names another user's data. The risky parts are new, and the design covers
each one: an account kind that today's gate would forward like any user (F2), the first case of one user's text
rendered in another person's browser (AC-14), and a restore that could bring back revoked shares (F5).

Conditions on building:

1. The gate branch, the proxy refusal and the supervisor refusal land **together in 9a**, before any viewer account can
   be created (controls C1-C3).
2. The text-only rendering test and the CSP check (C24) gate 9c. If the owner later lets existing members be grantees
   (question 1), they become a hard prerequisite of that change.
3. `restore_gateway_db` suspends every share (C16) before `--shared-views` is ever turned on.
4. The slow two-owner, two-viewer module passes, and the owner's elevated run on the installed build includes it
   (section 9).

## 1. Scope and method

Reviewed: multi-user-shared-view-design.md, and the existing code its controls depend on. That code is the gateway gate,
sessions and sign-in (`src/gateway/app.py`, `store.py`, `upstream.py`); forwarding (`proxy.py`); worker lifecycle
(`supervisor.py`, `accounts.py`) and Phase 8's scheduler (`insights_schedule.py`); folder permissions (`acl.py`); archives (`backup_store.py`); the admin console
(`admin_console.py`); FI worker mode, its allow-list and its mount (`financial_trends_reporter/main.py`,
`worker_mode.py`, `worker_allowlist.py`, `src/remote_insights_mount.py`); the desktop grant and percent view
(`src/identity/store.py`, `financial_trends_reporter/access_routes.py`, `percent_view.py`, `projections.py`); and the
planner allow-list (`src/server/remote_allowlist.py`).

Method: code reading of the functions named in each citation, plus one in-process probe of the desktop tab limit
(F1). No Phase 9 product code was written. The separate fix for F1 (owner decision 12) is in the same pull request:
`access_routes.py`, a few lines of the FI page, and one regression test module. Every statement about existing code
cites the file and line read. Line numbers are as of this branch: main at `329d4fe` (after Phase 8, PR #481) plus the
F1 fix. **Not verified** marks what was not read or not run. Controls are identified C1-C38 (section 7), abuse cases
AC-1 to AC-26 (section 6), residual risks R-1 to R-12 (section 8). The test modules named are proposed in the design's
test plan (design section 10); none exists yet unless marked "existing".

Severity is judged for this deployment: about ten mutually untrusted planner users, plus guests, on a public Funnel
listener.

## 2. Findings in the existing code that the design depends on

| Id | Sev | Finding | Evidence | Consequence and action |
|---|---|---|---|---|
| F1 | Medium (desktop remote listener); **fixed in this pull request** | **Tab limits on the desktop were presentation only.** Before the fix, a grant's `views` was read only by `whoami` and by the `/api/view` report; the page hid the other tabs, but their data routes still answered. | Before: the two readers (now `access_routes.py:265,273,358-360`), the page's tab hiding (`financial_trends_reporter/frontend/index.html:1017,1040`), and a test that checked only `whoami` and `/api/view` (`tests/test_insights_grant_gate_functional.py:79-87`). **Reproduced** 2026-11-18 with the test rig: a guest granted `views=["trends"]` got 403 on `POST /api/view` for projections, but 200 on `GET /api/projections`, `/api/live-snapshot` and `/api/realized`. After the fix the same probe gets 403 on all three, and `/api/history` still gets 200. | **Fixed (owner decision 12, moved in scope on 2026-11-18).** `VIEW_ROUTES` maps each tab's routes, and `TAB_FREE_ROUTES` names every other `/api/` rule (`access_routes.py:28-44`). The remote gate refuses a route whose tab a listed grant leaves out. It matches on the routed rule, so other spellings get no data (`access_routes.py:159-172`). The owner's local listener and worker mode are unchanged. When Trends is not granted, the page stops asking for Trends routes and drops the percent toggle, which needs `/api/balances` (`index.html:458,709,1094-1097`). Tests: `tests/test_insights_grant_tab_limit_regression.py` (11 tests, including a contract that every `/api/` rule is classified exactly once). Phase 9 still does not use `views` as an enforcement point: records are built by construction (C18). The percent filter is not affected (`access_routes.py:180-197`). |
| F2 | High if missed (design constraint) | **The gate forwards every active, non-gateway request to a worker with no role or kind check**, and the supervisor starts and provisions a worker, workspace and Windows account for any id. The admin console's create route runs the `user_created` hook. | `app.py:283-300`; `supervisor.py:180-193,214-219,442-450`; `admin_console.py:83-89` | A guest created through today's paths would get a planner. Controls C1-C3, C34 and an **Add viewer** route that skips `user_created`. |
| F3 | Info | Protective headers (`no-store`, `X-Frame-Options`, `no-referrer`, CSP) are added only for gateway-owned paths and a few status codes. Forwarded worker responses carry whatever the worker sets (not verified whether the worker sets `Cache-Control`). | `app.py:171-172,314-324` | Viewer and owner routes must be gateway paths (C25). |
| F4 | Info | FI worker mode has no percent hook; FI error bodies contain exception text, and the mount replaces it only on 5xx. | `main.py:470-472,346-348,356-358`; `access_routes.py:174-178`; `src/remote_insights_mount.py:94-96` | The snapshot builder calls the pure percent functions itself (C19) and never copies an error body (C21). |
| F5 | Medium (for Phase 9) | Restoring `gateway.db` brings back every row as of the archive. The restore writes the archived member to a new file, byte for byte; P7-O12 already notes that deleted or disabled users come back. | `backup_store.py:419-442`; `multi-user-server-security-review.md`, open item P7-O12 | Revoked shares would come back. Control C16. |
| F6 | Low (Medium without C3) | `user_ids()` returns every account, and backups and the supervisor's known ids use it. Phase 8's scheduler keeps every account that is neither disabled nor expired and starts its worker for the update. | `store.py:660-661`; `server.py:302,309,322-323`; `src/gateway/insights_schedule.py:122-125,143` | Viewers would enter per-workspace jobs, and each scheduled pass would ask the supervisor for a viewer's worker. Control C34 (members-only selection); C3 is the backstop. |
| F7 | Low (exists for every account) | No deadline for a new account's first TOTP enrolment: whoever first signs in with the temporary password enrols their own authenticator. | `store.py:265-284` (no deadline set); `app.py:411-413,473-484` | Guests are more likely to receive credentials by email. Control C10 for viewers; recommended for members too. |
| F8 | Info (inherent) | **Percent view is a scale, not secrecy.** Every money number is divided by one constant, today's net worth. The module itself drops share counts and prices because they give the scale back. Non-money keys such as ages and years pass through. | `percent_view.py:52-65,68-83,38-43,15-31` | One known real amount reveals the constant and, with it, every amount. Residual risk R-1; the owner UI says so. |
| F9 | Medium (open item, inherited) | The global login throttle can be triggered by any party (P7-O4). | `multi-user-server-security-review.md`, open item P7-O4 | More account holders (guests) can lock everyone out of sign-in. Residual risk R-4. |

## 3. Assets

| Asset | Why it matters |
|---|---|
| A1. The owner's financial data (plan, FI history, balances, holdings, spending) | The data the share projects; must not leave the grant |
| A2. Record bodies (`<data_root>/shares/<id>.json`) | A projection of A1, readable by a guest |
| A3. Share rows (owner, grantee, scope, expiry, state) | Their integrity is authorization: a forged or resurrected row is unauthorized access |
| A4. Viewer credentials and sessions (password hash, TOTP secret, session tokens) | A viewer session reads A2 |
| A5. Every other user's data | Must stay unreachable from any guest or owner action |
| A6. The gateway's privileges (service account, worker tokens, Windows account secrets) | A viewer path that reaches a worker or the supervisor abuses them |
| A7. Audit and the owner's access log | Accountability; the guest's privacy (address) |

## 4. Actors and trust assumptions

| Actor | Trusted for | Not trusted for |
|---|---|---|
| Gateway service | Everything it already holds | - |
| Admin | Account management (create, disable, reset, delete) | Reading user data: today there is no admin route into a worker's FI (`multi-user-insights-design.md` section 5); Phase 9 keeps that (C30, C11) |
| Owner (member) | Their own data and the choice to share it | Other users' data; the guest's browser (owner text is untrusted there, AC-14) |
| Guest (viewer) | Nothing beyond the records granted to them | Everything else; assumed curious or hostile |
| Other members | Their own data | Any share or viewer they do not own or sponsor |
| Workers | Their own user's workspace (confined, existing) | Anything a worker returns is untrusted input to the gateway (AC-15) |
| Network | - | Everything; TLS ends at Funnel (existing) |

## 5. Trust boundaries

```
Internet --(Funnel :8443)--> [TB1] gateway listener: preflight caps, Host, Origin, Fetch-Metadata (existing)
                                   |
                             [TB2] gate: session -> account kind                         (new branch, C1)
                               /                                   \
                    kind == 'member'                         kind != 'member' (viewer)
             planner and /insights/ (existing)          VIEWER_ALLOWED only (new, C4)
                        |                                          |
     [TB3] proxy -> the session's own worker            gateway viewer routes (C5, C6, C12)
           (worker token, loopback; existing)                      |
                        |                            [TB4] <data_root>/shares/<id>.json (gateway-only ACL, C31)
     owner's worker (owner's Windows account)                      ^
       share-snapshot route --JSON--> [TB5] publisher validates worker output (C18-C23)
                                                                   |
                                     [TB6] guest's browser renders owner-controlled text (C24, C38)
     [TB7] archives and restore carry gateway.db rows (C16, C17)
```

TB5 and TB6 are new kinds of crossing. For the first time on this server, a worker's output is served to a principal
other than its own user, and one user's text is rendered in another person's browser.

STRIDE summary: spoofing AC-2, AC-8, AC-20; tampering AC-11, AC-13, AC-15, AC-19; repudiation C32 (audit);
information disclosure AC-1, AC-3 to AC-7, AC-10, AC-16, AC-18, AC-23; denial of service AC-21; elevation of
privilege AC-3, AC-4, AC-5, AC-12, AC-14.

## 6. Abuse cases

The abuse cases the brief requires come first (AC-1 to AC-11), then the others found while reviewing.

| Id | Abuse case | How it is stopped | Controls | Tests (section 7 has each control's test) |
|---|---|---|---|---|
| AC-1 | **ID guessing.** A guest or a member guesses or iterates share ids (or viewer or owner ids) to read someone else's record | Every query is scoped by the session's user; ids are random 128-bit values and not capabilities; no route takes an owner or viewer id from a guest; one byte-identical 404 for every miss | C5, C6, C7 | `test_gateway_share_routes_functional.py`, `test_multi_user_isolation_shared_view_integration.py` |
| AC-2 | **Replay across sessions.** Guest G2 replays a share id or URL seen in G1's session; a cookie replayed after sign-out or expiry; a record URL replayed after revoke | The grantee comes from the session, so G2's set does not contain G1's share. Session tokens are stored hashed, and sign-out deletes the row (`store.py:153-154,638-640`; `app.py:486-494`). Rotation at each stage (`app.py:424-432`). Authorization is checked on every request | C5, C12; existing session controls | slow module; existing `tests/test_multi_user_isolation_attacks_integration.py` (logout-then-replay) |
| AC-3 | **Guest reaches planner routes** (`/api/plans`, uploads, builds, any planner path, including encoded, case-changed, `//` and trailing-slash variants) | A positive table at the gate: anything not in `VIEWER_ALLOWED` is refused before the forward line, so a path that matches no gateway route is refused rather than forwarded. The proxy and supervisor refuse a viewer as a second and third layer | C1-C4 | `test_gateway_viewer_gate_contract.py` |
| AC-4 | **Guest reaches `/insights/` of any worker** (none of their own exists; the owner's by guessing) | Same as AC-3; a viewer has no worker, and the supervisor refuses to create one | C1-C3 | contract test; slow module |
| AC-5 | **Guest reaches the admin console or admin API** | The viewer branch refuses first; the admin prefix guard still applies (`app.py:33-35,153-154,289-290`, existing `tests/test_gateway_admin_guard_contract.py`); a viewer cannot be an admin (the `CHECK` and `set_role` refusal) | C1, C4, and the role `CHECK` in C34's migration | contract test; `test_gateway_share_store_unit.py` |
| AC-6 | **Link leakage.** A share URL is forwarded by email, logged, cached or sent in a Referer | No secret in any URL (requirement R10); an id is useless without the grantee's session; `no-referrer`; the audit holds ids only | C5, C7, C25, C32 | slow module (URL with another session and with none) |
| AC-7 | **Cache and history leakage.** A shared computer, Back after sign-out, browser or intermediate caches | `no-store` on every viewer and owner response; `Clear-Site-Data: "cache"` on viewer sign-out; the page clears its content on sign-out and when a share becomes unavailable; short viewer sessions | C9, C25, C26 | `test_gateway_share_routes_functional.py`; `shared-view.spec.js` |
| AC-8 | **TOTP bypass.** A password-only (pending) session reaches records; enrolment is skipped; an admin reset is used to take over; first-login hijack | The existing stage gate (`app.py:268-275`) runs before the viewer branch; must-change runs first too (`app.py:285-288`); enrol-by deadline; an admin reset suspends the viewer's shares; break-glass works only on admin accounts (`multi-user-server-gateway-design.md`, "Admins") | C8, C10, C11 | `test_gateway_viewer_session_functional.py` |
| AC-9 | **Revocation lag.** Revoke while the guest is signed in; a cached authorization; an open tab keeps showing data; a publish in flight brings the record back | No authorization cache: every viewer request re-reads the row and the owner's state. Revoke deletes the body after the commit. The publish commit is conditional and discards its file when it loses. The open tab clears within 60 seconds (cosmetic) | C12, C13, C15 | routes, publish and lifecycle tests; e2e "revoke then reload" |
| AC-10 | **Enumeration of grants.** A guest learns that other shares, owners or guests exist; an owner learns another owner's viewers; differences in errors or timing | Each party lists only its own rows; the sponsor rule limits an owner's grantee choices to their own viewers; one byte-identical 404; only admins create accounts, so only admins can probe usernames (`store.py:282-283` raises "username in use" on the admin path). Timing: one indexed lookup whether or not the id exists (not measured, R-8) | C5, C6, C29 | routes tests |
| AC-11 | **Snapshot staleness shows revoked data.** An old body served after revoke; a narrowed scope still serves the wider old body; a restored file or database re-serves; a failed delete leaves a file | Body bound to its row by digest and revision; a scope change deletes the body before republishing; revoke and expiry delete; an hourly sweep removes orphans; bodies are not archived; a restored `gateway.db` suspends every share | C13-C17 | lifecycle, publish and backup tests |
| AC-12 | **A viewer becomes a planner user** (workspace, Windows account, worker) through lifecycle hooks, console create, Phase 8's scheduler, a role change or a gate bug | The gate branch, proxy and supervisor refusals; **Add viewer** never runs `user_created`; per-workspace jobs use `member_ids()` and the scheduler selects members only; the `CHECK` and the `set_role` refusal | C1-C3, C34 | contract test (fake supervisor); slow module "no worker or workspace for a viewer" |
| AC-13 | **Scope widening by request.** A guest adds `?views=`, `?money_view=dollars`, `?scope=` or headers | Viewer routes take no parameters except the id; the body is a fixed stored file; the scope comes only from the owner's row | C5, C18 | routes test "query and headers change nothing" |
| AC-14 | **Owner-to-guest script injection** through account, merchant, category or plan names, or the title | Strings normalised at publish; rendered as text only; gateway CSP `default-src 'self'` with no inline script (`app.py:40`); `nosniff` (`app.py:316`). If members later become grantees, injected script would run in a planner session, so C24 stays a hard gate | C24, C38 | `gateway_viewer_render.test.mjs`; e2e fails on any CSP violation |
| AC-15 | **A compromised or buggy owner worker returns hostile output** (huge, extra tabs, markup, wrong share id) | The gateway treats worker output as untrusted: status, type, size cap, exact schema, keys within the scope, leak re-check. The worker can only see its owner's workspace, so it cannot add another user's data | C20, C24, C33 | publish tests |
| AC-16 | **Scale recovery from percent data** | Not fully preventable. Share counts and prices are dropped (`percent_view.py:38-43,140-142`); the owner is warned | C19 | residual R-1 |
| AC-17 | **Wrong plan published** (plan switched in another tab, or the scheduler runs while a what-if plan is active) | `expected_plan_id` on create; the worker refuses unless the active plan is the share's plan | C22 | snapshot and publish tests |
| AC-18 | **Error or path leakage inside a record** | Failing routes are marked unavailable, and their bodies are never copied; the mount scrubs JSON (`remote_insights_mount.py:94-96`) | C21 | snapshot test |
| AC-19 | **Restore brings back revoked shares or old grants** | Restored `gateway.db` has every share suspended; bodies are not restored | C16, C17 | backup tests |
| AC-20 | **An admin impersonates a guest** (resets the password or TOTP, then signs in as the viewer) | The reset suspends that viewer's shares until the owner enables them; audited. An administrator with operating-system access can read files, as today for plans (R-9) | C11, C32 | session test |
| AC-21 | **Guest-driven resource abuse** (waking the owner's worker, publish floods, sign-in lockout) | Viewers never reach a worker; only owners publish, with rate and concurrency limits; viewer bodies are capped at 32 KiB (`app.py:60,293`). The global throttle DoS (P7-O4) is inherited | C1-C3, C33 | routes test; residual R-4 |
| AC-22 | **CSRF or clickjacking against owner routes** | The existing gate: Origin, `X-CSRF-Token`, Fetch-Metadata and body type on every unsafe method (`app.py:243-267`); `frame-ancestors 'none'` and `X-Frame-Options: DENY` | C25, C28 | routes test |
| AC-23 | **Another user's worker account reads the shares folder** | Gateway-only ACL; `acl check` walks the folder and fails on any worker-readable entry | C31 | backup and ACL test; the owner's elevated run |
| AC-24 | **Audit or logs leak amounts or content** | Events carry ids, revisions and byte counts only; details at most 300 characters (`store.py:42,230-235`) | C32 | lifecycle test |
| AC-25 | **Cross-owner confusion.** Owner B's share granted to a viewer sponsored by owner A | Store rule: the grantee's sponsor must be the owner; owner queries list only sponsored viewers | C29 | routes test |
| AC-26 | **A deleted owner's data lingers** | Shares cascade, sponsored viewers are deleted, bodies are purged in the delete lifecycle (`supervisor.py:460-472`), and the sweep is the backstop | C13, C36 | lifecycle test |

## 7. Controls and their tests

Test modules are those proposed in the design's test plan (design section 10). Names after `::` are the proposed test
functions. Writing them first is part of each phase's exit criteria.

| Id | Control | Where (design section) | Named test |
|---|---|---|---|
| C1 | Gate branch: any kind other than exactly `member` is answered only by `VIEWER_ALLOWED`; placed after the stage and must-change checks, before the admin check and the forward (`app.py:268-300`) | 5.1, 5.6 | `test_gateway_viewer_gate_contract.py::test_every_route_outside_the_table_is_refused_for_a_viewer`, `::test_unknown_kind_is_treated_as_a_viewer`, `::test_no_upstream_call_for_any_viewer_request` |
| C2 | Proxy refuses an identity whose kind is not `member` | 5.1 | `test_gateway_viewer_gate_contract.py::test_proxy_refuses_a_viewer_identity` |
| C3 | Supervisor refuses non-members in `endpoint`, `_start` and `user_created` | 5.1 | `test_gateway_viewer_gate_contract.py::test_supervisor_never_provisions_a_viewer`; `test_multi_user_isolation_shared_view_integration.py::test_no_worker_or_workspace_for_a_viewer` |
| C4 | `VIEWER_ALLOWED` is a reviewed literal, derived from no other table | 5.6 | `test_gateway_viewer_gate_contract.py::test_viewer_table_is_exactly_the_reviewed_set` |
| C5 | Session-scoped selection: viewer queries include `grantee_user_id = <session user>`, owner queries `owner_user_id = <session user>` | 5.6, 5.8 | `test_gateway_share_routes_functional.py::test_other_guests_share_id_gives_the_uniform_404`, `::test_owner_cannot_reach_another_owners_share`; slow `::test_id_guessing_and_replay_across_sessions` |
| C6 | One byte-identical not-found response for unknown, malformed, revoked, expired and other people's ids | 5.6, 5.8 | `test_gateway_share_routes_functional.py::test_not_available_responses_are_byte_identical` |
| C7 | Share ids are `secrets.token_hex(16)`, never sequential, never capabilities | 5.2 | `test_gateway_share_store_unit.py::test_share_ids_are_random_hex_and_never_reused` |
| C8 | Mandatory TOTP and the existing stages apply to viewers | 5.7 | `test_gateway_viewer_session_functional.py::test_pending_viewer_reaches_only_the_second_factor`, `::test_viewer_must_change_password_first` |
| C9 | Viewer session limits: idle 10 minutes, absolute 2 hours | 5.7 | `test_gateway_viewer_session_functional.py::test_viewer_idle_and_absolute_limits` |
| C10 | Enrol-by deadline of 72 hours for viewers | 5.7 | `test_gateway_viewer_session_functional.py::test_viewer_not_enrolled_within_the_deadline_is_locked` |
| C11 | An admin reset of a viewer's password or TOTP suspends their shares | 5.7 | `test_gateway_viewer_session_functional.py::test_admin_reset_suspends_the_viewers_shares` |
| C12 | Authorization on every request (no cache): row state, expiry, owner usable, viewer usable | 5.6, 7 | `test_gateway_share_routes_functional.py::test_revoke_takes_effect_on_the_next_request`, `::test_expired_share_is_not_served`; `test_gateway_share_lifecycle_functional.py::test_disabled_owner_serves_nothing` |
| C13 | Body deleted on revoke, scope change and expiry; hourly orphan sweep | 5.5, 7 | `test_gateway_share_lifecycle_functional.py::test_revoke_deletes_the_body`, `::test_scope_change_deletes_the_old_body_before_republishing`, `::test_sweep_removes_orphans` |
| C14 | Body bound to its row by SHA-256, `share_id` and `scope_rev` | 5.5 | `test_gateway_share_publish_functional.py::test_body_not_matching_its_row_is_never_served` |
| C15 | Conditional publish commit (`state = 'active'` and unchanged `scope_rev`); the losing file is deleted | 5.4 | `test_gateway_share_publish_functional.py::test_revoke_during_publish_leaves_nothing`, `::test_scope_change_during_publish_discards_the_wider_result` |
| C16 | `restore_gateway_db` suspends every share in the file it writes | 8 | `test_gateway_share_backup_functional.py::test_restored_gateway_db_has_every_share_suspended` |
| C17 | Bodies are not archived (default) | 8 | `test_gateway_share_backup_functional.py::test_archive_holds_rows_but_no_bodies` |
| C18 | Projection by construction: only the granted views' routes are rendered; never-included routes are absent | 5.3 | `test_insights_share_snapshot_functional.py::test_record_holds_only_the_granted_views`, `::test_transactions_and_settings_are_never_included` |
| C19 | The percent pipeline is the desktop's (`strip_detail`, `scale_payload`, the same basis) plus a leak check in the worker and again in the gateway | 5.3, 5.4 | `test_insights_share_snapshot_functional.py::test_percent_record_equals_the_desktop_percent_bodies`, `::test_leak_fails_the_publish`; `test_gateway_share_publish_functional.py::test_gateway_rechecks_for_money_leaks` |
| C20 | Worker output validation: 200, JSON, size cap, exact schema, keys within the scope | 5.4 | `test_gateway_share_publish_functional.py::test_output_outside_the_schema_or_scope_is_refused`, `::test_oversized_output_is_refused` |
| C21 | No error text or server path in a record | 5.4 | `test_insights_share_snapshot_functional.py::test_a_failing_route_is_marked_unavailable_without_its_error_text`, `::test_record_holds_no_server_path` |
| C22 | Active-plan binding (`expected_plan_id`; refresh only when the share's plan is active) | 5.4, 5.8 | `test_insights_share_snapshot_functional.py::test_other_active_plan_is_refused`; `test_gateway_share_publish_functional.py::test_plan_switched_in_another_tab_is_not_published` |
| C23 | The snapshot route is reachable only from the gateway (browser block in the proxy) | 5.4 | `test_gateway_share_publish_functional.py::test_browser_cannot_call_the_snapshot_route` |
| C24 | Text-only rendering, string normalisation at publish, gateway CSP | 5.4, 6.1 | `gateway_viewer_render.test.mjs` ("hostile strings render as text"); `test_gateway_share_publish_functional.py::test_strings_are_normalised`; `shared-view.spec.js` (fails on any CSP violation) |
| C25 | `/api/viewer/` and `/api/share/` are gateway paths: `no-store`, `X-Frame-Options: DENY`, `no-referrer`, CSP | 5.6 | `test_gateway_share_routes_functional.py::test_viewer_and_owner_responses_carry_no_store_and_csp` |
| C26 | Viewer sign-out sends `Clear-Site-Data: "cache"`; the page clears its content; Back shows nothing | 5.6, 6.1 | `test_gateway_viewer_session_functional.py::test_viewer_logout_clears_the_cache`; `shared-view.spec.js` ("Back after sign-out shows no data") |
| C27 | The status poll does not extend the session | 5.6 | `test_gateway_viewer_session_functional.py::test_status_poll_does_not_keep_the_session_alive` |
| C28 | CSRF and Origin on owner writes (the existing gate) | 5.8 | `test_gateway_share_routes_functional.py::test_owner_writes_need_csrf_and_origin` |
| C29 | Sponsor rule: an owner lists and grants only viewers they sponsor | 5.2, 5.8 | `test_gateway_share_routes_functional.py::test_owner_cannot_grant_or_list_viewers_they_do_not_sponsor` |
| C30 | Admins have no route that creates, reads or changes shares; the console shows counts only | 6.3 | `test_gateway_share_routes_functional.py::test_admin_cannot_read_or_create_shares` |
| C31 | The shares folder is gateway-only and walked by `acl check` | 5.5 | `test_gateway_share_backup_functional.py::test_acl_check_reports_a_worker_readable_shares_folder` (Windows-only parts skip elsewhere); the owner's elevated run |
| C32 | Audit events and the access log hold ids, revisions and counts only | 5.9 | `test_gateway_share_lifecycle_functional.py::test_audit_and_access_log_hold_ids_only` |
| C33 | Limits: shares per owner, viewers per sponsor, one publish per share per minute, two concurrent publishes, 32 KiB viewer bodies | 5.2, 5.4, 5.6 | `test_gateway_share_routes_functional.py::test_limits_refuse_with_409`, `::test_viewer_body_cap_is_the_gateway_cap` |
| C34 | Migration step 4 (kind and role `CHECK`, sponsor); `member_ids()` for per-workspace jobs; Phase 8's `eligible_users` selects members only | 5.1, 5.2 | `test_gateway_share_store_unit.py::test_migration_keeps_every_row_as_a_member`, `::test_viewer_cannot_be_made_admin`, `::test_member_ids_exclude_viewers`; `test_gateway_viewer_gate_contract.py::test_insights_scheduler_never_selects_a_viewer` |
| C35 | Plan delete revokes that plan's shares | 7 | `test_gateway_share_lifecycle_functional.py::test_deleting_the_plan_revokes_its_shares` |
| C36 | Owner deletion removes shares, sponsored viewers and bodies | 7 | `test_gateway_share_lifecycle_functional.py::test_deleting_the_owner_removes_shares_viewers_and_bodies` |
| C37 | With `--shared-views` off, every share and viewer route returns 404 | 5.10 | `test_gateway_share_lifecycle_functional.py::test_flag_off_serves_nothing` |
| C38 | The viewer page fetches only its three routes | 6.1 | `gateway_viewer_render.test.mjs` ("the page fetches only its three routes") |

Existing tests that must stay green: `tests/test_gateway_insights_schedule_unit.py` (Phase 8; 9a changes its user
selection, so it gains a viewer case rather than losing one), `tests/test_multi_user_isolation_integration.py`,
`tests/test_multi_user_isolation_attacks_integration.py`, `tests/test_multi_user_isolation_routes_integration.py`,
`tests/test_multi_user_isolation_insights_integration.py`, `tests/test_gateway_admin_guard_contract.py`,
`tests/test_gateway_insights_proxy_functional.py`, `tests/test_insights_worker_mount_functional.py`,
`tests/test_insights_worker_mount_allowlist_regression.py`, `tests/test_remote_mode_contract.py`,
`tests/test_trends_percent_view_unit.py`, `tests/test_trends_percent_view_functional.py`,
`tests/test_trends_percent_view_leak_guard_regression.py`, `tests/test_realized_percent_view_unit.py`,
`tests/test_gateway_backup_store_functional.py` and `tests/test_gateway_backup_multi_plan_functional.py`.

## 8. Residual risks (accepted or for the owner to accept)

| Id | Risk | Why it remains | Mitigation in place |
|---|---|---|---|
| R-1 | Anyone who knows one real amount can recover every amount from a percent record (F8) | Percent view divides by one constant; this is inherent | The owner is told plainly; share counts and prices are dropped; the dollars view is opt-in |
| R-2 | A guest keeps what they saw (screenshot, print, copy); revocation cannot recall it | Inherent to showing data | No export in v1; expiry; the owner is told |
| R-3 | Non-money personal data passes through: account, category and merchant names (dollars view), dates, ages, plan years | `NON_MONEY_KEYS` (`percent_view.py:15-31`); names are not money | Visible in the owner's preview; owner decision 3b can replace names |
| R-4 | Global sign-in throttle DoS by any account holder, guests included (P7-O4, open) | Not fixed by this work | Admin can disable an abusive viewer; P7-O4's proposed fix covers it |
| R-5 | First-login hijack window for members | The deadline (C10) is proposed for viewers only | Recommend extending C10 to members (owner) |
| R-6 | Old but valid data misread as current | A copy by design (Q2) | "As of" always shown; badge after 7 days; refresh |
| R-7 | Back-forward cache behaviour after sign-out differs between browsers | Playwright covers Chromium only; not verified elsewhere | `no-store`, `Clear-Site-Data`, the page clears its content |
| R-8 | Timing differences between "exists for someone else" and "does not exist" | Not measured | Single indexed lookup either way; random ids |
| R-9 | An administrator with operating-system access can read bodies and plans | Same as today for plan files | ACLs; archives encrypted; audit |
| R-10 | The guest page shares the gateway's origin with the planner | A second origin was rejected for FI (`multi-user-insights-design.md` section 3, option D) | Viewer-only grantees (Q1 default); text-only rendering; CSP. Revisit if members become grantees |
| R-11 | Installed-build ACL behaviour for the new folder | Only the owner's elevated run can show it | `acl check` walks the folder (C31) |
| R-12 | Archives already hold the owner's full plan and FI log | Not archiving bodies does not make archives less sensitive | Archives are AES-256-GCM encrypted (`multi-user-server-security-review.md`, "Reviewed and found sound") |

## 9. Sign-off checklist

Design sign-off (before 9a starts):

- [x] The owner answers Q1-Q5 in the design's section 3, or accepts the recommended defaults, plus decisions 6-13
      (design section 13). Done 2026-11-18: every recommended default except a 90-day default share expiry (Q4).
      No answer changes a control in this review; the longer default only lengthens how long a forgotten share stays
      open before it expires.
- [ ] The owner accepts residual risks R-1 to R-12, or asks for changes.
- [x] The owner schedules or declines the separate desktop fix for F1 (decision 12). Done 2026-11-18: fixed in this
      pull request (first scheduled as a separate fix, then moved in scope the same day);
      `tests/test_insights_grant_tab_limit_regression.py` passes.

Release sign-off (after 9e; `--shared-views` stays off until every box is ticked):

- [ ] Every test named in section 7 exists and passes. `VIEWER_ALLOWED` has been reviewed line by line against the
      design's table (C4).
- [ ] The existing tests listed at the end of section 7 pass; `python tools/fast_gates.py` passes; the system diagram
      is regenerated.
- [ ] `shared-view.spec.js` passes with zero CSP violations.
- [ ] The slow module `test_multi_user_isolation_shared_view_integration.py` passes (two owners, two viewers, real
      gateway and workers).
- [ ] The owner's elevated run on the installed build: `acl check` covers `<data_root>/shares` and reports nothing; the
      isolation modules, including the new one, pass in per-account mode (`tools/run_isolation_on_installed_build.ps1`
      gains the new module).
- [ ] Migration rehearsal: a copy of the live version 3 `gateway.db` migrates to version 4, every account reads as
      `member`, and sign-in works. Rollback is the pre-upgrade copy (an old gateway refuses version 4).
- [ ] Restore drill: restoring `gateway.db` into a scratch root shows every share as "Suspended: restored".
- [ ] Runbook lines added: the flag, backup scope, restore drill.
- [ ] Measurements recorded: record size and publish time on a real plan; guest page load time.
- [ ] This review is updated with the results (what ran, what did not), then the owner changes its status.

## 10. Not verified here

- How the code behaves after the change: nothing is built; every control above is a design commitment until its test
  exists and passes.
- Whether FI's chart modules render from a data object without `index.html`'s inline script (design 9c step 0).
- Whether `financial_trends_reporter.percent_view` imports cleanly inside the gateway (`percent_view.py:13` imports
  `balance_series`).
- SQLite acceptance of the cross-column `CHECK` in `ADD COLUMN` and the self-referencing foreign key added by
  `ALTER TABLE` (the 9a migration test proves it).
- Whether worker responses set `Cache-Control` (F3).
- Browser back-forward cache behaviour and `Clear-Site-Data` through Funnel (R-7).
- Timing side channels (R-8).
- Installed-build, per-account ACLs (R-11).
- `admin_app/frontend/users.js` (not read).
- The F1 probe ran in process on Linux with the desktop test rig, not on the owner's machine. It shows the code path,
  which has no platform-specific branch in the gate it exercises (`access_routes.py:114-162`).
- The F1 fix's page change was checked once in Chromium (Playwright) against the rig's own listeners. That check is
  throwaway, not a committed test. A Projections-only guest with `money_view` both saw only the Projections tab, no
  percent toggle and no Trends requests; the owner's page was unchanged. Not run on the owner's machine, through the
  real remote listener's Funnel address, or in other browsers.
