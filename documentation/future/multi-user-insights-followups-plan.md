# Financial Insight follow-ups: build plan (Phases 7, 8, 9)

Status: draft, nothing started
Date: 2026-11-18

Scope: the three optional items left open by `multi-user-insights-design.md` (sections 4.6, 4.7, 10, 11). Each is
independent. Recommended order: **7, then 8, then 9 design**. Phase 9 produces a design and a security review only; no
code until the owner signs it off.

| # | Follow-up | Gap today | Deliverable | Model / effort | Size |
|---|---|---|---|---|---|
| 7 | Back up the history log | A plan's FI log is not in the archive. Balances rebuild from the plan; the log cannot be rebuilt | Archive members, restore, tests, runbook line | Opus 5.5, high | Moderate |
| 8 | Scheduled per-user update | A log starts at first open and gains one entry per day the user opens FI | Gateway scheduler thread, audit event, admin status, tests | Sonnet 5.5, high | Moderate |
| 9 | Shared view for guests/advisors | Nobody but the owner can see a plan | Design doc + security review (no code) | Opus 5.5, max, design only | Heavy, but one document |

Token discipline for all three: read only the functions named below; never read `live_snapshot.py`, `dashboard.js` or
`admin.js` whole; run each slow test once and re-run only failures; log pytest to a scratch file (`-v -rfE`).
Phases 7 and 8 touch different files and can run as two parallel sub-agents on separate branches. Phase 9 is
single-threaded research and writing.

---

## Phase 7. Back up each plan's history log

### Facts (from the code)

- Archive writer: `src/gateway/backup_store.py` `write_archive` (lines 116-182). `FORMAT = 2`. Members are matched by
  `_MEMBER_RE` (line 41), `^users/<uid>/(app\.db|<plan file pattern>)$`. Anything else is never written back on
  restore, whoever signed the archive.
- Restore: `restore_user` (line 232) extracts to a staging folder, moves live files aside as
  `*.before-restore-<stamp>`, swaps in the restored files, rolls back on error. A format 2 archive also moves aside live
  plan files it does not hold (`_LIVE_PLAN_GLOBS`).
- The log lives at `<workspace>/output/plans/<plan_id>/insights/financial_trends_log.jsonl`
  (`multi-user-insights-design.md`, data location row). It is JSON lines, not SQLite, so `sqlite_bytes` does not apply.
- The same folder holds the balances SQLite (reproducible), pass-through decisions and display preferences.

### Design

1. **Format 3.** `FORMAT = 3`. Restore keeps `>= 2` as "full set" semantics, so v1 and v2 archives still restore
   exactly as now. Add a new, separately named member family, never a loosened `_MEMBER_RE`:
   `users/<uid>/insights/<plan_id>/<file>` where `<plan_id>` matches `[0-9a-f]{32}` (the same shape as
   `plans/<32 hex>.rpx`) or the literal workspace-plan id, and `<file>` is from a fixed allowlist.
2. **Allowlist, not glob-everything.** Back up the log. Decision for the owner (below): also the pass-through decisions
   file and the display-preferences file, since they are small and also not reproducible. Never the balances SQLite.
3. **Consistent read.** The log is appended while a worker may be running. Read the file once into memory, truncate the
   copy at the last complete line, and parse-check every kept line. Step 0 confirms whether `trends_log.append_or_replace_entry`
   rewrites atomically; if it does, a plain read is already consistent.
4. **Same guards as plan files.** Per file: `fsguard.has_reparse_point`, regular file only, name matched by the strict
   regex, size cap (for example 64 MB; a log over the cap is skipped and reported in `errors`, never truncated silently).
5. **Restore.** Extend `restore_user` so the staging area and the move-aside step cover `insights/`. For a format 3
   archive, live insight files not in the archive are moved aside too (same rule as plan files). A format 2 archive
   leaves the user's live logs untouched. Add the log paths to the "worker is running" guard's scope (already covers the
   workspace).
6. **Delete plan** already removes `output/plans/<id>/`; archives made earlier still hold that log, which is correct
   for a restore.
7. **Manifest** lists the new members; `verify_archive` already authenticates the whole stream, so no new crypto.

### Steps

0. Confirm `trends_log` write atomicity and the actual filenames in the insights folder (Grep `trends_log.py`,
   `passthrough_decisions.py`, `account_registry.py`; about 150 lines read).
1. Add the member regex, allowlist, bytes reader and size cap in `backup_store.py`; bump `FORMAT`.
2. Extend `write_archive` per user: enumerate `output/plans/*/insights/<allowed>` with guards, add members.
3. Extend `restore_user`: staging, move-aside, rollback.
4. Tests in the existing backup test module: round trip (write, restore, bytes equal); v2 archive restore unchanged;
   hostile member names (traversal, wrong plan id shape, other user's id, oversize) are ignored on restore; symlink or
   reparse log is skipped and reported; torn last line is dropped; restore into another user is refused.
5. Runbook: one line in `multi-user-server-operations-runbook.md` (what is and is not backed up), plus a restore drill
   step. Update `multi-user-insights-design.md` section 4.7 and the "not backed up in v1" rows.
6. Run `tools/fast_gates.py` and the backup tests once.

### Exit criteria

Round-trip test passes; a v2 archive restores byte-identically to today; every hostile-name test is rejected; restore
of user A never touches user B; fast gates green.

### Risks

| Risk | Mitigation |
|---|---|
| Widening the restore allowlist is the dangerous part | One new strict pattern, allowlisted filenames, tests for each rejection |
| Archive size grows with log age | Size cap with an error line; log growth is one entry per day |
| Restoring over a newer log loses newer days | Existing move-aside keeps the current files as `.before-restore-<stamp>` |

---

## Phase 8. Scheduled per-user update

### Facts

- The desktop app uses a 5 pm weekday Task Scheduler job. The server has none.
- An update runs **inside the user's worker**: `trends_job.run(..., worker=True)` opens the plan read-only and refreshes
  prices through `pricing_service`. The existing route is `POST /api/run-now` under `/insights/`, already on the worker
  allow-list.
- Workers start on demand and stop when idle (`Supervisor.endpoint`, `release`, `stop`, `monitor_once`). The build queue
  (`BuildQueue`, concurrency 2) bounds heavy work. `BackupScheduler` is the existing pattern for a gateway thread
  (`src/gateway/backups.py`: `_loop`, `_due`, `start`, `stop`).
- Insights auto-update on open already runs when the newest entry is older than the last NYSE session; the scheduled
  job must reuse that same "is it due" rule so the two never double-run.

### Design

1. **`InsightsScheduler`** in a new `src/gateway/insights_schedule.py`, modeled on `BackupScheduler`: a daemon thread,
   a 60 s check, injected clock, `last_result()` for the admin page. Started only when `--insights` and a new flag
   `--insights-schedule <HH:MM>` (gateway local time; default off) are set.
2. **Selection.** Each weekday after the cutoff, for every active, non-disabled user with insights access whose newest
   log entry predates the last NYSE session. Reuse the NYSE-session helper the auto-update uses; do not add a second
   calendar.
3. **Execution, one user at a time.** Ask the supervisor for the user's endpoint (this starts a worker if needed),
   `call_worker` the run-now POST with the worker token, poll the existing status route, then `supervisor.release` if no
   interactive session is attached. One at a time bounds memory and the shared price-provider rate limit. A user with a
   build in flight (`Supervisor.build_busy`) is skipped and retried on the next pass.
4. **Failure.** Record `{user_id, ok, reason}` in memory and as one audit event per run (`insights_scheduled_update`,
   counts and user ids only, never amounts). No retry storm: a failed user is retried at most once per pass, passes are
   hourly until the window closes (cutoff + 6 h), then give up until tomorrow.
5. **No backfill.** A day the server was off stays a gap in the per-day detail; net worth depth still comes from the
   Monarch balances. State this in the runbook.
6. **Opt-in granularity.** Global flag only in v1. A per-user switch would need a `gateway.db` migration; defer unless the
   owner wants it (decision below).
7. **Admin console.** One status line in the existing Operations page: last run time, users updated, users failed. Read
   from `last_result()`; no new route family.
8. **Security.** The scheduler runs in the gateway, which already holds each worker token. It sends no user data off the
   machine, adds no new inbound path, and the worker enforces read-only plan access as for any update.

### Steps

0. Confirm how `call_worker` authenticates to the FI mount and which status route `run-now` exposes (Grep
   `financial_trends_reporter/main.py:442` and `worker_allowlist.py`); confirm the due rule's function name.
1. Write `insights_schedule.py` with injectable clock, supervisor and "is due" predicate (pure function, unit tested).
2. Wire the flag in `server.py` (start and stop beside the backup scheduler) and `GatewayConfig`.
3. Audit event and admin status line.
4. Tests (fast, fakes for supervisor and `call_worker`): picks only due users; skips disabled users and weekends;
   one at a time; skips build-busy user; failure recorded and not retried inside the same pass; stops cleanly; does not
   run when the flag is off. One slow integration run with a real worker, run once.
5. Runbook and design-doc updates; `tools/fast_gates.py`.

### Exit criteria

With the flag on and a fake clock past the cutoff, every due user gets exactly one new log entry and a worker started
only for that purpose is released; with the flag off nothing changes; no second entry when a user opens FI the same day.

### Risks

| Risk | Mitigation |
|---|---|
| Many users start workers at once and exhaust memory | Serial execution; optional cap on users per pass |
| Price provider rate limit | Serial execution; one price refresh per user, as for a manual update |
| Double update (auto-on-open plus schedule) | Shared "is due" predicate |
| Scheduler outlives a gateway stop | `stop()` joins with a timeout, as `BackupScheduler` does |

---

## Phase 9. Shared view for guests and advisors (design and security review only)

This is the only item that crosses the isolation boundary. The multi-plan design deliberately keeps one user from
reaching another's workspace (`multi-user-multiple-plans-design.md`, decision 2; `multi-user-server-security-review.md`).
Do **not** write code until the owner approves the design and the review.

### Deliverables

1. `multi-user-shared-view-design.md` (to be created in this folder): requirements, options, recommendation, data model, UI,
   lifecycle, test plan, phase plan.
2. `multi-user-shared-view-security-review.md` (to be created in this folder): threat model, abuse cases, controls mapped to tests,
   residual risk, sign-off checklist.

### Questions the design must answer first (ask the owner)

1. Who are the viewers: other server users, or new low-privilege guest accounts, or both?
2. Is the view a live look at the current plan, or a published point-in-time copy?
3. What may a guest see: all FI tabs, a percent-only view, or a chosen set of tabs?
4. Can the owner revoke at once, set an expiry, and see who looked and when?
5. Is download or export ever allowed?

### Options to evaluate

| Option | Idea | Isolation | Assessment |
|---|---|---|---|
| A. Published snapshot (recommended) | The owner's own worker renders a read-only snapshot of the chosen view into a share record owned by the gateway. A guest session is served that record by a small viewer. The guest never gets a worker on the owner's workspace | Boundary holds: guest code path never opens the owner's plan or worker | Smallest blast radius; view is as fresh as the last publish (could be refreshed by Phase 8's scheduler) |
| B. Live read through the owner's worker | The gateway proxies a guest to the owner's worker with a read-only, scoped grant | Boundary crossed; owner worker must enforce per-guest scope | Fresh data, but every FI route needs per-viewer enforcement; highest risk |
| C. Export a file | Owner sends a PDF or page | None needed | Not a shared view; listed only as the fallback |

### What the design should reuse

The desktop FI already has a grant with `money_view` and `views` (percent view and per-tab limits;
`src/identity/store.py:58`, `financial_trends_reporter/projections.py`, `percent_view.py`). Option A reuses those
projections so a guest record is computed through the same percent/tab filter the desktop remote view already trusts.
The gateway already has accounts, TOTP, throttling, audit, session expiry and `access_expires` (admin console phase 2);
a guest is a gateway account with a `role` limited to the viewer and no planner access.

### Security review must cover

- Server-side projection: the guest record is built by the owner's worker and contains only what the grant permits;
  no filtering is left to the client.
- Authorization: guest session can read only records granted to that account id; no identifier in the request selects
  a record (same rule as the isolation design: session to record, never request to record). Test with two owners and two
  guests, including ID guessing and replay across sessions.
- Authentication: TOTP required for guests; short idle and absolute expiry; throttling as for users.
- Revocation and expiry: owner revoke takes effect on the next request; expired grants return the same response as
  none (no existence leak); published records are deleted on revoke.
- Data at rest: share records live under the gateway's locked data root, included in backups (Phase 7 pattern) and
  covered by the ACL `check`.
- Audit: grant created, viewed, revoked and expired, with ids only, never amounts.
- Abuse: a guest cannot reach any planner route, `/insights/api` of any worker, the admin console, or another guest's
  record; the allow-list is a new, minimal route table, not an extension of the planner's.
- Privacy: no share link containing a secret in a URL that could be logged or cached; no export unless the owner
  decides yes.

### Phase plan after sign-off (indicative, not started)

9a. Data model and gateway accounts for guests (migration step). 9b. Publish path in the owner's worker. 9c. Viewer and
route table. 9d. Owner UI (grant, scope, expiry, revoke, view log). 9e. Isolation and abuse test gates, then the
security review sign-off before any rollout.

---

## Owner decisions needed

| # | Decision | Recommendation |
|---|---|---|
| 1 | Phase 7 scope: log only, or log plus pass-through decisions and display preferences | Log plus the two small preference files |
| 2 | Phase 7 size cap per file | 64 MB, skip and report above it |
| 3 | Phase 8 cutoff time and window | 17:30 gateway local, window 6 h |
| 4 | Phase 8 control: global flag, or a per-user switch (needs a `gateway.db` migration) | Global flag first |
| 5 | Phase 9: approve starting the design, and answer its five questions | Start with Option A |

## Not verifiable from this plan

- Whether `trends_log` appends atomically (Phase 7 step 0 checks it).
- Exact preference filenames in the insights folder (Phase 7 step 0 checks them).
- The status route and auth header `run-now` uses from the gateway (Phase 8 step 0 checks them).
- Real worker timing and memory for a serial nightly pass (Phase 8 slow test measures it).
