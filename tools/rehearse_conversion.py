#!/usr/bin/env python
"""Conversion rehearsal (WP4, WP6): run steps C3, C3b, C4a, C4b and C4c on a COPY of a plan and prove the result.

    python tools/rehearse_conversion.py <plan_copy_dir> [--out <dir>] [--verbose-keys] [--skip-engine]

``<plan_copy_dir>`` is a copy of the workspace (or of its ``input`` folder) holding the plan CSV
set (``client_data.csv`` and its parts, holdings, spending, YTD ... ) and optionally the legacy
custom reference files (``capital_market_assumptions.csv``, ``asset_correlations.csv``).

What it does
------------
1. Read-only on ``<plan_copy_dir>``: the inputs are copied to a temp work folder; the converted
   plan is written to ``<out>/plan.rpx`` (default: a temp folder, removed at exit).
2. Runs C3, C3b, C4a (holdings, liabilities, HSA schedule, targets) then C4b (spending taxonomy,
   aliases, budget, budget lines, tier overrides, rules, category map, group budget, and the
   budget recovery seed / pre-recovery copy as plan revisions) then C4c (YTD transactions, account
   setup and import history) exactly as ``src/legacy_conversion/steps`` does.
3. Equivalence checks, old path vs converted plan:
   - flat datasets: per dataset, file row count vs table row count, and the column NAMES of each
   - sectioned data: ``migrate_sectioned_data(load_csv(...))`` vs ``PlanStore.sectioned_data()``
   - engine-ready config (``parse_client``) both ways
   - full engine output (``project``) both ways (skip with ``--skip-engine``)
4. Prints a PRIVACY-SAFE report: counts, MATCH/DIFF and the NAMES of differing columns / keys.
   Values are never printed. ``--verbose-keys`` adds section/subsection/label names of differing
   keys (names only).
5. Exit code 0 only when every check matches.

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
FLOAT_PLACES = 2
LEGACY_CUSTOM_FILES = {"capital_market_assumptions.csv": "cma", "asset_correlations.csv": "correlations"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")  # BOM tolerant


def _find_input_dir(plan_copy: Path) -> Path:
    if (plan_copy / "input" / "client_data.csv").is_file():
        return plan_copy / "input"
    if (plan_copy / "client_data.csv").is_file():
        return plan_copy
    raise SystemExit(f"no client_data.csv in {plan_copy} or {plan_copy / 'input'}")


def _round(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        return round(v, FLOAT_PLACES)
    if isinstance(v, dict):
        return {str(k): _round(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_round(x) for x in v]
    if isinstance(v, (str, int)):
        return v
    return f"<{type(v).__name__}>"  # engine helper objects compare by type, not memory address


def _diff_names(a, b, path="", out=None):
    """Names (never values) of the keys at which two nested structures differ."""
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}/{k}")
            else:
                _diff_names(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}[len]")
        for i, (x, y) in enumerate(zip(a, b)):
            _diff_names(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(path)
    return out


def _column_summary(paths):
    """Collapse diff paths to names: row-level column names (``/[3]/column`` -> ``column``)."""
    cols = Counter()
    for p in paths:
        parts = [s for s in p.split("/") if s and not s.startswith("[")]
        cols[parts[-1] if parts else "(root)"] += 1
    return cols


def _dataset_comparison(work_input: Path, store, c4b=None):
    """Per flat dataset: rows in the legacy file vs rows in the converted table, and whether the
    file's column names are all kept. Counts and column names only, never values.

    C4b converts a legacy-layout taxonomy (``section/subsection/label/value``) to the current
    columns, so its column check is against the mapped names; an aliases file C4b ignored (no
    ``match_value``/``category_id`` columns) is expected to leave the table empty."""
    import csv  # noqa: PLC0415

    from src.csv_exchange import FLAT_DATASET_FILES  # noqa: PLC0415

    out = []
    for name, file in FLAT_DATASET_FILES.items():
        path = work_input / file
        if not path.is_file():
            out.append((f"[SKIP ] dataset {name}: no {file}", True))
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            columns = [c for c in (reader.fieldnames or []) if c]
            file_rows = sum(1 for row in reader if any((v or "").strip() for v in row.values() if v is not None))
        repo = store.dataset(name)
        kept = set(repo.columns) | set(repo.extra_columns())
        note = ""
        if name == "spending_taxonomy" and c4b is not None and c4b.legacy_taxonomy_layout:
            kept |= {"section", "subsection", "value"}  # mapped to tracking_type, group, label
            note = ", legacy layout converted"
        if name == "spending_budget" and c4b is not None and c4b.legacy_budget_layout:
            kept |= {"category_id"}  # one row per category_id becomes a kind=category row
            file_rows, note = repo.count(), ", legacy layout converted (rows grouped per category)"
        if name == "spending_aliases" and c4b is not None and c4b.aliases_ignored:
            file_rows, note = 0, ", legacy layout not imported (readers seed from rules/category map)"
        missing = [c for c in columns if c not in kept]
        ok = repo.count() == file_rows and not missing
        detail = (f"file rows {file_rows}, table rows {repo.count()}" + note
                  + (f", columns not kept: {missing}" if missing else ""))
        out.append((f"[{'MATCH' if ok else 'DIFF '}] dataset {name}: {detail}", ok))
    # The recovery copies are plan revisions (rows of the budget retained by a revision).
    from src.legacy_conversion.steps.c4b_spending import RECOVERY_FILES  # noqa: PLC0415

    for key, file in RECOVERY_FILES.items():
        path = work_input / file
        if not path.is_file():
            out.append((f"[SKIP ] recovery copy {key}: no {file}", True))
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            file_rows = sum(1 for row in csv.DictReader(f) if any((v or "").strip() for v in row.values() if v is not None))
        if key == "recovery_seed":
            kept_rows = len(store.spending.recovery_seed())
        else:
            head = store.latest_revision("pre-recovery")
            kept_rows = len(store.revision_dataset_rows(head["id"], "spending_budget")) if head else 0
        ok = kept_rows == file_rows
        out.append((f"[{'MATCH' if ok else 'DIFF '}] recovery copy {key} (plan revision): file rows {file_rows}, revision rows {kept_rows}", ok))
    return out


def _verdict(name, paths, verbose_keys=False, limit=40):
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan_copy_dir")
    ap.add_argument("--out", default=None, help="folder for the converted plan.rpx (default: temp)")
    ap.add_argument("--verbose-keys", action="store_true", help="also print differing key names (never values)")
    ap.add_argument("--skip-engine", action="store_true", help="skip the full engine comparison")
    ap.add_argument("--show-errors", action="store_true",
                    help="print exception messages (they can contain plan values; default prints the type only)")
    args = ap.parse_args(argv)

    plan_copy = Path(args.plan_copy_dir).resolve()
    if not plan_copy.is_dir():
        raise SystemExit(f"not a folder: {plan_copy}")
    src_input = _find_input_dir(plan_copy)

    with tempfile.TemporaryDirectory(prefix="rehearsal_") as tmp:
        work = Path(tmp) / "ws"
        work_input = work / "input"
        work_input.mkdir(parents=True)
        for f in sorted(src_input.iterdir()):  # inputs are only read
            if f.is_file():
                shutil.copy2(f, work_input / f.name)
        if (plan_copy / "system_config.csv").is_file():
            shutil.copy2(plan_copy / "system_config.csv", work / "system_config.csv")
        out_dir = Path(args.out).resolve() if args.out else Path(tmp) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_file = out_dir / "plan.rpx"
        for stale in (plan_file, plan_file.with_name("plan.rpx-wal"), plan_file.with_name("plan.rpx-shm")):
            stale.unlink(missing_ok=True)

        os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(work)
        os.environ["RETIREMENT_SYSTEM_PLAN_DB"] = str(plan_file)
        os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
        os.environ["RETIREMENT_SYSTEM_NO_AUTO_OPEN"] = "1"
        sys.path.insert(0, str(ROOT))

        from src.data_io import load_csv, parse_client  # noqa: PLC0415
        from src.legacy_conversion.steps import c3_plan_rows, c3b_plan_overrides, c4a_datasets, c4b_spending, c4c_ytd  # noqa: PLC0415
        from src.plan_data_migration import migrate_sectioned_data  # noqa: PLC0415
        from src.stores import PlanStore  # noqa: PLC0415

        print("== Conversion rehearsal (privacy-safe: counts and names only) ==")
        all_ok = True

        # ---- C3 and C3b
        with PlanStore.open(plan_file) as store:
            c3 = c3_plan_rows.run(work_input, store)
            custom = {}
            for fname, kind in LEGACY_CUSTOM_FILES.items():
                path = work_input / fname
                if path.is_file():
                    custom[kind] = _read_text(path)
            c3b = c3b_plan_overrides.run(store, custom)
            c4a = c4a_datasets.run(work_input, store)
            c4b = c4b_spending.run(work_input, store)
            c4c = c4c_ytd.run(work_input, store)
            dataset_report = _dataset_comparison(work_input, store, c4b)
            converted = store.sectioned_data()
            marker_c3 = store.get_meta(c3_plan_rows.MARKER_KEY) is not None
            marker_c3b = store.get_meta(c3b_plan_overrides.MARKER_KEY) is not None
            marker_c4a = store.get_meta(c4a_datasets.MARKER_KEY) is not None
            marker_c4b = store.get_meta(c4b_spending.MARKER_KEY) is not None
            marker_c4c = store.get_meta(c4c_ytd.MARKER_KEY) is not None
            rows_by_section = Counter(r["section"] for r in store.all_rows())
            dup_keys = Counter()
            for r in store.all_rows():
                dup_keys[(r["section"], r["subsection"], r["label"])] += 1

        src = c3.source
        print("-- C3 (CSV set -> plan rows)")
        print(f"   files read: {getattr(src, 'files_read', '?')}   rows written: {c3.rows_written}")
        print(f"   legacy rows renamed/dropped: {c3.legacy_renamed}   retired labels dropped: {c3.retired_dropped}")
        for attr in ("comments_attached", "comments_dropped", "skipped"):
            if hasattr(src, attr):
                v = getattr(src, attr)
                print(f"   {attr}: {len(v) if isinstance(v, (list, tuple, set, dict)) else v}")
        print(f"   duplicate keys left in plan: {sum(1 for n in dup_keys.values() if n > 1)}")
        print(f"   marker c3: {'present' if marker_c3 else 'MISSING'}")
        print(f"-- C3b (custom reference files -> overrides): rows {c3b.rows_written or 'none'}  marker: "
              f"{'present' if marker_c3b else 'MISSING'}")
        print(f"-- C4a (flat datasets -> plan tables): rows {c4a.rows_written or 'none'}  marker: "
              f"{'present' if marker_c4a else 'MISSING'}")
        print(f"-- C4b (spending set -> plan tables, recovery copies -> plan revisions): rows {c4b.rows_written or 'none'}  marker: "
              f"{'present' if marker_c4b else 'MISSING'}")
        print(f"-- C4c (YTD files -> plan tables): rows {c4c.rows_written or 'none'}  marker: "
              f"{'present' if marker_c4c else 'MISSING'}")
        all_ok &= marker_c3 and marker_c3b and marker_c4a and marker_c4b and marker_c4c
        for line, ok in dataset_report:
            print(line)
            all_ok &= ok
        print("-- rows per section")
        for sec, n in sorted(rows_by_section.items()):
            print(f"   {n:5d}  {sec}")

        # ---- sectioned data equivalence
        old, _ = migrate_sectioned_data(load_csv(work_input / "client_data.csv"))
        paths = _diff_names(_round(old), _round(converted))
        all_ok &= _verdict("sectioned data: old path (load_csv + migrate) vs converted plan", paths, args.verbose_keys)

        def guarded(label, fn):
            """Run a stage; on an exception print the TYPE only (messages can quote plan values)."""
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - report, never traceback (values)
                msg = f": {exc}" if args.show_errors else " (message withheld; rerun with --show-errors)"
                print(f"[ERROR] {label}: {type(exc).__name__}{msg}")
                return None

        # ---- engine-ready config both ways
        # The first parse can leave per-process state (price snapshots, lot ids) behind; a warm-up
        # parse of the old data keeps the two compared runs in the same state.
        def parse_both():
            parse_client(old, "", skip_live_pricing=True)
            return (parse_client(old, "", skip_live_pricing=True),
                    parse_client(converted, "", skip_live_pricing=True))

        pair = guarded("engine config (parse_client)", parse_both)
        if pair is None:
            all_ok = False
        else:
            paths = _diff_names(_round(pair[0]), _round(pair[1]))
            all_ok &= _verdict("engine config (parse_client): old vs converted", paths, args.verbose_keys)

        # ---- full engine output both ways
        if args.skip_engine:
            print("[SKIP ] full engine output (--skip-engine)")
        else:
            from src.planning_engines import project  # noqa: PLC0415
            from src.report_compute import prepare_config_from_sectioned_data  # noqa: PLC0415
            def project_both():
                return tuple(project(prepare_config_from_sectioned_data(d, "", optimize_roth=True, skip_live_pricing=True))
                             for d in (old, converted))

            pair = guarded("full engine output (project)", project_both)
            if pair is None:
                all_ok = False
            else:
                paths = _diff_names(_round(pair[0]), _round(pair[1]))
                print(f"        engine rows compared: {len(pair[0])} vs {len(pair[1])}")
                all_ok &= _verdict("full engine output (project): old vs converted", paths, args.verbose_keys)

        print("== RESULT: " + ("ALL MATCH" if all_ok else "DIFFERENCES FOUND (see above)"))
        if args.out:
            print(f"converted plan written to {plan_file}")
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
