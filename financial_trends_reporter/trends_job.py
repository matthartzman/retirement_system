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

from .app_sync import sync_from_app  # noqa: E402
from .balance_store import DB_FILENAME, default_source_path, import_balances  # noqa: E402
from .passthrough_decisions import decisions_path_for_log, load_decisions  # noqa: E402
from .trends_log import append_or_replace_entry, default_log_path  # noqa: E402
from .trends_metrics import compute_snapshot  # noqa: E402


PRICE_REFRESH_TIMEOUT_SECONDS = 150


class RunCancelled(Exception):
    """The user pressed Cancel build in the Updating Data window."""


def _run_cancellable(cmd, *, cwd, timeout, cancel):
    """``subprocess.run`` that also stops (kills the child) when ``cancel()`` turns true."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    waited = 0.0
    while True:
        try:
            out, err = proc.communicate(timeout=0.25)
            return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            waited += 0.25
            if cancel():
                proc.kill()
                proc.communicate()
                raise RunCancelled()
            if waited >= timeout:
                proc.kill()
                proc.communicate()
                raise


def refresh_prices(base_dir: Path, *, timeout: float = PRICE_REFRESH_TIMEOUT_SECONDS, cancel=None) -> dict[str, Any]:
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
        cmd = [sys.executable, str(script)]
        if cancel is None:
            proc = subprocess.run(cmd, cwd=str(base_dir), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
        else:
            proc = _run_cancellable(cmd, cwd=str(base_dir), timeout=timeout, cancel=cancel)
    except RunCancelled:
        raise
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
        refresh: bool = True, cancel=None) -> dict[str, Any]:
    """``cancel``: optional callable; when it turns true the run stops at the next step and returns
    ``{"success": False, "cancelled": True}`` without writing the log."""
    base_dir = Path(retirement_system_base_dir)
    input_dir = base_dir / "input"

    if input_dir.exists():
        source_files = sorted(input_dir.glob("*.csv"))
        guard_errors = onedrive_guard.check_files_safe_to_read(source_files)
        if guard_errors:
            return {"success": False, "errors": guard_errors}

    try:
        pricing = refresh_prices(base_dir, cancel=cancel) if refresh else {"refreshed": False, "stale": False, "skipped": True}
    except RunCancelled:
        return {"success": False, "cancelled": True, "error": "Cancelled."}
    path = Path(log_path) if log_path else default_log_path(_APP_ROOT)
    # Monarch balances are best-effort here: the 03:30 chain imports them too, and a
    # missing/rejected file must not fail the snapshot (the result just reports it).
    balances_db = path.with_name(DB_FILENAME)
    try:
        balances = import_balances(balances_db, default_source_path(base_dir), today=today)
    except Exception as exc:  # noqa: BLE001 - a locked/unwritable store must not stop the snapshot
        balances = {"success": False, "status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
    if cancel and cancel():
        return {"success": False, "cancelled": True, "error": "Cancelled."}
    if balances.get("status") != "error":
        sync_from_app(balances_db, base_dir)  # type, match and ignore from the app's Monarch mapping (never raises)
    snapshot = compute_snapshot(base_dir, today=today, passthrough_decisions=load_decisions(decisions_path_for_log(path)),
                                balances_db=balances_db if balances.get("status") != "error" else None)
    if cancel and cancel():
        return {"success": False, "cancelled": True, "error": "Cancelled."}
    snapshot["pricing"] = pricing
    snapshot["run_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    history = append_or_replace_entry(path, snapshot)
    return {"success": True, "snapshot": snapshot, "log_path": str(path), "total_entries": len(history), "balances": balances}
