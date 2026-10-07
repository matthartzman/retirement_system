#!/usr/bin/env python3
"""Reset the v11 local desktop/development runtime settings.

The packaged app is local-only. This helper restores the root system_config.csv
values used by desktop and browser/server launchers.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "system_config.csv"
UPDATES = {
    ("System Configuration", "Runtime", "app_mode"): "LOCAL",
    ("System Configuration", "Runtime", "output_dir"): "output",
    ("System Configuration", "Dashboard", "host"): "127.0.0.1",
    ("System Configuration", "Dashboard", "port"): "5050",
    ("System Configuration", "Security", "session_cookie_secure"): "NO",
}

def main(config: Path = CONFIG) -> int:
    if not config.exists():
        raise SystemExit(f"Missing {config}")
    # Plain csv.reader keeps rows with extra/unquoted fields intact (DictReader
    # files them under a None key, which DictWriter then rejects).
    with config.open(newline="", encoding="utf-8-sig") as f:
        rows = [list(r) for r in csv.reader(f)]
    seen = set()
    for row in rows:
        key = tuple(c.strip() for c in row[:3])
        if len(key) == 3 and key in UPDATES and len(row) > 3:
            row[3] = UPDATES[key]
            seen.add(key)
    for key, value in UPDATES.items():
        if key not in seen:
            rows.append([key[0], key[1], key[2], value, "", "Set by local-mode reset."])
    # Write to a temp file and rename so a failure can never truncate the config.
    tmp = config.with_name(config.name + ".tmp")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerows(rows)
        tmp.replace(config)
    finally:
        tmp.unlink(missing_ok=True)
    print("Local development mode restored.")
    print("Open UI: http://127.0.0.1:5050")
    print("Admin UI: http://127.0.0.1:5050/admin")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
