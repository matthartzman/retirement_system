"""Source discovery and precedence for the one-time conversion (WP10.2, design F section 8.2).

An old install kept its plan in several places, each possibly stale; this module decides which
copy of every legacy file the conversion steps read and lays the chosen copies down in one
staging folder (a temp folder), so steps C3 .. C4c keep reading "a folder".

Layers, highest precedence first (a file is taken from the first layer that has it):

* **normal** install
  1. ``<workspace>/input/<name>`` (the real edit surface of the old versions);
  2. the legacy database's ``client_files`` row of that name
     (``local_state/retirement_system_v10.db``, or ``extra["legacy_db"]``: an old-format
     ``.rpx`` / ``.db`` the caller picked);
  3. the plan CSV set only, and only when no plan CSV file was found above: the latest
     ``plan_snapshots.sectioned_json`` of that database, written as one ``client_data.csv``.
* **mid-demo** install (an old demo was open: a ``*.before_demo`` backup exists), the
  ``input/`` folder and the live legacy database hold the DEMO household, so:
  1. ``local_state/<name>.before_demo`` (the real text backups the old demo took);
  2. ``client_files`` of ``local_state/retirement_system_v10.db.before_demo``;
  3. the latest snapshot of that backup (plan CSV set only, as above);
  4. ``input/<name>`` only for a file the bundled demo seed does not ship (the demo never
     overwrote it).
  The plan rows themselves come from ``plan.rpx.before_demo`` when it exists (WP4.5 - WP8.3
  demo): the runner starts the target from a copy of that file (``plan_seed``).

Nothing here writes to a source: databases are read from a private copy (copying the main
file and its ``-wal``), so not even a ``-shm`` file appears beside an original.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..csv_exchange import FLAT_DATASET_FILES, PLAN_CSV_FILES, RECOVERY_SEED_FILE, rows_to_text
from ..platform_runtime import package_root
from .steps.c3b_plan_overrides import LEGACY_FILES as C3B_FILES
from .steps.c4b_spending import RECOVERY_FILES

LEGACY_DB_NAME = "retirement_system_v10.db"
BEFORE_DEMO = ".before_demo"
PLAN_FILE_NAME = "plan.rpx"
SNAPSHOT_FILE = "client_data.csv"  # the name a snapshot is staged under

# Every legacy file name a step reads, by group.
OVERRIDE_FILES: tuple[str, ...] = tuple(C3B_FILES.values())
DATASET_FILES: dict[str, str] = dict(FLAT_DATASET_FILES)
EXTRA_FILES: tuple[str, ...] = tuple(dict.fromkeys([RECOVERY_SEED_FILE, *RECOVERY_FILES.values()]))
ALL_FILES: tuple[str, ...] = tuple(dict.fromkeys([*PLAN_CSV_FILES, *OVERRIDE_FILES, *DATASET_FILES.values(), *EXTRA_FILES]))


def demo_seed_dir() -> Path:
    return package_root() / "input" / "demo"


def legacy_db_path(workspace: Path) -> Path:
    return Path(workspace) / "local_state" / LEGACY_DB_NAME


# --------------------------------------------------------------------------- reading a db
def _private_copy(db: Path, tmp: Path) -> Path:
    """Copy ``db`` (and its ``-wal``) into ``tmp``; the original is never opened."""
    dest = tmp / (db.name + ".copy")
    shutil.copyfile(db, dest)
    wal = db.with_name(db.name + "-wal")
    if wal.is_file():
        shutil.copyfile(wal, dest.with_name(dest.name + "-wal"))
    return dest


def _tables(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def read_legacy_db(db: Path) -> tuple[dict[str, str], dict[str, Any] | None]:
    """``({file name: text} from client_files, latest sectioned snapshot or None)`` of a legacy
    database. A file that is not a SQLite database, or lacks the tables, reads as empty."""
    files: dict[str, str] = {}
    snapshot: dict[str, Any] | None = None
    if not Path(db).is_file():
        return files, snapshot
    with tempfile.TemporaryDirectory(prefix="legacy_db_") as tmp:
        copy = _private_copy(Path(db), Path(tmp))
        try:
            with closing(sqlite3.connect(copy)) as con:
                tables = _tables(con)
                if "client_files" in tables:
                    for name, content in con.execute("SELECT file_name, content FROM client_files"):
                        if name and content is not None:
                            files[Path(str(name)).name] = str(content)
                if "plan_snapshots" in tables:
                    row = con.execute("SELECT sectioned_json FROM plan_snapshots "
                                      "ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
                    if row and row[0]:
                        data = json.loads(row[0])
                        snapshot = data if isinstance(data, dict) and data else None
        except (sqlite3.DatabaseError, ValueError):
            return {}, None
    return files, snapshot


def read_latest_kpis(db: Path | None) -> dict[str, Any] | None:
    """The newest ``kpi_snapshots`` row of a legacy database (its ``kpi_json``), or None. Read
    from a private copy, like :func:`read_legacy_db`."""
    if db is None or not Path(db).is_file():
        return None
    with tempfile.TemporaryDirectory(prefix="legacy_db_") as tmp:
        copy = _private_copy(Path(db), Path(tmp))
        try:
            with closing(sqlite3.connect(copy)) as con:
                if "kpi_snapshots" not in _tables(con):
                    return None
                row = con.execute("SELECT kpi_json FROM kpi_snapshots "
                                  "ORDER BY created_at DESC, snapshot_id DESC LIMIT 1").fetchone()
        except sqlite3.DatabaseError:
            return None
    try:
        data = json.loads(row[0]) if row and row[0] else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def snapshot_csv_text(sectioned: dict[str, Any]) -> str:
    """A sectioned snapshot (``{section: {subsection: {label: value}}}``) as plan CSV text."""
    rows: list[list[str]] = [["section", "subsection", "label", "value", "units", "notes"]]
    for section, subs in sectioned.items():
        if not isinstance(subs, dict):
            continue
        for subsection, labels in subs.items():
            if not isinstance(labels, dict):
                continue
            for label, value in labels.items():
                rows.append([str(section), str(subsection), str(label), "" if value is None else str(value), "", ""])
    return rows_to_text(rows)


def _norm_text(text: str) -> str:
    return (text or "").lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


# --------------------------------------------------------------------------- the plan
@dataclass
class SourcePlan:
    """Which copy of every legacy file the conversion reads (names and origins only)."""

    workspace: Path
    mode: str = "normal"  # normal | mid_demo
    plan_seed: Path | None = None  # plan file the target starts from (mid-demo, WP4.5+)
    legacy_db: Path | None = None
    # file name -> (origin, path or None, text or None); path for files, text for db/snapshot
    chosen: dict[str, tuple[str, Path | None, str | None]] = field(default_factory=dict)
    # Every ``client_files`` text of the legacy database read (also the ones a higher layer
    # won), for the source-agreement check (WP10.3).
    db_texts: dict[str, str] = field(default_factory=dict)

    def disagreeing_files(self) -> list[str]:
        """Names taken from ``input/`` whose legacy-database copy holds other text (line endings
        and a BOM ignored). The old app read the database copy of a flat dataset first, so such
        a file may differ from what the old app showed."""
        out = []
        for name, (origin, path, _text) in sorted(self.chosen.items()):
            if origin != "input" or path is None or name not in self.db_texts:
                continue
            if _norm_text(path.read_bytes().decode("utf-8-sig", errors="replace")) != _norm_text(self.db_texts[name]):
                out.append(name)
        return out

    @property
    def has_plan_csv(self) -> bool:
        return any(n in self.chosen for n in PLAN_CSV_FILES)

    @property
    def has_any(self) -> bool:
        return bool(self.chosen) or self.plan_seed is not None

    def origins(self) -> dict[str, str]:
        return {name: origin for name, (origin, _, _) in sorted(self.chosen.items())}


def mid_demo_backups(workspace: Path) -> dict[str, Path]:
    """The old demo's backups that exist (``plan``: ``plan.rpx.before_demo``, ``legacy_db``:
    the legacy database's, ``texts``: the ``local_state`` folder holding text backups)."""
    ws = Path(workspace)
    out: dict[str, Path] = {}
    plan = ws / (PLAN_FILE_NAME + BEFORE_DEMO)
    if plan.is_file():
        out["plan"] = plan
    db = legacy_db_path(ws)
    db_backup = db.with_name(db.name + BEFORE_DEMO)
    if db_backup.is_file():
        out["legacy_db"] = db_backup
    if any((db.parent / (n + BEFORE_DEMO)).is_file() for n in ALL_FILES):
        out["texts"] = db.parent
    return out


def discover(workspace: str | Path, extra: dict[str, Any] | None = None) -> SourcePlan:
    """Pick the source of every legacy file (reads database copies, never writes)."""
    ws = Path(workspace)
    extra = extra or {}
    backups = mid_demo_backups(ws)
    plan = SourcePlan(ws, mode="mid_demo" if backups else "normal", plan_seed=backups.get("plan"))
    input_dir = ws / "input"

    def take(name: str, origin: str, path: Path | None = None, text: str | None = None) -> None:
        if name not in plan.chosen:
            plan.chosen[name] = (origin, path, text)

    if plan.mode == "mid_demo":
        if "texts" in backups:
            for name in ALL_FILES:
                p = backups["texts"] / (name + BEFORE_DEMO)
                if p.is_file():
                    take(name, "demo_text_backup", path=p)
        db = Path(extra["legacy_db"]) if extra.get("legacy_db") else backups.get("legacy_db")
        files, snapshot = read_legacy_db(db) if db else ({}, None)
        plan.legacy_db = db if (files or snapshot) else None
        for name in ALL_FILES:
            if name in files:
                take(name, "client_files_before_demo", text=files[name])
        if snapshot and not plan.has_plan_csv and plan.plan_seed is None:
            take(SNAPSHOT_FILE, "plan_snapshot", text=snapshot_csv_text(snapshot))
        seed_names = {p.name for p in demo_seed_dir().glob("*")} if demo_seed_dir().is_dir() else set()
        for name in ALL_FILES:
            if name not in seed_names and (input_dir / name).is_file():
                take(name, "input", path=input_dir / name)
        return plan

    for name in ALL_FILES:
        if (input_dir / name).is_file():
            take(name, "input", path=input_dir / name)
    db = Path(extra["legacy_db"]) if extra.get("legacy_db") else legacy_db_path(ws)
    files, snapshot = read_legacy_db(db)
    plan.legacy_db = db if (files or snapshot) else None
    plan.db_texts = {name: files[name] for name in ALL_FILES if name in files}
    for name in ALL_FILES:
        if name in files:
            take(name, "client_files", text=files[name])
    if snapshot and not plan.has_plan_csv:
        take(SNAPSHOT_FILE, "plan_snapshot", text=snapshot_csv_text(snapshot))
    return plan


def stage(plan: SourcePlan, dest: str | Path, names: Iterable[str]) -> list[str]:
    """Write the chosen copy of each of ``names`` into ``dest``; returns the names staged."""
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    staged: list[str] = []
    for name in names:
        if name not in plan.chosen:
            continue
        _, path, text = plan.chosen[name]
        if path is not None:
            shutil.copyfile(path, out / name)
        else:
            with open(out / name, "w", encoding="utf-8", newline="") as fh:
                fh.write(text or "")
        staged.append(name)
    return staged


def source_paths(workspace: str | Path, extra: dict[str, Any] | None = None) -> list[Path]:
    """Every original a conversion may read (the runner's "never modified" guard set)."""
    ws = Path(workspace)
    extra = extra or {}
    db = legacy_db_path(ws)
    paths = [ws / "input", ws / "client_files", ws / "plan_snapshots", ws / "saved_plans", ws / "data",
             ws / "system_config.csv", ws / (PLAN_FILE_NAME + BEFORE_DEMO),
             ws / (PLAN_FILE_NAME + BEFORE_DEMO + "-wal")]
    for p in (db, db.with_name(db.name + BEFORE_DEMO)):
        paths += [p, p.with_name(p.name + "-wal")]
    paths += [db.parent / (n + BEFORE_DEMO) for n in ALL_FILES]
    if extra.get("legacy_db"):
        p = Path(extra["legacy_db"])
        paths += [p, p.with_name(p.name + "-wal")]
    if not extra.get("delete_legacy_secrets"):
        paths.append(ws / "local_state" / "secrets.local.json")
    return paths
