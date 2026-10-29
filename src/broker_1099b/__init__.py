"""Broker 1099-B parsers with one shared normalized output (realized-sales ledger plan, step 5.1).

Pure: parses text (or PDF bytes) and returns an ``import_preview_v1``-style preview. It never touches the database and
does not match to ledger rows or apply official numbers (that is step 5.2). Add a broker by writing
``parse(text, *, known_symbols=None, account=None) -> ParsedStatement`` and calling ``register``.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from . import etrade, pdf_text
from .normalized import ParsedStatement

Parser = Callable[..., ParsedStatement]
REGISTRY: dict[str, Parser] = {}


def register(name: str, parser: Parser) -> None:
    REGISTRY[name] = parser


def available_brokers() -> list[str]:
    return sorted(REGISTRY)


register(etrade.BROKER, etrade.parse)


def _master_symbols() -> set[str]:
    from ..tlh import load_security_master
    return set(load_security_master())


def _refused(broker: str, source_format: str, errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "import_preview_v1", "kind": "broker_1099b", "broker": broker, "source_format": source_format,
            "received": 0, "will_write": [], "parsed": [], "can_apply": False, "warnings": [], "errors": errors,
            "control_totals": {"status": "missing", "buckets": [], "gaps": []}}


def preview_statement(broker: str, *, text: str | None = None, pdf_bytes: bytes | None = None,
                      known_symbols: Iterable[str] | None = None, account: str | None = None) -> dict[str, Any]:
    """Side-effect-free preview. ``parsed`` always lists every line read, so it can be checked; ``will_write`` holds
    them only when ``can_apply`` (no errors and the lines reproduce the statement's 1099-B summary totals)."""
    fmt = "pdf" if pdf_bytes is not None and text is None else "text"
    parser = REGISTRY.get(broker)
    if parser is None:
        return _refused(broker, fmt, [{"line": 0, "error": f"Unknown broker {broker!r}; available: {', '.join(available_brokers())}."}])
    if fmt == "pdf":
        try:
            text = pdf_text.extract_text(pdf_bytes)
        except (pdf_text.PdfUnavailable, pdf_text.PdfUnreadable) as exc:
            return _refused(broker, fmt, [{"line": 0, "error": str(exc)}])
    if known_symbols is None:
        known_symbols = _master_symbols()
    st = parser(text or "", known_symbols=known_symbols, account=account)
    errors = list(st.errors)
    status = st.control["status"]
    if status == "mismatch":
        errors.append({"line": 0, "error": "Control totals do not match the statement's 1099-B summary; "
                       "refusing to apply. See control_totals.gaps."})
    elif status == "missing" and st.rows:
        errors.append({"line": 0, "error": "No 1099-B summary totals were found, so the lines cannot be verified; "
                       "refusing to apply."})
    can_apply = not errors and bool(st.rows)
    return {"schema": "import_preview_v1", "kind": "broker_1099b", "broker": broker, "source_format": fmt,
            "received": len(st.rows), "will_write": list(st.rows) if can_apply else [], "parsed": list(st.rows),
            "can_apply": can_apply, "warnings": list(st.warnings), "errors": errors,
            "control_totals": st.control, "meta": st.meta}
