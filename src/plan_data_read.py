from __future__ import annotations

"""Read a Plan Data file the same way the running app does: SQLite
client_files table first (canonical), on-disk input/*.csv as a fallback.

A headless script (no Flask request context) that reads Plan Data directly
off disk only sees the import/export mirror -- if the SQLite DB already has
a newer row (the normal case once the app has run once), a disk-only read
returns stale data. See src/server/app_core.py: `_read_plan_data_file` for
the equivalent logic inside the running app, and src/monarch_db_sync.py for
the write-direction counterpart.
"""

from pathlib import Path

from . import config_backend


def read_plan_data_file(
    file_name: str,
    base_dir: str | Path,
    db_path: str | Path,
    *,
    workspace_id: str = "local",
    client_id: str = "local",
) -> str | None:
    content = config_backend.get_client_file(file_name, workspace_id, client_id, db_path)
    if content is not None:
        return content
    path = Path(base_dir) / "input" / file_name
    if path.exists():
        return path.read_text(encoding="utf-8-sig")
    return None
