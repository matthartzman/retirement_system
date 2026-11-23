# Financial Insights (FI)

Local trend dashboard for the Retirement Planning System: balance trends, liquid and net-worth history, realized
gains and recent projections, served from the weekday trends log. Entry point: `python financial_trends_reporter/main.py`.

## Ports

- **5057**: the owner's PC. Loopback only, no password; every request needs the per-boot local token (open it from the desktop shortcut, or run `python financial_trends_reporter\main.py --print-open-url`).
- **5058**: the remote listener for Tailscale Funnel. Sign-in required. See
  `documentation/reference/TRENDS_REMOTE_ACCESS_RUNBOOK.md`.

## Accounts live in the Admin app, not here

FI does not own accounts. People sign in against the shared identity store (`src/identity/`,
`local_state/identity.db`) and are admitted only if they hold a Financial Insights (`insights`) grant. Adding people,
resetting passwords, disabling, access expiry, two-factor resets, ending sessions, the activity log and each person's
money view (dollars, percent or both) are managed in the Admin app:

```
python -m admin_app                              # then open http://127.0.0.1:5056
python -m admin_app create-admin --username NAME # first administrator
```

Two-factor sign-in (TOTP with recovery codes) is enrolled by the person at sign-in when the Admin app requires it for them; an
administrator can reset it in the Admin app. A password reset, disable or grant removal ends that person's FI
sessions on their next request, even though the two apps are separate processes. The first start of FI or the Admin
app migrates a legacy `data/access.db` into the identity store.

The owner-only People and Activity pages and the `/api/people*` and `/api/activity` routes that used to live here were
removed; `/api/people` answers 404.

Overview of the three apps: `documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md` section 3.7.
