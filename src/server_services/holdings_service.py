from __future__ import annotations

"""Feature-owned holdings CSV service helpers."""

from pathlib import Path
from typing import Any

EMPTY_HOLDINGS_CSV = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
EMPTY_LIABILITIES_CSV = "liability_id,type,label,balance,interest_rate,monthly_payment,start_year,payoff_year,notes\n"


def read_holdings(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    try:
        from ..workspace_context import workspace_file
        from ..config_backend import get_client_file
    except ImportError:
        from src.workspace_context import workspace_file
        from src.config_backend import get_client_file
    p = workspace_file("client_holdings.csv", workspace_id, base_dir)
    if p.exists():
        return {"source": "workspace_file", "path": str(p), "content": None, "content_type": "text/csv"}
    content = get_client_file("client_holdings.csv", workspace_id, client_id, db_path)
    if content is not None:
        return {"source": "sqlite_client_file", "path": "", "content": content, "content_type": "text/csv"}
    return {"source": "empty_template", "path": "", "content": EMPTY_HOLDINGS_CSV, "content_type": "text/csv"}


def save_holdings(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    try:
        from ..workspace_context import workspace_file
        from ..config_backend import set_client_file
    except ImportError:
        from src.workspace_context import workspace_file
        from src.config_backend import set_client_file
    if not content:
        raise ValueError("No content in request")
    p = workspace_file("client_holdings.csv", workspace_id, base_dir, prefer_existing=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    set_client_file("client_holdings.csv", content, workspace_id, client_id, user_id, db_path)
    return {"success": True, "path": str(p), "bytes": len(content)}


def read_liabilities(*, base_dir: Path, workspace_id: str, client_id: str, db_path: Path) -> dict[str, Any]:
    try:
        from ..workspace_context import workspace_file
        from ..config_backend import get_client_file
    except ImportError:
        from src.workspace_context import workspace_file
        from src.config_backend import get_client_file
    p = workspace_file("client_liabilities.csv", workspace_id, base_dir)
    if p.exists():
        return {"source": "workspace_file", "path": str(p), "content": None, "content_type": "text/csv"}
    content = get_client_file("client_liabilities.csv", workspace_id, client_id, db_path)
    if content is not None:
        return {"source": "sqlite_client_file", "path": "", "content": content, "content_type": "text/csv"}
    return {"source": "empty_template", "path": "", "content": EMPTY_LIABILITIES_CSV, "content_type": "text/csv"}


def save_liabilities(*, content: str, base_dir: Path, workspace_id: str, client_id: str, user_id: str, db_path: Path) -> dict[str, Any]:
    try:
        from ..workspace_context import workspace_file
        from ..config_backend import set_client_file
    except ImportError:
        from src.workspace_context import workspace_file
        from src.config_backend import set_client_file
    if not content:
        raise ValueError("No content in request")
    p = workspace_file("client_liabilities.csv", workspace_id, base_dir, prefer_existing=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    set_client_file("client_liabilities.csv", content, workspace_id, client_id, user_id, db_path)
    return {"success": True, "path": str(p), "bytes": len(content)}
