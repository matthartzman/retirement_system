# Immediate Next Actions Implementation

Status: implemented as an additive stabilization pass after the system evaluation.

## 1. Baseline reconciliation

The workspace previously documented several ownership/contract files that were not present in the inspected tree. This pass restores those files rather than removing the documentation claims:

- `src/api_contracts.py`
- `src/server/route_manifest.py`
- `src/server/features/*.py`
- `frontend/js/dashboard_source_truth_banners.js`
- `frontend/js/modules/phase3_module_manifest.js`
- matching `output/js/...` static assets

The `/api/contracts` route is now live and returns both the typed contract registry and route ownership manifest.

## 2. Framework-neutral API contracts

Added `/api/contracts` as a stdlib-runtime route adapter. The registry is dependency-free and intentionally does not require Flask, Werkzeug, Pydantic, or a build step.

Immediate covered endpoint families include build preflight, config rows, spending model, holdings, detailed results, import previews, local backups, snapshot restore/compare, system configuration, and the contract registry itself.

## 3. Healthcare terminology migration guardrail

Added `src/terminology_aliases.py` as the canonical migration seam. It establishes `healthcare_premium` / `Healthcare Premium` as the product language while preserving legacy `wellness_*` identifiers at import/export and projection boundaries.

The registry also records that Medical OOP Cap is a cap/reference, not a standalone spending expense.

## 4. Frontend modularization start

Added two loaded browser modules without introducing a bundler:

- `frontend/js/api_client.js`: shared fetch/timeout/error normalization and CSRF propagation.
- `frontend/js/app_store.js`: small state mirror for rows, dirty count, plan source, runtime, and build flags.

`dashboard.js` now uses the API client seam for JSON/text requests and mirrors selected state into the app store while preserving the current monolithic behavior.

## 5. Backend service extraction start

Added feature-owned services:

- `src/server_services/pricing_service.py`
- `src/server_services/holdings_service.py`

Route modules now delegate pricing refresh, price snapshot lookup, symbol trace setup, and holdings CSV get/save logic to those services.

## 6. Clean-overlay acceptance

Added `tools/validate_clean_overlay.py`. It applies an overlay zip to a pristine base zip and runs dependency-light checks:

- Python compile checks for the new framework-neutral contract/service files.
- Stdlib route smoke for `/api/ping`, `/api/runtime`, `/api/build/preflight`, `/api/summary`, and `/api/contracts`.
- JavaScript syntax checks for `dashboard.js`, `api_client.js`, and `app_store.js` when Node is available.

## Deferred follow-up

The remaining deeper cleanup is to eliminate `from .app_core import *` in route modules by replacing it with explicit route context objects. This pass reduces that risk by moving more business logic out of broad route adapters first.
