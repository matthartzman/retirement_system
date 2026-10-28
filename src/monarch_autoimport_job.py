from __future__ import annotations

"""The Monarch auto-import job logic (ticket 305), importable both from the
headless CLI entry point (tools/monarch_autoimport.py, run by Windows Task
Scheduler at 4am) and from the server's "run now" route
(src/server/plan_routes.py), so a manual in-app trigger and the unattended
scheduled run share one code path.
"""

import subprocess
from pathlib import Path
from typing import Any

from . import monarch_autoupdate as mau
from . import monarch_import as mi
from .monarch_balances_import import import_balances
from . import onedrive_guard
from . import ytd_tracking as ytd

_MARK_DELIVERED_TIMEOUT_SECONDS = 60
# What monarch_extract.py --mark-delivered prints when the run was already acknowledged.
_ALREADY_DELIVERED = "No pending events found for run ID"


def _resolve_extractor_python(extractor_dir: Path) -> Path | None:
    """Find the Monarch Extractor's own venv Python.

    monarch_extract.py imports playwright unconditionally at module scope
    (even for --mark-delivered, which otherwise touches nothing but its own
    SQLite outbox), so it must run under the venv where playwright is
    actually installed -- plain `sys.executable` will not have it.
    """
    candidates = [
        extractor_dir / ".venv" / "Scripts" / "python.exe",  # Windows
        extractor_dir / ".venv" / "bin" / "python",  # POSIX (dev/CI parity)
    ]
    return next((c for c in candidates if c.exists()), None)


def _mark_runs_delivered(extractor_dir: Path, run_ids: list[str]) -> list[str]:
    """Best-effort: acknowledge each imported run_id to the extractor's own
    outbox so its pending-events files stop re-emitting it.

    Returns a list of error strings (empty if every run_id was marked
    delivered, or there was nothing to mark). Never raises -- this must not
    fail an otherwise-successful import; an unmarked run_id just means the
    same (already-upserted, idempotent) rows reappear next cycle.
    """
    if not run_ids:
        return []
    script = extractor_dir / "monarch_extract.py"
    if not script.exists():
        return [f"monarch_extract.py not found at {script}; could not mark {len(run_ids)} run(s) delivered."]
    python_exe = _resolve_extractor_python(extractor_dir)
    if python_exe is None:
        return [f"No extractor venv Python found under {extractor_dir}\\.venv; could not mark {len(run_ids)} run(s) delivered."]

    errors: list[str] = []
    for run_id in run_ids:
        try:
            proc = subprocess.run(
                [str(python_exe), str(script), "--mark-delivered", run_id],
                capture_output=True,
                text=True,
                timeout=_MARK_DELIVERED_TIMEOUT_SECONDS,
                check=False,
            )
            if proc.returncode != 0:
                # The extractor prints its failure on stdout, so report both streams.
                detail = " ".join(part.strip() for part in (proc.stderr, proc.stdout) if part and part.strip())
                if _ALREADY_DELIVERED in detail:
                    continue  # acknowledged on an earlier run; nothing left to mark
                errors.append(f"--mark-delivered {run_id} exited {proc.returncode}: {detail}")
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"--mark-delivered {run_id} failed to run: {exc}")
    return errors


def run(base_dir: str | Path, *, force: bool = False) -> dict[str, Any]:
    """The daily job: two independent steps under one schedule -- transactions, then
    account balances. Each is switched by its own policy checkbox and records its own
    status; one failing never stops or fails the other. ``force`` ignores only the
    master enabled flag (the "Import now" button)."""
    policy = mau.load_policy(base_dir)["policy"]
    if not policy["enabled"] and not force:
        return {"success": True, "skipped": True, "skip_reason": "disabled"}
    result: dict[str, Any] = {"success": True, "skipped": True, "skip_reason": "transactions off"}
    if policy["transactions"]:
        try:
            result = _run_transactions(base_dir, force=True)
        except Exception as exc:  # noqa: BLE001 - the balances step still runs
            status = mau.write_status(base_dir, success=False, errors=[f"{exc.__class__.__name__}: {exc}"])
            result = {"success": False, "status": status}
    if policy["balances"]:
        try:
            src = mau.resolve_source_dir(base_dir, policy) / "balances.csv"
            bal = import_balances(base_dir, src)
        except Exception as exc:  # noqa: BLE001
            bal = {"success": False, "status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
        result["balances"] = bal
        mau.write_balances_status(
            base_dir, success=bool(bal.get("success")), status=str(bal.get("status")),
            detail=str(bal.get("error") or bal.get("skip_reason")
                       or f"{bal.get('rows', 0)} rows, {bal.get('accounts', 0)} accounts"),
        )
        if bal.get("status") == "ok":
            try:  # copy the imported balance into rows set to "always update"; never fatal
                from . import reconcile
                auto = reconcile.auto_apply(Path(base_dir) / "input")
                result["auto_update"] = {"success": True, "applied": len(auto["applied"]), "held": len(auto["held"])}
            except Exception as exc:  # noqa: BLE001
                result["auto_update"] = {"success": False, "error": f"{exc.__class__.__name__}: {exc}"}
    return result


def _run_transactions(base_dir: str | Path, *, force: bool = False) -> dict[str, Any]:
    base_dir = Path(base_dir)
    loaded = mau.load_policy(base_dir)
    policy = loaded["policy"]
    if not policy["enabled"] and not force:
        return {"success": True, "skipped": True, "skip_reason": "disabled"}

    field_map = mi.load_field_map(policy["field_map_path"] or None)
    source_dir = mau.resolve_source_dir(base_dir, policy)

    if source_dir.exists():
        candidate_paths = [source_dir / name for name in mi.CONSUMABLE_FILENAMES if (source_dir / name).exists()]
        guard_errors = onedrive_guard.check_files_safe_to_read(candidate_paths)
        if guard_errors:
            status = mau.write_status(base_dir, success=False, errors=guard_errors)
            return {"success": False, "status": status}

    result = mi.read_monarch_output_folder(source_dir, field_map)
    file_errors = [f"{name}: {'; '.join(msgs)}" for name, msgs in result["errors"].items()]

    if not result["rows"] and not result["files_consumed"]:
        status = mau.write_status(base_dir, success=not file_errors, errors=file_errors)
        return {"success": not file_errors, "skipped": True, "skip_reason": "no_rows", "status": status}

    input_dir = base_dir / "input"
    # The YTD tables are in the plan file (WP6.4): the upsert is the save the running app reads.
    upsert_result = ytd.upsert_transactions_by_monarch_id(input_dir, result["rows"])

    # Acknowledge every imported run to the extractor's own outbox now that
    # the upsert has succeeded, so new_transactions.csv/changed_transactions.csv
    # stop re-emitting these rows on the next cycle. Best-effort: a failure
    # here is reported but does not undo or fail the (already-committed)
    # import -- see _mark_runs_delivered's own docstring.
    #
    # System review 2026-09-07 SEC-2: the extractor directory (and therefore
    # the interpreter _mark_runs_delivered executes) used to be derived from
    # `source_dir.parent` -- an attacker-influenced value once `source_dir`
    # was confined only loosely. It is now pinned to the one real location
    # this app ships the extractor at, independent of the configured
    # `source_dir` (which only ever needs to name the *output* subfolder).
    extractor_dir = base_dir / "Monarch Extractor"
    # Only a Monarch Extractor install has an outbox to acknowledge; other sources have none.
    mark_delivered_errors = (
        _mark_runs_delivered(extractor_dir, result["run_ids"]) if (extractor_dir / "monarch_extract.py").exists() else []
    )

    status = mau.write_status(
        base_dir,
        success=True,
        files_consumed=result["files_consumed"],
        rows_added=upsert_result["added"],
        rows_updated=upsert_result["updated"] + upsert_result["adopted"],
        rows_skipped=upsert_result["skipped"],
        errors=file_errors + mark_delivered_errors,
    )
    return {"success": True, "upsert": upsert_result, "mark_delivered_errors": mark_delivered_errors, "status": status}
