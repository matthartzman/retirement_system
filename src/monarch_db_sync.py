from __future__ import annotations

"""Mirror on-disk YTD CSVs into the local SQLite plan-data store.

The running desktop app's canonical Plan Data storage is the local SQLite
database (the `client_files` table -- see
src/server/app_core.py: `_read_plan_data_file` / `_write_plan_data_file`).
`input/*.csv` on disk is only an import/export mirror that seeds the DB the
first time it's read; once the DB has a row for a file, disk writes to that
file are invisible to the running app unless also pushed into the DB.

tools/monarch_autoimport.py writes ytd_transactions.csv (and the account
setup / import history files it touches) to disk headlessly, with no Flask
app or request context available to go through `_write_plan_data_file`. This
module does the same "push to DB" step standalone.
"""

from pathlib import Path

from . import config_backend

YTD_FILES = ["ytd_transactions.csv", "ytd_account_setup.csv", "ytd_import_history.csv"]


def sync_ytd_files_to_db(
    input_dir: str | Path,
    db_path: str | Path,
    *,
    workspace_id: str = "local",
    client_id: str = "local",
    updated_by: str = "monarch_autoupdate",
) -> list[str]:
    """Push the current on-disk YTD CSVs into the SQLite client_files table.

    Returns the filenames actually synced; a file absent on disk (e.g. no
    import history yet on a brand new workspace) is skipped, not an error.
    """
    synced: list[str] = []
    input_dir = Path(input_dir)
    for name in YTD_FILES:
        path = input_dir / name
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8-sig")
        config_backend.set_client_file(name, content, workspace_id, client_id, updated_by, db_path)
        synced.append(name)
    return synced
