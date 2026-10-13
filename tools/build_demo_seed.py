#!/usr/bin/env python
"""Build the shipped seed demo plan ``src/reference/demo_seed.rpx`` from ``input/demo`` (WP11.2).

    python tools/build_demo_seed.py            # rebuild the seed
    python tools/build_demo_seed.py --check    # exit 1 if the seed's plan rows differ from input/demo

A frozen build ships this plan file instead of the ``input/demo`` CSV folder; a fresh workspace
(``seed_frozen_workspace``) and Open/Reset demo copy it. ``--check`` compares content (plan rows and
flat datasets), not bytes.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.active_plan import build_plan_file_from_csv_folder  # noqa: E402
from src.sqlite_util import connect  # noqa: E402
from src.stores import PlanStore  # noqa: E402

DEMO_DIR = ROOT / "input" / "demo"
SEED = ROOT / "src" / "reference" / "demo_seed.rpx"


def _content(path: Path) -> object:
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.sectioned_data(), sorted(map(repr, store.all_rows()))


def _sealed(path: Path) -> None:
    """Leave one self-contained file: fold the WAL in and drop the sidecars."""
    with connect(path) as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if "--check" in argv:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "demo_seed.rpx"
            build_plan_file_from_csv_folder(fresh, DEMO_DIR)
            if not SEED.is_file() or _content(fresh) != _content(SEED):
                print("demo_seed.rpx is stale: run python tools/build_demo_seed.py")
                return 1
        print("demo_seed.rpx is current")
        return 0
    rows = build_plan_file_from_csv_folder(SEED, DEMO_DIR)
    _sealed(SEED)
    print(f"wrote {SEED.relative_to(ROOT)} ({rows} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
