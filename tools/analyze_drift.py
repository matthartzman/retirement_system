from __future__ import annotations
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config_backend import load_active_config, setting
from src.system_config import load_system_config
from src.portfolio_analytics import analyze_drift


def _pct_threshold(value: str, default: float = 0.05) -> float:
    try:
        s = str(value or "").strip().replace("%", "")
        f = float(s)
        return f / 100.0 if f > 1 else f
    except Exception:
        return default


def main() -> int:
    data, meta = load_active_config()
    system_data = load_system_config()
    workspace_id = meta.get("workspace_id", "local")
    threshold = _pct_threshold(setting(system_data, "System Configuration", "Portfolio Drift", "rebalance_threshold_pct", "5.00%"), 0.05)
    rows = analyze_drift(
        threshold_pct=threshold,
        workspace_id=workspace_id,
    )
    print(json.dumps(rows, indent=2))  # the caller (portfolio_service) reads the rows from stdout
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
