#!/usr/bin/env python
"""Record an OLD reference-data loader's output as a golden fixture (WP3).

Usage
-----
    python tools/capture_reference_golden.py --list
    python tools/capture_reference_golden.py NAME [NAME ...] [--force]

Writes ``tests/fixtures/reference_golden/<NAME>.json`` in the canonical encoding
of ``tests/reference_golden.py``. Run it BEFORE the slice deletes the old loader;
the new getter registered under NAME in ``src.stores.ref_getters.GOLDEN_GETTERS``
must then reproduce the file exactly (``tests/test_reference_golden_regression.py``).

Each entry in ``CAPTURES`` calls the old loader exactly as product code does, with
any date-dependent arguments pinned. When a slice deletes its old loader it also
deletes its entry here (the golden file stays as the frozen truth).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.reference_golden import write_golden  # noqa: E402


def _csv_rows(name: str) -> Any:
    """Helper for captures of plain-CSV loaders: rows as str dicts (``csv.DictReader`` shape)."""
    import csv
    with (ROOT / "reference_data" / name).open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


# Old-loader captures live here only while the old loader still exists: add the entry,
# run this tool, move the source, switch consumers, delete the entry (see the runbook).
# The slices landed so far have all been captured and their old loaders deleted; their
# fixtures under tests/fixtures/reference_golden/ are the permanent record.
CAPTURES: dict[str, Callable[[], Any]] = {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record old reference loaders' output as golden fixtures.")
    ap.add_argument("names", nargs="*", help="capture names (see --list)")
    ap.add_argument("--list", action="store_true", help="list capture names")
    ap.add_argument("--force", action="store_true", help="overwrite an existing golden fixture")
    args = ap.parse_args(argv)
    if args.list or not args.names:
        print("\n".join(sorted(CAPTURES)))
        return 0
    unknown = [n for n in args.names if n not in CAPTURES]
    if unknown:
        print(f"unknown capture(s): {unknown}; known: {sorted(CAPTURES)}", file=sys.stderr)
        return 2
    for name in args.names:
        try:
            path = write_golden(name, CAPTURES[name](), force=args.force)
        except FileExistsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
