"""``python -m src.identity create-admin``: make the first administrator (and migrate ``access.db``)."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .store import LEGACY_ACCESS_DB, default_db_path, open_identity_store


def main(argv: list[str] | None = None, read_password=getpass.getpass) -> int:
    parser = argparse.ArgumentParser(prog="identity")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="create an administrator account (password is prompted, never an argument)")
    p.add_argument("--username", required=True)
    p.add_argument("--name", default="", help="display name (defaults to the username)")
    p.add_argument("--db", type=Path, default=None, help="identity.db path (default: <workspace>/local_state/identity.db)")
    p.add_argument("--access-db", type=Path, default=None, help="legacy Financial Insights access.db to migrate first")
    args = parser.parse_args(argv)

    db = args.db or default_db_path()
    legacy = args.access_db
    if legacy is None and args.db is None:
        from src import platform_runtime

        legacy = platform_runtime.workspace_root() / "financial_trends_reporter" / "data" / LEGACY_ACCESS_DB
    store = open_identity_store(db, legacy_access_path=legacy)
    password = read_password("Password (10+ characters): ")
    if read_password("Repeat password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        store.add_user(args.name or args.username, args.username, password, role="admin", insights=False, must_change=False)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    store.log_admin("cli", "create-admin", args.username.strip().lower())
    print(f"Administrator '{args.username.strip().lower()}' created in {db}.")
    return 0
