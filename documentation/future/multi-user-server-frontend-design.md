# Multi-user server: frontend (Phase 5)

Status: implemented

Plan: `multi-user-server-plan.md`, Phase 5. Code: `frontend/js/remote_mode.js`, `frontend/js/remote_files.js`.

## Remote-mode detection

One place: `window.RetirementRemote.enabled`. `remote_mode.js` is loaded right after `render_hooks.js`, wraps
`window.fetch` once, and pings `/api/ping` at load. A worker in remote mode answers `{"remote_mode": true}`
(`src/server/base_routes.py`), the gateway forwards it, and the wrapper turns the flag on, adds class
`remote-mode` to `<html>`, and re-renders. Nothing runs under pywebview or `file://`; against a desktop server the
ping has no `remote_mode`, so desktop behaviour is unchanged. No gateway page injection is needed.

## 401 handling

The `fetch` wrapper is the single place, so `api_client.js`, the `api` helper in `admin.js` and every raw
`fetch(` are covered without being edited. A 401 on an `/api/` call (except `/api/auth/login` and `/api/auth/totp`)
goes to `/login?next=<current page>` when remote mode is on, or when the body says `{"authenticated": false}`
(the gateway's shape, which covers a 401 that arrives before the first ping is answered). A plain 401 with no
marker on a desktop server is left alone.

## Session keep-alive

The gateway's idle clock (15 minutes, `store.IDLE_SECONDS`) restarts on every authenticated request, and the
planner pings every 15 seconds (`admin.js` every 5), so before this phase an open tab never expired. Now:

- The status ping is answered locally (last good reply) while the tab is hidden or the user has not touched it for
  a minute, so an idle or background tab stops refreshing the session.
- User activity (key, pointer, touch, tab becoming visible) sends one `GET /api/auth/session` at most once a minute.
- A notice with "Stay signed in" appears at 12 minutes without a successful request, and turns into "Sign in" at
  15. The next API call after expiry gets the 401 and goes to the login page.
- A running build keeps the session alive on purpose: its progress polling is a real request, and the supervisor
  never reaps a worker mid-build.

No backend change was needed.

## Save As, Load, and path-based controls

- Save Plan As downloads `GET /api/plan/download` (saving unsaved changes first). Load Saved Plan uploads the file
  as base64 JSON to `POST /api/plan/upload` in `open` mode; a "Restore From File" button (remote only) uses
  `restore` mode. Files over 47 MiB are refused before they are read.
- Hidden by CSS in remote mode (the worker refuses them): local backups card, Monarch auto-update card, conversion
  notice, System Configuration console card, "Recover previous setup", admin "Clear cache" and "Shut down app".
  The header Exit button becomes Sign out (gateway logout, then `/login`).
- The `127.0.0.1:5050` fallback in `checkAppStatus` is skipped in remote mode.

## Monarch CSV upload

Where the auto-update card lives (Settings, Data & Backups), `monarchUploadCardHtml()` shows a Transactions and a
Balances upload. Each file is sent with `dry_run: true`, the result (counts, date range, masked account names as
returned) is shown, and only "Import N rows" sends the real request. The function carries a comment marking where a
future "Connect Monarch" button goes.

## Queued builds

A start answer with `queued: true` or a `queued-` job id, and progress with `status: "queued"`, show "Waiting for
another build to finish" with the gateway's position text, no animated progress, and no error styling. When the job
becomes real the usual progress takes over. `/api/build/status` is forwarded to the worker and says nothing about
the queue; only the start and progress answers do.
