"""Broker activity (all-transactions history) parsers with one normalized output.

Pure: parses a downloaded history file and never touches the database. ``src/broker_import.py`` turns the rows into
lots, sale orders and income rows. Add a broker by writing ``parse(text, *, file_name=None) -> ParsedActivity``,
``account_hint(file_name)`` and ``detect(text, file_name)`` and calling ``register``. A parser reports its account in
``meta["account_hint"]`` (one account per file) or in each row's ``account_hint`` (several accounts in one file).
"""
from __future__ import annotations

from typing import Any

from . import etrade, fidelity, vanguard
from .normalized import ParsedActivity, assign_row_keys, date_range, group_orders, row_hints  # noqa: F401

REGISTRY: dict[str, Any] = {}
BROKER_LABELS = {"fidelity": "Fidelity", "etrade": "E*Trade", "vanguard": "Vanguard"}


def register(name: str, module: Any) -> None:
    REGISTRY[name] = module


def available_brokers() -> list[str]:
    return sorted(REGISTRY)


register(fidelity.BROKER, fidelity)
register(etrade.BROKER, etrade)
register(vanguard.BROKER, vanguard)


def detect_broker(text: str, file_name: str | None = None) -> str | None:
    """The one broker whose parser recognizes the file's header, else ``None`` (none, or more than one)."""
    hits = [name for name, mod in sorted(REGISTRY.items()) if mod.detect(text, file_name)]
    return hits[0] if len(hits) == 1 else None


def parse_raw(broker: str, text: str, *, file_name: str | None = None) -> ParsedActivity:
    """Parse ``text`` without row keys (the account of each row is not chosen yet)."""
    mod = REGISTRY.get(broker)
    if mod is None:
        return ParsedActivity(broker=broker, errors=[{"line": 0, "error": f"Unknown broker {broker!r}; available: "
                                                                          f"{', '.join(available_brokers())}."}])
    return mod.parse(text, file_name=file_name)


def parse_file(broker: str, text: str, *, account: str, file_name: str | None = None) -> ParsedActivity:
    """Parse ``text`` and key every row for ``account`` (the plan account the user chose)."""
    parsed = parse_raw(broker, text, file_name=file_name)
    assign_row_keys(parsed.rows, broker=broker, account=account)
    return parsed


def account_hint(broker: str, file_name: str | None) -> str | None:
    mod = REGISTRY.get(broker)
    return mod.account_hint(file_name) if mod is not None else None
