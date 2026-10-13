#!/usr/bin/env python
"""H1 report helper: dump the sale-year columns for fixed sale scenarios as JSON.

Run once on the old code (``git stash``) and once on the new code, then diff the two
files with ``--diff old.json new.json``. Fixtures only; no real plan data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COLS = ("agi", "irmaa_magi_current", "irmaa_magi_used", "irmaa_tier", "irmaa", "niit", "fed_tax",
        "state_tax", "ltcg_gain", "home_sale_taxable", "home_sale_tax", "total_tax", "taxable_inc")


def scenarios():
    from tests import rental_fixtures as rf
    out = {
        "home_sale_2029": lambda: rf.project(rf.base_config({"home_sale_yr": 2029})),
        "home_sale_2045": lambda: rf.project(rf.base_config({"home_sale_yr": 2045})),
        "converted_passes": lambda: rf.project(rf.rental_config("converted_passes")),
        "converted_fails": lambda: rf.project(rf.rental_config("converted_fails")),
        "rental_sale_recapture": lambda: rf.project(rf.rental_config("sale_with_recapture")),
        "owner_shaped": lambda: rf.project(rf.rental_config(rf.RentalCase(
            [rf.CONVERTED_HOME, rf.SALE_WITH_RECAPTURE], plan={"home_sale_yr": 2029}))),
    }
    return out


def dump(path):
    res = {}
    for name, run in scenarios().items():
        rows = run()
        res[name] = {str(r["year"]): {k: round(float(r.get(k, 0) or 0), 2) for k in COLS} for r in rows}
    Path(path).write_text(json.dumps(res, indent=1, sort_keys=True))


def diff(old, new):
    a, b = json.loads(Path(old).read_text()), json.loads(Path(new).read_text())
    n = 0
    for sc in sorted(a):
        for yr in sorted(a[sc], key=int):
            for k in COLS:
                x, y = a[sc][yr][k], b[sc][yr][k]
                if abs(x - y) > 0.005:
                    n += 1
                    print(f"{sc} | {yr} | {k} | {x:,.2f} -> {y:,.2f} ({y - x:+,.2f})")
    print(f"moved cells: {n}")


if __name__ == "__main__":
    if sys.argv[1] == "--diff":
        diff(sys.argv[2], sys.argv[3])
    else:
        dump(sys.argv[1])
