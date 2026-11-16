# Multi-user server: Phase 6 measurements and checks

Status: draft (the owner-run measurements below are open; each says what was and was not run)
Date: 2026-11-16

Successor note to the "what was not measured" list of `multi-user-server-phase0-results.md` (that file is not
edited). Machine changes (any `tailscale funnel` or `serve` change, a service install, a power-plan change, an ACL
change, a reboot) are made only with the owner's approval, with throwaway names, and undone and verified.

## Results so far

| Check | Result | Evidence |
|---|---|---|
| Mandatory TOTP at first login, through the gateway | **Verified** (no rebuild): a new account signs in with its temporary password, is held on a "pending" session that reaches only the enrolment page and `/api/auth/*` (any planner route returns 401 and `/` redirects to `/gateway/enrol`), must enrol and confirm a code, gets a rotated cookie and CSRF token, and only then reaches the upstream; wrong codes lock the account and codes cannot be replayed. | `tests/test_gateway_auth_functional.py::test_first_login_requires_totp_enrolment`, `::test_enrolled_user_must_pass_totp_and_wrong_codes_lock_the_account`, `::test_totp_code_cannot_be_replayed`, and the real-process `tests/test_multi_user_isolation_integration.py` (users created with TOTP, signed in over HTTP) |
| Funnel layout on the owner's PC, read-only | `tailscale serve status --json` shows exactly one entry, external 443 -> `http://127.0.0.1:5058` (the reporter), Funnel on. The new `ops funnel check --funnel-port 5065` parsed it and reported OK. | run 2026-11-16, nothing changed |
| No-sleep policy, read-only | `ops power show` on the owner's PC: AC standby 0 s, hibernate 0 s (never). Nothing to apply. | run 2026-11-16, nothing changed |
| Service restart on failure | Confirmed in code: three restart actions 10 s apart, counter reset after 24 h, start type automatic. Not exercised by killing the process on the server. | `src/gateway/service.py` `install_service`; `tests/test_gateway_service_install_integration.py` is `elevated` (skipped by default) |

## Open measurements (owner, on the real server)

### A. Real external Funnel download bandwidth for a large workbook

Why: Phase 0's 33 to 102 MB/s was node-to-itself, not a valid figure; Funnel traffic leaves over the home uplink.

1. Elevated PowerShell on the server. Make a ~20 MB test file in a throwaway folder (never `C:\RetirementPlanning\Version 12`):
   `New-Item -ItemType Directory C:\funnel_test; fsutil file createnew C:\funnel_test\blob.bin 20971520`
2. Serve it on the throwaway Funnel port 8443 only if the gateway is not using it (otherwise use 10000):
   `python -m http.server 5099 --bind 127.0.0.1 --directory C:\funnel_test` in one window, and in another
   `tailscale funnel --bg --https=8443 http://127.0.0.1:5099`. (Run `ops funnel check` first; 443 must remain the reporter.)
3. From a **different network** (a phone on cellular, not Wi-Fi): fetch `https://<node>.ts.net:8443/blob.bin` three times
   and write down seconds for each (`curl -o NUL -w "%{time_total} %{speed_download}\n" <url>` on a laptop, or the
   browser's download time). Also run a speed test on the server for its upload rate.
4. Undo and verify: `tailscale funnel --https=8443 off`; stop the python server; `tailscale serve status --json` shows only
   443 -> 5058 again; delete `C:\funnel_test`.
5. Record below: three times, MB/s, uplink speed, and whether a typical workbook (size from a real build) would take
   an acceptable time for users.

Result: **not measured**.

### B. Tailscale and Funnel after a reboot with nobody logged in

1. Before: `tailscale funnel status` (or `serve status --json`) and note the entries; confirm the Tailscale service is
   Automatic: `Get-Service Tailscale | Select Status,StartType`.
2. Make sure no one will sign in at the console: reboot from an elevated shell (`shutdown /r /t 30`), then **do not log in** at
   the machine (use another PC's remote tools only for reading, not for a session on this one).
3. From another network, after 3 to 5 minutes, fetch `https://<node>.ts.net/` (the reporter) and
   `https://<node>.ts.net:8443/login` (the gateway, once it is installed). Check the gateway service came up:
   `Get-Service RetirementGateway`.
4. Then log in locally and compare `tailscale funnel status` with step 1.
5. Record: did both external addresses answer without a login, how long after boot, and anything missing.

Result: **not measured**.

### C. Port 10000 (optional)

Same as A with `--https=10000`; confirm it is reachable from outside. Only worth doing if 8443 turns out to be blocked
for some users' networks. Result: **not tried**.

### D. Service restart on failure, on the server (elevated)

Find the gateway's process id (`Get-CimInstance Win32_Process | Where-Object CommandLine -match 'service.py run' | Select ProcessId`) and stop **only that id** with `Stop-Process -Id <pid> -Force` (never `-Name python`: that would also kill the trends reporter). Within 30 seconds `Get-Service RetirementGateway` should show Running again and the health page uptime should have reset.
Result: **not run**.

## What a future session must not assume

* No external bandwidth figure exists. Phase 7's load test should treat download speed as "unknown, uplink-limited".
* Reboot survival of Funnel and the gateway service is unproven until B is recorded.
