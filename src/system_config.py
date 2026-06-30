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
