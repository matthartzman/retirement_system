from __future__ import annotations

"""The weekday-5pm trends job logic (ticket 306), importable from both the
headless CLI (tools/append_trends_log.py, run by Windows Task Scheduler) and
the app's own "run now" route, so both take the same code path.
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src import onedrive_guard  # noqa: E402

from .trends_log import append_or_replace_entry, default_log_path  # noqa: E402
from .trends_metrics import compute_snapshot  # noqa: E402


def run(retirement_system_base_dir: str | Path, *, log_path: str | Path | None = None, today: date | None = None) -> dict[str, Any]:
    base_dir = Path(retirement_system_base_dir)
    input_dir = base_dir / "input"

    if input_dir.exists():
        source_files = sorted(input_dir.glob("*.csv"))
        guard_errors = onedrive_guard.check_files_safe_to_read(source_files)
        if guard_errors:
            return {"success": False, "errors": guard_errors}

    snapshot = compute_snapshot(base_dir, today=today)
    snapshot["run_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    path = Path(log_path) if log_path else default_log_path(_APP_ROOT)
    history = append_or_replace_entry(path, snapshot)
    return {"success": True, "snapshot": snapshot, "log_path": str(path), "total_entries": len(history)}
