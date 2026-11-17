# Multi-User Server: Monarch Upload, Per-User Secrets and Disables (Phase 4 design)

Status: draft
Date: 2026-11-16
Plan: `documentation/future/multi-user-server-plan.md` (revision 3), "Phase 4 - Secrets, per-user Monarch and
disables", the Secrets bullet of "Security requirements", and decision 6. Phase 0 results section 7 changed the
order: CSV upload first, Monarch's MCP connector second and optional.

## 1. Monarch CSV upload (built)

A remote user downloads Monarch's own CSV exports in their browser (Transactions > Download CSV; Accounts >
Download balance history) and uploads them. Nothing about Monarch is stored except the imported rows: no
password, no session, no token.

**Route (worker, on the remote allow-list):** `POST /api/monarch/upload`, permission `write_config`.

    {"kind": "transactions" | "balances", "filename": "Transactions.csv",
     "content_base64": "<the file's bytes, base64>", "dry_run": false}

Base64 inside JSON for the same reason as `POST /api/plan/upload`: the worker's CSRF gate accepts only JSON or
text bodies and the stdlib server has no multipart parser. Limits: 16 MiB of decoded file, 250,000 data rows,
UTF-8 (with or without BOM) or Windows-1252, a header row that matches the kind. `dry_run` validates and counts
without writing. Desktop mode can use the same route.

**Response:** `{"success", "kind", "dry_run", "accounts": <count>, "account_names": [masked, at most 200],
"date_range": [first, last]}` plus, for transactions, `rows_read`, `rows_without_id`, `duplicates_in_file`,
`added`, `updated`, `adopted`, `skipped`; for balances, `rows`, `latest_date`, `status` ("ok" | "rejected" |
"dry_run"), `renamed` (masked pairs) and `mapping_seed` (counts per bucket, or null without a seed file).
A rejected balances file (stale export, more than a 20% account drop) is a 400 with `status: "rejected"`. Errors are 400 with `{"success": false, "error": "..."}`; every message is
masked. The route audits `monarch_uploaded` with the kind and counts, never names.

**Normalising.** The extractor's normalisers (`Monarch Extractor/monarch_extract.py:normalize_transaction`,
`clean_key`; `monarch_balances.py:normalize_balances_csv`) are not called: the folder is not a package (its
name has a space), it is not part of the installed or frozen worker, the functions take a file path, and the
modules carry Playwright and repo-folder globals. `src/monarch_upload.py` re-implements the two small functions
on text, and `tests/test_monarch_upload_unit.py` loads the extractor's modules by file path and asserts the two
produce the same rows for the same synthetic input, so they cannot drift apart unnoticed.

**Feeding the existing import shapes.**
- Transactions: raw rows become the extractor's output shape (`id,date,merchant,amount,account,category` plus
  the cleaned extra columns) in memory, then go through `monarch_import.map_monarch_csv_text` with the shipped
  field map, then `ytd_tracking.upsert_transactions_by_monarch_id`. Monarch's `Id` column is required; rows
  without one are counted and skipped (the upsert cannot merge them safely). No `run_id` or mark-delivered step.
- Balances: `monarch_balances_import.import_balances` is split so its guards (stale export, 20% account drop,
  rename migration, import record) run on rows as well as on a file (`import_balance_rows`). Nothing is written
  to disk: the uploaded bytes never leave memory except as rows in the user's own plan file.

**Masking.** Account names can carry numbers. Every account name and error message in a response or log line
goes through `monarch_upload.mask_names`: `account_numbers.mask_text` (cue-based) and then any remaining run of
5 or more digits becomes `…NNNN`. Stored rows keep Monarch's names, because mappings key on them.

## 2. Account mapping seed (built)

Gateway setting `--monarch-mapping-csv <path>`: an admin-curated mapping CSV
(`Monarch,App Location,App Field,Status,Primary Source`, the `monarch_mapping_seed` format). The gateway
validates it at start (parses, at most 1 MiB) and, when a user is created, copies it into that user's workspace
as `local_state/monarch_mapping_seed.csv`. A fresh workspace has no balances, so `seed_mapping` would save
nothing at creation time (it saves only accounts it has seen). The worker therefore runs
`seed_mapping(workspace, csv_path=<that copy>, overwrite=False)` after every accepted balances upload: new
accounts get their admin-suggested match, and a match the user already saved or edited on the Reconcile page is
kept. Mappings stay per user and editable (`/api/reconcile/map`, `/api/reconcile/seed`). Changing the admin file
later affects only users created afterwards.

## 3. Per-user secrets (built)

A worker that runs as its own Windows account keeps its secrets in **its own `app.db` under machine-scope DPAPI**
(`src/dpapi_machine.py`, used by `src/secrets_store.py` in remote mode). It was first built on Windows Credential
Manager, which is that account's own store (Phase 0), but the elevated runs measured it losing entries when the
account's password is rotated (section 3.1), so Credential Manager is **not** used in remote mode. Desktop mode is
unchanged (keyring). What could fall back to a shared store, and what this phase does about it:

| Path | Risk | Remote-mode rule |
|---|---|---|
| Same-account launcher (CI, development) | every worker shares the gateway account's Credential Manager | `secrets_store` refuses (`SecretStoreUnavailable`) unless the worker was started by the per-account launcher, which sets `RETIREMENT_SYSTEM_DEDICATED_ACCOUNT=1`. The supervisor refuses that name in `--worker-env`, so it cannot be faked. |
| Another keyring backend (a `keyrings.alt` file, a `PYTHON_KEYRING_BACKEND` override) | a file in a shared or readable place | a dedicated worker does not use `keyring` at all (it uses the DPAPI store above), and a same-account worker is refused before any backend is looked at; worker environments are built from nothing, so an override is not inherited either. |
| Machine-scope `FMP_API_KEY` etc. | every user gets a key nobody chose to give them | workers get only the OS essentials (`launchers.os_env`) plus what the gateway passes; tested. |
| Key fingerprints in `/api/prices/test-symbol` and the pricing diagnostics | a stable identifier of the shared key | `None` in remote mode. |

### 3.1 What the elevated runs measured (2026-11-16, Windows 11 10.0.26300, owner's machine)

1. **Credential Manager works for a batch-logon worker** (`WinVaultKeyring` with the profile loaded: set, get and
   delete all succeeded, and a fresh logon, a pause and four reads in a row all still saw the entry).
2. **It does not reliably survive a password rotation.** `NetUserChangePassword` with the old password, with no
   logon session open, lost the stored entry in **5 of 9 rotations**; once lost it stayed lost over four further
   reads. Which rotations kept it did not follow any pattern the runs could isolate (a read before the rotation
   kept it twice, but that is two data points).
3. **Launching from an interactive elevated shell is the wrong place to test a worker.** There the gateway process
   has no `SeAssignPrimaryTokenPrivilege`, so `PerAccountLauncher` falls back to `CreateProcessWithTokenW`, and the
   worker cannot initialise `user32.dll` ("not enough memory resources"; `ole32` and `uxtheme` fail too), so
   `_ctypes`, `_ssl` and so `keyring` and any HTTPS call fail with "DLL initialization routine failed". Job limits,
   file ACLs and the desktop name (NULL, empty, `WinSta0\Default`, with and without a Job) made no difference.
   The same worker started as SYSTEM in session 0, which is how the gateway service runs, loads all of them.
   `CreateProcessWithTokenW` also caps the command line at 1024 characters. The elevated credential test therefore
   runs as SYSTEM (`tools/run_elevated_tests_as_system.ps1`) and fails with a clear message elsewhere.
4. The throwaway accounts could not read the repository folder (`C:\RetirementPlanning` is readable by the owner,
   Administrators and SYSTEM only), so the test copies `src` into its own readable folder.

Because user-scope DPAPI keys (and a user-DPAPI file) hang off the same account password, the smallest alternative
that survives rotation is a machine-scope key. **Trade-off, stated plainly:** any local account that can read the
blob can decrypt it, so the protection is the ACL on the worker's data folder (only that account and the gateway;
`acl check` verifies it) and a per-secret entropy that ties a blob to its name. It protects against a stolen or
copied `app.db`/backup on another machine, not against code running as another local account that can already
read the file (which the isolation design prevents). Plain text is never written. A worker's secrets go with its
workspace when the user is deleted.

**Not yet confirmed by an elevated run:** the new store itself under the rotation loop. The updated test
`test_a_stored_credential_survives_repeated_password_rotation_and_goes_with_the_user` rotates four times and must
be run as SYSTEM by the owner; the unit tests cover the store with the real machine-scope DPAPI of the
unelevated account.

**Deletion.** The secrets are rows in the worker's `app.db` inside its workspace. Deleting a user does
`NetUserDel` + `DeleteProfileW` and removes the workspace (`src/gateway/accounts.py`), so they go with it; the
elevated test asserts the profile and the workspace are gone.

## 4. Shared price-provider key (built)

The gateway holds it in its own environment and copies it to workers with `--pass-env NAME` (Phase 3). Every
worker can refresh prices and run builds, so every worker needs it; the gateway passes it to nothing else.
Added here: `--worker-env` refuses the provider key names (a value there would sit on the command line and in
the service config), fingerprints are hidden in remote mode, and a gate test passes a sentinel key and checks it
never appears in a response or in any file under either user's workspace.

## 5. Disables (tests added, gaps closed)

Refused for remote users, each with a test: `GET /api/plan/monarch-autoupdate`, `POST .../config` (registers the
machine-wide scheduled task), `POST .../run` (runs the extractor's mark-delivered launcher), `POST /api/secrets`
(the secret-store UI). Defence in depth: `monarch_autoupdate.register_scheduled_task` and
`monarch_autoimport_job.run` return a refusal in remote mode even if a route is ever re-allowed. Gaps found in
the shared-state inventory and closed: the same-account Credential Manager (section 3), key fingerprints
(section 3), provider keys on `--worker-env` (section 4).

## 6. Monarch MCP connector (built, optional, off by default)

**Probe, 2026-11-16, with the owner's own sign-in (Read only).** Scripts and logs are outside the repo, in the
session notes folder (`phase4-monarch-probe/`); they print only shapes, counts and dates.
- Server "Monarch Money" 3.3.1, 47 tools (19 read-only). Scopes offered `mcp:read`, `mcp:write`; only `mcp:read`
  is requested. Every tool needs `intent` (an enum; the connector sends `financial_planning`). Results arrive as
  `structuredContent: {"result": "<JSON string>"}`.
- Tokens: access 1 hour, a refresh token with no stated lifetime; refresh works and **rotates** the refresh
  token. Unattended refresh after a day is not yet measured (the probe's `refresh` command, run later).
- **Redirects:** dynamic registration accepted `http://127.0.0.1/callback` and `http://127.0.0.1:<port>/callback`
  and refused ("Redirect URI is not supported") `https://<node>.ts.net:8443/gateway/monarch/callback`,
  `https://<node>.ts.net/gateway/monarch/callback`, and loopback addresses on that same path. Further probing of
  which paths and hosts are accepted was stopped (each try registers a client). So a callback cannot reach the
  server: the design below replaced the gateway callback with a paste-back step.
- Data, compared in memory with the owner's own plan (counts only): `GetTransactions` pages of up to 100 with
  `next_offset`, each row with a stable `id`, `date`, `merchant`, `amount`, `category`, `account`, `pending`;
  6,794 listed (79 pages, 37 s) though `transaction_count` says 7,898 (the gap is not explained; hidden
  transactions did not change the count). On the 5,591 ids also in the plan: amount 100% (same sign convention),
  category 100%, date 99.98%, merchant 95% (Monarch-side renames since import), account 76% raw, 100% once
  whitespace is normalised (one account: non-breaking and doubled spaces differ between the CSV export and the
  connector). `GetAccounts` lists 28 accounts with id, name, type, balance; **one account is hidden** from
  connectors by Monarch (`finicity_excluded.hidden_account_count`), the Finicity gap Phase 0 predicted.
  `GetNetWorthHistory(accounts=[name], interval="day")` is a per-account daily history: for four accounts it
  equalled the plan's imported CSV balances on every one of 653-661 days.

**Design as built.** `src/monarch_connector.py`, routes in `src/server/monarch_routes.py`, all on the remote
allow-list (permission `read_config` for status, `write_config` for the rest). Off unless the worker has
`RETIREMENT_SYSTEM_MONARCH_CONNECTOR=1` (gateway `--monarch-connector`); desktop mode can set it too.
- Everything happens in the user's own worker; the gateway has no connector routes and holds nothing. Because
  the redirect is loopback, there is no callback to receive: `POST /api/monarch/connector/start` registers a
  public client once (`token_endpoint_auth_method: none`, kept as the `monarch.client_id` secret), creates a
  PKCE S256 verifier and a state **in this process's memory** (one at a time, ten minutes) and returns the
  authorization address (`scope=mcp:read`, `resource=https://api.monarch.com/mcp`). The user signs in in their
  own browser, which ends on an `http://127.0.0.1/callback?code=...&state=...` page that does not load; they
  paste that address into `POST /api/monarch/connector/complete {"callback_url"}`. The state is compared in
  constant time and is single-use; the pasted code is useless without the verifier, which never leaves the
  worker. A token response without `mcp:read` is refused.
- Discovery must name `https://api.monarch.com` as issuer and every endpoint under `https://api.monarch.com/`;
  the transport refuses any other address. Responses are capped at 8 MiB, requests time out after 30 s.
- Tokens are `monarch.access_token`, `monarch.refresh_token` (plus `monarch.connector_meta`: connected since,
  access expiry, last sync summary) in `secrets_store`, so section 3's guard applies: a same-account server
  worker cannot connect at all (gate-tested), and deleting the user's profile deletes them. No token, code,
  account name or number is logged, returned or written to a file. An `invalid_grant` on refresh forgets the
  tokens and asks the user to connect again.
- `POST /api/monarch/connector/sync {"dry_run", "full"}`: `GetAccounts`; per account one daily
  `GetNetWorthHistory`, kept only when the response's `account_deltas` name exactly that account id (or, with no
  deltas, the last day equals the current balance), and skipped when two accounts' names differ only in case;
  `GetTransactions` pages (pending rows skipped until posted; account names cleaned like the balances'). Then
  `monarch_upload.import_transaction_rows` and `import_balance_rows_for_upload(source="monarch connector")`,
  so the upsert, the import guards, masking and the mapping seed are shared. The first sync reads from
  2000-01-01; later ones from the last sync minus 30 days (edits arrive), and the balances upsert keeps older
  days. One sync at a time per worker. About 40-60 s for the owner's 6,800 transactions and 28 accounts,
  inside the proxy's 120 s read timeout.
- The 20% account-drop guard compares a connector sync only with earlier connector syncs
  (`import_balance_rows(compare_same_source=True)`, `MonarchRepo.last_import(source=)`): a CSV export lists
  closed accounts too (the owner's plan: 41) and the connector only open, visible ones (28), so comparing the
  two would reject every connector sync after a CSV import.
- `POST /api/monarch/connector/disconnect` revokes both tokens at the revocation endpoint (best effort) and
  deletes them; the client id is kept. `GET /api/monarch/connector` reports `available` (with a `reason`
  when not), `connected`, `connected_at`, `last_sync`, `sign_in_pending`.
- Tests: `tests/test_monarch_connector_unit.py` runs everything against a fake Monarch built from the probe's
  measurements (no live calls); the isolation gate starts the gateway with `--monarch-connector` and checks
  that neither same-account worker can start a sign-in.

**Caveats.** The hidden (Finicity) account still needs the CSV upload. Mixing CSV transaction uploads and
connector syncs for the same user can leave one account's transactions under two spellings that differ only in
spaces (the upload keeps the export's raw name, as the extractor does). Unattended refresh over days is
unmeasured: if the refresh token turns out short-lived, users reconnect when told to.

**Remaining owner steps.** Tomorrow or later: `python monarch_mcp_probe.py refresh` (in the notes folder) to
see whether the refresh token still works after a day, then `python monarch_mcp_probe.py cleanup` (revokes and
deletes the probe's tokens from your Credential Manager). The probe registered two OAuth clients at Monarch
(one signed in, one from an accepted redirect check, never used; refused checks register nothing); Monarch >
Settings > MCP Connector lists any granted access.

## 7. What did not run (needs the owner)

- The elevated test `test_a_stored_credential_survives_repeated_password_rotation_and_goes_with_the_user`
  (`tests/test_worker_accounts_elevated_integration.py`): skipped by default; run it as SYSTEM with
  `powershell -ExecutionPolicy Bypass -File tools\run_elevated_tests_as_system.ps1 -Filter credential`. The
  Credential Manager version of this test failed (section 3.1), which is why the store moved to machine-scope
  DPAPI; "a stored credential survives worker-account password rotation" is unverified for the new store until
  this passes.
- The day-later refresh check and the probe cleanup (section 6, "Remaining owner steps").
- A live connector sign-in through the built routes (the probe exercised the same calls from a script; the
  routes are tested only against the fake).
