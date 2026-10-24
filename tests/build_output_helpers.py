"""Locate a build artifact: builds write under <output dir>/plans/<plan id>/ (the per-plan layout)."""
from __future__ import annotations

from pathlib import Path


def built_file(out_dir: Path, name: str) -> Path:
    return next(iter(sorted(Path(out_dir).rglob(name))), Path(out_dir) / name)
