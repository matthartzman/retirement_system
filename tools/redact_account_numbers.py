#!/usr/bin/env python3
"""One-time, idempotent redaction of account numbers already stored in the plan file.

Design: documentation/future/superpowers/plans/2026-10-31-account-number-protection-design-and-plan.md (4.3).

Re-applies ``src/account_numbers`` masking to ``broker_imports.file_name``, ``broker_activity.action`` /
``description`` and the cue-word cases in the ``ytd_transactions`` text columns. ``broker_activity.row_key`` is left
as stored. Prints COUNTS ONLY, never values. Dry run by default; ``--apply`` first makes a fresh plan backup (and
refuses to change anything if that fails). Safe to re-run.

Usage: python tools/redact_account_numbers.py [--base-dir WORKSPACE] [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import active_plan  # noqa: E402
from src.account_numbers import mask_file_name, mask_text  # noqa: E402

YTD_COLUMNS = ("Merchant", "Original Statement", "Notes")


def _scan(store) -> dict:
    """Pending changes: {'imports': [(id, new)], 'activity': [(id, action, description)], 'ytd': [rows], ...}."""
    with store._read() as con:
        imports = [(r["import_id"], mask_file_name(r["file_name"])) for r in
                   con.execute("SELECT import_id, file_name FROM broker_imports")
                   if mask_file_name(r["file_name"]) != r["file_name"]]
        activity = []
        for r in con.execute("SELECT activity_id, action, symbol, description FROM broker_activity"):
            keep = (r["symbol"] or "",)
            a, d = mask_text(r["action"], exempt=keep), mask_text(r["description"], exempt=keep)
            if a != r["action"] or d != r["description"]:
                activity.append((r["activity_id"], a, d))
    ds = store.dataset("ytd_transactions")
    rows = ds.rows()
    ytd_changed = 0
    new_rows = []
    for row in rows:
        new = dict(row)
        for col in YTD_COLUMNS:
            if new.get(col):
                new[col] = mask_text(new[col])
        ytd_changed += new != row
        new_rows.append(new)
    return {"imports": imports, "activity": activity, "ytd_rows": new_rows, "ytd_changed": ytd_changed}


def redact(base_dir: str | Path, *, apply: bool = False) -> dict:
    """Return counts (and, with ``apply``, the backup path). Never returns values."""
    base = Path(base_dir)
    with active_plan.workspace_store(base) as store:
        found = _scan(store)
    counts = {"broker_imports.file_name": len(found["imports"]),
              "broker_activity.rows": len(found["activity"]),
              "ytd_transactions.rows": found["ytd_changed"]}
    result = {"applied": False, "counts": counts, "backup": None}
    if not apply or not any(counts.values()):
        return result
    from src import local_backup_scheduler as lbs  # noqa: PLC0415
    backup = lbs.run_backup(base, active_plan.plan_path_for_workspace(base), trigger="pre-redaction", force=True)
    if not backup.get("created"):
        raise SystemExit("Refusing to redact: could not make a plan backup first.")
    result["backup"] = str(backup.get("path") or backup.get("backup_path") or backup.get("file") or "(created)")
    with active_plan.workspace_store(base, write=True) as store:
        found = _scan(store)
        with store._write() as con:
            for iid, name in found["imports"]:
                con.execute("UPDATE broker_imports SET file_name = ? WHERE import_id = ?", (name, iid))
            for aid, action, desc in found["activity"]:
                con.execute("UPDATE broker_activity SET action = ?, description = ? WHERE activity_id = ?",
                            (action, desc, aid))
        if found["ytd_changed"]:
            store.dataset("ytd_transactions").replace_all(found["ytd_rows"])
    result["applied"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-dir", default=None, help="workspace root (default: the live workspace)")
    ap.add_argument("--apply", action="store_true", help="make a backup, then redact (default: dry run)")
    args = ap.parse_args(argv)
    base = args.base_dir
    if base is None:
        from src import platform_runtime  # noqa: PLC0415
        base = platform_runtime.workspace_root()
    res = redact(base, apply=args.apply)
    print(("APPLIED" if res["applied"] else "DRY RUN") + " - rows needing redaction (counts only):")
    for k, v in res["counts"].items():
        print(f"  {k}: {v}")
    if res["backup"]:
        print(f"Backup made first: {res['backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
