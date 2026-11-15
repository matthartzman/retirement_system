# Multi-User Server: Phase 0 Results

Status: draft
Date: 2026-11-15
Plan: `documentation/future/multi-user-server-plan.md` (revision 3), section "Phase 0"

Everything here was measured on the owner's machine on 2026-11-15 with throwaway scripts (not committed; a copy is
in the shared notes folder under `phase0-scripts/`). No product code was changed. Items that could not be done are
marked **NOT MEASURED** with the steps still needed. No figure below is estimated.

**Test machine:** Windows 11 Pro 10.0.26300, 12 logical CPUs, 64 GB RAM (about 33 GB free during the tests), Python
3.12.10, source run (not the frozen exe). Sample plan: the repo's frozen CSV fixture
(`tests/fixtures/csv_exchange/sample_plan_frozen/`), with live price providers disabled and the date pinned. Every
workspace was a temp directory; the repo root and the owner's real data were never used as a workspace.

## Summary of calls

| Question | Call |
|---|---|
| Option A (worker process per user) | **GO** on resources and process model: a worker is about 64 MB idle, starts in about 1-2.5 s; a build tree peaks near 1 GB. |
| Per-user Windows accounts | **UNPROVEN, not a no-go.** The account test needs elevation and the UAC prompt was not approved, so it was not run. Treat as the gating item for Phase 3; the script is ready (see item 5). |
| Funnel or Cloudflare | **Funnel confirmed** as workable: the node is a running automatic service, port 8443 works from the public internet. Real external bandwidth and reboot survival are not measured. |
| Monarch connector or CSV upload | **Build the CSV upload fallback first; keep the connector as an optional add-on.** The connector is live and supports third-party OAuth clients, but Monarch states it does not return Mastercard Connect (Finicity) accounts, which "may particularly affect brokerage accounts through Fidelity". The live tool list and data coverage were not tested (needs the owner's login). |
| `pywin32` or `ctypes` | **`ctypes`** (provisional; not live-tested): no new dependency, `pywin32` is not installed here, and only a handful of calls are needed. |

## 1. Headless worker: cold start and memory

Method: `worker.py` models `tools/e2e_server.py:78-98` but binds `LocalHTTPServer(("127.0.0.1", 0), create_app())` and
writes the chosen port to a file. Time is from process start to the socket being bound, measured inside the process;
then `/api/ping`, `/api/config/rows` and `/` were requested. Memory is `psutil` RSS and USS of the worker about 1 s
after the requests.

| Workspace | Start to listening | of which seeding the plan from CSV | `/api/config/rows` first call | RSS | USS |
|---|---|---|---|---|---|
| Seeded (sample plan) | 2.5 s | 0.37 s | 0.81 s (433 KB) | 64 MB | 46 MB |
| Empty | 0.9-1.0 s | 0 | 0.28 s (41 KB, 0 rows) | 62 MB | 45 MB |

Port 0 works with `LocalHTTPServer` as is (the port is read from `server_address`). `/api/ping` returns
`package_root` (the install path) to any caller: a leak the plan already lists under Remote mode item 5.

Not measured: a frozen-exe worker (the plan chooses a frozen build in Decision 7); expect a slower first start from
PyInstaller unpacking and somewhat different memory. Re-measure in Phase 1 once the headless entry point exists.

## 2. Completely empty workspace

Method: `worker.py <dir> empty` on a directory containing only the four empty folders `input`, `output`,
`local_state`, `saved_plans`.

- **It starts and does not fail.** On first import it creates an empty `plan.rpx` and `local_state/app.db`
  (plus `-wal`/`-shm`); it does not seed the demo plan.
- The API serves, but the plan has **0 rows**: `/api/config/rows` returns metadata and an empty row list.
- `POST /api/build/start` is accepted (HTTP 200, a job id) and the build then **fails within about 2 s** with
  "Build process returned an error". So an unprovisioned user can click Build and get an unexplained failure.

Consequence for Phase 1/3: provisioning must be explicit (copy the demo or blank plan into the workspace before the
worker starts), the empty case needs a clear message, and the headless worker should refuse to run a build on a plan
with no rows.

## 3. Peak memory of a whole build tree

Method: `buildmem.py` starts N workers (separate temp workspaces, seeded), posts `/api/build/start` to each at the
same moment, and samples every 250 ms the sum of RSS and USS over each worker's whole process tree, plus the
system-wide "used memory" delta. `full` is the default simulation count; `small` is the e2e count
(`RETIREMENT_MC_SIMS=16`).

| Case | Wall time | Processes at peak | Sum of RSS | Sum of USS (private) | System used-memory delta |
|---|---|---|---|---|---|
| 1 user, small sims | 54.5 s | 13 | 988 MB | 744 MB | 1045 MB |
| 1 user, default sims | 56.3 s | 13 | 980 MB | 735 MB | 606 MB |
| 2 users at once, default sims (run 1) | 126.3 s | 26 | 1930 MB | 1438 MB | 1395 MB |
| 2 users at once, default sims (run 2) | 109.0 s | 26 | 1934 MB | 1442 MB | 1301 MB |

Reading: a build is 1 worker + 1 build process + **11 pool processes** (CPU count 12 minus 1), about **1 GB per
build** and about 70 MB per pool process. Two simultaneous builds are about 1.9 GB, linear in build count, but each
build takes about 2x longer (109-126 s versus 56 s) because 22 pool processes compete for 12 CPUs. Build output was
"QC: 38 / 38 PASS" every time.

Sizing for about 10 users: memory is not the constraint on this 64 GB machine (even 10 simultaneous builds is about
10 GB); **CPU time is**. Ten simultaneous builds would take on the order of 10 x 56 s of CPU-bound work, so a global
build queue with concurrency of 2-3 and a per-build pool cap (for example 4-5 processes) is the sensible design.
That extrapolation is arithmetic from the figures above, not a measurement; the Phase 7 load test must measure it.

Not measured: with the pool cap lowered, how build wall time changes; builds on a plan larger than the sample.

## 4. Job Object kill test

Method: `jobtest.py` starts a worker, starts a build, waits until the tree has 12 child processes, then kills the
worker only (`taskkill /F /PID`, no `/T`) in the first case, or closes a kill-on-close Job Object handle in the
second. Win32 calls through `ctypes` (`CreateJobObjectW`, `SetInformationJobObject`, `AssignProcessToJobObject`).

| Case | Immediately after (about 4 s) | Later |
|---|---|---|
| Worker killed, no Job Object | **All 12 child processes still alive** (build process plus 11 pool processes), still running the build | 11 gone by +5 s; the build process itself survived 5-10 s more and was gone by +15 s |
| Kill-on-close Job Object closed | **0 of 12 alive** | n/a |

So killing a worker does orphan its running build; a kill-on-close Job Object fixes it completely, including
grandchildren (the job applies to processes started after the worker was assigned, which is why assigning
right after `Popen` works). The orphan eventually exits on its own in this run. My reading is that it dies when its
stdout pipe to the dead worker breaks, but I did not verify the cause, and a build that stays quiet longer could
live longer; do not rely on it.

Job memory limit (bonus, one run each): a 500 MB job cap made the build **fail cleanly** (job status `failed`, the
worker survived and stayed reachable); a 1500 MB cap let the build finish (`done`). So a per-user cap of about
**1.5-2 GB** is a workable setting for a one-build-at-a-time user; it fails the build, not the worker. The exact
minimum between 500 and 1500 MB was not found.

The test process was launched from the Claude desktop app's shell; nested Job Objects worked there
(`AssignProcessToJobObject` returned success). Re-test if the gateway runs as a service, where the parent may
already be in a job.

## 5. Per-user Windows accounts: NOT MEASURED

The owner approved the test, but it needs an elevated shell and the UAC prompt was cancelled/not approved both
times (this session cannot see the secure desktop). **No account, profile, folder or scheduled task was created**;
nothing needs cleaning up. Confirmed beforehand: the session was not elevated.

A ready script exists in the shared notes folder: `phase0-scripts/acct/run_elevated.ps1` plus
`launch_as.py` and `probe_user.py`. To run it, open an elevated PowerShell 7 and run:

```
pwsh -NoProfile -ExecutionPolicy Bypass -File "<notes folder>\phase0-scripts\acct\run_elevated.ps1"
```

(edit the `$S` path on its second line first). It creates `p0test_a` and `p0test_b` with random passwords held in an
admin-only folder, copies a readable Python runtime to `C:\p0test\py`, then:

1. Part 1: `CreateProcessWithLogonW` with `LOGON_WITH_PROFILE` from the elevated session, running a probe as each
   user in the order A set, B get (expect `None`), B set, A get (expect A's own value), to show Credential Manager
   separation via `keyring` and `cmdkey /list`.
2. Part 2: `LogonUser` (batch, then interactive) + `LoadUserProfile` + `CreateEnvironmentBlock` +
   `CreateProcessAsUser` from a one-shot scheduled task as `SYSTEM`, which is the LocalSystem case.
3. The probe tries to read the other account's folder, an admin-only "gateway" folder, the owner's profile and the
   repo, and tries to write to the runtime folder.
4. A `finally` block deletes both accounts, their profiles, `C:\p0test` and the task, and prints what remains.

Known gaps even when it runs: it does not set the "deny interactive/remote logon" and "log on as a batch job" rights
(that is a local security policy change and was not authorized); the plan's "deny interactive logon" and the
logon type that `CreateProcessWithLogonW` uses (interactive) may conflict, so Phase 3 must test a batch-logon design
after granting `SeBatchLogonRight`. Also note: the owner's Python lives under `C:\Users\MattHartzman\AppData\...`,
which other accounts cannot read, so the script copies it; this confirms Decision 7 (a frozen build in a shared
read-only folder such as `C:\Program Files\...`) is required, not optional.

`pywin32` vs `ctypes` (provisional, from reading and from the Job Object tests above): choose **`ctypes`**.
`pywin32` is not installed in this environment (only `pywin32-ctypes`, a keyring dependency); the Job Object code
worked first time with `ctypes`; `launch_as.py` shows the account-launch calls are about 6 functions. Revisit only if
the live test finds a call that is awkward to bind (for example `LsaAddAccountRights`), in which case `pywin32` or a
`net`/`secedit` subprocess is the alternative.

## 6. Tailscale Funnel

Read-only checks (`tailscale status`, `serve status`, `funnel status`, `version`, `netcheck`, service query):

- Tailscale 1.104.5, node `hartzmanpc72024` online. Public name `https://hartzmanpc72024.tail22bbfa.ts.net`.
- **Funnel is currently on for port 443**, proxying `/` to `http://127.0.0.1:5058`, the trends reporter's remote
  listener. So **443 is taken**; the planner gateway needs 8443 or 10000.
- The Windows service `Tailscale` is Running with start type **Automatic**.
- Netcheck: UDP and IPv4/IPv6 available, nearest relay Chicago (25 ms).

Changes made with the owner's approval: a temporary Funnel listener `--https=8443` proxying to a local
`python -m http.server` on 127.0.0.1:8099 serving a 20 MB random file and a one-line text file. Then removed with
`tailscale funnel --https=8443 off`; `funnel status` afterwards shows only the original 443 -> 5058 entry. The local
file server was stopped.

- **Port 8443 works from the public internet**: a fetch of the text file from outside this machine (through the
  Claude web fetch tool) returned its contents. This also means 8443 is free for the gateway; 10000 was not tried.
- Download of the 20 MB file from this same machine through its public name: 0.60 s, then 0.20 s twice (about
  33, 100 and 102 MB/s). **This is not a valid bandwidth figure**: the request comes from the same node and
  almost certainly does not leave the machine. The local loopback baseline was 82 MB/s. **Real external download
  bandwidth is NOT MEASURED.** Needed: the same 20 MB file fetched from a machine on another network (or a phone on
  cellular) while Funnel 8443 is up, repeated 3 times; and the real upload rate of this connection (Funnel traffic
  goes out over the owner's home uplink, so the uplink speed, not Funnel, is the likely limit for a workbook
  download).
- **Reboot survival is NOT MEASURED.** Evidence is only the Automatic start type and that the Funnel config is stored
  by the Tailscale service (`--bg`). To measure: reboot, then `tailscale funnel status` and an external fetch with no
  one logged in. A Windows service starting before logon is the case that matters for an always-on server.

Decision: keep Funnel (the plan's choice) because 8443 works and 443 is the only conflict; the Cloudflare fallback is
not needed on present evidence. Two follow-ups for Phase 6: the gateway must use 8443/10000 and never 443/5058, and
the reporter's `check_funnel_target` only checks port 5057, so Phase 1/6 must extend it to the gateway's workers.

## 7. Monarch MCP connector

Sources: Monarch's help article "Monarch MCP Connector" (public help-center API, `updated_at` 2026-11-13, created
2026-06-11) and unauthenticated requests to `https://api.monarch.com`. No login, no OAuth flow, and **no client
registration was performed** (registration creates a record at Monarch; left for the owner).

**Settled by documentation and discovery endpoints**

| Question | Answer | Evidence |
|---|---|---|
| Current status | **Live and supported**: article created 2026-06-11, updated 2026-11-13, lists Claude Desktop/Claude Code/Gemini/Cursor/ChatGPT; no pause notice. The "pause and October relaunch" report was not corroborated. | help article |
| Third-party OAuth client allowed? | **Yes, by protocol**: `/.well-known/oauth-authorization-server` advertises `registration_endpoint` (dynamic client registration, `https://api.monarch.com/oauth/register`), `code` flow with **PKCE S256**, token endpoint auth `none`/`client_secret_basic`/`client_secret_post`, and `resource_indicators_supported`. Other, unlisted clients "may be able to connect" but are not officially supported. Whether registration accepts a non-loopback HTTPS redirect URI such as the Funnel name is **not tested**. | discovery document; help article |
| Token refresh | `grant_types_supported` includes `refresh_token`; revocation endpoint exists. **Token lifetimes are not published and not tested.** | discovery document |
| Scopes | `mcp:read` and `mcp:write`; default is read-only; the user chooses on the consent screen. | protected-resource document; help article |
| Transport | `POST` and `DELETE` on `/mcp` (a GET returns 405 "allow: POST, DELETE"); an unauthenticated `tools/list` returns 401 with a `WWW-Authenticate` pointing at the resource metadata, so standard MCP OAuth discovery works. | requests |
| Rate limits | Weekly usage limits (reset weekly, shown in Monarch Settings > MCP Connector), plus short-term limits that reset in a few minutes, plus 100,000 writes a week. **Read-call numbers are not published.** | help article |
| Revocation / sharing | The user can revoke any connected tool in Monarch Settings > MCP Connector, effective immediately; each authorization is tied to one Monarch account; no customer-facing audit log. | help article |

**The blocker for this owner:** the article states that data from **Mastercard Connect (Finicity) is not available
through the MCP**, with accounts from such connections silently missing from results, and says this "may
particularly affect brokerage accounts through Fidelity". Terms with Finicity are "still being worked through". If
any of the household's accounts (or any user's) go through Finicity, the connector cannot provide them. The user's
Monarch page lists the incompatible institutions.

**NOT TESTED (needs the owner in their own browser):** the tool names and what they return; whether transactions
carry stable ids, dates, merchants and categories and whether balance history is available the way
`src/monarch_balances_import.py` needs; result paging and how many years of history can be pulled; actual token
lifetime and whether refresh works unattended; the redirect-URI check. To measure: write a read-only throwaway
script with the `mcp` Python SDK that registers a client, prints the authorization URL for the owner to open and
approve with **Read only** ticked, then lists tools and pulls a page of accounts, balances and transactions; run it
again a day later to see whether a refresh token still works. The owner chose "not now" for this in this session.

**Call:** do not depend on the connector for the first release. Build the Phase 4 **CSV upload fallback first**
(it works for every account provider, stores no Monarch credentials, and ends the Finicity problem), then add the
connector for users whose accounts are all Plaid/MX once the live test above passes. The Phase 4 estimate of 5-7 days
should be re-split: about 3-4 days for the CSV path (the plan's own figure) in the minimum slice, and the connector
as a separate follow-on of about 3-4 days.

## Changes Phases 1-4 must make because of these findings

1. **Phase 1:** make the headless worker refuse builds on a plan with no rows, and provision explicitly (an empty
   workspace starts fine but a build fails after 2 s with an unhelpful message). Port 0 binding needs no change to
   `LocalHTTPServer`. Remove `package_root` from `/api/ping` in remote mode.
2. **Phase 3, concurrency:** the constraint is CPU, not memory. Plan a global build queue (2-3 at once) and cap the
   process pool (the `os.cpu_count() - 1` at `src/reporting/sheets_strategy.py:445-451` makes 11 processes per
   build here). A 1-user build is about 1 GB, 2 simultaneous builds about 1.9 GB and each runs about 2x slower.
3. **Phase 3, Job Objects:** kill-on-close works and is required (orphaned builds outlive a killed worker for several
   seconds in this test). Add a job memory limit of roughly 1.5-2 GB per user; a build that exceeds it fails cleanly
   without taking the worker down.
4. **Phase 3, accounts:** run `run_elevated.ps1` before committing to the design; until it passes, per-user accounts
   are unproven. Install the runtime in a shared read-only location (the owner's current Python is under a user
   profile that other accounts cannot read). Test the logon type against the "deny interactive logon" requirement.
5. **Phase 4:** CSV upload first; connector second and only for non-Finicity accounts; confirm redirect-URI
   registration with the Funnel name; request `mcp:read` only. Use dynamic client registration with PKCE.
6. **Phase 6:** the gateway listens on Funnel 8443 (443 belongs to the trends reporter); extend
   `check_funnel_target` to the gateway's rules; measure real external bandwidth and reboot behaviour.

## What was not measured, in one list

- Per-user Windows account creation, launch, folder separation, Credential Manager separation, keyring (needs UAC).
- Real external Funnel bandwidth; Tailscale/Funnel after reboot; port 10000.
- Monarch live tool list, data coverage, paging, token lifetime/refresh, redirect-URI acceptance (needs the owner's
  Monarch login in their browser).
- Frozen-exe worker start time and memory.
- Ten-user load and pool-cap effects (Phase 7).
