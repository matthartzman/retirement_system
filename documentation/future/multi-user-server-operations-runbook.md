# Multi-user server: operations runbook

Status: draft (written with Phase 6; the commands marked "not run on the server yet" have been tested only against fixtures and fakes)
Date: 2026-11-16

For the Windows administrator of the always-on server. Design reasons are in `multi-user-server-operations-design.md`,
the gateway in `multi-user-server-gateway-design.md`, workers and ACLs in `multi-user-server-supervisor-design.md`.
Open measurements are in `multi-user-server-operations-measurements.md`.

All commands run in an **elevated PowerShell** on the server, from the install folder, with the **runtime Python**
(`$PY` below). Never paste a password, key or token into a command line, a ticket or a chat.

## 0. Layout used in this runbook (change the drive or names as you like)

| What | Path | Who may read it |
|---|---|---|
| Code (read-only for everyone but admins) | `C:\RetirementPlanner\app` | admins write; workers read and execute |
| Runtime Python (a venv inside the code folder) | `C:\RetirementPlanner\app\runtime` | same |
| Gateway state: `gateway.db`, logs | `C:\RetirementPlanner\state` | gateway (SYSTEM) and admins only |
| User workspaces | `C:\RetirementPlanner\data\users\<id>` | that user's worker account, SYSTEM, admins |
| Encrypted backups | `C:\ProgramData\RetirementPlannerGateway\backups` | SYSTEM and admins only |
| Backup key | `C:\ProgramData\RetirementPlannerGateway\keys\backup.key` | SYSTEM and admins only |

Rules the tools enforce: the backup folder is never inside OneDrive or another synced folder, a user profile, the
data folder or the install folder; the key is never inside the backup folder; `C:\RetirementPlanning\Version 12`
(the owner's working copy, real data) is never changed by any command here.

## 1. Install order

1. **Runtime and code.** Install Python 3.12 or later *for all users* (so its files are readable by worker accounts,
   not under anyone's profile); this server's runtime uses Python 3.13 from `C:\Program Files\Python313`. Copy the
   release into `C:\RetirementPlanner\app` (a copy without `.git`: the ACL tool refuses to change permissions inside a
   git working copy), then build the runtime from that install's **full path**. Do not use `py -3.x`: the launcher can
   pick a Python installed for your account only (under `C:\Users\...\AppData`). Worker accounts cannot run that one,
   and every worker would then fail to start.
   ```powershell
   & "C:\Program Files\Python313\python.exe" -m venv C:\RetirementPlanner\app\runtime
   Get-Content C:\RetirementPlanner\app\runtime\pyvenv.cfg   # "home" must not be under C:\Users
   $PY = "C:\RetirementPlanner\app\runtime\Scripts\python.exe"
   & $PY -m pip install -r C:\RetirementPlanner\app\requirements.txt -r C:\RetirementPlanner\app\requirements-gateway.txt
   Set-Location C:\RetirementPlanner\app
   ```
2. **Folders.**
   ```powershell
   New-Item -ItemType Directory -Force C:\RetirementPlanner\state, C:\RetirementPlanner\data | Out-Null
   ```
3. **Permissions (`acl setup`, then `acl check --forbid`).** The service runs as LocalSystem, so the gateway SID is
   SYSTEM (`S-1-5-18`); say so explicitly (the default would be your own account).
   ```powershell
   & $PY -m src.gateway.acl setup --data-root C:\RetirementPlanner\data --gateway-db C:\RetirementPlanner\state\gateway.db `
       --install-dir C:\RetirementPlanner\app --backup-dir C:\ProgramData\RetirementPlannerGateway\backups --gateway-sid S-1-5-18
   & $PY -m src.gateway.acl check --data-root C:\RetirementPlanner\data --gateway-db C:\RetirementPlanner\state\gateway.db `
       --install-dir C:\RetirementPlanner\app --backup-dir C:\ProgramData\RetirementPlannerGateway\backups --gateway-sid S-1-5-18 `
       --forbid "C:\RetirementPlanning\Version 12"
   ```
   `--forbid` only *checks*; if it fails for the owner's working copy, fix that by hand (this runbook never changes it).
   Re-run `acl check` after the first user signs in, after a restore, and after any upgrade.
4. **Backup key** (once; never overwritten; creates and locks the `keys` folder when it does not exist):
   ```powershell
   & $PY -m src.gateway.ops backup-key create --key-file C:\ProgramData\RetirementPlannerGateway\keys\backup.key `
       --backup-dir C:\ProgramData\RetirementPlannerGateway\backups --data-root C:\RetirementPlanner\data
   ```
   **Copy the key file offline now** (a USB stick in a safe and a password-manager attachment). It exists nowhere else.
   Without it every backup is unreadable; with it the backup folder alone is useless to a thief. Test the copy by
   running the section 5 restore drill with the copied file.
5. **Service config** `C:\RetirementPlanner\state\gateway.json` (forward slashes are fine). The destination and key
   settings live **only here**; there is no web setting for them, so only a Windows administrator can change them:
   ```json
   {"log_file": "C:/RetirementPlanner/state/logs/gateway.log",
    "argv": ["--db", "C:/RetirementPlanner/state/gateway.db",
             "--funnel-port", "5065",
             "--public-origin", "https://hartzmanpc72024.<tailnet>.ts.net:8443",
             "--data-root", "C:/RetirementPlanner/data",
             "--launcher", "per-account",
             "--install-dir", "C:/RetirementPlanner/app",
             "--python", "C:/RetirementPlanner/app/runtime/Scripts/python.exe",
             "--backup-dir", "C:/ProgramData/RetirementPlannerGateway/backups",
             "--backup-key-file", "C:/ProgramData/RetirementPlannerGateway/keys/backup.key",
             "--backup-hours", "24", "--backup-keep", "14"]}
   ```
   Lock the file to admins: `icacls C:\RetirementPlanner\state /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F"`.
   The gateway refuses to start (exit 2, in the log) when the destination is a synced, profile, data or install folder,
   when `--backup-dir` has no `--backup-key-file`, or when the key is missing, unreadable or inside the backup folder.
6. **First admin** (a hidden password prompt; refused once any admin exists):
   ```powershell
   & $PY -m src.gateway.cli create-admin --db C:\RetirementPlanner\state\gateway.db --username owner
   ```
7. **Service** (the `$PY` that runs `install` is the Python the service uses):
   ```powershell
   & $PY -m src.gateway.service install --config C:\RetirementPlanner\state\gateway.json
   & $PY -m src.gateway.service start
   & $PY -m src.gateway.service status
   ```
   The service starts automatically at boot and is restarted by Windows three times, 10 seconds apart, when the
   process dies (failure counter resets after 24 h). The gateway log rotates at 5 MB, five files kept.
8. **Funnel** (only with the owner's approval: it publishes the gateway to the internet). The reporter keeps 443; the
   planner uses 8443. Dry run first, then apply, which checks before and after:
   ```powershell
   & $PY -m src.gateway.ops funnel check --config C:\RetirementPlanner\state\gateway.json
   & $PY -m src.gateway.ops funnel apply --config C:\RetirementPlanner\state\gateway.json --external-port 8443          # prints the command
   & $PY -m src.gateway.ops funnel apply --config C:\RetirementPlanner\state\gateway.json --external-port 8443 --yes
   ```
   It runs `tailscale funnel --bg --https=8443 http://127.0.0.1:5065`. It refuses 443, ports 5057/5058, and any
   configuration where Funnel or Serve already points at a worker port, the reporter's local port 5057, the gateway's
   local listener, or anything but 5058 on 443. It never runs `tailscale funnel reset` (that would also remove the
   reporter). To withdraw: `... funnel off --external-port 8443 --yes`. Run `funnel check` after every change to
   Tailscale and from time to time: it exits 1 on a problem and also when Tailscale cannot be read (unverified).
9. **No-sleep policy** (only with the owner's approval; the first command only reads):
   ```powershell
   & $PY -m src.gateway.ops power show
   & $PY -m src.gateway.ops power apply --state-file C:\RetirementPlanner\state\power_before.json          # dry run
   & $PY -m src.gateway.ops power apply --state-file C:\RetirementPlanner\state\power_before.json --yes
   & $PY -m src.gateway.ops power revert --state-file C:\RetirementPlanner\state\power_before.json --yes
   ```
   Sets the active plan's AC standby and hibernate timeouts to never (the screen may still turn off) and remembers
   the originals for `revert`. Measured on the owner's PC on 2026-11-16: already "never" on AC, so nothing to apply there.
10. **Verify**: sign in at `https://<node>.ts.net:8443` from another network, enrol two-factor, open
    `https://<node>.ts.net:8443/api/auth/admin/health` while signed in as the admin.

## 2. Daily operation

* **Health**: `GET /api/auth/admin/health` while signed in as an admin (a browser tab is enough). It is admin-only, not
  loopback-only, because behind Funnel every internet request arrives from 127.0.0.1 and every worker (a different,
  untrusted user) can also reach loopback. It shows gateway status and uptime, schema version, running workers, build
  queue (running, waiting), free space on the data and backup volumes, and the last backup result, with a `warnings` list
  (low disk under 10 percent or 5 GB, backup errors, no complete backup within two intervals, backups not configured,
  many failed sign-ins). Its `sign_in` block shows failed sign-ins in the last 10 minutes; above 50 it warns and the
  Audit log gets one `login failure surge` event per window. That is detection only: sign-in is throttled per address
  and per username, never for everyone (security review P7-O4).
  From the server without signing in: `ops health --config ...` prints disk and newest-backup age only.
* **Logs**: `C:\RetirementPlanner\state\logs\gateway.log` (rotating); each user's `local_state\logs\app.log`
  (1 MB x 3) and `worker_console.log` (one run, plus `.1`). The gateway trims an idle user's console log above 5 MB and
  removes old rotated copies hourly. Logs mask account numbers; do not paste them into chat without reading them.
* **Audit**: the Admin console's **Audit log** page (admins), or `GET /api/auth/admin/audit`.
* **Service**: `& $PY -m src.gateway.service status|stop|start`.
* **Scheduled Financial Insight update (optional)**: with `--insights --insights-schedule 17:30` (server local time; off by
  default, there is no per-user switch) the gateway asks each active, non-disabled user's own worker to run the same
  read-only update as the **Update** button, one user at a time, every weekday after the cutoff. Pick a cutoff after 21:00
  UTC (5 pm New York), because "due" is the page's own rule: the newest log entry is older than the last weekday 21:00 UTC.
  A pass runs hourly until six hours after the cutoff; a failed or build-busy user is retried on the next pass, then left
  until tomorrow. Workers it had to start are released when the user has no signed-in session. **Missed days are not
  backfilled** (a gateway that was down, or a failed day, leaves that day without an entry). The health report's
  `insights_schedule` line shows the last run time, users updated and users failed (a failure adds a warning), and the
  Audit log has one `insights_scheduled_update` event per pass with user ids and counts only. Design: `src/gateway/insights_schedule.py`.

## 3. User account lifecycle

All steps except break-glass are in the **Admin console** at `https://<node>.ts.net:8443/gateway/admin` (an admin with
two-factor; the old `/gateway/users` address redirects there). The console lists people from `gateway.db`, adds and edits
them in a dialog, and shows the audit log under **Audit log**. Settings, process start/stop and shutdown are not in it
and never will be: they stay with the gateway CLI and configuration. Every action is in the audit log with the admin's
name. Before upgrading the server code, copy `C:\RetirementPlanner\state\gateway.db` aside (the console adds no
schema change in this phase, but the copy is the rollback for later ones). The console page needs the
`admin_app\frontend\users.js` and `admin.css` files from the same code drop as `src\gateway`; if either is missing the page
loads blank and the gateway log says `admin console file missing`.

| Task | How | What happens |
|---|---|---|
| **Create** | Admin console, Add person: username, display name, role, a one-time temporary password (say it to them out of band) | Account in `gateway.db`; Windows account `rpw_<id>` and the locked-down folder are made automatically. At first sign-in the user must choose a new password **and enrol two-factor** (QR code or key); nothing else is reachable until then. |
| **Disable** | Admin console, Edit, Password, sessions and removal, Disable | Sessions end at once, the worker stops, the Windows account is disabled, data is kept. Enable reverses it. |
| **Delete** | Admin console, Edit, Password, sessions and removal; type the person's username to enable Delete (cannot be undone: it says their plans and data are deleted) | Worker stopped, a last encrypted snapshot `<stamp>.user<id>.rpbak` taken, the Windows account, its rights, profile and the `data\users\<id>` folder removed. Verify: `net user rpw_<id>` says no such user, the folder is gone, `ops backup list` shows the snapshot. **The user's data still sits in that snapshot and in every retained full backup** (14 days with the defaults). To purge sooner, delete the snapshot and the older `*.rpbak` files you accept losing. |
| **User password** | The user: `/gateway/account`. If forgotten: admin, reset password (a new temporary one; they must change it) | Sessions end. |
| **Lost phone** | Admin, reset two-factor | They re-enrol at next sign-in. |
| **Locked out** | Admin console, Edit, Unlock (shown while they are locked) | Lockout is 5 failures for 15 minutes otherwise. |
| **Second admin** | Admin console, Edit, Role: Administrator, Save | Any admin can promote or demote; the last active admin cannot be demoted, disabled or deleted. Keep **two** admins so a lost phone is a reset, not an incident. |
| **Break-glass** (every admin locked out) | On the server: `& $PY -m src.gateway.cli break-glass --db C:\RetirementPlanner\state\gateway.db --username owner` | Hidden prompt for a new password; two-factor cleared (re-enrol at next sign-in), account unlocked and enabled, sessions ended, audited as `cli:<windows user>`. Only a Windows administrator on the server can do it. |
| **Worker account passwords** | Automatic: rotated every `--account-rotate-days` (default 90) with `NetUserChangePassword`; never shown or logged | Nothing to do. There is no manual command. |
| **Shared price-provider key** | Set the machine environment variable, then restart the service | Passed to workers with `--pass-env`; never put on a command line. |
| **Backup key** | See section 4 | |
| **Two-factor deadline** (every account, from the Phase 9 release) | Nothing to do if they enrol in time | An account must enrol two-factor within 72 hours of creation or of an admin reset (password or two-factor). After that the password is refused with the usual error and the Audit log says `reason enrol_overdue`; reset the password to give a fresh 72 hours. Accounts that had not enrolled when the release was installed got 72 hours from the upgrade. |
| **Shared views on or off** | Add `--shared-views` to the service's command line (it needs `--insights` and `--data-root`; the service refuses to start otherwise) and restart. **Do not turn it on until the Phase 9 release checklist in `multi-user-shared-view-security-review.md` is complete.** Settings: `--share-default-days` (90), `--share-max-days` (365), `--share-max-mb` (8), `--viewer-idle-minutes` (10), `--viewer-max-hours` (2), `--max-shares-per-owner` (10), `--max-viewers-per-sponsor` (5) | Off: every owner and viewer page answers 404 and nothing is published; rows and records are kept, and turning it on again restores them. On: members see **Share…** in Financial Insight; records live in `<data root>\shares\`, which `acl setup` locks to the gateway and `acl check` walks. |
| **Add viewer** (only with `--shared-views`, which stays off until the Phase 9 release checklist is complete) | Admin console, Add viewer: display name, username, temporary password, the sponsoring member, access end (default 90 days) | A low-privilege account that can only read the shared views its sponsor grants it. No Windows account, folder or worker is created, and a viewer can never be made an admin. Resetting a viewer's password or two-factor suspends their shares until the owner enables each one again. Deleting a member deletes the viewers they sponsor. |

## 4. Backups

**What**: every `--backup-hours` (24) the gateway writes one encrypted file `<UTC stamp>.rpbak` holding every user's
`local_state\app.db` and every plan file their plan list names (`plan.rpx`, `plans\*.rpx`, `saved_plans\*.rpx`; the demo plan is left out), each plan's Financial Insight history log, pass-through decisions and live-snapshot settings (`output\plans\<plan id>\insights\`; archive format 3; the FI balances database is rebuilt, not backed up; a file over 64 MB is skipped and listed in the backup errors) plus `gateway.db`, taken with the SQLite backup API (consistent while workers
write), verified by reading it back before it is accepted. `--backup-keep` (14) full sets are kept. AES-256-GCM,
per-archive key from the key file; nothing is written unencrypted. A user deletion also writes a `.user<id>.rpbak`.

```powershell
& $PY -m src.gateway.ops backup run --config C:\RetirementPlanner\state\gateway.json     # a set right now (also fine while the service runs)
& $PY -m src.gateway.ops backup list --config C:\RetirementPlanner\state\gateway.json
& $PY -m src.gateway.ops backup verify --config C:\RetirementPlanner\state\gateway.json --archive <file>
```

**Restore one user** (stop the service first: a running worker blocks the restore, by design; no other user is touched):
```powershell
& $PY -m src.gateway.service stop
& $PY -m src.gateway.ops restore --config C:\RetirementPlanner\state\gateway.json --archive <file> --user <id>
& $PY -m src.gateway.acl check ...      # as in step 3 of the install
& $PY -m src.gateway.service start
```
The user's previous files are kept as `*.before-restore-<stamp>`; delete them when satisfied. A format 2 archive is one point in time for all of the user's plans, so plans made after the backup are moved aside too (they stay as `*.rpx.before-restore-<stamp>` and still count toward the user's disk quota until deleted); older format 1 archives restore `plan.rpx` and `app.db` only. A format 3 archive also restores the Financial Insight files and moves aside live ones it does not hold; a format 2 archive leaves the live Financial Insight files as they are. A wrong key or a
damaged or truncated archive is refused with exit 1 and **nothing is changed**.

**Restore `gateway.db`**: `restore --archive <file> --gateway-db-out C:\RetirementPlanner\state\gateway.restored.db`
(never writes over the live file), then with the service stopped rename the old file aside and the new one into place.

**Shared views and backups (Phase 9):** share rows (who shares what with whom, expiry, state) travel inside `gateway.db`.
The published records under `<data root>\shares\` are **not** backed up: they are rebuilt by republishing. A restored
`gateway.db` therefore has every shared view **Suspended: restored**, with nothing to serve, and a share revoked since
the backup stays revoked. Each owner opens Shared views and chooses Enable, which republishes from their current data.
Restoring one user (`--user`) does not touch shares.

**Restoring on a rebuilt machine (or another account):** `gateway.db` holds DPAPI blobs, which open only for the account
and machine that sealed them: the worker account passwords (the gateway recreates them) and, since P7-O1, every user's
TOTP secret. After the swap the service starts and logs `the TOTP secret of user id(s) ... cannot be opened here`; those
users cannot pass the second factor until an admin resets their two-factor on the Users page and they enrol again. Their
passwords and plans are unaffected. Restoring on the same machine and account needs nothing. Archives written before the
upgrade still contain clear-text TOTP secrets until they age out of `--backup-keep`.

**Drill** (do it once now, then quarterly): restore a throwaway user from last night's archive with the *offline copy*
of the key, and confirm the plan opens. For a user with several plans also check that the plan list shows every plan without "file missing", that each plan switches, and that one build finishes. For a user with Financial Insight history, open `/insights/` after the restore and check that the history chart reaches the archive's date and that a pass-through decision made before the backup is still applied. Take a manual `backup run` right after upgrading to the multi-plan release: the first format 2 set is the first one that protects plans stored in `saved_plans\`.

**Shared-view restore drill** (with the Phase 9 release, once before turning `--shared-views` on): restore
`gateway.db` from last night's archive into a scratch file with `--gateway-db-out`, open it with
`sqlite3 <file> "SELECT state, state_reason, count(*) FROM shares GROUP BY 1, 2"`, and check that no row is `active`
(every former active share reads `suspended | restored`). Delete the scratch file afterwards.

**Off-server copy**: the `.rpbak` files are safe to copy anywhere (encrypted; the key is separate), including to an
external disk or a cloud folder *you copy to by hand*. The gateway itself refuses to write into a synced folder, so a
sync client never sees partial files. A disk failure takes the data, the backups and the key folder with it unless you
copy the encrypted folder and the key off the machine.

**Key rotation**: `backup-key create` with a new file name, point `--backup-key-file` at it, restart the service. Keep
the old key for as long as old archives are retained (the archive header says which key it needs; the error names a wrong key).

## 5. Upgrades and rollback

Startup migration swallows failures by design, so upgrade with the offline command instead of letting each user
migrate lazily on their next sign-in.

`tools/upgrade_installed_server.ps1` runs steps 1 to 5 below, in that order, from your checkout (it self-elevates and
installs `origin/main`). It stops at the first failed step, including a failed fetch, `acl setup` or `acl check`. A stop
before the export starts the service again; a later stop leaves the service stopped, and you fix the cause or roll back
(below). It does not tell users or open the health page for you.

1. Tell users; stop the service: `& $PY -m src.gateway.service stop`.
2. Full backup with the *old* code: `ops backup run ...` and keep its file name.
3. Copy the new release over `C:\RetirementPlanner\app` (elevated: `powershell -ExecutionPolicy Bypass -File "<checkout>\tools\export_main_to_install.ps1"`, which
   exports `main` with `git archive` and copies without deleting; `-DryRun` first), update the runtime (`pip install -r requirements.txt -r requirements-gateway.txt`), run
   `acl setup`/`check` as in step 3.
4. Migrate everyone with the *new* code (it snapshots each user first, migrates in a fresh process per user, never
   stops at the first failure, and migrates `gateway.db` when it opens it):
   ```powershell
   & $PY -m src.gateway.ops migrate-all --config C:\RetirementPlanner\state\gateway.json --report C:\RetirementPlanner\state\migrate_report.json
   ```
   The report lists each user as `OK`, `FAILED` (with the reason) or `SKIPPED` (a worker was running, or no folder), the
   snapshot used, and ends `RESULT: ...`. Exit 0 means every user migrated; 1 means look at the report. A user whose
   snapshot could not be taken is **not** migrated.
5. Start the service and open the health page.

The Phase 9 release moves `gateway.db` to schema version 4 the first time it opens it (every account becomes a member;
an older gateway refuses version 4, so the rollback is the copy of `gateway.db` taken before the upgrade). It also
starts the 72-hour two-factor deadline for every account that has not enrolled (section 3).

**Rollback** (any time after step 2): stop the service; for each affected user
`ops restore --archive <their ...user<id>.rpbak from the report> --user <id>`; for `gateway.db`
`restore --archive <the step-2 full backup> --gateway-db-out <new file>` and swap it in (the new code may have migrated
`gateway.db` beyond what the old code reads); put the previous release back into `app`; `acl check`; start the service.
The rollback is tested with fixture users in `tests/test_gateway_ops_functional.py`.

### 5.1 Verifying an installed build (isolation gate, per-account)

After installing or upgrading, and before opening the server to users, run from an **elevated** PowerShell (owner's
say-so; it creates and removes throwaway `rpwtest_` accounts and a `C:\rpwtest_*` folder, never `data` or `state`):

```
powershell -ExecutionPolicy Bypass -File C:\RetirementPlanner\app\tools\run_isolation_on_installed_build.ps1
```

Add `-Filter attacks` (any pytest `-k` expression) to run part of it, `-KeepVenv` to keep the throwaway test venv.
It runs the three isolation modules and the worker-account suite as SYSTEM from the installed folder with real
per-account workers. Read `C:\Windows\Temp\rpw_isolation_installed.txt`; the printout must end with empty accounts,
folders and profiles lists and "clean". Afterwards `net user` should show no `rpwtest_` account.

### 5.2 Phase 9 (shared views): the owner's elevated run, before and at the upgrade

These steps are the release checklist's owner items in `multi-user-shared-view-security-review.md` (section 9).
`--shared-views` stays off throughout.

**Do not install the Phase 9 build onto `C:\RetirementPlanner\app` before it is merged and you are upgrading.** The next
service start on that code moves the live `gateway.db` to schema 4. It also starts the 72-hour two-factor deadline for
every account that has not enrolled (section 3). Part A therefore runs against a separate test copy and touches
neither `data`, `state` nor the running service.

**Part A: before the merge, against a separate test copy** (elevated PowerShell; `$repo` is your checkout):

1. Fetch the branch:
   ```powershell
   $repo = "C:\RetirementPlanning\Version 12"
   git -C $repo fetch origin claude/shared-view-build
   ```
2. Export it into its own folder. `-Force` only gets past the "service is running" guard, and the target is not the live
   install. The script must end with `tools\run_isolation_on_installed_build.ps1: True` and
   `tests\isolation_per_account.py: True`.
   ```powershell
   New-Item -ItemType Directory C:\rp-phase9-test\app -Force | Out-Null
   powershell -ExecutionPolicy Bypass -File "$repo\tools\export_main_to_install.ps1" -Ref origin/claude/shared-view-build -InstallDir C:\rp-phase9-test\app -Force
   ```
3. Give the copy its own runtime, built on **the same Python as the live runtime**. Per-account workers run as other
   Windows accounts, so the base Python must be installed for all users (for example under `C:\Program Files`).
   A Python installed for one account only (under that account's `AppData`, which `py` may pick) cannot be run by the
   worker accounts. Every worker then fails to start, and the isolation run reports "Your planner could not be
   started". Read the base from the live runtime instead of guessing:
   ```powershell
   $base = (Select-String C:\RetirementPlanner\app\runtime\pyvenv.cfg -Pattern '^executable = (.+)$').Matches[0].Groups[1].Value.Trim()
   & $base -m venv C:\rp-phase9-test\app\runtime
   $PY = "C:\rp-phase9-test\app\runtime\Scripts\python.exe"
   & $PY -m pip install -r C:\rp-phase9-test\app\requirements.txt -r C:\rp-phase9-test\app\requirements-gateway.txt
   ```
4. Run the per-account isolation run against the copy. It covers four isolation modules (the shared-view module
   included) and the worker-account suite, takes several minutes, and runs as SYSTEM. It creates and removes
   throwaway `rpwtest_` accounts and `C:\rpwtest_*` folders.
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\rp-phase9-test\app\tools\run_isolation_on_installed_build.ps1 -InstallDir C:\rp-phase9-test\app
   ```
5. Read `C:\Windows\Temp\rpw_isolation_installed.txt`. Pass looks like this:
   - `test_multi_user_isolation_shared_view_integration.py` reports 7 passed, and every other module passes;
   - the tail ends with empty account, folder and profile lists and "clean";
   - `net user` shows no `rpwtest_` account.

   Worker and gateway logs from a failed run are in `C:\Users\Public\rpw_isolation`. If every module fails with "Your
   planner could not be started" and no `worker_console.log` exists there, the workers never started. Check step 3's
   base Python first (`Get-Content C:\rp-phase9-test\app\runtime\pyvenv.cfg`). Remove any `rpwtest_` profile left
   behind before running again:
   `Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like '*\rpwtest_*' } | Remove-CimInstance`.
6. Rehearse the migration on a copy of the live `gateway.db`. The copy is taken with SQLite's backup API, which only
   reads the live file, so it is safe while the service runs.
   ```powershell
   cd C:\rp-phase9-test\app
   & $PY -c "import sqlite3; s=sqlite3.connect(r'file:C:\RetirementPlanner\state\gateway.db?mode=ro', uri=True); d=sqlite3.connect(r'C:\rp-phase9-test\gateway-rehearsal.db'); s.backup(d); d.close(); s.close()"
   & $PY -c "import time; from src.gateway.store import GatewayStore; s=GatewayStore(r'C:\rp-phase9-test\gateway-rehearsal.db'); u=s.list_users(time.time()); print('schema', s.schema_version()); print('kinds', sorted({x['kind'] for x in u})); print('accounts', len(u)); print('not yet enrolled (get the 72-hour clock):', [x['username'] for x in u if x['totp'] != 'enrolled'])"
   ```
   Expect `schema 4`, `kinds ['member']` and today's account count. The last line names who will have 72 hours to
   enrol after the upgrade: warn them, or have them enrol first. This rehearsal cannot prove sign-in, because the
   two-factor secrets open only for the service's account (SYSTEM). Sign-in is checked in step 10.
7. Clean up: `Remove-Item C:\rp-phase9-test -Recurse -Force`.

**Part B: at the upgrade, after the merge, flag still off:**

8. Upgrade as in section 5, steps 1 to 5. Before step 1, copy `C:\RetirementPlanner\state\gateway.db` aside: an older
   gateway refuses schema 4, so that copy is the rollback.
9. In step 3, `acl setup` now creates and locks `C:\RetirementPlanner\data\shares`. `acl check` (section 1, step 3)
   must say `OK`; any finding that names `data/shares` is a failure.
10. Sign in through the Funnel address to confirm sign-in works after the migration.
11. Run step 4 again against the real install, without `-InstallDir`.
12. Restore drill (section 4, "Shared-view restore drill"): restore last night's `gateway.db` into a scratch file with
    `--gateway-db-out`, then:
    ```powershell
    & $PY -c "import sqlite3; print(sqlite3.connect(r'<scratch file>').execute('SELECT state, state_reason, count(*) FROM shares GROUP BY 1, 2').fetchall())"
    ```
    With the flag off nobody can create a share, so expect `[]` (the table exists and is empty). The full check that
    every share reads Suspended: restored needs shares to exist. Like the measurements on your real plan, it waits for
    a controlled trial with the flag on.

## 6. Incident quick reference

| Symptom | First look |
|---|---|
| Nobody can sign in from outside | `ops funnel check`; `tailscale status`; `service status`; health page from the server's own browser |
| Many users get "The server is busy" or 503 | too many connections or password checks at once: `--max-connections`, `--hash-concurrency` in `gateway.json`; look for a flood in `gateway.log` first |
| Log says a TOTP secret "cannot be opened here" | `gateway.db` came from another machine or account: reset that user's two-factor (section 4, rebuilt machine) |
| Gateway will not start | the end of `gateway.log` (a refused backup destination or key prints the reason); exit code 2 means configuration |
| `acl check` fails | the listed folder; never widen a permission to make it pass |
| Health warns "no complete backup" | `ops backup run`; check disk space; check the key file is readable by SYSTEM |
| Disk low | the backup folder first (`--backup-keep`), then user `output` folders; never delete inside `data\users` by hand |
| Health warns "many failed sign-ins", or the Audit log shows `login failure surge` | someone is guessing passwords; no one is refused for it (one event per 10-minute window). Look at the `login failed` events for the addresses and usernames: each address and each username is slowed on its own after 10 failures, and 5 wrong passwords lock that account for 15 minutes. Disable an abusive account; block an address at the Funnel or firewall if it persists |
| A user's workbook build is stuck | health page queue; the build limit is `--max-build-minutes` (30) |
