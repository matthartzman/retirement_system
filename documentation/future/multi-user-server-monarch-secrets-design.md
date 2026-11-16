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

## 3. Per-user secrets (built: guard only)

`src/secrets_store.py` is unchanged in behaviour for a worker that runs as its own Windows account with its
profile loaded: `keyring` picks `WinVaultKeyring` and the Credential Manager is that account's own (measured in
Phase 0). What could fall back to a shared store, and what this phase does about it:

| Path | Risk | Remote-mode rule |
|---|---|---|
| Same-account launcher (CI, development) | every worker shares the gateway account's Credential Manager | `secrets_store` refuses (`SecretStoreUnavailable`) unless the worker was started by the per-account launcher, which sets `RETIREMENT_SYSTEM_DEDICATED_ACCOUNT=1`. The supervisor refuses that name in `--worker-env`, so it cannot be faked. |
| Another keyring backend (a `keyrings.alt` file, a `PYTHON_KEYRING_BACKEND` override) | a file in a shared or readable place | remote mode accepts only `WinVaultKeyring`; worker environments are built from nothing, so an override is not inherited either. |
| Machine-scope `FMP_API_KEY` etc. | every user gets a key nobody chose to give them | workers get only the OS essentials (`launchers.os_env`) plus what the gateway passes; tested. |
| Key fingerprints in `/api/prices/test-symbol` and the pricing diagnostics | a stable identifier of the shared key | `None` in remote mode. |

The fallback "per-user encrypted secrets in the user's own database" is **not built**: the credential store is
reliable under the per-account launcher, and an encrypted blob in `app.db` would be readable by the same user's
worker anyway, so it adds no protection over Credential Manager. Revisit only if the elevated rotation test
below fails.

**Deletion.** Credential Manager entries live in the account's profile (`AppData\...\Microsoft\Credentials`,
`Vault`). Deleting a user already does `NetUserDel` + `DeleteProfileW` (`src/gateway/accounts.py`), so stored
secrets and any connector tokens go with the profile. The elevated test stores a credential as a throwaway
account, rotates the password, reads it back, deletes the user and checks the profile is gone.

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

## 6. Monarch MCP connector: NOT BUILT

**Why:** the build was conditional on a live probe with the owner's Monarch login (tool list, data coverage,
paging, token lifetime and refresh, redirect-address check). The owner chose not to run it on 2026-11-16, so
nothing about the connector's data is known beyond Phase 0's discovery documents, and the Finicity gap
(Fidelity brokerage accounts silently missing) still argues against depending on it. The CSV upload covers
every account provider.

**Design, for when it is built.** Optional, off by default (gateway setting `--monarch-connector`).
- The seam: a connector produces the same two shapes the upload produces and calls
  `monarch_upload.import_transaction_rows` (normalised rows with Monarch's `Id`) and
  `monarch_upload.import_balance_rows_for_upload` (`(date, account_key, account, balance)`), so the import
  guards, masking and mapping seed are shared and nothing in the importers changes.
- OAuth is the gateway's (a worker is not reachable from the browser, and a callback must not be proxied):
  `POST /gateway/monarch/connect` (CSRF-checked) registers the client once per gateway with dynamic client
  registration (`https://api.monarch.com/oauth/register`, `token_endpoint_auth_method: none`), creates a PKCE
  S256 verifier and a state bound to the session, stores both in `gateway.db` for ten minutes, and returns the
  authorization address with `scope=mcp:read` and `resource=https://api.monarch.com/mcp`.
  `GET /gateway/monarch/callback` on the public Funnel name (`https://<node>.ts.net:8443/gateway/monarch/callback`)
  checks state and session, exchanges the code, and hands the tokens to the user's worker over the token-
  authenticated loopback channel (`POST /api/monarch/connector/tokens`, refused unless the gateway token is
  presented and never on the remote allow-list for browsers).
- Tokens live in the worker account's Credential Manager (`secrets_store`, names `monarch.access_token`,
  `monarch.refresh_token`), so the guard in section 3 applies and deletion goes with the profile. The gateway
  keeps only "connected: yes/no, since, last sync".
- Sync on login and on demand (`POST /api/monarch/connector/sync`): refresh the access token if needed, page
  through accounts, balances and transactions, import. Disconnect (`POST /api/monarch/connector/disconnect`)
  revokes at the revocation endpoint and deletes both secrets.
- New dependency: none needed (Streamable HTTP is JSON-RPC over HTTPS POST; the probe uses `urllib`). The `mcp`
  SDK is not installed in the build's Python 3.12 and is optional.

**Exact remaining steps.**
1. Owner runs the probe (kept outside the repo, in the session notes folder:
   `phase4-monarch-probe/monarch_mcp_probe.py`): `python monarch_mcp_probe.py run`, signs in with Read only,
   keeps `monarch_probe_report.json` (shapes, counts and dates only).
2. Owner runs `python monarch_mcp_probe.py redirect-check https://<node>.ts.net:8443/gateway/monarch/callback`
   to learn whether registration accepts the non-loopback HTTPS redirect. If refused, the connector cannot be
   built as designed (a loopback redirect would need the user's browser on the server).
3. A day later: `python monarch_mcp_probe.py refresh` (does unattended refresh work, is the refresh token
   rotated). Then `cleanup` (revokes and deletes the stored probe tokens).
4. Compare the report with what the importers need: transactions with a stable id, date, merchant, amount,
   account and category; a balance history per account per day (or at least current balances), covering
   several years with paging. If balance history is missing, the connector can feed transactions only.
5. Only then build the routes above, with tests against a fake MCP server (no live calls in CI).

## 7. What did not run (needs the owner)

- The elevated test `test_a_stored_credential_survives_password_rotation_and_goes_with_the_user`
  (`tests/test_worker_accounts_elevated_integration.py`): skipped by default, needs an elevated shell with
  `RETIREMENT_ELEVATED_TESTS=1`. Until it passes, "a stored credential survives worker-account password
  rotation" stays unverified. If it fails, either stop rotating (`--account-rotate-days 0`) or build the
  per-user encrypted fallback in section 3.
- The Monarch connector probe (section 6).
