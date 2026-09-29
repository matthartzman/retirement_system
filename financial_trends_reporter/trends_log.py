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

from src.plan_file_io import write_text_atomic

LOG_FILENAME = "financial_trends_log.jsonl"


def default_log_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "data" / LOG_FILENAME


def rejected_path(log_path: str | Path) -> Path:
    """Sidecar that holds lines quarantined from the log (WI-203)."""
    path = Path(log_path)
    return path.with_name(path.name + ".rejected")


def _parse_lines(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (parsed entries, raw unparseable lines)."""
    entries: list[dict[str, Any]] = []
    bad: list[str] = []
    if not path.exists():
        return entries, bad
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad.append(line)
            continue
        if isinstance(obj, dict):
            entries.append(obj)
        else:
            bad.append(line)
    return entries, bad


def read_history(log_path: str | Path) -> list[dict[str, Any]]:
    # a corrupted/partial line must not take down the whole log
    return _parse_lines(Path(log_path))[0]


def append_or_replace_entry(log_path: str | Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Add ``entry`` to the log, replacing any existing line with the same
    ``as_of_date`` (the run day). Unparseable lines are moved to a
    ``.rejected`` sidecar rather than dropped, and the rewrite is atomic.
    Returns the full history after the write."""
    as_of = entry.get("as_of_date")
    if not as_of:
        raise ValueError("entry must have an as_of_date")
    path = Path(log_path)
    existing, bad = _parse_lines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if bad:
        # Quarantine first: if the main rewrite then fails, nothing is lost.
        with rejected_path(path).open("a", encoding="utf-8") as fh:
            fh.write("\n".join(bad) + "\n")
    history = [e for e in existing if e.get("as_of_date") != as_of]
    history.append(entry)
    history.sort(key=lambda e: str(e.get("as_of_date") or ""))
    write_text_atomic(path, "\n".join(json.dumps(e, sort_keys=True) for e in history) + "\n")
    return history
