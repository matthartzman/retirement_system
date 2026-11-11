"""Single source for Plan Data field defaults: the schema's ``default`` column.

System review 2026-11-10, W1-04 / QA-001. A blank or missing Plan Data value means
the schema default, or zero / none when the schema default is blank. The parsers
used to carry their own literal defaults, and some were one household's figures
(a $293,284 mortgage, a $1,313,000 home), so a plan with blank rows projected
numbers nobody entered.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _schema_defaults() -> dict[tuple[str, str, str], str]:
    from .schema_registry import load_schema  # noqa: PLC0415 (schema_registry imports heavy registries)

    return {key: str((spec or {}).get("default") or "").strip() for key, spec in load_schema().items()}


def schema_default_text(section: str, subsection: str, label: str) -> str:
    """The schema default as text; '' when the row has no default or is not in the schema."""
    return _schema_defaults().get((section, subsection, label), "")


def has_schema_row(section: str, subsection: str, label: str) -> bool:
    return (section, subsection, label) in _schema_defaults()
