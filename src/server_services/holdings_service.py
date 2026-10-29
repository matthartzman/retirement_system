from __future__ import annotations

"""Feature-owned holdings, liabilities and HSA schedule service helpers.

Since WP6 the three datasets are tables of the active plan file (``holdings_lots``,
``liabilities``, ``hsa_schedule``); the CSV text the routes speak is rendered from and
parsed into them. ``base_dir`` / ``workspace_id`` / ``client_id`` / ``db_path`` are kept so the
route calls do not change; the plan file is the active plan (``active_plan``).
"""

from datetime import date
from pathlib import Path
from typing import Any

from .. import platform_runtime
from ..active_plan import active_plan_store
from ..import_preview import _REPLACE_MODES, _csv_dict_rows, detect_sold_lots
from ..plan_datasets import active_dataset_text, write_active_dataset

EMPTY_HOLDINGS_CSV = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
EMPTY_LIABILITIES_CSV = "liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year,payoff_month,carry_zero,notes\n"
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


def save_holdings(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path,
                  import_mode: str | None = None, today: date | None = None) -> dict[str, Any]:
    """Save the holdings CSV. A replace-style ``import_mode`` also queues the lots the new file no longer
    holds as unmatched sale candidates (never confirmed here); a plain save infers nothing."""
    if str(import_mode or "").strip().lower() not in _REPLACE_MODES:
        return _save("holdings", content)
    previous = active_dataset_text("holdings") or ""
    result = _save("holdings", content)
    found = detect_sold_lots(_csv_dict_rows(previous)[0], _csv_dict_rows(content)[0])
    result["sale_candidates_added"] = _queue_candidates(found["candidates"], (today or platform_runtime.today()).isoformat())
    result["potential_sales"] = {"count": len(found["candidates"]), **found}
    return result


def _queue_candidates(candidates: list[dict[str, Any]], sale_date: str) -> int:
    """Add ``candidates`` to the sale queue, skipping one already waiting for the same account, symbol and
    shares so saving the same import twice never doubles the queue. Returns how many were added."""
    if not candidates:
        return 0
    store = active_plan_store()
    try:
        repo = store.sales
        waiting = {(c["account"].lower(), c["symbol"], round(float(c["shares"] or 0), 6))
                   for c in repo.list_candidates(state="unmatched") if c["source"] == "holdings_diff"}
        added = 0
        for c in candidates:
            key = (c["account"].lower(), c["symbol"], round(c["shares"], 6))
            if key in waiting:
                continue
            repo.add_candidate(source="holdings_diff", sale_date=sale_date, account=c["account"], symbol=c["symbol"], shares=c["shares"])
            waiting.add(key)
            added += 1
        return added
    finally:
        store.close()


def read_liabilities(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    return _read("liabilities", EMPTY_LIABILITIES_CSV)


def save_liabilities(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    return _save("liabilities", content)


def read_hsa_schedule(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    return _read("hsa_schedule", EMPTY_HSA_SCHEDULE_CSV)


def save_hsa_schedule(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    return _save("hsa_schedule", content)
