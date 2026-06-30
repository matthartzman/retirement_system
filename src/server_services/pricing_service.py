from __future__ import annotations

"""Feature-owned pricing service helpers.

HTTP adapters pass local workspace/runtime context into these functions.  The
service owns request-independent pricing refresh, symbol trace, and snapshot
lookup logic so route modules can stay thin while the Flask-free runtime is
being decomposed.
"""

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable


def refresh_prices(
    *,
    base_dir: Path,
    output_dir: Path,
    system_config_csv: Path,
    max_build_seconds: int | float,
) -> dict[str, Any]:
    """Run the local price refresh tool and return its parsed payload."""
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV"] = str(system_config_csv)
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8:replace")
    out_path = output_dir / "price_refresh_result.json"
    try:
        if out_path.exists():
            out_path.unlink()
    except Exception:
        pass
    result = subprocess.run(
        [sys.executable, str(base_dir / "tools" / "refresh_prices.py")],
        cwd=str(base_dir),
        capture_output=True,
        text=True,
        timeout=max_build_seconds,
        env=env,
    )
    payload: dict[str, Any] = {}
    if out_path.exists():
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {"error": f"Price refresh result was not valid JSON: {exc}"}
    else:
        text = (result.stdout or "").strip()
        try:
            start = text.rfind("{\n")
            payload = json.loads(text[start:] if start >= 0 else text) if text else {}
        except Exception:
            payload = {"error": "Price refresh did not produce price_refresh_result.json", "returncode": result.returncode}
    success = (result.returncode == 0) and not payload.get("error")
    return {"success": success, "result": payload, "stdout": result.stdout[-4000:], "stderr": result.stderr[-2000:], "returncode": result.returncode}


def configured_market_data_provider(load_active_config_fn: Callable[[], tuple[dict, dict]] | None = None):
    try:
        from ..market_data import MarketDataProvider
        from ..config_backend import load_active_config, setting
    except Exception:
        from src.market_data import MarketDataProvider
        from src.config_backend import load_active_config, setting
    loader = load_active_config_fn or load_active_config
    try:
        data, meta = loader()
    except Exception:
        data, meta = {}, {"backend": "unavailable"}
    provider = MarketDataProvider()
    provider.configure_api_keys(
        fmp_api_key=setting(data, "Market Pricing", "API", "fmp_api_key", "") if data else "",
        alpha_vantage_api_key=setting(data, "Market Pricing", "API", "alpha_vantage_api_key", "") if data else "",
    )
    provider.configure_holdings_pricing(
        mode="LIVE",
        cache_hours=setting(data, "Market Pricing", "Holdings", "cache_hours", "24") if data else "24",
    )
    provider.configure_transport(
        timeout_seconds=os.environ.get("RETIREMENT_SYSTEM_PRICE_TIMEOUT_SECONDS", "4"),
        max_retries=os.environ.get("RETIREMENT_SYSTEM_PRICE_MAX_RETRIES", "1"),
    )
    return provider, meta


def run_price_symbol_trace(symbol: str, *, workspace_id: str, on_step=None) -> dict[str, Any]:
    provider, meta = configured_market_data_provider()
    trace = provider.verbose_symbol_test(str(symbol or "").strip().upper(), on_step=on_step)
    trace["config_backend"] = meta.get("backend")
    trace["config_path"] = str(meta.get("path") or "")
    trace["workspace_id"] = workspace_id
    return trace


def single_symbol_test_payload(body: dict[str, Any], *, workspace_id: str, audit: Callable[[str, dict[str, Any]], None] | None = None) -> tuple[dict[str, Any], int]:
    symbol = str((body or {}).get("symbol") or "").strip().upper()
    if not symbol:
        return {"success": False, "error": "Enter a ticker symbol to test."}, 400
    try:
        trace = run_price_symbol_trace(symbol, workspace_id=workspace_id)
        live_ok = bool(trace.get("success"))
        if audit:
            audit("price_symbol_tested", {"symbol": symbol, "success": live_ok, "selected_provider": trace.get("selected_provider")})
        return {"success": True, "live_pricing_working": live_ok, "result": trace}, 200
    except Exception as exc:  # noqa: BLE001 - diagnostic endpoint reports trace tail
        err_trace = {
            "success": False,
            "symbol": symbol,
            "summary": f"Tester route failed before the provider trace completed: {exc}",
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-4000:],
            "steps": [],
        }
        if audit:
            audit("price_symbol_test_failed", {"symbol": symbol, "error": str(exc)})
        return {"success": True, "live_pricing_working": False, "result": err_trace}, 200


class PriceSymbolTestRegistry:
    def __init__(self, ttl_seconds: int = 15 * 60):
        self.ttl_seconds = ttl_seconds
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def prune(self) -> None:
        now = time.time()
        with self.lock:
            for jid, job in list(self.jobs.items()):
                if now - float(job.get("started_at", now)) > self.ttl_seconds:
                    self.jobs.pop(jid, None)

    def start_payload(self, body: dict[str, Any], *, workspace_id: str) -> tuple[dict[str, Any], int]:
        self.prune()
        symbol = str((body or {}).get("symbol") or "").strip().upper()
        if not symbol:
            return {"success": False, "error": "Enter a ticker symbol to test."}, 400
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "symbol": symbol, "status": "running", "started_at": time.time(), "updated_at": time.time(), "steps": [], "result": None, "error": ""}
        with self.lock:
            self.jobs[job_id] = job

        def worker() -> None:
            def on_step(step: dict[str, Any]) -> None:
                with self.lock:
                    j = self.jobs.get(job_id)
                    if not j:
                        return
                    j.setdefault("steps", []).append(step)
                    j["updated_at"] = time.time()
            try:
                trace = run_price_symbol_trace(symbol, workspace_id=workspace_id, on_step=on_step)
                with self.lock:
                    j = self.jobs.get(job_id)
                    if j is not None:
                        j["status"] = "completed"
                        j["result"] = trace
                        j["updated_at"] = time.time()
            except Exception as exc:  # noqa: BLE001 - diagnostic endpoint reports trace tail
                err_trace = {"success": False, "symbol": symbol, "summary": f"Tester worker failed before the provider trace completed: {exc}", "error": str(exc), "traceback_tail": traceback.format_exc()[-4000:], "steps": []}
                with self.lock:
                    j = self.jobs.get(job_id)
                    if j is not None:
                        j["status"] = "error"
                        j["error"] = str(exc)
                        j["result"] = err_trace
                        j["updated_at"] = time.time()

        threading.Thread(target=worker, name=f"price-symbol-test-{job_id}", daemon=True).start()
        return {"success": True, "job_id": job_id, "symbol": symbol, "status": "running"}, 200

    def status_payload(self, job_id: str) -> tuple[dict[str, Any], int]:
        with self.lock:
            job = dict(self.jobs.get(job_id) or {})
            if job.get("steps") is not None:
                job["steps"] = list(job.get("steps") or [])
        if not job:
            return {"success": False, "error": "Pricing tester job was not found. Start a new test."}, 404
        result = job.get("result") or {"success": False, "symbol": job.get("symbol"), "summary": "Calling live providers...", "steps": job.get("steps") or [], "selected_provider": "", "selected_price": None}
        if job.get("result") and not result.get("steps") and job.get("steps"):
            result["steps"] = job.get("steps") or []
        return {
            "success": True,
            "job_id": job_id,
            "status": job.get("status"),
            "symbol": job.get("symbol"),
            "live_pricing_working": bool(result.get("success")),
            "result": result,
            "steps": job.get("steps") or [],
            "error": job.get("error") or "",
        }, 200


def latest_price_snapshots(*, workspace_id: str, db_path: Path) -> dict[str, Any]:
    try:
        from ..portfolio_analytics import load_latest_snapshots
    except Exception:
        from src.portfolio_analytics import load_latest_snapshots
    return load_latest_snapshots(workspace_id=workspace_id, db_path=db_path)
