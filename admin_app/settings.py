"""Install-wide settings for the Admin app: the one module that reads and writes them.

The rows are the runtime settings held in ``app.db`` (``src/system_config.py``). Engine knobs belong to a plan and are
refused here. A later move of these rows to a ``system.db`` (multi-user server) is a change to this file only.
No value of a secret row is ever returned, logged or audited.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.app_state import app_store_path_for
from src.engine_defaults import ENGINE_SECTIONS
from src.server_services import admin_service
from src.system_config import load_system_config, save_settings_rows, settings_rows, system_setting
from src.version import VERSION

PLANNER_PORT = 5050
INSIGHTS_LOCAL_PORT = 5057
INSIGHTS_REMOTE_PORT = 5058
SECRET_ROWS = admin_service.SECRET_CONFIG_LABELS


class SettingsService:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.app_db = app_store_path_for(self.root)

    # -- rows ---------------------------------------------------------------------------------------------------
    def rows(self) -> list[list[str]]:
        return [self._mask(r) for r in settings_rows(self.app_db)]

    @staticmethod
    def _mask(row: list[str]) -> list[str]:
        row = list(row)
        if len(row) > 3 and str(row[2]).strip() in SECRET_ROWS:
            row[3] = ""
        return row

    def payload(self) -> dict[str, Any]:
        return {"success": True, "path": str(self.app_db), "rows": self.rows()}

    def _values(self) -> dict[tuple, str]:
        return {tuple(str(c) for c in r[:3]): (str(r[3]) if len(r) > 3 else "") for r in settings_rows(self.app_db)[1:]}

    def save(self, rows: Any) -> tuple[dict[str, Any], int]:
        """Save runtime rows. Returns ``(payload, status)``."""
        if isinstance(rows, str):
            rows = list(csv.reader(io.StringIO(rows)))
        if not isinstance(rows, list):
            return {"success": False, "error": "rows required"}, 400
        clean = [list(r) for r in rows if isinstance(r, (list, tuple)) and r]
        engine = [r for r in clean if str(r[0]).strip() in ENGINE_SECTIONS]
        if engine:
            return {"success": False,
                    "error": "Engine settings are saved per plan; use Plan assumptions in the planner.",
                    "engine_sections": sorted({str(r[0]).strip() for r in engine})}, 400
        before = self._values()
        clean, stored = admin_service.divert_secret_rows(clean)
        save_settings_rows(clean, self.app_db)
        after = self._values()
        changed = sum(1 for k in set(before) | set(after) if before.get(k) != after.get(k))
        payload: dict[str, Any] = {"success": True, "path": str(self.app_db), "changed": changed}
        if stored:
            payload["secrets_stored"] = stored
        return payload, 200

    def setting(self, subsection: str, label: str, default: str = "") -> str:
        return system_setting(load_system_config(self.app_db), subsection, label, default)

    # -- system -------------------------------------------------------------------------------------------------
    def planner_port(self) -> int:
        try:
            return int(float(self.setting("Dashboard", "port", str(PLANNER_PORT)) or PLANNER_PORT))
        except ValueError:
            return PLANNER_PORT

    def server_status(self) -> dict[str, Any]:
        host = self.setting("Dashboard", "host", "127.0.0.1")
        port = self.planner_port()
        out = admin_service.server_status_payload(
            version=VERSION, cfg=SimpleNamespace(dashboard_host=host, dashboard_port=port), system_config_path=self.app_db)
        out["apps"] = {name: ping(p) for name, p in (("planner", port), ("insights_local", INSIGHTS_LOCAL_PORT),
                                                      ("insights_remote", INSIGHTS_REMOTE_PORT))}
        out["restart_required_note"] = "Host and port changes take effect after the planner restarts."
        return out

    def clear_webview_cache(self) -> dict[str, Any]:
        return admin_service.clear_webview_disk_cache(self.root)

    def tax_law_dashboard(self) -> dict[str, Any]:
        from src.governance import tax_law_dashboard  # noqa: PLC0415

        try:
            max_lag = int(float(self.setting("Tax Governance", "max_tax_table_lag_years", "1") or 1))
        except ValueError:
            max_lag = 1
        return {"success": True, "version": VERSION, "rows": tax_law_dashboard(max_lag_years=max_lag), "max_lag_years": max_lag}

    def shutdown_planner(self) -> dict[str, Any]:
        port = self.planner_port()
        if not ping(port):
            return {"success": False, "error": f"The planner is not answering on port {port} (desktop mode has no local server)."}
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/admin/server/shutdown", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 - fixed loopback URL
                return json.loads(r.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return {"success": False, "error": f"Could not reach the planner: {exc}"}


def ping(port: int, timeout: float = 0.6) -> bool:
    """True when something answers HTTP on this loopback port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/api/ping", timeout=timeout):  # noqa: S310
            return True
    except urllib.error.HTTPError:
        return True  # it answered, even if with an error status
    except (urllib.error.URLError, OSError, ValueError):
        return False
