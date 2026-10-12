#!/usr/bin/env python
"""Conversion rehearsal (WP4, WP6, WP10.3): run the whole conversion on a COPY of a workspace and prove the result.

    python tools/rehearse_conversion.py <plan_copy_dir> [--out <dir>] [--verbose-keys] [--skip-engine] [--show-errors]

``<plan_copy_dir>`` is a copy of the workspace (or of its ``input`` folder) holding the plan CSV
set (``client_data.csv`` and its parts, holdings, spending, YTD ... ) and optionally the legacy
custom reference files (``capital_market_assumptions.csv``, ``asset_correlations.csv``),
``system_config.csv``, the legacy database (``local_state/retirement_system_v10.db``), an old
demo's ``*.before_demo`` backups, a ``plan.rpx`` and the last build's ``output/plan_summary.json``.

What it does
------------
1. Read-only on ``<plan_copy_dir>``: the files listed above are copied into a temporary workspace
   (never ``secrets.local.json``); the converted plan is written to ``<out>/plan.rpx`` (default: a
   temp folder, removed at exit).
2. Runs ``legacy_conversion.convert_workspace`` there: the same code the app runs at first launch
   (backup, every step, verification, swap, registration), on the temporary copy.
3. Prints the verification (``src/legacy_conversion/verify.py``, the converter's own checks):
   - sectioned data: the old loader path (``load_csv`` + ``migrate_sectioned_data``) vs the plan
   - engine config (``parse_client``) and full engine output (``project``), old path vs converted
   - flat datasets: legacy file vs table, row counts and every cell, by column name
   - tier mapping: the projection before vs after the tier/switch mapping (must be identical)
   - the last old build's KPIs and input/ vs database copies (warnings only)
4. The report is PRIVACY-SAFE: counts, MATCH/DIFF and the NAMES of differing columns / keys.
   Values are never printed. ``--verbose-keys`` adds the full key names (names only).
5. Exit code 0 only when every blocking check matches (the conversion would complete).

Nothing is sent anywhere; nothing in ``<plan_copy_dir>`` is modified.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.legacy_conversion.verify import diff_names as _diff_names, name_summary as _column_summary, round_values as _round  # noqa: E402,F401

LEGACY_CUSTOM_FILES = {"capital_market_assumptions.csv": "cma", "asset_correlations.csv": "correlations"}
CHECK_LABELS = {
    "plan_rows": "sectioned data: old path (load_csv + migrate) vs converted plan",
    "engine_config": "engine config (parse_client): old vs converted",
    "engine_output": "full engine output (project): old vs converted",
    "datasets": "flat datasets: legacy files vs plan tables (rows and cells)",
    "tier_mapping": "tier mapping: projection before vs after (safeguard)",
    "old_build_kpis": "last old build KPIs vs converted plan (warning only)",
    "source_agreement": "input/ files vs legacy database copies (warning only)",
}
TAGS = {"match": "MATCH", "diff": "DIFF ", "error": "ERROR", "skipped": "SKIP ", "not_applicable": "N/A  "}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")  # BOM tolerant


def _find_input_dir(plan_copy: Path) -> Path:
    if (plan_copy / "input" / "client_data.csv").is_file():
        return plan_copy / "input"
    if (plan_copy / "client_data.csv").is_file():
        return plan_copy
    raise SystemExit(f"no client_data.csv in {plan_copy} or {plan_copy / 'input'}")


def _copy_workspace(plan_copy: Path, src_input: Path, work: Path) -> list[str]:
    """Copy what a conversion reads into ``work`` (never the secrets file); returns the names."""
    copied: list[str] = []
    (work / "input").mkdir(parents=True)
    (work / "local_state").mkdir()
    for f in sorted(src_input.iterdir()):  # inputs are only read
        if f.is_file():
            shutil.copy2(f, work / "input" / f.name)
    if src_input == plan_copy:
        return copied
    for rel in ("system_config.csv", "plan.rpx", "plan.rpx-wal", "plan.rpx.before_demo", "plan.rpx.before_demo-wal",
                "local_state/retirement_system_v10.db", "local_state/retirement_system_v10.db-wal",
                "local_state/retirement_system_v10.db.before_demo",
                "local_state/retirement_system_v10.db.before_demo-wal", "output/plan_summary.json"):
        src = plan_copy / rel
        if src.is_file():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, work / rel)
            copied.append(rel)
    for f in sorted((plan_copy / "local_state").glob("*.before_demo")):
        if f.is_file() and not (work / "local_state" / f.name).exists():
            shutil.copy2(f, work / "local_state" / f.name)
            copied.append(f"local_state/{f.name}")
    return copied


def _verdict(name, paths, verbose_keys=False, limit=40):
    """Print one check line from diff paths (names only); True when nothing differs."""
    ok = not paths
    print(f"[{'MATCH' if ok else 'DIFF '}] {name}")
    if ok:
        return True
    print(f"        differing cells/keys: {len(paths)}")
    cols = _column_summary(paths)
    print("        names: " + ", ".join(f"{k} x{n}" for k, n in cols.most_common(limit)))
    if verbose_keys:
        for p in paths[:limit]:
            print("        key: " + p)
    return False


def _print_check(check, verbose_keys: bool, show_errors: bool) -> None:
    label = CHECK_LABELS.get(check.name, check.name)
    tag = TAGS.get(check.status, check.status.upper())
    if check.status == "error":
        msg = f": {check.message}" if show_errors and check.message else " (message withheld; rerun with --show-errors)"
        print(f"[ERROR] {label}: {check.error_type}{msg}")
        return
    print(f"[{tag}] {label}" + (f"  ({check.note})" if check.note and check.status != "diff" else ""))
    if check.status == "diff":
        print(f"        differing cells/keys: {check.differing}")
        print("        names: " + ", ".join(f"{k} x{n}" for k, n in check.summary.items()))
        if verbose_keys:
            for p in check.names:
                print("        key: " + p)


def _print_steps(res) -> None:
    for s in res.steps:
        d = s.get("detail") or {}
        line = f"   {s['step']:<10}{s['status']}"
        if s.get("error_type"):
            line += f"  ({s['error_type']}; message withheld)"
        if s["step"] == "SRC" and d.get("staged"):
            line += "  staged " + ", ".join(f"{o} x{n}" for o, n in Counter(d["staged"].values()).most_common())
        elif s["step"] == "C3" and s["status"] == "converted":
            src = d.get("source") or {}
            line += (f"  files read {len(src.get('files_read', []))}, rows written {d.get('rows_written')}, "
                     f"legacy renamed/dropped {d.get('legacy_renamed')}, retired dropped {d.get('retired_dropped')}, "
                     f"comments attached {src.get('comments_attached', 0)}, skipped {len(src.get('skipped', []))}")
        elif isinstance(d.get("rows_written"), dict):
            line += "  rows " + (", ".join(f"{k}:{n}" for k, n in sorted(d["rows_written"].items())) or "none")
        elif s["step"] == "T8" and d.get("mapping"):
            m = d["mapping"]
            line += (f"  tier {m['tier']}{' (customized)' if m['customized'] else ''}; on: "
                     f"{', '.join(m['turn_on']) or 'none'}; off: {', '.join(m['turn_off']) or 'none'}")
        elif s["step"] in ("C6a", "C6a.flags"):
            line += f"  flags {len(d.get('flags_written', []))}, knobs {len(d.get('knobs_written', []))}"
        print(line)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan_copy_dir")
    ap.add_argument("--out", default=None, help="folder for the converted plan.rpx (default: temp)")
    ap.add_argument("--verbose-keys", action="store_true", help="also print differing key names (never values)")
    ap.add_argument("--skip-engine", action="store_true", help="skip the engine comparisons (parse_client, project)")
    ap.add_argument("--show-errors", action="store_true",
                    help="print exception messages (they can contain plan values; default prints the type only)")
    args = ap.parse_args(argv)

    plan_copy = Path(args.plan_copy_dir).resolve()
    if not plan_copy.is_dir():
        raise SystemExit(f"not a folder: {plan_copy}")
    src_input = _find_input_dir(plan_copy)

    saved_env = {k: os.environ.get(k) for k in ("RETIREMENT_SYSTEM_WORKSPACE_ROOT", "RETIREMENT_SYSTEM_APP_DB",
                                                 "RETIREMENT_SYSTEM_PLAN_DB", "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS",
                                                 "RETIREMENT_SYSTEM_NO_AUTO_OPEN")}
    with tempfile.TemporaryDirectory(prefix="rehearsal_") as tmp:
        work = Path(tmp) / "ws"
        copied = _copy_workspace(plan_copy, src_input, work)
        out_dir = Path(args.out).resolve() if args.out else Path(tmp) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_file = out_dir / "plan.rpx"
        for stale in (plan_file, plan_file.with_name("plan.rpx-wal"), plan_file.with_name("plan.rpx-shm")):
            stale.unlink(missing_ok=True)
        os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(work)
        os.environ["RETIREMENT_SYSTEM_APP_DB"] = str(work / "local_state" / "app.db")
        os.environ.pop("RETIREMENT_SYSTEM_PLAN_DB", None)
        os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
        os.environ["RETIREMENT_SYSTEM_NO_AUTO_OPEN"] = "1"
        try:
            from src import plan_registry  # noqa: PLC0415
            from src.legacy_conversion import convert_workspace  # noqa: PLC0415

            plan_registry.invalidate()
            print("== Conversion rehearsal (privacy-safe: counts and names only) ==")
            if copied:
                print(f"   copied besides input/: {len(copied)} file(s): " + ", ".join(copied))
            res = convert_workspace(work, extra={"_skip_engine": args.skip_engine, "_keep_staging": str(plan_file)})
            print(f"-- conversion: {res.status}" + (f" ({res.blocked_reason})" if res.blocked_reason else "")
                  + f", mode {res.mode}")
            _print_steps(res)
            c3 = res.step("C3") or {}
            print(f"   marker c3: {'present' if c3.get('status') in ('converted', 'skipped') else 'MISSING'}")
            if res.backup:
                print(f"-- backup of the originals: {res.backup.get('files')} file(s), "
                      f"{'verified' if res.backup.get('verified') else 'NOT verified'}")
            for check in res.checks:
                _print_check(check, args.verbose_keys, args.show_errors)
            all_ok = res.verified and res.status == "done"
            if res.warnings:
                print("   warnings: " + ", ".join(res.warnings))
            print("== RESULT: " + ("ALL MATCH" if all_ok else "DIFFERENCES FOUND (see above)"))
            if args.out:
                print(f"converted plan written to {plan_file}")
            return 0 if all_ok else 1
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    raise SystemExit(main())
