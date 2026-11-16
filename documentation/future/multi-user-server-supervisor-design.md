# Multi-user server: supervisor, proxy, per-user accounts and the isolation gate (Phase 3 design)

Status: draft (built on branch claude/multi-user-phase-3-supervisor-proxy-40c924, stacked on the Phase 2 branch, not merged)
Date: 2026-11-15

Implements "Phase 3" of `multi-user-server-plan.md`: one worker per signed-in user behind the Phase 2 gateway,
Job Objects, a gateway-wide build queue, the reverse proxy, per-user Windows accounts, the ACL setup and check
command, the gateway as a Windows service, gateway-driven backups and the two-user isolation gate. It builds on
the worker contract in Phase 1 (`src/remote_worker.py`) and the seam in Phase 2 (`src/gateway/upstream.py`).

## Layout

| File | Role |
|---|---|
| `src/gateway/proxy.py` | `WorkerProxy`, the real `Upstream`: buffered forward, header contract, limits, build interception |
| `src/gateway/build_queue.py` | `BuildQueue`: gateway-wide build slots (default 2), queued builds, completion tracking |
| `src/gateway/supervisor.py` | `Supervisor`: one worker per user, readiness, crash restart, idle reaping, lifecycle hooks |
| `src/gateway/launchers.py` | `WorkerLauncher` interface; `SameAccountLauncher` (CI, development) and `PerAccountLauncher` |
| `src/gateway/winapi.py` | `ctypes` only: Job Objects, suspended start and resume, listening-port owner, SIDs, DPAPI, logon |
| `src/gateway/accounts.py` | `AccountManager` interface; `NullAccountManager` and `WindowsAccountManager` (create, rights, disable, delete, rotate) |
| `src/gateway/acl.py` | apply and verify the folder ACLs; `python -m src.gateway.acl setup|check` |
| `src/gateway/backups.py` | `BackupScheduler`: per-user plan and `app.db` snapshots plus `gateway.db`, with retention |
| `src/gateway/service.py` | the gateway as a real Windows service (`ctypes` service control dispatcher), install and remove |

`pywin32` is not used (Phase 0 decision); every Win32 call goes through `ctypes`.

## Request path

```
client -> gateway gate (Phase 2: Host, Origin, CSRF, session, TOTP, role)
       -> WorkerProxy.forward(request, identity)
            refuse: /api/build/events/*, POST /api/build, absolute or unusual targets
            /api/build/start, /api/build/progress/<id>, /api/build/cancel/<id>  -> BuildQueue
            Supervisor.endpoint(user_id) -> (port, pid, token)   [starts the worker if needed]
            check that the listening socket on port is owned by pid (GetExtendedTcpTable)
            http.client to 127.0.0.1:port, req.path + query only, upstream_headers(), one Content-Length
            buffered response, capped; drop hop-by-hop, Set-Cookie, CORS; rewrite a loopback Location
```

- **Limits:** request body 64 MiB (the worker's own cap), response body 256 MiB, connect timeout 5 s, read
  timeout 120 s, all in `ProxyConfig`. Over the limit gives 413 or 502; a timeout gives 504. Bodies are never
  streamed, which is safe because the worker's responses are fully buffered and nothing uses keep-alive,
  chunked bodies or WebSockets.
- **Port-owner check.** Before each forward the proxy confirms that the TCP listener on the worker's port belongs
  to the worker process the supervisor started. Without it, a worker that died could leave its port free for
  another user's (compromised) worker to bind, and the gateway would then send the first user's requests, token
  included, to the wrong process. A mismatch marks the worker dead and answers 503.
- **Retries:** a connection failure on `GET`/`HEAD` restarts the worker once and retries; unsafe methods are never
  retried (no double writes), they get 502.
- The gateway's own listeners get a 60 s socket timeout (a slow client cannot pin a thread forever).

## Build queue

`POST /api/build/start` never goes straight to a worker. One build per user at a time (a second start while one
is queued or running gets 409). With a free slot (default 2, `--build-concurrency`) the start is forwarded and
the worker's `job_id` is recorded as holding the slot. Otherwise the gateway answers at once with
`{"success": true, "queued": true, "job_id": "queued-<hex>", "position": n, "phase": "Waiting for a free build
slot"}`; progress polls for that id get a synthetic `{"job": {"status": "queued", ...}}` until a slot frees, and
the dispatcher thread then forwards the stored start request for that user. Afterwards polls on the queued id are
forwarded with the real id. Cancelling a queued build removes it. A slot is released when the proxy sees a final
status (`done`, `failed`, `cancelled`) go past, when the monitor (every 5 s) reads one from the worker, when the
worker exits, or after `max_build_seconds` (default 30 min). Holding a request thread while waiting was rejected:
it would pin one gateway thread per waiting user.

**Pool cap:** the worker passes `RETIREMENT_SYSTEM_BUILD_POOL_MAX` (an application variable, so the scrubbed
build environment keeps it) to the build; `sheets_strategy.py` uses `min(pending, cap)` when it is a positive
integer and today's `cpu_count - 1` when it is unset or invalid, so desktop mode and the golden masters do not
change. The supervisor sets it to 4 by default (`--build-pool-max`).

## Supervisor

- **Start:** `Supervisor.endpoint(user_id)` takes a per-user lock, creates `data/users/<id>/` under the data root,
  removes a stale port file, makes a fresh token (`secrets.token_urlsafe(32)`), and asks the launcher to start
  `python -E -s -B -X utf8 -m src.remote_worker --workspace <dir> --provision <demo|blank> --port-file
  <dir>/local_state/worker.port.json --parent-pid <gateway pid> --console-log <dir>/local_state/logs/worker_console.log`
  with cwd at the install folder. Provisioning is a gateway setting (`--provision`, default `blank`); the worker
  never overwrites a plan that has rows.
- **Environment:** built from nothing: the OS essentials (from the gateway for the same-account launcher, from
  `CreateEnvironmentBlock` for the account's own profile otherwise), `TEMP`/`TMP` pinned to
  `<workspace>/local_state/tmp`, the token, the pool cap, and `ProxyConfig.extra_env` (the shared provider key,
  test switches). Never `RETIREMENT_SYSTEM_BASE_DIR`, `PYTHONPATH` or the gateway's own variables. `-E` makes
  Python ignore `PYTHON*` variables and `-s` the user site-packages.
- **Readiness:** the port file must appear with `pid` equal to the started process, then the port-owner check
  must pass and `/api/ping` with the token must answer 200, within `start_timeout` (60 s). The worker writes its
  console output to a file itself (`--console-log`), so no pipes cross the account boundary.
- **Crash restart:** the monitor thread polls each process. An unexpected exit while the user was active in the
  idle window restarts the worker; more than 3 exits in 10 minutes stops restarting for 10 minutes (requests get
  503 with a plain message), and a running build's slot is released.
- **Stop:** closing the worker's Job Object handle kills the whole tree (worker, build, pool). Logout of the last
  session, disable and delete stop the worker at once unless a build is running; then the stop happens when the
  build ends. **Idle reaping** (default 30 minutes without a proxied request) never reaps while the queue holds a
  build for the user or the worker's `/api/build/status` reports `build_running` (a field added to that route).
- **Gateway death:** the kill-on-close job dies with the gateway's handles; `--parent-pid` is the second line.

## Job Objects

Every worker is created suspended, assigned to its own job, then resumed, so no child can start outside the job
(Phase 0 assigned after `Popen`, which leaves a short window). Limits: `KILL_ON_JOB_CLOSE`,
`DIE_ON_UNHANDLED_EXCEPTION`, `JobMemoryLimit` (default 1792 MiB, `--worker-memory-mb`; Phase 0: 500 MB failed a
build cleanly, 1500 MB let a full-pool build finish) and an active-process limit of 64. Nested jobs work on
Windows 8 and later; whether assignment works when the gateway already runs inside a service's job is one of the
elevated checks.

## Launchers and accounts

```
WorkerLauncher.launch(LaunchSpec) -> WorkerProcess(pid, poll(), kill(), job)
AccountManager.ensure(user_id) / disable(user_id, flag) / remove(user_id) / rotate(user_id) / reconcile(known_ids)
```

- `SameAccountLauncher` (CI and development): `subprocess.Popen` with `CREATE_SUSPENDED`, assignment to the job,
  `NtResumeProcess`. Isolation between users then rests on tokens and the gateway only, which is what CI can test
  unelevated.
- `PerAccountLauncher`: `LogonUserW` type 4 (batch) with the account's password, `LoadUserProfileW`,
  `CreateEnvironmentBlock`, then `CreateProcessAsUserW` suspended (needs LocalSystem's
  `SeAssignPrimaryTokenPrivilege`; when that is missing, as in an elevated admin shell, it falls back to
  `CreateProcessWithTokenW`, which needs only `SeImpersonatePrivilege` and still uses the batch token, unlike
  `CreateProcessWithLogonW`, which logs on interactively). The profile is unloaded after the worker exits.
- `WindowsAccountManager`: `NetUserAdd` (standard account `rpw_<id>`, random 32-character password, password never
  expires), `LsaAddAccountRights` for `SeBatchLogonRight`, `SeDenyInteractiveLogonRight`,
  `SeDenyRemoteInteractiveLogonRight` and `SeDenyNetworkLogonRight`, then the data-folder ACL. Disable sets
  `UF_ACCOUNTDISABLE`. Remove stops the worker, takes a last backup, removes the rights, deletes the account
  (`NetUserDel`), the profile (`DeleteProfileW`) and the data folder. Rotate uses `NetUserChangePassword` with the
  old password (a change, not an admin reset, so the account's DPAPI master keys and Credential Manager entries
  survive; an admin reset would orphan them). Passwords are generated in memory, stored only DPAPI-protected (user
  scope of the gateway account) in `gateway.db` table `worker_accounts`, and never printed, logged or returned.
  `reconcile` retries the cleanup of accounts whose gateway user is gone.
- The gateway calls these through lifecycle hooks added to `create_gateway_app(..., lifecycle=...)`: user created,
  disabled or enabled, deleted, signed out (with the count of sessions left).

## ACLs (`python -m src.gateway.acl setup|check`)

| Path | Who has access |
|---|---|
| data root and `data/users/` | SYSTEM, Administrators, the gateway account; inheritance removed |
| `data/users/<id>/` | the above plus that user's worker account (modify); inheritance removed |
| install folder and runtime | the above (full) plus Users read and execute; no write for anyone else |
| `gateway.db` folder, backups folder | SYSTEM, Administrators, the gateway account only |

`setup` applies these with `icacls` (no secret on any command line). `check` reads each DACL
(`GetNamedSecurityInfoW`) and fails, listing every finding, when a folder is readable by Everyone, Users,
Authenticated Users, INTERACTIVE, BATCH or any worker account other than its owner, or writable by a worker; it
walks each user folder for widened child ACEs. `--forbid <path>` adds folders that must not be readable by
worker accounts (the owner's working copy is reported, never changed). Applying ACLs to real folders is an
owner-approved step on the server.

## Backups and the service

`BackupScheduler` runs in the gateway (reaped workers cannot): every `--backup-hours` (default 24) it copies each
user's `plan.rpx` and `local_state/app.db` with the SQLite backup API (consistent while the worker writes) and
`gateway.db`, into `<backup-dir>/<UTC stamp>/users/<id>/`, keeping `--backup-keep` (default 14) sets. The folder
gets the gateway-only ACL. Encryption, restore and a configurable remote destination are Phase 6.

`python -m src.gateway.service install --config <gateway.json> [--name RetirementGateway]` registers a real
Windows service (LocalSystem, automatic start, restart on failure) whose command runs
`python -m src.gateway.service run --config ...`; `run` hands control to the service control dispatcher and
runs the gateway in a thread, answering stop and shutdown. `remove`, `start`, `stop` and `status` are included,
and `--config` holds the same settings as the gateway's command line.

## Isolation gate

`tests/test_multi_user_isolation_integration.py` starts the real gateway as a subprocess with the same-account
launcher and a temp data root, creates two users with TOTP in `gateway.db` first, signs both in over HTTP, and
asserts: each reaches only its own worker (a plan edit by A is not visible to B); a guessed worker port with no
token, with A's token on B's port, and with forged Host or Origin is refused; client `Authorization`,
`X-API-Token`, `Cookie` and `X-Forwarded-*` never reach a worker or switch the user; the SSE route is refused;
logout stops the worker. It runs in the PR tier, unelevated. Elevated checks (`@pytest.mark.elevated`, skipped
unless `RETIREMENT_ELEVATED_TESTS=1` in an elevated shell) cover the per-account path.

## Not done here

Frozen-exe dispatch for the worker (the frozen build must gain an explicit `remote_worker` entry), encrypted and
off-machine backups, restore, Funnel, the health page and log rotation (Phase 6); per-user secrets and Monarch
(Phase 4); the planner frontend's handling of the `queued` build status (Phase 5).
