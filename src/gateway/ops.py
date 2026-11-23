"""Operator commands for the gateway server, run by the Windows administrator (no web route reaches them).

    python -m src.gateway.ops backup-key create  --config gateway.json
    python -m src.gateway.ops key check|seal|rotate|export  --config gateway.json [--out <file>]
    python -m src.gateway.ops backup run|list|verify  --config gateway.json [--archive <file>]
    python -m src.gateway.ops restore --config gateway.json --archive <file> (--user <id> | --gateway-db-out <new file>)
    python -m src.gateway.ops migrate-all --config gateway.json [--report <file>]
    python -m src.gateway.ops funnel check|apply|off --config gateway.json [--external-port 8443] [--yes]
    python -m src.gateway.ops power show|apply|revert [--yes]
    python -m src.gateway.ops health --config gateway.json

``--config`` is the same gateway.json the service uses; explicit flags override it.  Commands that change the
machine (``funnel apply|off``, ``power apply|revert``) do nothing without ``--yes``: they print what they would do.
Exit status: 0 success, 1 a check or operation failed, 2 refused or bad arguments.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TextIO

from . import backup_crypto as bc
from . import backup_dest as bd
from . import backup_store as bs


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.gateway.ops", description=__doc__.split("\n\n", 1)[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="the service's gateway.json (supplies the defaults below)")
    common.add_argument("--data-root", type=Path)
    common.add_argument("--gateway-db", type=Path)
    common.add_argument("--backup-dir", type=Path)
    common.add_argument("--key-file", type=Path)
    common.add_argument("--install-dir", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    k = sub.add_parser("backup-key", parents=[common])
    k.add_argument("action", choices=["create"])
    kk = sub.add_parser("key", parents=[common], help="inspect, seal (DPAPI) or rotate the backup key")
    kk.add_argument("action", choices=["check", "seal", "rotate", "export"])
    kk.add_argument("--out", type=Path, help="export: where to write the PLAIN key ring (an offline copy)")
    kk.add_argument("--gateway-sid", help="check: the gateway's account SID (default SYSTEM, the service account)")
    b = sub.add_parser("backup", parents=[common])
    b.add_argument("action", choices=["run", "list", "verify"])
    b.add_argument("--archive", type=Path)
    r = sub.add_parser("restore", parents=[common])
    r.add_argument("--archive", type=Path, required=True)
    r.add_argument("--user", type=int)
    r.add_argument("--gateway-db-out", type=Path)
    m = sub.add_parser("migrate-all", parents=[common])
    m.add_argument("--report", type=Path)
    m.add_argument("--python", default=sys.executable)
    f = sub.add_parser("funnel", parents=[common])
    f.add_argument("action", choices=["check", "apply", "off"])
    f.add_argument("--external-port", type=int, default=8443)
    f.add_argument("--funnel-port", type=int)
    f.add_argument("--local-port", type=int)
    f.add_argument("--yes", action="store_true")
    w = sub.add_parser("power")
    w.add_argument("action", choices=["show", "apply", "revert"])
    w.add_argument("--state-file", type=Path, default=Path("power_plan_before.json"))
    w.add_argument("--yes", action="store_true")
    sub.add_parser("health", parents=[common])
    return p


def _defaults(args: argparse.Namespace) -> None:
    """Fill unset options from the gateway config's argv (the same parser the gateway itself uses)."""
    if not getattr(args, "config", None):
        return
    from .server import _parser as gateway_parser  # noqa: PLC0415
    from .service import config_argv  # noqa: PLC0415

    g = gateway_parser().parse_args(config_argv(args.config))
    pick = {"data_root": g.data_root, "gateway_db": g.db, "backup_dir": g.backup_dir,
            "key_file": getattr(g, "backup_key_file", None), "install_dir": g.install_dir}
    for name, value in pick.items():
        if hasattr(args, name) and getattr(args, name) is None and value:
            setattr(args, name, Path(value))
    for name, value in (("funnel_port", g.funnel_port), ("local_port", g.local_port)):
        if hasattr(args, name) and getattr(args, name) is None:
            setattr(args, name, value)


def _need(args: argparse.Namespace, *names: str) -> str | None:
    missing = [n.replace("_", "-") for n in names if getattr(args, n, None) is None]
    return ("missing: --" + ", --".join(missing) + " (or give --config)") if missing else None


def _dest(args: argparse.Namespace) -> Path:
    return bd.validate_backup_destination(args.backup_dir or bd.default_backup_dir(), data_root=args.data_root,
                                          install_dir=args.install_dir, key_file=args.key_file)


def _worker_ports(data_root: Path | None) -> list[int]:
    ports: list[int] = []
    if data_root and (Path(data_root) / "users").is_dir():
        for f in (Path(data_root) / "users").glob("*/local_state/worker.port.json"):
            try:
                ports.append(int(json.loads(f.read_text(encoding="utf-8"))["port"]))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return ports


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None, stderr: TextIO | None = None,
         run=None, clock=time.time) -> int:
    import subprocess  # noqa: PLC0415

    out, err = stdout or sys.stdout, stderr or sys.stderr
    run = run or subprocess.run
    args = _parser().parse_args(argv)

    def say(text: str = "") -> None:
        print(text, file=out)

    def refuse(text: str, code: int = 2) -> int:
        print(text, file=err)
        return code

    try:
        _defaults(args)
        if args.command == "power":
            return _power(args, say, refuse, run)
        if args.command == "funnel":
            return _funnel(args, say, refuse, run, err)
        if args.command == "health":
            return _health(args, say)
        if args.command == "key":
            return _key(args, say, refuse)
        return _backup_family(args, say, refuse, clock)
    except bd.BackupDestinationError as exc:
        return refuse(f"Refused: {exc}")
    except bc.WrongKeyError as exc:
        return refuse(f"Wrong or missing key: {exc}. Nothing was changed.", 1)
    except bc.CorruptBackupError as exc:
        return refuse(f"The archive is damaged: {exc}. Nothing was changed.", 1)
    except bs.RestoreError as exc:
        return refuse(f"Not restored: {exc}", 1)
    except ValueError as exc:
        return refuse(str(exc))


_DEFAULT = object()


def _key(args, say, refuse, *, crypt=_DEFAULT) -> int:
    """``key check|seal|rotate|export`` (SEC-08). ``crypt`` is a (protect, unprotect) pair; Windows DPAPI by default."""
    from . import key_acl  # noqa: PLC0415

    if (miss := _need(args, "key_file")):
        return refuse(miss)
    crypt = bc.default_protect() if crypt is _DEFAULT else crypt  # None: no DPAPI here (tests, non-Windows)
    path = Path(args.key_file)
    unprotect = crypt[1] if crypt else None
    ring = bc.read_key_file(path, unprotect=unprotect)
    sealed = bc.is_sealed(path)
    if args.action == "check":
        findings = key_acl.key_file_findings(path, gateway_sid=args.gateway_sid or "S-1-5-18")
        say(f"Key file: {path}")
        say(f"  keys in the ring: {len(ring.keys)} (current id {ring.current_id.hex()})")
        say("  sealed with DPAPI: " + ("yes (machine scope)" if sealed else "NO (plain file; run 'key seal' on the server)"))
        for f in findings:
            say(f"  PROBLEM: {f}")
        say("  permissions: " + ("not checked on this platform" if not findings and crypt is None else
                                 "only the expected accounts can read it" if not findings else "TOO OPEN"))
        return 1 if findings else 0
    if args.action == "export":
        if args.out is None:
            return refuse("missing: --out")
        bd.validate_key_location(args.out, backup_dir=args.backup_dir, data_root=args.data_root, install_dir=args.install_dir)
        if Path(args.out).exists():
            return refuse("The output file already exists; it is never overwritten.", 1)
        bc.write_keyring_file(Path(args.out), ring)  # plain on purpose: this is the offline recovery copy
        say(f"Plain key ring ({len(ring.keys)} key(s)) written to {args.out}. Move it OFFLINE now and delete it here.")
        return 0
    if args.action == "seal":
        if crypt is None:
            return refuse("Sealing needs Windows DPAPI; on this platform the key stays a plain file.", 1)
        if sealed:
            say("The key file is already sealed; nothing to do.")
            return 0
        bc.write_keyring_file(path, ring, protect=crypt[0])
        back = bc.read_key_file(path, unprotect=unprotect)
        if bytes(back) != bytes(ring) or set(back.keys) != set(ring.keys):
            return refuse("The sealed key did not read back; the file was NOT trusted. Restore your offline copy.", 1)
        say("Sealed with Windows DPAPI (machine scope: the service and any administrator on THIS machine can open it; "
            "a copy of the file elsewhere is useless). Keep your offline copy of the key: it is what restores backups "
            "on a rebuilt machine.")
        return 0
    # rotate
    new = bc.rotate_keyring(ring)
    bc.write_keyring_file(path, new, protect=crypt[0] if (sealed and crypt) else None)
    say(f"New backup key {new.current_id.hex()} is now current; {len(new.keys) - 1} earlier key(s) are kept, so old "
        "archives still open. Restart the gateway service so it encrypts new backups with the new key, then run "
        "'ops key export' and store the new offline copy (the old offline copy does NOT contain the new key).")
    return 0


def _backup_family(args, say, refuse, clock) -> int:
    cmd = args.command
    if cmd == "backup-key":
        if (miss := _need(args, "key_file")):
            return refuse(miss)
        dest = _dest(args)
        bd.validate_key_location(args.key_file, backup_dir=dest, data_root=args.data_root, install_dir=args.install_dir)
        fresh_folder = not args.key_file.parent.exists()
        try:
            bc.write_key_file(args.key_file)
        except FileExistsError:
            return refuse("A key file already exists there; it is never overwritten (that would orphan every backup).", 1)
        locked = False
        if fresh_folder:  # only a folder this command created is locked; an existing one is never re-permissioned
            try:
                from . import acl, winapi  # noqa: PLC0415

                acl.lock_gateway_only(args.key_file.parent, gateway_sid=winapi.current_user_sid())
                locked = True
            except Exception:  # noqa: BLE001 - not on Windows or not elevated: say so, never claim it was locked
                locked = False
        say("The key folder is readable only by the gateway account, SYSTEM and Administrators." if locked else
            "NOTE: the key folder's permissions were NOT changed; lock it to the gateway account yourself.")
        say(f"Backup key created at {args.key_file}. COPY IT OFFLINE NOW (a USB stick in a safe, a password manager "
            "attachment): without it every backup is unreadable. It is not stored anywhere else.")
        return 0
    if cmd == "backup" and args.action == "list":
        dest = _dest(args)
        for a in bs.list_archives(dest):
            say(f"{a['name']}  {a['kind']:<4} {'user ' + str(a['user']) if a['user'] else '':<8} {a['size']} bytes")
        return 0
    if (miss := _need(args, "key_file")):
        return refuse(miss)
    master = bc.read_key_file(args.key_file)
    if cmd == "backup" and args.action == "verify":
        if args.archive is None:
            return refuse("missing: --archive")
        m = bs.verify_archive(args.archive, master)
        say(f"OK: {args.archive.name} is intact; users {m['users']}, members {len(m['members'])}, "
            f"errors recorded when it was written: {len(m['errors'])}.")
        return 0
    if cmd == "restore":
        if (args.user is None) == (args.gateway_db_out is None):
            return refuse("give exactly one of --user <id> or --gateway-db-out <new file>")
        if args.user is not None:
            if (miss := _need(args, "data_root")):
                return refuse(miss)
            rep = bs.restore_user(args.archive, master, data_root=args.data_root, user_id=args.user)
            say(f"Restored user {rep['user']}: {', '.join(rep['restored'])} from {rep['archive']}. Their previous "
                "files were kept next to them as *.before-restore-*; delete those when satisfied, then run "
                "'acl check'. No other user was touched.")
            return 0
        path = bs.restore_gateway_db(args.archive, master, args.gateway_db_out)
        say(f"gateway.db restored to {path}. With the service stopped, swap it in for the live database.")
        return 0
    if (miss := _need(args, "data_root", "gateway_db")):
        return refuse(miss)
    dest = _dest(args)
    if cmd == "backup":  # run
        from .store import GatewayStore  # noqa: PLC0415

        sched = bs.EncryptedBackupScheduler(data_root=args.data_root, gateway_db=args.gateway_db, dest=dest,
                                            master=master, user_ids=GatewayStore(args.gateway_db).member_ids, clock=clock)
        path = sched.run_once()
        res = sched.last_result()
        say(f"Backup written: {path.name}  users {res['users']}  errors {len(res['errors'])}")
        for e in res["errors"]:
            say("  error: " + e)
        return 0 if res["ok"] else 1
    if cmd == "migrate-all":
        return _migrate_all(args, say, dest, master, clock)
    return refuse("unknown command")


def _migrate_all(args, say, dest: Path, master: bytes, clock) -> int:
    from . import migrate_all as ma  # noqa: PLC0415
    from .store import GatewayStore  # noqa: PLC0415

    install = args.install_dir or Path(__file__).resolve().parents[2]
    store = GatewayStore(args.gateway_db)  # opening it migrates gateway.db's own schema
    say(f"gateway.db is at schema version {store.schema_version()}.")
    sched = bs.EncryptedBackupScheduler(data_root=args.data_root, gateway_db=args.gateway_db, dest=dest,
                                        master=master, user_ids=store.member_ids, clock=clock)
    def snapshot(uid: int) -> Path:
        path = sched.backup_user(uid)
        errors = bs.verify_archive(path, master)["errors"]
        if errors:  # a snapshot that could not capture everything is no rollback point
            raise RuntimeError("the snapshot is incomplete: " + "; ".join(errors))
        return path

    report = ma.migrate_all(data_root=args.data_root, user_ids=list(store.member_ids()), snapshot=snapshot,
                            migrate=lambda ws: ma.run_child(ws, install_dir=Path(install), python=args.python))
    say(ma.format_report(report))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def _funnel(args, say, refuse, run, err) -> int:
    from src import funnel_guard as fg  # noqa: PLC0415

    if args.funnel_port is None:
        return refuse("missing: --funnel-port (or give --config)")
    ports = _worker_ports(args.data_root)
    if args.action == "check":
        report = fg.check_funnel(gateway_funnel_port=args.funnel_port, gateway_local_port=args.local_port,
                                 worker_ports=ports, run=run)
        if report.unreadable:
            return refuse("Could not read 'tailscale serve status --json' (tailscale missing, stopped or not signed "
                          "in). The Funnel configuration is UNVERIFIED.", 1)
        for e in report.exposures:
            say(f"external {e.external_port} -> {e.target}" + ("  [Funnel]" if e.funnel else "  [tailnet only]"))
        for problem in report.problems:
            print("PROBLEM: " + problem, file=err)
        say("Funnel configuration OK." if report.ok else "Funnel configuration REFUSED (see problems above).")
        return 0 if report.ok else 1
    cmd = fg.funnel_command(args.external_port, args.funnel_port) if args.action == "apply" \
        else fg.funnel_off_command(args.external_port)
    say("Command: " + " ".join(cmd))
    if not args.yes:
        say("Not run (dry run). Add --yes, with the owner's approval, to run it.")
        return 0
    before = fg.check_funnel(gateway_funnel_port=args.funnel_port, gateway_local_port=args.local_port,
                             worker_ports=ports, run=run)
    if args.action == "apply" and before.problems:
        for problem in before.problems:
            print("PROBLEM: " + problem, file=err)
        return refuse("Refusing to change Funnel while it is already misconfigured; fix that first.", 1)
    r = run(cmd, capture_output=True, text=True, timeout=60)
    say((getattr(r, "stdout", "") or "").strip())
    if getattr(r, "returncode", 0) != 0:
        return refuse((getattr(r, "stderr", "") or "tailscale failed").strip(), 1)
    after = fg.check_funnel(gateway_funnel_port=args.funnel_port, gateway_local_port=args.local_port,
                            worker_ports=ports, run=run)
    if after.ok:
        say("Verified: Funnel configuration OK.")
    elif after.unreadable:
        say("Verified: could not re-read the Funnel status.")
    else:
        say("Verified: PROBLEMS: " + "; ".join(after.problems))
    return 0 if after.ok or args.action == "off" else 1


def _power(args, say, refuse, run) -> int:
    from . import power  # noqa: PLC0415

    try:
        if args.action == "show":
            policy = power.read_policy(run)
            say(f"AC standby timeout: {policy['standby']} s, hibernate timeout: {policy['hibernate']} s (0 = never)")
            say("This machine WILL sleep on AC power." if power.sleeps(policy) else "This machine will not sleep on AC power.")
            return 0
        if not args.yes:
            say("Not run (dry run): would set the AC standby and hibernate timeouts to never." if args.action == "apply"
                else "Not run (dry run): would restore the saved timeouts. Add --yes, with the owner's approval.")
            return 0
        res = power.apply_policy(args.state_file, confirmed=True, run=run) if args.action == "apply" \
            else power.revert_policy(args.state_file, confirmed=True, run=run)
        say(json.dumps(res))
        return 0
    except power.PowerError as exc:
        return refuse(str(exc), 1)


def _health(args, say) -> int:
    from .health import disk_report  # noqa: PLC0415

    dest = _dest(args) if (args.backup_dir or args.config) else None
    report = {"disk": {"data": disk_report(args.data_root), "backups": disk_report(dest)}}
    archives = bs.list_archives(dest) if dest else []
    full = [a for a in archives if a["kind"] == "full"]
    report["backup"] = {"archives": len(full), "newest_age_seconds":
                        round(time.time() - full[-1]["epoch"]) if full else None}
    say(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
