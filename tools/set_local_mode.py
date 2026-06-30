#!/usr/bin/env python3
"""Reset the v10 local desktop/development runtime settings.

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
    ("System Configuration", "Runtime", "config_file"): "input/client_data.csv",
    ("System Configuration", "Runtime", "json_config_file"): "input/client_data.json",
    ("System Configuration", "Runtime", "yaml_config_file"): "input/client_data.yaml",
    ("System Configuration", "Runtime", "output_dir"): "output",
    ("System Configuration", "Runtime", "local_plan_data_dir"): "",
    ("System Configuration", "Dashboard", "host"): "127.0.0.1",
    ("System Configuration", "Dashboard", "port"): "5050",
    ("System Configuration", "Security", "session_cookie_secure"): "NO",
}

def main() -> int:
    if not CONFIG.exists():
        raise SystemExit(f"Missing {CONFIG}")
    with CONFIG.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or ["section", "subsection", "label", "value", "units", "notes"]
        rows = list(reader)
    seen = set()
    for row in rows:
        key = (row.get("section", ""), row.get("subsection", ""), row.get("label", ""))
        if key in UPDATES:
            row["value"] = UPDATES[key]
            seen.add(key)
    for key, value in UPDATES.items():
        if key not in seen:
            rows.append({"section": key[0], "subsection": key[1], "label": key[2], "value": value, "units": "", "notes": "Set by local-mode reset."})
    with CONFIG.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print("Local development mode restored.")
    print("Open UI: http://127.0.0.1:5050")
    print("Admin UI: http://127.0.0.1:5050/admin")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
