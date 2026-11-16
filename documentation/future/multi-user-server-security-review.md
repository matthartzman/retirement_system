# Multi-user server: Phase 7 verification and security review

Status: draft (review of the stack through Phase 6, dated 2026-11-16; the owner-run checks listed under "Did not run" are open)
Date: 2026-11-16
Branch: `claude/multi-user-phase-7-verification-f1a555`, based on the Phase 6 branch.

## Verdict: NO-GO for real users today; GO once the six conditions below are met

Cross-user leakage is the risk the plan names, and this review found and fixed three ways one user could reach
another user's data or permissions (P7-01, P7-02, P7-03), all through paths the earlier phases had not covered.
The remaining open items include one that decides whether the Windows-account boundary exists at all (the
elevated checks have never run), and a privilege-escalation path that depends on how the owner installs Python.
Before putting real users on the server:

1. **Run the elevated suite with the owner** (`tests/test_worker_accounts_elevated_integration.py`, steps under
   "Did not run"). The per-account folder isolation, the deny-logon rights and the credential survival across
   password rotation are unverified; the same-account tests in this review prove only the application's own
   confinement.
2. **Install the Python runtime, the gateway code and the service config where worker accounts cannot write**
   (P7-O2), and confirm with a recursive ACL listing, not just `acl check`, which inspects only the top folder.
3. **Remove the standard-account read access to `C:\RetirementPlanning\Version 12`** (Phase 0 finding), or run the
   gateway from a clean install folder with no owner data.
4. **Decide on pre-authentication exhaustion (P7-O3):** either cap request bodies and concurrent connections in the
   gateway, or confirm Funnel's own limits make the listener safe. As built, an unauthenticated client can hold
   memory and threads.
5. **Encrypt the TOTP secrets at rest** (P7-O1), or accept in writing that anyone who can read `gateway.db`
   (backups included) can mint codes.
6. **Re-run the isolation gate and the elevated tests on the installed (frozen or clean-folder) build**, because
   everything here ran from the source tree with the same-account launcher.

## Scope and method

Reviewed: the gateway (`src/gateway/`, `src/access_core.py`), the reverse proxy, the supervisor and Windows
account layer, backups and restore, the health endpoint and Funnel check, Phase 1's remote mode (the allow-list,
`confine_path`, the worker, plan upload and download), and Phase 4's Monarch upload, secrets guard and connector.

Method: I read the authentication, proxy and framing code myself and attacked it. Four independent read-only
review passes (account layer; backups and operations; Monarch; worker confinement) each reported findings with
evidence; I verified each before accepting it, and the findings below say which were reproduced. Every confirmed
finding got a failing test first, then the smallest fix, in its own commit. No existing test was weakened.

## Findings

Severity is my judgement for this deployment (10 mutually untrusted users, public Funnel listener).

### Fixed

| Id | Sev | Finding | Evidence | Fix |
|---|---|---|---|---|
| P7-01 | High | A user uploads a crafted `.rpx` whose build snapshot record names another plan file, then calls `POST /api/plan/snapshot/restore`; the path was used unconfined and an empty hash skips the check, so any plan file the worker can read is copied into the user's plan and downloadable. Under the same-account launcher this reaches every user's plan. | Reproduced by the confinement pass (full chain through the test client). The new isolation test drives it through the gateway and passes. | `aeec1919` |
| P7-02 | High | The gateway's privileged jobs followed directory junctions a worker can create inside its own folder without privilege: backup read another user's `app.db` into the wrong archive, restore replaced another user's live database, migrate-all and log housekeeping read and rewrote through links. | Reproduced by the backups pass with `write_archive` and `restore_user`; regression tests cover backup, log trim and the guard. | `387f2f9d` (new `src/gateway/fsguard.py`) |
| P7-03 | Medium | `acl setup` runs `icacls <folder>\* /reset /T`, which follows a planted junction and resets the permissions of its target (for example a hardened key file). | Reproduced: a file's ACL changed from owner-only to inherited. | `b4e6968d` removes links first |
| P7-04 | Medium | Re-entering the correct password cleared the failed-code counter, so a holder of a password got unlimited second-factor guesses (bounded only by the per-address throttle); and a failure that raced past the lock check overwrote the lock with "unlocked". | Reproduced at store level by two tests. | `9ce3893e` |
| P7-05 | Medium | The price tester returned `repr(exc)` including the request URL, so a connection error exposed the shared provider key (`?apikey=...`) to any user. | Reproduced by the confinement pass with a fake key. | `4a1c4859` |
| P7-06 | Medium | `GET /api/ytd/status` scanned stored roots and folders beside the install and merged any account-setup file it found into the user's plan (another install's names and balances). | Reproduced: a candidate outside the workspace was found. | `ae0ab502` |
| P7-07 | Medium | Parallel `POST /api/build/start` from one user all passed the "has a build" check and each queued a body of up to 64 MiB, pushing that user ahead of others. | Reproduced: three entries for one user. | `edda1c0c` |
| P7-08 | Medium | A 16 MiB Monarch CSV of blank lines never hit the row cap and cost about 1.2 GB; an over-long field raised an unhandled error. | Reproduced with tracemalloc (313 MB at 4 MiB). | `34b92c98` |
| P7-09 | Low | The Monarch connector's transport followed 301/302/303 redirects to any host while carrying the Bearer token. | Reproduced with the redirect handler. | `34b92c98` |
| P7-10 | Low | `POST /api/plan` returned a traceback and the exception text in remote mode. | Reproduced. | `d53c3c85` |
| P7-11 | Low | A NUL byte in `/files/<name>` gave an unhandled 500. | Found by the new path tests. | `5799782f` |
| P7-12 | Low | Log housekeeping read a whole multi-GB console log into gateway memory. | Code reading. | `387f2f9d` |
| P7-13 | Low | The Funnel guard ignored foreground serve sessions and accepted a target on another machine. | Reproduced with synthetic status documents. | `52f9eb0a` |
| P7-14 | Low | The download filename root went unsanitised into `Content-Disposition` (header injection into the user's own response). | Code reading plus unit test. | `c0bbb101` |

### Open (not fixed here)

| Id | Sev | Finding | Failure scenario | Proposed fix |
|---|---|---|---|---|
| P7-O1 | Medium | TOTP secrets are plain text in `gateway.db` (known). The file is in every backup. | Anyone who reads `gateway.db` or a restored backup can mint codes; passwords still need cracking, so it is one factor, not both. | Encrypt the column with the DPAPI scheme already used for worker passwords, or a key from the backup key file; migrate in place. |
| P7-O2 | High if the install is writable | The service runs as LocalSystem from `sys.executable` and a `--config` file; `acl check` inspects only the install folder's own ACL. | If Python (stdlib, site-packages, DLLs) or the config sits under an inherited Authenticated-Users:Modify folder, a worker can overwrite a module and gain SYSTEM at the next service start. Code reading only; not reproduced. | Install Python and code in an admin-only folder; extend `acl check` to walk the Python home, the install tree and the config file and fail on any worker-writable ACE. |
| P7-O3 | Medium | Pre-authentication exhaustion: unbounded threads, a 64 MiB body read before the gate, a per-read (not total) socket timeout that a slow sender can reset, scrypt (32 MiB) with no concurrency cap. | An unauthenticated client opens many connections, or sends many logins at once, and exhausts memory or CPU for all users. Not reproduced at scale. Funnel may absorb some of it; that is unmeasured. | Run the gate on headers before reading the body, cap gateway-owned bodies at tens of KiB, bound concurrent connections, add a semaphore around password hashing, add a total read deadline. |
| P7-O4 | Medium | The global login throttle (50 failures per 10 minutes, then up to 60 s delay for everyone) lets three or four addresses lock all logins out. | Login denial of service against every user including admins. | Throttle per username and per address; make the global limit only slow, not refuse, known-good sessions; alert on it. |
| P7-O5 | Medium | No per-user limits beyond memory: a 256 MiB response buffered per request, no disk quota (uploaded plans are kept in `saved_plans/`), no CPU limit, no cap on parallel builds in the worker itself. | One user fills the shared disk or the gateway's memory. | Stream or cap responses, per-user quota and plan count, Job Object CPU rate limit. |
| P7-O6 | Medium | Job Objects are the only containment; processes started through Task Scheduler or WMI escape them, and removing an account never kills its remaining processes. | A compromised worker keeps running after logout, disable or delete. Not reproduced (needs elevation). | Kill every process whose token SID equals the account before disable and delete; deny the batch-logon scheduling rights where possible. |
| P7-O7 | Medium | Backup retention counts a set missing a user (locked or corrupt `plan.rpx`) as complete, so bad sets push out good ones after `--backup-keep` nights; backups read whole SQLite files into gateway memory (no size limit); a restored file may lack the worker account's ACE and `acl check` reports only extra access, never missing. | Silent loss of the last good copy; gateway out of memory during backup; a restored user cannot open their plan. | Prune only complete sets; stream via the SQLite backup API; make restore re-apply the user ACL and have `check` report missing access. |
| P7-O8 | Low | Smaller backup and operations items: key file permission window between create and lock; `-journal` not moved aside on restore and a partial rollback on a failed second member; `worker.port.json` is user-writable and trusted to decide "in use"; a mapped or `subst` drive can hide a share; other sync tools are not recognised; `restore --gateway-db-out` writes a plaintext `gateway.db` with inherited ACLs; `power.py` revert rounds timeouts under 60 s to "never". | Each needs a specific unlucky sequence. | Listed so Phase 8 or a follow-up can pick them up. |
| P7-O9 | Low | Account layer races: `ensure` can leave an account whose password does not match the store; rotation is not atomic; disable and delete are not atomic with a request already past the gate (a worker can start for a just-disabled user and live until idle); a failed delete can leave the data folder; the port file is read without a size cap. | Narrow windows or admin-visible failures; none reads another user's data. | Serialise lifecycle per user under one lock; make rotation write-then-commit; retry the folder removal in housekeeping. |
| P7-O10 | Low | Information still disclosed in remote mode: `/api/status` names the credential backend, the price tester names environment variable names, and pricing routes return exception text and a traceback tail. | Fingerprints the server; no secret. | Route these through the generic error and scrub list. |
| P7-O11 | Low | `RETIREMENT_SYSTEM_PLAN_DB` bypasses confinement (environment only, so not request-reachable). | Only if the supervisor environment is wrong. | Confine it at startup. |
| P7-O12 | Info | `gateway.db` in backups also holds DPAPI blobs that do not open on a rebuilt machine, and restoring an old copy revives deleted or disabled users; there is no freshness protection on archives. | Disaster-recovery surprise. | Document in the runbook; add a counter or signed manifest later. |
| P7-O13 | Info | The Monarch connector's `disconnect` returns 403 when the connector flag is off, so a user cannot revoke stored tokens until it is re-enabled. | Design note. | Allow disconnect regardless of the flag. |

### Reviewed and found sound

Password hashing (scrypt with per-user salt, constant-time compare, equal work for unknown users); TOTP (window of
one step, a used step is never accepted twice); session ids stored only as hashes, rotated at each stage change, a
fresh id per login, idle (15 min) and absolute (12 h) expiry, logout and disable ending sessions; cookie
(`__Host-`, `Secure`, `HttpOnly`, `SameSite=Strict`) and refusal of two session cookies; CSRF compared in constant
time and Origin required on every unsafe method; the open-redirect guard on `next`; the allow-list, token gate and
`confine_path` (case sweep including junctions, UNC, `\\?\`, drive-relative, device names and alternate streams);
route matching on the raw path, so percent-encoding cannot reach the build-queue or event-stream blocks; header
stripping, Host and Origin rewriting and single `Content-Length` in the proxy; process creation (no handle
inheritance, explicit environment, job assignment before resume); AES-256-GCM backups (per-archive key, no nonce
reuse, authenticated header, chunk reorder, duplicate, flip and truncation all detected, verification before any
live file changes, member names matched by an allow-list so restore cannot traverse); Monarch OAuth (state and PKCE
verifier from `secrets`, single use, expiry, endpoint host checks, read-only scope, tokens only in the credential
store, nothing in logs); the health endpoint (admin only, no paths or ids).

## What was tested and how

**Isolation gate (same-account launcher, no elevation, real gateway and real worker processes).** Three modules,
32 tests, all passing:

- `tests/test_multi_user_isolation_integration.py` (existing, 12 tests; its fixture now also starts a gateway for
  the other two modules).
- `tests/test_multi_user_isolation_attacks_integration.py`: a copied session id with no, wrong or truncated CSRF
  token; missing, garbage and pending sessions; idle and absolute expiry (set directly in `gateway.db`) and a
  logout-then-replay; forged `X-Forwarded-For` against the throttle (left-most values varied, right-most fixed);
  proxy headers refused on the local listener; five request-smuggling framings (conflicting `Content-Length` and
  `Transfer-Encoding`, duplicates, an obfuscated header, a signed length) each producing exactly one response;
  duplicate cookie headers, a 70 KB header, a 70 MiB declared body and a negative length; cross-site, `null` and
  wrong-origin requests; a guessed worker port with every token shape; the gateway log and worker logs free of
  secrets, session ids, codes and the other user's paths; an admin disabling a user, ending the live session and
  stopping the worker.
- `tests/test_multi_user_isolation_routes_integration.py`: every `(method, rule)` in `ALLOWED` is called as user A
  (a skip list of 14 heavy or covered routes, each with a reason, and a check that it stays a subset of `ALLOWED`),
  then again with hostile bodies naming user B's paths in every field a route might read; each response is
  checked for B's data, server paths and tracebacks. Crafted paths (traversal, encoded and double-encoded,
  absolute, UNC, `\\?\`, alternate stream, short name, NUL) against `/files/`, `/frontend/`, `/api/export/` and
  `/api/plan/forms/`; a junction from A's workspace to B's folder; a path to B's folder stored in every settings
  key a path could hide in; and the crafted-snapshot upload (P7-01) end to end. A final test checks B's bytes did
  not reach A's folder.

Not covered by these and left to the elevated suite: per-account file permissions (under the same account every
worker can read every folder, so only the application's own confinement is shown).

**Unit and regression tests added:** second-factor lockout, upload limits and redirects, reparse-point guard (backup,
log trim), ACL junction, snapshot restore, ytd recovery, build queue, key redaction, output file names, Funnel guard,
filename root.

## Load test (10 users, measured)

Script kept outside the repo (`loadtest.py`, scratch folder); real gateway, ten real workers from source under the
same-account launcher, demo plan per user, `--build-concurrency 2`, pool cap 4, worker memory cap 1792 MB.

Machine state: 12 logical CPUs, 64 GB RAM (about 40.9 GB free at start), Windows 11, Python 3.12.10, another
unrelated session active (CPU idle baseline 16.6 % before the run). Run on 2026-11-16 12:01 to 12:09 local.

| Measure | Result |
|---|---|
| Cold start, all 10 users first request at once | all 200; 6.2 to 6.7 s each, 6.7 s wall |
| 10 idle workers | 645 MB resident for the whole gateway tree, 21 processes |
| Gateway latency with 10 users, no builds (300 requests each) | `/api/ping`: p50 86 ms, p95 116 ms, max 140 ms. `/api/config/rows` (worker work): p50 1,125 ms, p95 1,311 ms, max 3,757 ms. No errors. |
| Burst: 10 builds submitted at once | all 10 finished (`done`); 8 queued at submit; queue wait min 0.5 s, median 197 s, max 360 s; run time 64 to 101 s (median 90 s); burst wall time 440 s |
| Memory during the burst | peak 1,323 MB resident across the gateway tree, 31 processes; lowest system free memory 39.8 GB |
| Gateway latency during the burst (417 probes) | `/api/ping` p50 53 ms, p95 78 ms, max 193 ms, no failures |
| CPU | peaked at 100 % during builds |

Reading: at 10 users the queue is the limit, not memory: with two builds at a time the last user waits about six
minutes, and the gateway stays responsive throughout. The resident figure is RSS summed over processes and counts
shared pages more than once; the Phase 0 figure of about 1 GB per build tree is consistent with it. Not measured:
per-account launching, the frozen exe, ten simultaneous Monarch uploads, and a build on a large real plan (the demo
plan is small).

## Verification set

Results are filled in below from the logged runs (log tails quoted).

VERIFICATION_PLACEHOLDER

## Carried-over open items

From the Phase 3 to 6 notes, none closed by this review:

- Phase 3's elevated check that one worker account cannot read another's folder under the new ACLs is unverified (the UAC prompt was cancelled).
- The elevated test that a stored credential survives worker-account password rotation has not run.
- The Monarch connector UI was tested only with a faked API.
- The frozen exe has no worker entry point, so workers run from source.
- Phase 0: standard accounts could read `C:\RetirementPlanning\Version 12` (inherited permissions).
- Phase 6 owner measurements (Funnel bandwidth, reboot survival): see `multi-user-server-operations-measurements.md`.
- TOTP secrets in clear (P7-O1).

## Did not run, and how to run it

Nothing needing the owner was run: no elevated test, account creation, ACL or policy change, service install, Funnel
change or reboot. The owner can run, in an elevated shell and with approval:

```
set RETIREMENT_ELEVATED_TESTS=1
pytest tests/test_worker_accounts_elevated_integration.py -v -rfE > elevated.txt 2>&1
```

The suite creates throwaway `rpwtest_` accounts and a throwaway `C:\rpwtest_*` folder and removes them; check that
`net user` shows none afterwards. It covers the per-account folder isolation, the Job Object kill, password
rotation, deleting a user while its worker runs, and credential survival across rotation. The three isolation
modules start the gateway with the same-account launcher only; running them per-account needs a launcher option
added to `launch_gateway` (a gap, not done here), so the elevated suite is the per-account proof for now.
