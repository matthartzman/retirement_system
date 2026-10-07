from __future__ import annotations

"""Feature-owned holdings, liabilities and HSA schedule service helpers.

Since WP6 the three datasets are tables of the active plan file (``holdings_lots``,
``liabilities``, ``hsa_schedule``); the CSV text the routes speak is rendered from and
parsed into them. ``base_dir`` / ``workspace_id`` / ``client_id`` / ``db_path`` are kept so the
route calls do not change; the plan file is the active plan (``active_plan``).
"""

from pathlib import Path
from typing import Any

from ..plan_datasets import active_dataset_text, write_active_dataset

EMPTY_HOLDINGS_CSV = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
EMPTY_LIABILITIES_CSV = "liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year,notes\n"
EMPTY_HSA_SCHEDULE_CSV = "year,optimizer_amount,override_amount,locked,note\n"


def _read(dataset: str, empty: str) -> dict[str, Any]:
    content = active_dataset_text(dataset)
    if content is not None:
        return {"source": "plan_file", "path": "", "content": content, "content_type": "text/csv"}
    return {"source": "empty_template", "path": "", "content": empty, "content_type": "text/csv"}


def _save(dataset: str, content: str) -> dict[str, Any]:
    if not content:
        raise ValueError("No content in request")
    rows = write_active_dataset(dataset, content)
    return {"success": True, "path": "", "bytes": len(content), "rows": rows}


def read_holdings(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    return _read("holdings", EMPTY_HOLDINGS_CSV)


def save_holdings(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    return _save("holdings", content)


def read_liabilities(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    return _read("liabilities", EMPTY_LIABILITIES_CSV)


def save_liabilities(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    return _save("liabilities", content)


def read_hsa_schedule(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    return _read("hsa_schedule", EMPTY_HSA_SCHEDULE_CSV)


def save_hsa_schedule(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    return _save("hsa_schedule", content)
