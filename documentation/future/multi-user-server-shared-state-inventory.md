# Multi-User Server: Shared-State Inventory (Phase 1 exit criterion)

Status: draft
Date: 2026-11-15
Plan: `documentation/future/multi-user-server-plan.md` (revision 3), "Phase 1 - Remote mode for one worker"

Every piece of state that is shared between processes or users on the server machine (not under
one worker's workspace root), and what remote mode (`RETIREMENT_SYSTEM_REMOTE_MODE=1`) does with
it. Built by Grep over `src/`, `tools/`, `financial_trends_reporter/` and `Monarch Extractor/` on
request-field names, `Path(`, route decorators, `os.environ`/`os.getenv` and settings keys, reading
only the matching functions. Line numbers are as of this branch.

Treatments:
- **disabled**: refused in remote mode (route on the refused list in `src/server/remote_allowlist.py`,
  or the code path returns early).
- **confined**: the path goes through `remote_mode.confine_path` and must lie inside the workspace.
- **per user**: already lives under the workspace root, or is per Windows account, so it is
  separated once each worker has its own workspace and (Phase 3) its own account.
- **Phase N**: still shared after this phase; the named phase owns it.

Workspace root: `platform_runtime.workspace_root()` (`src/platform_runtime.py:73`) honours
`RETIREMENT_SYSTEM_WORKSPACE_ROOT`; the worker (`src/remote_worker.py`) sets it, and pins
`RETIREMENT_SYSTEM_SQLITE_DB`, `RETIREMENT_SYSTEM_APP_DB` and `RETIREMENT_SYSTEM_OUTPUT_DIR` inside it,
before any module that caches it is imported. Anything resolved from `package_root()`,
`BASE_DIR` (`src/server/app_core.py:132`) or `Path(__file__).parents[N]` is the install's
shared folder.

## 1. Scheduled tasks (Task Scheduler names are machine-wide)

| Item | Evidence | Remote mode |
|---|---|---|
| `RetirementSystem_MonarchAutoImport`, registered by the app when the Monarch auto-update policy is saved | `src/monarch_autoupdate.py:318-336`, called from `src/server/plan_routes.py` (`monarch_autoupdate_config`); script `tools/launchers/register_monarch_autoimport_task.ps1:44,74-76` | **disabled**: `GET /api/plan/monarch-autoupdate`, `POST .../config` and `POST .../run` are refused. Phase 4 replaces Monarch per user; unattended sync is not planned. |
| `RetirementSystem_MonarchExtract` | `Monarch Extractor/register_monarch_extract_task.ps1:55` | **disabled** for workers (operator-only tool, never started by the app). |
| `FinancialTrendsReporter_Server`, `FinancialTrendsReporter_AppendLog` | `financial_trends_reporter/tools/launchers/register_trends_server_task.ps1:22`, `register_trends_report_task.ps1:45` | Not started by the planner; stays an operator service outside workers (see section 5). |

No other code under `src/` registers a task.

## 2. Credential store

| Item | Evidence | Remote mode |
|---|---|---|
| Windows Credential Manager service `RetirementSystem` (via `keyring`) | `src/secrets_store.py:24` | **disabled** from the web (`POST /api/secrets` refused). **Per user** under the per-account launcher (own account, profile loaded). Phase 4: in remote mode the store is used only when the worker carries `RETIREMENT_SYSTEM_DEDICATED_ACCOUNT=1` (set by the per-account launcher only; refused in `--worker-env`) and the backend is `WinVaultKeyring`; a same-account worker would share the gateway account's store and gets `SecretStoreUnavailable` instead. Deleted with the user's profile. |
| Key fingerprints in pricing diagnostics (`/api/prices/test-symbol`) | `src/market_data.py:_secret_fingerprint` | Phase 4: `None` in remote mode (a stable identifier of the shared key). |
| Secret-name index | `src/secrets_store.py` (`NAMES_KEY` in `app.db` settings) | **per user** (workspace `app.db`). |
| `Security/secrets_store` setting (`local_state/secrets.db`) | `src/runtime_config.py:69,159` | Nothing in `src/` reads it; no file is created. No action. |
| Price-provider keys read from the environment first | `src/market_data.py:270-312` | The shared key is a gateway-held environment variable passed to workers with `--pass-env` only (plan decision 6); `--worker-env` refuses the five provider-key names, and a machine-scope value is not inherited (workers get only `launchers.OS_ENV_KEYS`). `remote_mode.subprocess_env` passes exactly the five names to build and tool subprocesses. The isolation gate checks a sentinel key never reaches a response or a workspace file. |

## 3. Environment keys

The worker process gets its environment from the supervisor; every build and tool subprocess it
starts gets `remote_mode.subprocess_env()` (`src/remote_mode.py`): OS essentials, names starting
`RETIREMENT_SYSTEM_`, `RETIREMENT_MC_`, `RETIREMENT_TAX_`, and the provider keys. The worker token
(`RETIREMENT_SYSTEM_SERVER_API_TOKEN`) and everything else (`PYTHONPATH`, gateway secrets, the
owner's shell settings) are dropped. Call sites: `src/server/workbook_routes.py` (`build_start`,
`build`), `src/server_services/pricing_service.py:refresh_prices`,
`src/server_services/portfolio_service.py:drift_payload`. Off: a plain `os.environ` copy as before.

| Key | Evidence | Remote mode |
|---|---|---|
| `RETIREMENT_SYSTEM_WORKSPACE_ROOT` | `src/platform_runtime.py:80` | Set by the worker from `--workspace`: the isolation key. |
| `RETIREMENT_SYSTEM_REMOTE_MODE` | `src/remote_mode.py` | Set by the worker. |
| `RETIREMENT_SYSTEM_SERVER_API_TOKEN` | `src/remote_mode.py:worker_token` | Set by the supervisor; the **only** auth source in remote mode (a token stored in `app.db` is ignored). Never passed to subprocesses. |
| `RETIREMENT_SYSTEM_SQLITE_DB`, `_APP_DB`, `_OUTPUT_DIR` | `src/runtime_config.py:157-158`, `src/app_state.py:22` | Pinned by the worker inside the workspace (`setdefault`, so a supervisor value wins); the environment wins over stored settings (`_env_text`); all three are **confined**, and the worker refuses to start (exit 2) if a pinned value is outside. |
| `RETIREMENT_SYSTEM_PLAN_DB`, `_PLAN_ID`, `_PLAN_REVISION` | `src/active_plan.py` (`plan_db_env`) | Set by the server for the build subprocess from the (confined) active plan. |
| `RETIREMENT_SYSTEM_BASE_DIR` | `src/spending_tracker.py:57` | Not set by the worker. The supervisor must not set it (it would redirect the spending tracker's root). Phase 3 supervisor rule. |
| `RETIREMENT_SYSTEM_DASHBOARD_HOST`/`_PORT` | `src/runtime_config.py:120,154` | Host forced to `127.0.0.1`; the port setting is not used (the worker binds port 0). |
| Policy and test keys (`MAX_BUILD_SECONDS`, `DISABLE_LIVE_PRICE_PROVIDERS`, `FROZEN_TODAY`, `FORCE_*_MODULES`, `RETIREMENT_MC_SIMS`, tax-year keys) | `src/runtime_config.py`, `src/market_data.py`, `src/module_catalog.py`, `src/taxes.py` | Shared policy; fine at machine scope. |

## 4. `BASE_DIR` / package-root fallbacks for data

| Item | Evidence | Remote mode |
|---|---|---|
| Download and Detailed Results fallback to `<package>/output` | `src/server/workbook_routes.py` (`_legacy_output_fallback`, used by `_download_file` and `get_detailed_results`) | **disabled** (returns `None`). |
| Index page fallback to `<package>/output/index.html` | `src/server/base_routes.py` (`index`) | **disabled**. |
| Demo plan built from `<package>/input/demo` CSVs when `demo_seed.rpx` is missing | `src/server/plan_routes.py` (`_demo_csv_dir`) | **disabled** (raises); the demo comes only from the shipped `src/reference/demo_seed.rpx`. |
| `local_plan_data_roots` resolved against `BASE_DIR`, and the loopback switch-off of the server-path guard | `src/server/plan_routes.py` (`_path_roots_from_config`, `_server_path_requires_allowlist`, `_server_path_allowed`) | Guard always on; it uses the workspace resolver, not configured roots. The one caller, `POST /api/ytd/account-setup/recover` (which also searches `BASE_DIR.parent`), is **disabled**. |
| WebView2 cache delete under `<package>/local_state/webview` | `src/server/admin_routes.py:84`, `src/server_services/admin_service.py:164` | **disabled** (`POST /api/admin/clear-webview-cache` refused). |
| Build subprocess `cwd=BASE_DIR`, `BUILD_SCRIPT` | `src/server/workbook_routes.py`, `src/server_services/build_job_service.py:325` | Code only, kept; outputs go to the workspace through the environment. Phase 3/Decision 7: the install folder is read-only to worker accounts. |
| `project_root=BASE_DIR` for holdings import preview | `src/server/workbook_routes.py:699`, `src/import_preview.py:288` | The parameter is accepted but never read. No action. |
| Frontend assets, reference DB | `src/server/base_routes.py`, `src/stores/ref_access.py` | Read-only shared code and reference data: workers need read access only. |
| `admin_service.build_csv_backup_zip(BASE_DIR)` | `src/server/admin_routes.py:150` | The argument is unused; it reads the active plan. Allowed. |

## 5. Ports

| Item | Evidence | Remote mode |
|---|---|---|
| Planner server default port 5050 | `src/runtime_config.py:65,120`, `src/bootstrap.py:42` | Not used: the worker binds `127.0.0.1` port 0 and reports the port. |
| `allow_reuse_address = True` on the listening socket | `src/http_runtime/server.py:71` | The worker uses an exclusive socket (`allow_reuse_address = False`, `SO_EXCLUSIVEADDRUSE` on Windows; `src/remote_worker.py:_exclusive_server_class`), so another account's process cannot bind over a worker's port. Tested. Desktop unchanged. |
| Trends reporter local 5057 and remote 5058 | `financial_trends_reporter/main.py:481-483`, `listeners.py:53` | Not started by the planner and not part of a worker. Funnel 443 belongs to it (Phase 0); the gateway uses 8443. **Phase 6**: extend `check_funnel_target` to the gateway's rules so Funnel never targets a worker or 5057. If the reporter is ever offered per user it needs its own ports and `--retirement-system-dir <workspace>`. |
| Tailscale Funnel configuration | machine-wide | Operator-managed (Phase 6). |

## 6. Logs

| Item | Evidence | Remote mode |
|---|---|---|
| `local_state/logs/app.log` (rotating, redacted, account numbers masked) | `src/bootstrap.py:73-107` | **per user** (workspace-rooted; the worker calls the same bootstrap after pinning the workspace). |
| Audit events | `src/security.py:86`, `src/server/security_audit.py` (written to `app.db`) | **per user**, but alterable by that user's own worker; the plan keeps the authoritative audit log in the gateway (Phase 2). |
| Unhandled-error detail | `src/server/app_core.py:_json_unhandled_error` | Logged with an error id; the response body is generic in remote mode. |

## 7. Temp directories

| Item | Evidence | Remote mode |
|---|---|---|
| Atomic-write temp files (`mkstemp(dir=<destination folder>)`) | `src/plan_db_replace.py:104,167`, `src/plan_file_io.py:87`, `src/server_services/demo_plan_service.py:84` | **per user** (beside the destination, in the workspace). The new upload and download temp files are also created inside the workspace. |
| Conversion dry-run temp dirs | `src/legacy_conversion/runner.py:254,298` | Random names in the system temp; the conversion routes are **disabled**. |
| Open-in-viewer temp file | `src/desktop_api.py:199` | Desktop bridge only, not reachable over HTTP. |
| Fixed file names in `%TEMP%` | none found in `src/` | n/a. `%TEMP%` is per Windows account once workers have their own accounts (Phase 3). |

## 8. Other machine-wide state

| Item | Evidence | Remote mode |
|---|---|---|
| Price cache | `src/market_data.py:207,400-415` (table in `app.db`) | **per user**. The one-time legacy JSON import reads a relative path; harmless with a clean install directory. |
| pywebview profile `<package>/local_state/webview` | `src/desktop_app.py:90-92` | Desktop only; never created by a worker. |
| `Path.home()` save dialogs | `src/desktop_api.py` | Desktop bridge only. |
| `__pycache__` writes into the install | not measured | Phase 3: a frozen, read-only install (Decision 7) avoids it; `PYTHONDONTWRITEBYTECODE` is passed through to subprocesses if the supervisor sets it. |
| Frozen-build auto-seeding of an empty workspace | `src/platform_runtime.py:seed_frozen_workspace` | **disabled** in remote mode: provisioning is explicit (`--provision demo|blank|none`). |

## 9. Monarch Extractor

| Item | Evidence | Remote mode |
|---|---|---|
| Playwright browser profile with the logged-in Monarch session, inside the repo | `Monarch Extractor/monarch_extract.py:31-32,1192`, `monarch_balances.py:29-30,141` | **disabled** for workers (no route starts it). Phase 4 replaces it (CSV upload first, connector later). |
| Extractor output and raw folders inside the repo | `Monarch Extractor/monarch_extract.py:33-40` | **disabled**, as above. |
| User-set absolute `source_dir` | `src/monarch_autoupdate.py:203-219` | **confined** (`resolve_source_dir`), and the routes that use it are **disabled**. |
| `run_monarch.ps1` targeting the repo root | `Monarch Extractor/run_monarch.ps1:3-4,24` | Operator tool; not started by a worker. |
| Scheduled-task registration and the extractor import job, if ever called | `src/monarch_autoupdate.py:register_scheduled_task`, `src/monarch_autoimport_job.py:run` | Phase 4: both refuse in remote mode (defence in depth behind the refused routes). |
| Replacement for remote users | `POST /api/monarch/upload` (`src/monarch_upload.py`) | **per user**: Monarch's own CSV exports uploaded from the browser into the user's own plan; nothing written outside the plan store. Admin mapping CSV (`--monarch-mapping-csv`) copied into each new workspace (`local_state/monarch_mapping_seed.csv`). |

## 10. Request-borne and settings-borne paths (the resolver's coverage)

| Path | Where it arrives | Remote mode |
|---|---|---|
| Save As destination, Load Saved Plan source | `POST /api/plan/save-as`, `POST /api/plan/load-file` (`src/server_services/plan_file_service.py`) | Routes **disabled**; the service also **confines** both (defence in depth). Replaced by `GET /api/plan/download` and `POST /api/plan/upload`. |
| Backup folder | stored policy, `POST /api/plan/backups/config` (`src/local_backup_scheduler.py:resolve_backup_dir`) | Config route **disabled**; the stored value is **confined** wherever it is used (status, run, prune). |
| Monarch source folder | stored policy (`src/monarch_autoupdate.py:resolve_source_dir`) | **confined**; routes **disabled**. |
| `Runtime/sqlite_db` | stored setting (`src/server/app_core.py:_sqlite_db`) | **confined**; env pin wins. |
| `RETIREMENT_SYSTEM_APP_DB` | environment (`src/app_state.py:app_store_path`) | **confined**. |
| `Runtime/output_dir` | stored setting or env (`src/workspace_context.py:workspace_output_dir`) | **confined**; env pin wins. |
| `Downloads/desktop_download_folder` | `POST /api/settings/workbook-download` | A non-empty value is refused (400); the browser chooses where downloads go. |
| `local_plan_data_roots` | setting | Ignored in remote mode (section 4). |
| Plan registry absolute paths | `src/plan_registry.py` (`register_plan_file`, `activate`, `active_plan_file`) | **confined**: registering, switching to (`POST /api/plans/switch`) or serving an active plan outside the workspace fails closed. |
| System configuration (all settings, including the token and paths) | `GET`/`POST /api/admin/system-config`, `POST /api/admin/mode` | **disabled**: server configuration is the operator's. |

## Left for later phases

- Phase 2: the gateway owns login, sessions, CSRF and the authoritative audit log; the worker's
  `/login` and `/api/auth/*` are refused.
- Phase 3: per-user Windows accounts (unproven in Phase 0), Job Objects, the build queue and pool
  cap, `RETIREMENT_SYSTEM_BASE_DIR` never set, read-only install.
- Phase 4 (done, `multi-user-server-monarch-secrets-design.md`): per-user secrets guard, Monarch CSV upload,
  mapping seed. Still open: the elevated credential-rotation test and the Monarch connector probe (owner).
- Phase 6: Funnel target check extended to the gateway and workers.
