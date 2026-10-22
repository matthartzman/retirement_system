#!/usr/bin/env python3
"""Verify the Contextual Help Panel prose inventory (Phase 4 closeout).

Checks documentation/future/ui_prose_inventory.csv:
  1. every row's destination starts with moved: / deleted: / kept:  (no class A row left unmoved);
  2. class A rows are not `kept:` unless they are hover-only tooltips;
  3. every class D row's merged_into target exists (a file, `file:line` within the file, or a
     registry / ADMIN_HELP / SYSTEM_CONFIG_FIELD_HELP key that is present in its file).
Usage: python tools/verify_ui_prose_inventory.py [--counts]
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "documentation" / "future" / "ui_prose_inventory.csv"
PREFIXES = ("moved", "deleted", "kept")


def load(path: Path = CSV_PATH):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def target_exists(target: str, root: Path = ROOT) -> bool:
    target = target.strip()
    if not target:
        return False
    m = re.match(r"^(?P<file>[\w./-]+\.(?:js|html|py|md))(?::(?P<ref>.+))?$", target)
    if m:
        path = root / m["file"]
        if not path.is_file():
            return False
        ref = m["ref"]
        text = path.read_text(encoding="utf-8")
        if not ref:
            return True
        if ref.isdigit():
            return int(ref) <= len(text.splitlines())
        return ref.split(".")[-1] in text
    m = re.match(r"^HELP_(?:SECTIONS|PAGES|FIELDS)\[([\w.]+)\]$", target)
    if m:
        registry = (root / "frontend" / "js" / "help_registry.js").read_text(encoding="utf-8")
        return f'"{m[1]}"' in registry or re.search(rf"^  {re.escape(m[1])}:", registry, re.M) is not None
    return False


def problems(rows, root: Path = ROOT):
    out = []
    for r in rows:
        where = f'{r["file"]}:{r["line"]} "{r["text"][:50]}"'
        dest = r["destination"].strip()
        if not dest.startswith(PREFIXES):
            out.append(f"{where}: destination '{dest[:40]}' is not moved:/deleted:/kept:")
        elif r["class"] == "A" and dest.startswith("kept") and "tooltip" not in dest:
            out.append(f"{where}: class A row is still in the centre ('{dest[:50]}')")
        if r["class"] == "D" and not target_exists(r["merged_into"], root):
            out.append(f"{where}: merged_into '{r['merged_into'][:60]}' does not exist")
    return out


def counts(rows):
    table = collections.Counter((r["level"], r["class"]) for r in rows)
    disp = collections.Counter(r["destination"].split(":")[0] for r in rows)
    return table, disp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true")
    args = ap.parse_args(argv)
    rows = load()
    if args.counts:
        table, disp = counts(rows)
        for level in ("page", "section", "field", "message"):
            print(level, {c: table[(level, c)] for c in "ABCD"}, sum(table[(level, c)] for c in "ABCD"))
        print(dict(disp), len(rows))
    bad = problems(rows)
    for line in bad:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
