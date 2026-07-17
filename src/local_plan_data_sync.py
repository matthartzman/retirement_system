from __future__ import annotations
"""Local Plan Data folder sync helpers.

The browser sends the selected local folder contents to the server before a
build. Command-line builds can use `System Configuration / Runtime /
local_plan_data_dir` in multi_user/system_config.csv for the same behavior.
"""

import os
import shutil
from pathlib import Path

try:
    from .runtime_config import load_runtime_config
    from .workspace_context import active_workspace_id, workspace_input_dir
    from .plan_data_registry import client_data_csv_files, client_data_derived_files
except Exception:  # pragma: no cover
    from src.runtime_config import load_runtime_config
    from src.workspace_context import active_workspace_id, workspace_input_dir
    from src.plan_data_registry import client_data_csv_files, client_data_derived_files

PLAN_DATA_CSV_FILES = [
    *client_data_csv_files(),
    "client_holdings.csv",
    "client_liabilities.csv",
    "target_allocation.csv",
    "client_spending_taxonomy.csv",
    "client_spending_aliases.csv",
    "client_spending_budget.csv",
    "client_spending_budget_lines.csv",
]
YTD_PLAN_DATA_FILES = [
    "ytd_transactions.csv",
    "ytd_account_setup.csv",
    "ytd_import_history.csv",
]
PLAN_DATA_DERIVED_FILES = client_data_derived_files()
PLAN_DATA_FILES = [*PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES, *PLAN_DATA_DERIVED_FILES]
REQUIRED_PLAN_DATA_CSV_FILES = {"client_data.csv", "client_holdings.csv"}


def _resolve_folder(root: Path) -> Path | None:
    try:
        raw = getattr(load_runtime_config(), "local_plan_data_dir", "")
    except Exception:
        raw = ""
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_absolute() else root / p


def sync_plan_data_from_folder(folder: str | Path, root: str | Path | None = None, *, require_required: bool = True) -> dict:
    project_root = Path(root or Path(__file__).resolve().parent.parent)
    source_dir = Path(folder).expanduser()
    if not source_dir.is_absolute():
        source_dir = project_root / source_dir
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"Plan Data folder not found: {source_dir}")

    missing = [name for name in REQUIRED_PLAN_DATA_CSV_FILES if not (source_dir / name).exists()]
    if require_required and missing:
        raise FileNotFoundError("Missing required Plan Data file(s): " + ", ".join(sorted(missing)))

    dest_dir = workspace_input_dir(active_workspace_id("local"), project_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in PLAN_DATA_FILES:
        src = source_dir / name
        if not src.exists():
            continue
        dest = dest_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        copied.append({"file": name, "source": str(src), "destination": str(dest), "bytes": dest.stat().st_size})
    return {"source_dir": str(source_dir), "destination_dir": str(dest_dir), "files": copied}


def sync_plan_data_from_env(root: str | Path | None = None, *, require_required: bool = True) -> dict | None:
    """Optionally copy the configured local Plan Data folder for CLI builds.

    UI/API builds save edits into the server working copy before launching the
    workbook process. Those builds set RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC
    so this command-line convenience hook cannot re-copy a stale
    local_plan_data_dir over the just-saved UI edits.
    """
    if str(os.environ.get("RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC", "") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    project_root = Path(root or Path(__file__).resolve().parent.parent)
    folder = _resolve_folder(project_root)
    if folder is None:
        return None
    return sync_plan_data_from_folder(folder, project_root, require_required=require_required)
