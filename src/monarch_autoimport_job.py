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
from . import monarch_db_sync
from . import monarch_import as mi
from . import onedrive_guard
from . import ytd_tracking as ytd

_MARK_DELIVERED_TIMEOUT_SECONDS = 60


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
        return [f"No Monarch Extractor venv Python found under {extractor_dir}\\.venv; could not mark {len(run_ids)} run(s) delivered."]

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
                errors.append(f"--mark-delivered {run_id} exited {proc.returncode}: {proc.stderr.strip()}")
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"--mark-delivered {run_id} failed to run: {exc}")
    return errors


def run(base_dir: str | Path, *, force: bool = False) -> dict[str, Any]:
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
    upsert_result = ytd.upsert_transactions_by_monarch_id(input_dir, result["rows"])

    db_path = base_dir / "local_state" / "retirement_system_v10.db"
    monarch_db_sync.sync_ytd_files_to_db(input_dir, db_path)

    # Acknowledge every imported run to the extractor's own outbox now that
    # the upsert has succeeded, so new_transactions.csv/changed_transactions.csv
    # stop re-emitting these rows on the next cycle. Best-effort: a failure
    # here is reported but does not undo or fail the (already-committed)
    # import -- see _mark_runs_delivered's own docstring.
    mark_delivered_errors = _mark_runs_delivered(source_dir.parent, result["run_ids"])

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
