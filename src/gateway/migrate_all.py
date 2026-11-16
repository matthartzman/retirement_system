"""Offline "migrate all users": back each user up, migrate each plan, report every failure.

Run with the gateway service stopped.  One user's failure never stops the others; the exit status is non-zero
when any user failed or was skipped.  The pre-migration snapshot of each user is an encrypted ``.userN.rpbak``
archive: restoring it (``ops restore``) is the rollback.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .backup_store import workspace_in_use
from .migrate_user import RESULT_PREFIX


def run_child(workspace: Path, *, install_dir: Path, python: str = sys.executable, timeout: float = 900.0) -> dict:
    """Migrate one workspace in a fresh Python process; always returns a result dict."""
    argv = [python, "-E", "-s", "-B", "-X", "utf8", "-m", "src.gateway.migrate_user", "--workspace", str(workspace)]
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(argv, cwd=str(install_dir), env=env, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": f"timed out after {int(timeout)} s"}
    except OSError as exc:
        return {"ok": False, "detail": f"could not start the migration: {type(exc).__name__}"}
    for line in reversed((r.stdout or "").splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                return json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                break
    tail = (r.stderr or "").strip().splitlines()[-1:] or ["no result line"]
    return {"ok": False, "detail": f"exit {r.returncode}: {tail[0][:200]}"}


def migrate_all(*, data_root: Path, user_ids: list[int], snapshot: Callable[[int], Path],
                migrate: Callable[[Path], dict], in_use: Callable[[Path], bool] = workspace_in_use) -> dict:
    """The orchestration; ``snapshot`` and ``migrate`` are injected so it is testable without processes."""
    results = []
    for uid in sorted(set(int(u) for u in user_ids)):
        ws = Path(data_root) / "users" / str(uid)
        entry: dict = {"user": uid, "status": "ok", "snapshot": None, "detail": ""}
        results.append(entry)
        if not ws.is_dir():
            entry.update(status="skipped", detail="no workspace folder (user never signed in)")
            continue
        if in_use(ws):
            entry.update(status="skipped", detail="a worker is running; stop the gateway service first")
            continue
        try:
            entry["snapshot"] = snapshot(uid).name
        except Exception as exc:  # noqa: BLE001
            entry.update(status="failed", detail=f"no pre-migration snapshot, not migrated ({type(exc).__name__})")
            continue
        try:
            res = migrate(ws)
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
        entry["detail"] = res.get("detail", "")
        if not res.get("ok"):
            entry["status"] = "failed"
    failed = [r["user"] for r in results if r["status"] == "failed"]
    skipped = [r["user"] for r in results if r["status"] == "skipped"]
    return {"users": results, "failed": failed, "skipped": skipped, "ok": not failed and not skipped}


def format_report(report: dict) -> str:
    lines = []
    for r in report["users"]:
        lines.append(f"user {r['user']}: {r['status'].upper()}  {r['detail']}"
                     + (f"  (snapshot {r['snapshot']})" if r["snapshot"] else ""))
    lines.append("RESULT: " + ("all users migrated" if report["ok"] else
                               f"failed {report['failed']}, skipped {report['skipped']}"))
    return "\n".join(lines)
