"""User approve/deny decisions for near-match investment pass-through transfers.

A withdrawal from one investment account and a deposit into another whose
amounts differ by up to $100 might be one investment-to-investment move routed
through checking. The trends snapshot lists such pairs (``passthrough_review``);
the user approves (exclude from withdrawals/contributions) or denies (count
normally) each, and the answer is stored here keyed by the pair's stable key so
it is never asked twice.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.plan_file_io import write_text_atomic

DECISIONS_FILENAME = "passthrough_decisions.json"
VALID_DECISIONS = ("approve", "deny")


def decisions_path_for_log(log_path: str | Path) -> Path:
    """The decisions file lives beside the trend log it belongs to."""
    return Path(log_path).with_name(DECISIONS_FILENAME)


def load_decisions(path: str | Path) -> dict[str, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if v in VALID_DECISIONS}


def save_decision(path: str | Path, key: str, decision: str) -> dict[str, str]:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}")
    if not key or not isinstance(key, str):
        raise ValueError("key is required")
    decisions = load_decisions(path)
    decisions[key] = decision
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(Path(path), json.dumps(decisions, indent=2, sort_keys=True))
    return decisions
