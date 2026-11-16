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

Result (2026-11-16, owner, phone on cellular, Funnel 8443, 20 MB file): each download took **under 2 seconds** (single approximate report, not three stopwatch timings), so **at least ~10 MB/s (~80 Mbps) downstream**. The phone's own speed test was 361 Mbps down, so the true Funnel figure may be higher; the phone's browser rounding means this is a lower bound only. **Upload of the home connection was measured by the phone's test as 4.59 Mbps up, but that is the phone's upload, not the server's.** The server's own uplink was not measured separately; the file arrived fast, so it is at least ~80 Mbps. Undone and verified: Funnel 8443 off, only 443 -> 5058 remains, test server stopped; `C:unnel_test` still to be deleted by the owner.

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

Result (2026-11-16, owner): **Funnel did NOT survive the reboot.** Six minutes after boot the phone on cellular got "This site can't be reached" for https://hartzmanpc72024.tail22bbfa.ts.net/, and `tailscale serve status --json` on the PC returned `{}` (no Serve or Funnel entries at all; before the reboot it held 443 -> 5058). The Tailscale service itself is Automatic and was running, so the node stayed up, but the Funnel configuration was lost. Possible cause (not confirmed): the reporter's 443 entry was created without `--bg` (session-bound) or the config was cleared at boot. Consequence for the server: the gateway's Funnel must be re-applied at boot, e.g. by a scheduled task at startup running `ops funnel apply --yes` (or confirm `tailscale funnel --bg` persists on its own by repeating this test after applying 8443 with `--bg` and rebooting). The trends reporter's own 443 Funnel is also currently down until it is re-created. Not determined: whether the console login mattered (the screenshot was taken after the owner logged in; the phone test was before).

Run started 2026-11-16 (owner approved; reboot issued from the Claude session, so that session ended). **Before:** Tailscale service Running, StartType Automatic; `serve status --json` shows only external 443 -> http://127.0.0.1:5058 with Funnel on; last boot 2026-11-10 14:53; console user AzureAD\MattHartzman (logged in). **After (owner to fill in):** do NOT log in at the PC; from the phone on cellular after 3 to 5 minutes open https://hartzmanpc72024.tail22bbfa.ts.net/ . A reporter page or a 502/bad-gateway both prove Funnel and Tailscale came back (a 502 only means the reporter app itself is not a boot service). Then log in and run `tailscale serve status --json` and compare with the Before line. Record: answered without login (yes/no), minutes after boot, differences.

### C. Port 10000 (optional)

Same as A with `--https=10000`; confirm it is reachable from outside. Only worth doing if 8443 turns out to be blocked
for some users' networks. Result: **not tried**.

### D. Service restart on failure, on the server (elevated)

Find the gateway's process id (`Get-CimInstance Win32_Process | Where-Object CommandLine -match 'service.py run' | Select ProcessId`) and stop **only that id** with `Stop-Process -Id <pid> -Force` (never `-Name python`: that would also kill the trends reporter). Within 30 seconds `Get-Service RetirementGateway` should show Running again and the health page uptime should have reset.
Result: **not run**.

## What a future session must not assume

* No external bandwidth figure exists. Phase 7's load test should treat download speed as "unknown, uplink-limited".
* Reboot survival of Funnel and the gateway service is unproven until B is recorded.
