# Financial Insight: Remote Access Runbook

How the Financial Insight app is reached from outside the home network, and how to run it.
Design: `documentation/future/superpowers/plans/2026-10-27-trends-remote-access-design.md`.

## How it works

- The server listens on two loopback ports. **5057** is the owner's PC: no password, and the only place the People and Activity screens exist. **5058** is for Tailscale Funnel only: every request needs a personal sign-in.
- Everyone, including you on your phone, uses the same `https://<pc>.<tailnet>.ts.net/` link and signs in with their own username and password.
- Remote sessions end after 10 minutes without anyone touching the page. Exit becomes "Sign out" and only ends that person's session.
- The server runs in the background whenever you are logged on to Windows. Exit never stops it.

## One-time setup (you do these; nothing here is done for you)

### 1. Tailscale admin console (https://login.tailscale.com/admin)

1. **DNS** page: turn on **MagicDNS** and **HTTPS Certificates** (accept the notice that machine names appear in public certificate logs).
2. **Access controls** page: make sure the policy file has a `nodeAttrs` entry giving this PC the `funnel` attribute, for example `{"target": ["autogroup:member"], "attr": ["funnel"]}`. Tailscale can add it for you the first time you run the funnel command below.

### 2. On the PC

1. Register the always-on server (PowerShell, from the repo folder):
   `powershell -ExecutionPolicy Bypass -File financial_trends_reporter\tools\launchers\register_trends_server_task.ps1 -Action Register`
   Then, as a separate command: `Start-ScheduledTask -TaskName FinancialTrendsReporter_Server`.
2. Point Funnel at the **remote** port only: `tailscale funnel --bg 5058`
3. Check: `tailscale funnel status` shows `https://<pc>.<tailnet>.ts.net` proxying to `http://127.0.0.1:5058`. Nothing may point at 5057. If it does, run `tailscale funnel reset` and redo step 2. The server also refuses to start if it sees 5057 exposed.
4. Your link is the `https://<pc>.<tailnet>.ts.net/` address from step 3.

### 3. Add people

Open http://127.0.0.1:5057 on the PC, click **People & Activity**, **Add person…**, and give each person a username and a temporary password (10+ characters). They are made to choose their own at first sign-in. Send the link and the temporary password by whatever channel you trust (not both in one message, ideally).

### 4. Choose what each person sees: $ / % / Both

Each person has a **money view** setting in People & Activity (the Add person dialog and the person's row):

- **%** (the default for new people): amounts appear only as percentages. Account balances and spending are shown as a percent of net worth, the Net Worth and Liquid charts as percent change since the start of the scope, spending as a share of total spending, and flows as a share of the liquid balance. Their data is scaled on the server before it leaves the PC, so no dollar figure is sent to their device. Each card names its base once in its heading (for example *% of net worth*, *% of total*, *share of gross assets*) and the cells show bare percentages.
- **$**: dollars only, as on the PC.
- **Both**: dollars, with a **$ | %** toggle in the page header to switch.

A %-only person does **not** see merchant detail, individual transactions or the reconciliation section of Current Snapshot, and the transaction list route answers 403 for them. They also get no share counts, purchase prices or index levels: a share count times a public price, or a public level against its scaled value, would give back the hidden scale and every dollar figure. Notes that quote amounts (for example the investment-transfer review) are left out or reworded.

Changing a person's setting applies on their next tap; they do not need to sign in again.

Adding any new `/api/` route fails `tests/test_trends_percent_view_leak_guard_regression.py` until the route is classified (scaled, passed through, withheld or owner-only), so a new route cannot leak dollars to a %-only person by accident.

## Day to day

- **Stop the server:** `financial_trends_reporter\tools\launchers\stop_trends_server.ps1`. **Restart:** `Start-ScheduledTask -TaskName FinancialTrendsReporter_Server`.
- **Reset a forgotten password / remove someone:** People & Activity, Reset password or Delete. Their open sessions end on their next tap.
- **Read the log:** People & Activity, Activity (filter by exact name).
- After an unattended reboot the link is down until you log on to the PC.
- Double-clicking `START_TRENDS_APP.bat` while the server is already running just opens the browser.

## Still to confirm on the real setup

Funnel's real `Host` header and whether it forwards the visitor's address (`X-Forwarded-For`; the Activity log's "From" column stays blank if not). If sign-in works and the From column fills in, nothing is needed; otherwise note it here.

## Phone test checklist (off Wi-Fi, mobile data)

1. Open the link: you see the sign-in page, not the app.
2. Wrong password: a generic "Incorrect username or password."
3. Sign in with a temporary password: you are asked to choose a new one; afterwards the app loads.
4. Current Snapshot and a chart view load.
5. Leave the page untouched for 10 minutes: the next tap returns to sign-in.
6. Sign out: back at sign-in; the **back** button does not show data.
7. Sign in as a second person on another device: signing out of one does not affect the other.
8. On the PC, delete the second person: their device lands on sign-in on its next tap.
9. On the phone, open `<link>/api/history` while signed out: it must say sign-in required, not show data. Open `<link>/api/people`: it must say not found.
10. On the PC, Activity shows the sign-ins, views and actions above.
11. Reboot the PC, log on, and confirm the link works again without starting anything by hand.
