"""Roth UI/build handoff guards for Retirement System v10.

These helpers keep user-selected Roth conversion settings canonical as they move
from the browser UI to Plan Data CSVs, JSON/YAML mirrors, and the projection
engine. The core safety rule is that an explicit user-selected Roth policy
(fill_to_bracket, fill_to_irmaa, fixed_dollar, or none) must not be treated as
OPTIMIZER_CHOOSES during workbook build.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

EXPLICIT_ROTH_POLICIES = {"fill_to_bracket", "fill_to_irmaa", "fixed_dollar", "none"}
OPTIMIZER_ROTH_POLICIES = {"", "optimize", "optimizer_chooses", "optimize_terminal_tax", "terminal_tax_optimize", "balanced_optimize"}

POLICY_ALIASES = {
    "": "optimize_terminal_tax",
    "optimizer chooses": "optimize_terminal_tax",
    "optimizer_chooses": "optimize_terminal_tax",
    "optimize": "optimize_terminal_tax",
    "optimize_terminal_tax": "optimize_terminal_tax",
    "terminal_tax_optimize": "optimize_terminal_tax",
    "balanced_optimize": "optimize_terminal_tax",
    "balanced retirement optimizer": "optimize_terminal_tax",
    "none": "none",
    "no voluntary conversions": "none",
    "no_voluntary_conversions": "none",
    "fill to bracket": "fill_to_bracket",
    "fill_to_bracket": "fill_to_bracket",
    "fill target bracket": "fill_to_bracket",
    "fill_target_bracket": "fill_to_bracket",
    "fill to irmaa": "fill_to_irmaa",
    "fill_to_irmaa": "fill_to_irmaa",
    "irmaa guarded": "fill_to_irmaa",
    "irmaa_guarded": "fill_to_irmaa",
    "fixed dollar": "fixed_dollar",
    "fixed_dollar": "fixed_dollar",
}

IRMAA_MODE_ALIASES = {
    "ignore": "IGNORE",
    "warn": "WARN_ONLY",
    "warn only": "WARN_ONLY",
    "warn_only": "WARN_ONLY",
    "avoid next tier": "AVOID_NEXT_TIER",
    "avoid_next_tier": "AVOID_NEXT_TIER",
    "avoid tier 2 or above": "AVOID_TIER_2_OR_ABOVE",
    "avoid_tier_2_or_above": "AVOID_TIER_2_OR_ABOVE",
    "custom magi cap": "CUSTOM_MAGI_CAP",
    "custom_magi_cap": "CUSTOM_MAGI_CAP",
}

POLICY_TO_BRACKET_STRATEGY = {
    "fill_to_bracket": "FILL_TARGET_BRACKET",
    "fill_to_irmaa": "IRMAA_GUARDED",
    "fixed_dollar": "FIXED_DOLLAR",
    "none": "NONE",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value).lower().replace("-", "_").replace("_", " ")).strip()


def normalize_roth_policy(value: Any, default: str = "optimize_terminal_tax") -> str:
    """Return an engine-valid Roth policy from UI values or display labels."""
    text = _clean(value)
    if not text:
        return default
    key = _key(text)
    if "fill" in key and "bracket" in key:
        return "fill_to_bracket"
    if "irmaa" in key and ("fill" in key or "guard" in key):
        return "fill_to_irmaa"
    return POLICY_ALIASES.get(key, text)


def normalize_irmaa_guardrail_mode(value: Any, default: str = "AVOID_NEXT_TIER") -> str:
    """Return an engine-valid IRMAA guardrail mode from UI values/display labels."""
    text = _clean(value)
    if not text:
        return default
    return IRMAA_MODE_ALIASES.get(_key(text), text.upper())


def normalize_percent_display(value: Any, default: str = "") -> str:
    """Normalize values like `0.22`, `22% bracket`, or long labels to `22.00%`."""
    text = _clean(value)
    if not text:
        return default
    pct = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text.replace(",", ""))
    m = pct or re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not m:
        return text
    num = float(m.group(1) if pct else m.group(0))
    if abs(num) <= 1.0 and not pct:
        num *= 100.0
    return f"{num:.2f}%"


def percent_to_float(value: Any, default: float = 0.0) -> float:
    """Parse a UI percent value or label into decimal form, e.g. 22% -> 0.22."""
    norm = normalize_percent_display(value)
    if not norm:
        return default
    try:
        return float(norm.replace("%", "").strip()) / 100.0
    except Exception:
        return default


def is_explicit_user_roth_policy(value: Any) -> bool:
    return normalize_roth_policy(value) in EXPLICIT_ROTH_POLICIES


def strategy_for_roth_policy(value: Any, default: str = "OPTIMIZER_CHOOSES") -> str:
    return POLICY_TO_BRACKET_STRATEGY.get(normalize_roth_policy(value), default)


def normalize_roth_csv_value(section: Any, subsection: Any, label: Any, value: Any) -> str:
    """Canonicalize Roth/IRMAA values before storing them in Plan Data CSVs."""
    lbl = _clean(label)
    val = _clean(value)
    if lbl == "roth_conversion_policy":
        return normalize_roth_policy(val)
    if lbl == "roth_target_bracket_rate":
        return normalize_percent_display(val, val)
    if lbl == "irmaa_guardrail_mode":
        return normalize_irmaa_guardrail_mode(val)
    if lbl in {"roth_headroom_usage_pct", "roth_irmaa_headroom_usage_pct"}:
        return normalize_percent_display(val, val)
    return val


def canonicalize_roth_csv_content(content: str) -> str:
    """Canonicalize Roth controls in a CSV string without changing other rows."""
    rows = list(csv.reader(io.StringIO(content or "")))
    changed = False
    for row in rows:
        if len(row) < 4:
            continue
        while len(row) < 6:
            row.append("")
        new_value = normalize_roth_csv_value(row[0], row[1], row[2], row[3])
        if new_value != row[3]:
            row[3] = new_value
            changed = True
    if not changed:
        return content
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue()
