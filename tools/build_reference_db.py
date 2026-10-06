#!/usr/bin/env python
"""Build the shipped, read-only ``reference.db`` from ``reference_src/`` (WP3.1).

Usage
-----
    python tools/build_reference_db.py              # rebuild src/reference/reference.db
    python tools/build_reference_db.py --out PATH   # build somewhere else
    python tools/build_reference_db.py --check      # exit 1 if the committed db is stale

Each slice in ``tools/reference_slices`` turns its ``reference_src/`` files into
tables; this tool merges them and writes the database with
``src.stores.ref_data.build``. The output is deterministic: tables in name
order, rows sorted, no timestamps, and ``data_version`` is ``REFERENCE_RELEASE``
plus the first 12 hex digits of the content hash, so two builds from the same
sources are byte-identical with the same SQLite library.

``--check`` rebuilds into a temp dir and compares ``ref_meta`` (schema,
data_version, content hash) and every table's DDL with the committed file. It
compares content, not raw bytes, because the SQLite file header records the
library version that wrote it, which differs across CI platforms.

Recipe for adding a slice: documentation/reference/REFERENCE_DB_SLICES.md.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.stores import ref_data  # noqa: E402
from src.stores.ref_access import shipped_reference_path  # noqa: E402
from tools.reference_slices import SLICES  # noqa: E402

# Bump when reference data is re-released (for example the annual tax update).
REFERENCE_RELEASE = "2026.10"
SOURCE_DIR = ROOT / "reference_src"
DEFAULT_OUT = shipped_reference_path()

Tables = dict[str, tuple[list[str], list[tuple]]]


_IGNORED = {".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep"}


class ReferenceBuildError(RuntimeError):
    """The sources or slice registry are inconsistent; nothing was written."""


def data_version_for(content_hash: str) -> str:
    return f"{REFERENCE_RELEASE}+{content_hash[:12]}"


def collect_tables(src_dir: Path = SOURCE_DIR, slices: tuple[str, ...] = SLICES) -> Tables:
    """Run every slice builder; refuse duplicate tables and unowned or missing sources."""
    tables: Tables = {}
    owner: dict[str, str] = {}
    for name in slices:
        mod = importlib.import_module(f"tools.reference_slices.{name}")
        for rel in mod.SOURCES:
            if rel in owner:
                raise ReferenceBuildError(f"source {rel} claimed by both {owner[rel]} and {name}")
            if not (src_dir / rel).is_file():
                raise ReferenceBuildError(f"slice {name}: source reference_src/{rel} not found")
            owner[rel] = name
        for table, (cols, rows) in mod.build(src_dir).items():
            if table in tables:
                raise ReferenceBuildError(f"table {table} produced by two slices (second: {name})")
            tables[table] = (list(cols), list(rows))
    present = {p.relative_to(src_dir).as_posix() for p in src_dir.rglob("*") if p.is_file() and p.name not in _IGNORED}
    unowned = sorted(present - set(owner))
    if unowned:
        raise ReferenceBuildError(f"reference_src files not owned by any slice: {unowned}")
    return tables


def build_reference_db(out: Path = DEFAULT_OUT, src_dir: Path = SOURCE_DIR) -> str:
    """Build to a temp file next to ``out`` and move it into place; return the content hash."""
    tables = collect_tables(src_dir)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=".refbuild-") as td:
        tmp = Path(td) / out.name
        digest = ref_data.build(tmp, tables, data_version=data_version_for)
        os.replace(tmp, out)
    return digest


def fingerprint(path: Path) -> dict[str, Any]:
    """What ``--check`` compares: verified ref_meta plus the DDL of every object."""
    with ref_data.RefData.open(path, verify=True) as ref:
        ddl = [tuple(r) for r in ref.query("SELECT type, name, sql FROM sqlite_master ORDER BY type, name")]
        return {"meta": ref.meta(), "ddl": ddl}


def check(committed: Path = DEFAULT_OUT, src_dir: Path = SOURCE_DIR) -> list[str]:
    """Differences between ``committed`` and a fresh build (empty list = fresh)."""
    if not Path(committed).is_file():
        return [f"{committed} does not exist"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "reference.db"
        build_reference_db(tmp, src_dir)
        fresh = fingerprint(tmp)
    try:
        old = fingerprint(Path(committed))
    except ref_data.RefDataError as exc:
        return [f"{committed}: {exc}"]
    problems = [f"ref_meta {k}: committed {old['meta'].get(k)!r} != fresh {fresh['meta'].get(k)!r}"
                for k in sorted(set(old["meta"]) | set(fresh["meta"])) if old["meta"].get(k) != fresh["meta"].get(k)]
    if old["ddl"] != fresh["ddl"]:
        problems.append("table definitions differ")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output path (default: %(default)s)")
    ap.add_argument("--check", action="store_true", help="exit 1 if --out differs from a fresh build")
    ap.add_argument("--src", type=Path, default=SOURCE_DIR, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        if args.check:
            problems = check(args.out, args.src)
            if problems:
                print("reference.db is stale; run `python tools/build_reference_db.py`:\n  " + "\n  ".join(problems))
                return 1
            print(f"{args.out} is fresh")
            return 0
        digest = build_reference_db(args.out, args.src)
    except ReferenceBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.out} (data_version {data_version_for(digest)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
