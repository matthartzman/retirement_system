from __future__ import annotations

"""Feature-owned secret-management service helpers.

Routes own permission checks and audit logging.  This module validates payloads
and calls the local encrypted secret store so the route layer does
not own business rules.
"""

from pathlib import Path
from typing import Any, Callable


def set_secret_payload(
    body: dict[str, Any],
    *,
    workspace_id: str,
    db_path: Path,
    set_secret_fn: Callable[..., Any],
) -> tuple[dict[str, Any], int]:
    name = str((body or {}).get("name") or "").strip()
    value = str((body or {}).get("value") or "")
    if not name or not value:
        return {"success": False, "error": "name and value are required"}, 400
    set_secret_fn(name, value, workspace_id=workspace_id, db_path=db_path)
    return {"success": True, "name": name}, 200
