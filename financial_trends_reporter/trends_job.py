from __future__ import annotations

"""The weekday-5pm trends job logic (ticket 306), importable from both the
headless CLI (tools/append_trends_log.py, run by Windows Task Scheduler) and
the app's own "run now" route, so both take the same code path.
"""

import json
import subprocess
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


PRICE_REFRESH_TIMEOUT_SECONDS = 150


def refresh_prices(base_dir: Path, *, timeout: float = PRICE_REFRESH_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Refresh market prices with the main app's own tool before a snapshot.

    Holdings (and so net worth) are valued from the local price cache, which only
    the main app's refresh updates; without this step the log goes flat the day
    nobody opens that app. Never raises -- a failed refresh just marks the
    snapshot's prices as stale so the dashboard can say so.
    """
    script = base_dir / "tools" / "refresh_prices.py"
    if not script.exists():
        return {"refreshed": False, "stale": True, "error": "price refresh tool not found"}
    try:
        proc = subprocess.run(
            [sys.executable, str(script)], cwd=str(base_dir), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except Exception as exc:  # timeout, OS error
        return {"refreshed": False, "stale": True, "error": f"price refresh failed: {exc.__class__.__name__}"}
    result: dict[str, Any] = {}
    text = proc.stdout or ""
    start = text.find("{")
    if start >= 0:
        try:
            result, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            result = {}
    live = int(result.get("live_prices_resolved") or 0)
    status: dict[str, Any] = {
        "refreshed": live > 0,
        "stale": live == 0,
        "live_prices_resolved": live,
        "prices_resolved": int(result.get("prices_resolved") or 0),
        "symbols_requested": int(result.get("symbols_requested") or 0),
    }
    if live == 0:
        status["error"] = str(result.get("pricing_best_guess_cause") or f"no live prices (exit code {proc.returncode})")
    return status


def run(retirement_system_base_dir: str | Path, *, log_path: str | Path | None = None, today: date | None = None,
        refresh: bool = True) -> dict[str, Any]:
    base_dir = Path(retirement_system_base_dir)
    input_dir = base_dir / "input"

    if input_dir.exists():
        source_files = sorted(input_dir.glob("*.csv"))
        guard_errors = onedrive_guard.check_files_safe_to_read(source_files)
        if guard_errors:
            return {"success": False, "errors": guard_errors}

    pricing = refresh_prices(base_dir) if refresh else {"refreshed": False, "stale": False, "skipped": True}
    snapshot = compute_snapshot(base_dir, today=today)
    snapshot["pricing"] = pricing
    snapshot["run_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    path = Path(log_path) if log_path else default_log_path(_APP_ROOT)
    history = append_or_replace_entry(path, snapshot)
    return {"success": True, "snapshot": snapshot, "log_path": str(path), "total_entries": len(history)}
