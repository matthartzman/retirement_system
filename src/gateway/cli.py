"""Server-side gateway CLIs, run by the Windows administrator on the server; no web route reaches them.

    python -m src.gateway.cli create-admin --db <gateway.db> --username <name> [--display-name <text>]
    python -m src.gateway.cli break-glass  --db <gateway.db> --username <admin>

The password is read from a hidden prompt (asked twice), or from one line of stdin with
``--password-stdin``. It is never taken from the command line, where it would land in shell history.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from typing import TextIO

from src.access_core import DEFAULT_SCRYPT_N

from .store import Actor, GatewayStore


def _actor() -> Actor:
    try:
        who = os.getlogin()
    except OSError:
        who = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    return Actor(None, f"cli:{who}", listener="cli")


def _password(args: argparse.Namespace, stdin: TextIO, stderr: TextIO) -> str | None:
    if args.password_stdin:
        return stdin.readline().rstrip("\r\n")
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat it: ")
    if first != second:
        print("The passwords do not match.", file=stderr)
        return None
    return first


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.gateway.cli", description=__doc__.split("\n\n", 1)[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in [("create-admin", "create the first admin (refused once any admin exists)"),
                            ("break-glass", "reset an admin's password and two-factor, unlock and re-enable it")]:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--db", required=True, help="path to gateway.db")
        sp.add_argument("--username", required=True)
        sp.add_argument("--password-stdin", action="store_true", help="read the password from one line of stdin")
        if name == "create-admin":
            sp.add_argument("--display-name", default="")
    return p


def main(argv: list[str] | None = None, *, stdin: TextIO | None = None, stdout: TextIO | None = None,
         stderr: TextIO | None = None, scrypt_n: int = DEFAULT_SCRYPT_N) -> int:
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    args = _parser().parse_args(argv)
    store = GatewayStore(args.db, scrypt_n=scrypt_n)
    actor, now = _actor(), time.time()
    if args.command == "create-admin":
        if store.count_active_admins() or any(u["role"] == "admin" for u in store.list_users(now)):
            print("An admin already exists; add more admins from the Users page (or use break-glass).", file=stderr)
            return 1
        password = _password(args, stdin, stderr)
        if password is None:
            return 2
        try:
            GatewayStore.check_password(password)
            uid = store.create_user(args.username, args.display_name, "admin", password, now=now, actor=actor,
                                    must_change=False, event="first admin created")
        except ValueError as exc:
            print(f"Not created: {exc}", file=stderr)
            return 2
        print(f"Admin '{store.get_user(uid)['username']}' created (id {uid}). Two-factor is set up at first sign-in.",
              file=stdout)
        return 0

    user = store.find_user(args.username)
    if user is None:
        print(f"There is no such account: {args.username}", file=stderr)
        return 1
    if user["role"] != "admin":
        print("That account is not an admin; reset ordinary accounts from the Users page.", file=stderr)
        return 1
    password = _password(args, stdin, stderr)
    if password is None:
        return 2
    try:
        GatewayStore.check_password(password)
    except ValueError as exc:
        print(f"Not reset: {exc}", file=stderr)
        return 2
    uid = int(user["id"])
    store.set_password(uid, password, must_change=False, now=now, actor=actor, event="break-glass reset")
    store.reset_totp(uid, now=now, actor=actor, event=None)
    store.unlock(uid, now=now, actor=actor, event=None)
    if user["disabled"]:
        store.set_disabled(uid, False, now=now, actor=actor)
    store.end_user_sessions(uid)
    print(f"Admin '{user['username']}' reset: new password set, two-factor cleared (set up again at next sign-in), "
          "account unlocked and enabled, sessions ended.", file=stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
