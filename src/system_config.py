from __future__ import annotations
"""Local runtime configuration loaded from system_config.csv."""

import csv
import os
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SYSTEM_CONFIG_CSV = PROJECT_ROOT / "system_config.csv"
SettingMap = Dict[str, Dict[str, Dict[str, str]]]


def _clean_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _add(result: SettingMap, section: object, subsection: object, label: object, value: object) -> None:
    sec = _clean_text(section)
    sub = _clean_text(subsection)
    lbl = _clean_text(label)
    if not sec or sec.startswith("#") or not lbl or lbl.lower() == "label":
        return
    result.setdefault(sec, {}).setdefault(sub, {})[lbl] = _clean_text(value)


def _load_csv(path: str | Path) -> SettingMap:
    result: SettingMap = {}
    p = Path(path)
    if not p.exists():
        return result
    with p.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            _add(result, row.get("section"), row.get("subsection"), row.get("label"), row.get("value"))
    return result


def discover_system_config_csv() -> Path:
    override = os.getenv("RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV")
    if override:
        p = Path(override)
        return p if p.is_absolute() else PROJECT_ROOT / p
    return DEFAULT_SYSTEM_CONFIG_CSV


def load_system_config(path: str | Path | None = None) -> SettingMap:
    p = Path(path) if path is not None else discover_system_config_csv()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return _load_csv(p)


def system_setting(data: SettingMap, subsection: str, label: str, default: str = "") -> str:
    return data.get("System Configuration", {}).get(subsection, {}).get(label, default)


def setting(data: SettingMap, section: str, subsection: str, label: str, default: str = "") -> str:
    return data.get(section, {}).get(subsection, {}).get(label, default)


WORKBOOK_DOWNLOAD_SUBSECTION = "Downloads"
DEFAULT_WORKBOOK_FILENAME_ROOT = "Retirement Workbook"


def workbook_filename_root(data: SettingMap) -> str:
    root = system_setting(data, WORKBOOK_DOWNLOAD_SUBSECTION, "filename_root", DEFAULT_WORKBOOK_FILENAME_ROOT).strip()
    return root or DEFAULT_WORKBOOK_FILENAME_ROOT


def workbook_desktop_download_folder(data: SettingMap) -> str:
    return system_setting(data, WORKBOOK_DOWNLOAD_SUBSECTION, "desktop_download_folder", "").strip()


def upsert_system_setting(
    path: str | Path,
    subsection: str,
    label: str,
    value: object,
    units: str = "",
    notes: str = "",
) -> None:
    """Update one "System Configuration" row in system_config.csv in place,
    preserving every other row, or append it if not already present.

    A full read-modify-write of the small CSV rather than a targeted line
    edit, matching admin_service.save_system_config()'s own whole-file
    round-trip -- this file is small (system settings, not plan data) and
    every other writer already treats it as small enough to rewrite wholesale.
    """
    from .plan_file_io import atomic_write, plan_file_lock  # noqa: PLC0415

    p = Path(path)
    with plan_file_lock(p):
        rows: list[list[str]] = []
        if p.exists():
            with p.open(newline="", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        if not rows:
            rows = [["section", "subsection", "label", "value", "units", "notes"]]
        updated = False
        for row in rows[1:]:
            if len(row) >= 3 and row[0] == "System Configuration" and row[1] == subsection and row[2] == label:
                while len(row) < 6:
                    row.append("")
                row[3] = str(value)
                if units:
                    row[4] = units
                if notes:
                    row[5] = notes
                updated = True
                break
        if not updated:
            rows.append(["System Configuration", subsection, label, str(value), units, notes])
        with atomic_write(p) as f:
            csv.writer(f, lineterminator="\n").writerows(rows)
