from __future__ import annotations
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config_backend import load_active_config, setting
from src.system_config import load_system_config
from src.portfolio_analytics import analyze_drift
from src.workspace_context import candidate_input_files, first_existing, workspace_output_dir


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
    target_setting = setting(system_data, "System Configuration", "Portfolio Drift", "target_allocation_file", "target_allocation.csv") or "target_allocation.csv"
    target_file = first_existing(candidate_input_files(Path(target_setting).name, workspace_id, ROOT)) or (ROOT / target_setting)
    threshold = _pct_threshold(setting(system_data, "System Configuration", "Portfolio Drift", "rebalance_threshold_pct", "5.00%"), 0.05)
    rows = analyze_drift(
        target_file=target_file,
        holdings_csv=first_existing(candidate_input_files("client_holdings.csv", workspace_id, ROOT)) or (ROOT / "input/client_holdings.csv"),
        security_master_csv=first_existing(candidate_input_files("security_master.csv", workspace_id, ROOT)) or (ROOT / "reference_data" / "security_master.csv"),
        threshold_pct=threshold,
        workspace_id=workspace_id,
    )
    out = workspace_output_dir(workspace_id, ROOT) / "portfolio_drift.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
