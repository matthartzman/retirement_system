from __future__ import annotations

"""Append-only JSON Lines trend log (ticket 306).

One JSON object per weekday-5pm run, keyed by ``as_of_date``. A JSON category
breakdown is used (not CSV) because the category key set changes as
categories are added/renamed -- CSV would need a header rewrite every time
that happens; JSONL just appends. Re-running on the same ``as_of_date``
overwrites that date's line rather than duplicating it, so a manual re-run
or a retried scheduled fire is safe.
"""

import json
from pathlib import Path
from typing import Any

LOG_FILENAME = "financial_trends_log.jsonl"


def default_log_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "data" / LOG_FILENAME


def read_history(log_path: str | Path) -> list[dict[str, Any]]:
    path = Path(log_path)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a corrupted/partial line must not take down the whole log
    return entries


def append_or_replace_entry(log_path: str | Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Add ``entry`` to the log, replacing any existing line with the same
    ``as_of_date``. Returns the full history after the write."""
    as_of = entry.get("as_of_date")
    if not as_of:
        raise ValueError("entry must have an as_of_date")
    history = [e for e in read_history(log_path) if e.get("as_of_date") != as_of]
    history.append(entry)
    history.sort(key=lambda e: str(e.get("as_of_date") or ""))

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in history) + "\n", encoding="utf-8")
    return history
