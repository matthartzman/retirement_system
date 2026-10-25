"""Stores that test helpers hand back open; ``conftest`` closes them after each test.

A helper that returns a ``PlanStore`` (so the test can use it) cannot close it itself.
``track`` records it and the autouse fixture in ``conftest.py`` calls ``close_all``, so the
handle never reaches garbage collection open (``ResourceWarning: unclosed database``).
"""
from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")
_OPEN: list[Any] = []


def track(store: T) -> T:
    _OPEN.append(store)
    return store


def close_all() -> None:
    while _OPEN:
        _OPEN.pop().close()
