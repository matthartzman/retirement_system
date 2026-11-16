"""Migrate ONE user's workspace in this process: ``python -m src.gateway.migrate_user --workspace <folder>``.

The workspace is cached at import by the application, so ``migrate_all`` runs this as a fresh child process per
user.  Prints one line ``MIGRATE_RESULT {json}`` and exits 0 only when the migration finished without an error
(unlike startup migration, which swallows failures).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULT_PREFIX = "MIGRATE_RESULT "


def migrate_workspace(workspace: Path) -> dict:
    from src.remote_worker import _pin_environment  # noqa: PLC0415

    workspace = Path(workspace).resolve()
    _pin_environment(workspace)
    from src import platform_runtime  # noqa: PLC0415
    from src.active_plan import PLAN_FILE_NAME  # noqa: PLC0415
    from src.plan_data_migration import migrate_plan_data_at_rest  # noqa: PLC0415
    from src.active_plan import PlanStore  # noqa: PLC0415

    plan = workspace / PLAN_FILE_NAME
    if not plan.is_file():
        return {"ok": True, "detail": "no plan file yet (nothing to migrate)", "total_changed": 0}
    platform_runtime.ensure_workspace_dirs()
    PlanStore.open(plan).close()  # creates nothing new; migrates an older schema
    report = migrate_plan_data_at_rest(workspace / "input", plan_path=plan)
    if report.get("error"):
        return {"ok": False, "detail": str(report["error"])[:300], "total_changed": report.get("total_changed", 0)}
    return {"ok": True, "detail": "migrated" if not report.get("skipped") else "already current",
            "total_changed": report.get("total_changed", 0)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.gateway.migrate_user")
    p.add_argument("--workspace", required=True)
    args = p.parse_args(argv)
    try:
        result = migrate_workspace(Path(args.workspace))
    except Exception as exc:  # noqa: BLE001 - reported to the caller, never swallowed
        result = {"ok": False, "detail": f"{type(exc).__name__}: {str(exc)[:300]}", "total_changed": 0}
    print(RESULT_PREFIX + json.dumps(result), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
